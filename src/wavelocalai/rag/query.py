"""Service de question aux documents : une question, ses sources, puis la réponse (AD-5, AD-9, AD-14).

Un run `rag` est composite (AD-5) : la racine publie seule le flux, et porte des feuilles : un
`embedding` par recherche (la question, ou la réponse hypothétique de HyDE, mesuré comme un lot
d'ingestion), une `generation` par appel de modèle de la stratégie (réponse hypothétique, notation,
reformulation : appels silencieux, `co2` cloud estimé par ecologits) et la `generation` de la
réponse, comme le chat. Seuls les documents `ready` sont interrogés (AD-16).

Ordre des événements : des `retrieval_step {strategy, step, duration_s}` (champs additifs `round`,
`fallback` et, pour `grade`, `checked` et `relevant`), puis `sources`, puis les `token` de la réponse,
`metrics` (débit D3, `retrieval_s` à part, `co2` de la génération) et, si la réponse cite des
sources, `citations`. Chaque étape est publiée à sa **fin**, quand sa durée est connue ; les sources
partent donc avant le premier `token`. Étapes : `naive` = `embedding`, `search` ; `hyde` =
`hypothesis`, `embedding`, `search` ; `self_rag` = par tour `embedding`, `search`, `grade`, puis
`rewrite` si aucun extrait n'est pertinent et que la borne n'est pas atteinte (`rag/strategies.py`).

`sources` est persisté sans `text` ; le hub le réhydrate depuis `chunks` au rejeu (AD-7).
`runs.params` ne reçoit ni la question ni les extraits (AD-7) : la question vit dans `messages`.

Une question est indépendante : le prompt ne reprend pas l'historique de la conversation.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from wavelocalai.config import Settings
from wavelocalai.errors import AppError, build_envelope
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.chat import cloud_estimator
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import CANCELLED_CO2, stream_into_run
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import ChatMessage, ChatModel, ChatRequest, ChatResult, Embedder
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.rag import repo
from wavelocalai.rag.embedding_leaf import embed_into_leaf, leaf_error
from wavelocalai.rag.index import VectorIndex
from wavelocalai.rag.passage import pick_passage, relevance_label, similarity
from wavelocalai.rag.settings import effective
from wavelocalai.rag.strategies import (
    MAX_TOP_K,
    STRATEGIES,
    clean_query,
    grade_request,
    hyde_request,
    merge_best,
    parse_grade,
    rewrite_request,
    verify_citations,
)
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import Co2, RunHandle
from wavelocalai.runs.system_bus import SystemBus
from wavelocalai.store.db import Store
from wavelocalai.store.preferences import PreferenceStore

logger = logging.getLogger("wavelocalai.rag")

TEMPERATURE = 0.1  # une réponse qui s'appuie sur des extraits : peu de créativité
NOT_STARTED_CO2 = Co2(
    mg=None, method="unmeasurable", reason="réponse non lancée : la recherche a échoué"
)

SYSTEM_PROMPT = (
    "Tu réponds en français à la question de l'utilisateur à partir des extraits de documents "
    "fournis, et d'eux seuls. Cite les extraits utilisés par leur numéro entre crochets, par "
    "exemple [1], sans jamais citer un numéro qui n'est pas dans la liste. Si les extraits ne "
    "permettent pas de répondre, dis-le franchement au lieu d'inventer une réponse."
)


@dataclass(frozen=True)
class RagCommand:
    question: str
    model: str
    strategy: str = "naive"
    allow_cloud: bool = False
    conversation_id: str | None = None
    top_k: int | None = None  # nombre d'extraits de cette question ; sinon `rag.top_k`


@dataclass
class _Rag:
    handle: RunHandle
    model: ChatModel
    embedder: Embedder
    embedding_leaf_id: str
    generation_leaf_id: str
    question: str
    strategy: str
    top_k: int
    embedding_used: bool = False  # la feuille créée au départ sert à la première recherche


def build_sources(
    found: list[dict[str, Any]], question: str, very_close: float, close: float
) -> list[dict[str, Any]]:
    """Les sources de l'événement `sources` : numéro et rang (1 pour le plus proche), libellé de
    pertinence, score brut (similarité cosinus, 4 décimales) et passage à surligner (D-21)."""
    return [
        {
            "n": rank,
            "doc_id": item["doc_id"],
            "document": item["document"],
            "page": item["page"],
            "chunk_id": item["chunk_id"],
            "text": item["text"],
            "rank": rank,
            "relevance_label": relevance_label(item["distance"], very_close, close),
            "raw_score": round(similarity(item["distance"]), 4),
            "passage": pick_passage(question, item["text"]),
        }
        for rank, item in enumerate(found, 1)
    ]


def build_request(question: str, sources: list[dict[str, Any]]) -> ChatRequest:
    """Prompt de la stratégie `naive` : consigne, extraits numérotés, puis la question."""
    blocks = []
    for source in sources:
        where = source["document"] + (f", page {source['page']}" if source["page"] else "")
        blocks.append(f"[{source['n']}] ({where})\n{source['text']}")
    user = "Extraits :\n\n" + "\n\n".join(blocks) + f"\n\nQuestion : {question}"
    return ChatRequest(
        messages=[ChatMessage("system", SYSTEM_PROMPT), ChatMessage("user", user)],
        temperature=TEMPERATURE,
    )


class RagService:
    def __init__(
        self,
        hub: RunHub,
        registry: ModelRegistry,
        factory: ModelFactory,
        slot: LocalSlot,
        settings: Settings,
        index: VectorIndex,
        *,
        meter: LocalMeter | None = None,
        bus: SystemBus | None = None,
        preferences: PreferenceStore | None = None,
    ) -> None:
        self._hub = hub
        self._store: Store = hub.store
        self._registry = registry
        self._factory = factory
        self._slot = slot
        self._settings = settings
        self._index = index
        self._preferences = preferences  # `top_k` choisi à l'écran (AD-15), prime sur le .toml
        self._meter = meter  # sans compteur, le CO2 d'une feuille locale n'est pas mesuré
        self._bus = bus  # sans bus, `carbon_updated` n'est pas publié
        self._tasks: set[asyncio.Task[None]] = set()  # références fortes jusqu'à la fin

    async def start(self, command: RagCommand) -> RunHandle:
        """Crée le run et rend `{run_id, conversation_id}` aussitôt ; la suite se fait en tâche.

        Lève `model_not_found`, `cloud_not_allowed` ou `model_not_chat` (registre, AD-9),
        `invalid_request` (stratégie inconnue), `rag_base_empty` (aucun document `ready`),
        `model_not_found` / `model_not_embedding` pour le modèle d'embedding de la base, `run_busy`
        (un run `rag` est déjà actif, AD-14) ou `not_found` (conversation inconnue)."""
        if command.strategy not in STRATEGIES:
            raise AppError(
                "invalid_request", f"strategy : {command.strategy!r} n'est pas prise en charge."
            )
        rag = self._settings.rag
        # `top_k` de la question s'il est envoyé, sinon le réglage de l'écran Base (AD-15), sinon .toml.
        top_k = effective(rag, self._preferences).top_k if command.top_k is None else command.top_k
        if not 1 <= top_k <= MAX_TOP_K:
            raise AppError("invalid_request", f"top_k : de 1 à {MAX_TOP_K} extraits.")
        ref = self._registry.resolve(command.model, command.allow_cloud)
        model = self._factory.chat_model(ref)
        base = await self._store.aread(repo.READY_BASE_SQL)
        if not base:
            raise AppError("rag_base_empty", "Aucun document `ready` dans la base.")
        embedder = self._factory.embedder(
            self._registry.resolve_embedder(base[0]["embedding_model"])
        )
        await self._check_vectors(base[0]["chunks"])
        params: dict[str, Any] = {
            "strategy": command.strategy,
            "allow_cloud": command.allow_cloud,
            "embedding_model": embedder.ref.tag,
            "top_k": top_k,
            "temperature": TEMPERATURE,
        }
        if command.strategy == "self_rag":
            params["self_rag_max_iterations"] = rag.self_rag_max_iterations
        handle = await self._hub.create_run(
            "rag",
            models=[ref.tag],
            params=params,
            user_message=command.question,
            conversation_id=command.conversation_id,
        )
        try:
            embedding = await self._hub.create_run(
                "embedding", models=[embedder.ref.tag], parent_run_id=handle.run_id
            )
            generation = await self._hub.create_run(
                "generation", models=[ref.tag], parent_run_id=handle.run_id
            )
        except BaseException:
            error = build_envelope("internal", "Création des feuilles du run rag impossible.")
            with contextlib.suppress(Exception):
                await self._hub.finish_run(handle.run_id, "error", error=error)
            raise
        # Annulées avant leur première tentative, les feuilles gardent un `co2` (AD-10).
        self._hub.declare_leaf(embedding.run_id, CANCELLED_CO2)
        self._hub.declare_leaf(generation.run_id, CANCELLED_CO2)
        rag_run = _Rag(
            handle,
            model,
            embedder,
            embedding.run_id,
            generation.run_id,
            command.question,
            command.strategy,
            top_k,
        )
        task = asyncio.create_task(self._run(rag_run), name=f"wavelocalai-rag-{handle.run_id}")
        self._hub.attach_task(handle.run_id, task)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return handle

    async def _check_vectors(self, chunks: int) -> None:
        """Refus explicite d'une base dont les vecteurs ont disparu : avec l'index de repli (sans
        sqlite-vec), ils vivent en mémoire et ne survivent pas à un redémarrage. La question
        trouverait zéro extrait et le dirait faussement « aucun document prêt ». Lève
        `vector_index_lost`."""
        if self._index.persistent:
            return
        vectors = await self._store.aread_with(lambda conn: self._index.count(conn))
        if vectors < int(chunks or 0):
            raise AppError(
                "vector_index_lost",
                f"{vectors} vecteurs en mémoire pour {chunks} extraits prêts (index de repli).",
            )

    # --- le run --------------------------------------------------------------------------------

    async def _run(self, run: _Rag) -> None:
        secrets = self._settings.secret_values()
        root = run.handle.run_id
        try:
            try:
                sources, retrieval_s = await self._retrieve(run, secrets)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - la feuille `embedding` est déjà close
                error = leaf_error(exc, secrets)
                # La génération n'a jamais commencé : sa raison le dit (pas « annulée »).
                self._hub.declare_leaf(run.generation_leaf_id, NOT_STARTED_CO2)
                await self._hub.finish_run(root, "error", error=error)
                return
            leaf = await stream_into_run(
                self._hub,
                run.generation_leaf_id,
                run.model,
                build_request(run.question, sources),
                secrets=secrets,
                estimate_co2=self._cloud_estimator(run.model),
                slot=self._slot,
                timeout_s=self._settings.delays.lane_timeout_s,
                retry_interrupted=True,
                publish_to=root,
                meter=self._meter,
                on_leaf_closed=self._announce_carbon,
                metrics_extra={"retrieval_s": retrieval_s},
            )
            if leaf.status == "ok":
                self._publish_citations(root, sources)
                await self._hub.finish_run(root, "ok")
            else:
                await self._hub.finish_run(root, "error", error=leaf.error)
        except asyncio.CancelledError:
            raise  # `hub.cancel` a déjà fixé `cancelled` ; les feuilles sont closes avec lui
        except Exception as exc:  # noqa: BLE001 - ne jamais laisser le run actif
            logger.error("Run rag en échec", exc_info=exc)
            error = build_envelope("internal", f"{type(exc).__name__}: {exc}", secrets)
            with contextlib.suppress(Exception):
                await self._hub.finish_run(root, "error", error=error)

    async def _retrieve(
        self, run: _Rag, secrets: Sequence[str]
    ) -> tuple[list[dict[str, Any]], float]:
        """La recherche de la stratégie, puis `sources` ; rend les sources et la durée de la
        recherche (réponse hypothétique, embeddings et notations compris). Lève `rag_base_empty` si
        rien n'est interrogeable."""
        started = time.perf_counter()
        if run.strategy == "hyde":
            found = await self._hyde(run, secrets)
        elif run.strategy == "self_rag":
            found = await self._self_rag(run, secrets)
        else:
            found = await self._search(run, run.question, secrets)
        if not found:  # base vidée entre-temps, ou index perdu (repli numpy après un redémarrage)
            raise AppError("rag_base_empty", "La recherche n'a trouvé aucun extrait.")
        rag = self._settings.rag
        sources = build_sources(found, run.question, rag.relevance_very_close, rag.relevance_close)
        self._hub.publish(
            run.handle.run_id, "sources", {"strategy": run.strategy, "sources": sources}
        )
        return sources, round(time.perf_counter() - started, 6)

    async def _search(
        self, run: _Rag, text: str, secrets: Sequence[str], round_: int | None = None
    ) -> list[dict[str, Any]]:
        """Embedding de `text` (une feuille `embedding`), puis les `top_k` extraits les plus proches
        de documents `ready` : étapes `embedding` et `search`."""
        root = run.handle.run_id
        leaf_id = await self._embedding_leaf(run)
        started = time.perf_counter()
        vectors = await embed_into_leaf(
            self._hub,
            leaf_id,
            run.embedder,
            [text],
            slot=self._slot,
            meter=self._meter,
            timeout_s=self._settings.delays.lane_timeout_s,
            secrets=secrets,
            on_leaf_closed=self._announce_carbon,
        )
        embedded = time.perf_counter()
        self._step(root, run.strategy, "embedding", embedded - started, round=round_)
        found = await self._store.aread_with(
            lambda conn: repo.search_chunks(conn, self._index, vectors[0], run.top_k),
            vec=self._store.vec_available,
        )
        self._step(root, run.strategy, "search", time.perf_counter() - embedded, round=round_)
        return found

    async def _hyde(self, run: _Rag, secrets: Sequence[str]) -> list[dict[str, Any]]:
        """HyDE : le modèle rédige un passage hypothétique, la recherche s'appuie sur lui. Sans
        passage (appel en échec ou vide), elle retombe sur la question (`fallback`)."""
        started = time.perf_counter()
        hypothesis = await self._ask(run, hyde_request(run.question), secrets)
        self._step(
            run.handle.run_id,
            run.strategy,
            "hypothesis",
            time.perf_counter() - started,
            fallback=None if hypothesis else "question",
        )
        return await self._search(run, hypothesis or run.question, secrets)

    async def _self_rag(self, run: _Rag, secrets: Sequence[str]) -> list[dict[str, Any]]:
        """Self-RAG : recherche, notation des extraits, reformulation tant qu'aucun n'est pertinent,
        au plus `self_rag_max_iterations` fois ; la borne atteinte, les meilleurs extraits vus."""
        root = run.handle.run_id
        max_rewrites = self._settings.rag.self_rag_max_iterations
        query = run.question
        seen: list[list[dict[str, Any]]] = []
        for round_ in range(max_rewrites + 1):
            found = await self._search(run, query, secrets, round_)
            if not found:
                break
            seen.append(found)
            started = time.perf_counter()
            verdicts = parse_grade(
                await self._ask(run, grade_request(run.question, found), secrets) or ""
            )
            # Un extrait sans verdict lisible est gardé : le doute lui profite.
            kept = [item for rank, item in enumerate(found, 1) if verdicts.get(rank, True)]
            self._step(
                root,
                run.strategy,
                "grade",
                time.perf_counter() - started,
                round=round_,
                checked=len(found),
                relevant=len(kept),
                fallback=None if verdicts else "all",
            )
            if kept:
                return kept
            if round_ == max_rewrites:
                break
            started = time.perf_counter()
            rewritten = clean_query(
                await self._ask(run, rewrite_request(run.question, query), secrets) or ""
            )
            self._step(
                root,
                run.strategy,
                "rewrite",
                time.perf_counter() - started,
                round=round_,
                fallback=None if rewritten and rewritten != query else "stop",
            )
            if not rewritten or rewritten == query:
                break  # rien de neuf à essayer
            query = rewritten
        return merge_best(seen, run.top_k)

    async def _ask(self, run: _Rag, request: ChatRequest, secrets: Sequence[str]) -> str | None:
        """Un appel de modèle de la stratégie, **silencieux** (rien n'est publié dans le flux) et en
        feuille `generation` du run, mesurée comme les autres. Rend le texte, ou `None` si l'appel
        échoue ou ne rend rien : la stratégie a alors son repli."""
        leaf_id = await self._leaf(run, "generation", run.model.ref.tag)
        captured: list[str] = []
        result = await stream_into_run(
            self._hub,
            leaf_id,
            run.model,
            request,
            secrets=secrets,
            estimate_co2=self._cloud_estimator(run.model),
            slot=self._slot,
            timeout_s=self._settings.delays.lane_timeout_s,
            publish_to=run.handle.run_id,
            meter=self._meter,
            on_leaf_closed=self._announce_carbon,
            capture=captured,
        )
        if result.status != "ok":
            logger.warning(
                "Appel de stratégie %s en échec (%s)",
                run.strategy,
                (result.error or {}).get("code"),
            )
            return None
        return "".join(captured).strip() or None

    async def _embedding_leaf(self, run: _Rag) -> str:
        """La feuille `embedding` de la prochaine recherche : celle créée au départ pour la
        première, une nouvelle ensuite (reformulations de Self-RAG)."""
        if not run.embedding_used:
            run.embedding_used = True
            return run.embedding_leaf_id
        return await self._leaf(run, "embedding", run.embedder.ref.tag)

    async def _leaf(self, run: _Rag, kind: str, tag: str) -> str:
        """Crée une feuille du run, annulée par défaut tant qu'elle n'est pas jouée (AD-10). Le
        parent qui se clôt (annulation) interrompt la stratégie."""
        try:
            leaf = await self._hub.create_run(kind, models=[tag], parent_run_id=run.handle.run_id)
        except ValueError:
            raise asyncio.CancelledError from None
        self._hub.declare_leaf(leaf.run_id, CANCELLED_CO2)
        return leaf.run_id

    def _step(self, run_id: str, strategy: str, step: str, duration_s: float, **extra: Any) -> None:
        data: dict[str, Any] = {
            "strategy": strategy,
            "step": step,
            "duration_s": round(duration_s, 6),
        }
        data.update({key: value for key, value in extra.items() if value is not None})
        self._hub.publish(run_id, "retrieval_step", data)

    def _publish_citations(self, run_id: str, sources: list[dict[str, Any]]) -> None:
        """`citations` : les marqueurs `[n]` de la réponse qui désignent une source de `sources`
        (`rag/strategies.py::verify_citations`). Rien n'est publié sans marqueur vérifié : le front
        n'en fabrique alors aucun."""
        answer = self._hub.answer_text(run_id) or ""
        citations = verify_citations(answer, {source["n"] for source in sources})
        if citations:
            self._hub.publish(run_id, "citations", {"citations": citations})

    def _cloud_estimator(self, model: ChatModel) -> Callable[[ChatResult], Co2] | None:
        return cloud_estimator(model, self._settings)

    async def _announce_carbon(self) -> None:
        """`carbon_updated` après chaque feuille (AD-10) ; un échec est journalisé, sans effet."""
        session_id = self._hub.app_session_id
        if self._bus is None or session_id is None:
            return
        try:
            await announce_carbon_updated(self._bus, self._store, session_id)
        except Exception as exc:  # noqa: BLE001 - une annonce manquée ne change pas le run
            logger.warning("carbon_updated non publié : %r", exc)


async def chunk_view(store: Store, chunk_id: int) -> dict[str, Any]:
    """Un extrait en entier, avec son document et sa page (`GET /api/rag/chunks/{id}`).

    Lève `chunk_not_found` si l'extrait n'existe plus ou si son document n'est pas `ready`."""
    rows = await store.aread(repo.CHUNK_SQL, (chunk_id,))
    if not rows:
        raise AppError("chunk_not_found", f"Extrait {chunk_id} introuvable.", chunk_id=chunk_id)
    row = rows[0]
    return {
        "chunk_id": row["id"],
        "doc_id": row["document_id"],
        "document": row["source"],
        "page": row["page"],
        "position": row["position"],
        "text": row["text"],
    }
