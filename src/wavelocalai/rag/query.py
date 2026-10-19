"""Service de question aux documents : une question, ses sources, puis la réponse (AD-5, AD-9, AD-14).

Un run `rag` est composite (AD-5) : la racine publie seule le flux, et porte deux feuilles, un
`embedding` (la question, mesurée comme un lot d'ingestion) et une `generation` (la réponse, comme le
chat, `co2` cloud estimé par ecologits). Seuls les documents `ready` sont interrogés (AD-16).

Ordre des événements, stratégie `naive` : `retrieval_step {strategy, step: "embedding", duration_s}`,
`retrieval_step {strategy, step: "search", duration_s}`, `sources`, puis les `token` de la réponse
et `metrics` (débit D3, `retrieval_s` à part, `co2` de la génération). Chaque étape est publiée à sa
**fin**, quand sa durée est connue ; les sources partent donc avant le premier `token`.

`sources` est persisté sans `text` ; le hub le réhydrate depuis `chunks` au rejeu (AD-7).
`runs.params` ne reçoit ni la question ni les extraits (AD-7) : la question vit dans `messages`.

Une question est indépendante : le prompt ne reprend pas l'historique de la conversation (une
stratégie qui réécrit la question d'après l'historique viendra avec les stratégies suivantes).
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
from wavelocalai.inference.streaming import CANCELLED_CO2, Guard, stream_into_run
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import ChatMessage, ChatModel, ChatRequest, ChatResult, Embedder
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.rag import repo
from wavelocalai.rag.embedding_leaf import embed_into_leaf, leaf_error
from wavelocalai.rag.index import VectorIndex
from wavelocalai.rag.passage import pick_passage, relevance_label, similarity
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import Co2, RunHandle
from wavelocalai.runs.system_bus import SystemBus
from wavelocalai.store.db import Store

logger = logging.getLogger("wavelocalai.rag")

STRATEGIES = ("naive",)
TEMPERATURE = 0.1  # une réponse qui s'appuie sur des extraits : peu de créativité
NOT_STARTED_CO2 = Co2(
    mg=None, method="unmeasurable", reason="réponse non lancée : la recherche a échoué"
)

SYSTEM_PROMPT = (
    "Tu réponds en français à la question de l'utilisateur à partir des extraits de documents "
    "fournis, et d'eux seuls. Cite les extraits utilisés par leur numéro entre crochets, par "
    "exemple [1]. Si les extraits ne permettent pas de répondre, dis-le franchement au lieu "
    "d'inventer une réponse."
)


@dataclass(frozen=True)
class RagCommand:
    question: str
    model: str
    strategy: str = "naive"
    allow_cloud: bool = False
    conversation_id: str | None = None


@dataclass
class _Rag:
    handle: RunHandle
    model: ChatModel
    embedder: Embedder
    embedding_leaf_id: str
    generation_leaf_id: str
    question: str
    strategy: str


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
        guard: Guard | None = None,
    ) -> None:
        self._hub = hub
        self._store: Store = hub.store
        self._registry = registry
        self._factory = factory
        self._slot = slot
        self._settings = settings
        self._index = index
        self._meter = meter  # sans compteur, le CO2 d'une feuille locale n'est pas mesuré
        self._bus = bus  # sans bus, `carbon_updated` n'est pas publié
        self._guard = guard  # garde-fou mémoire de la réponse locale (story 4.8)
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
        ref = self._registry.resolve(command.model, command.allow_cloud)
        model = self._factory.chat_model(ref)
        base = await self._store.aread(repo.READY_BASE_SQL)
        if not base:
            raise AppError("rag_base_empty", "Aucun document `ready` dans la base.")
        embedder = self._factory.embedder(
            self._registry.resolve_embedder(base[0]["embedding_model"])
        )
        rag = self._settings.rag
        handle = await self._hub.create_run(
            "rag",
            models=[ref.tag],
            params={
                "strategy": command.strategy,
                "allow_cloud": command.allow_cloud,
                "embedding_model": embedder.ref.tag,
                "top_k": rag.top_k,
                "temperature": TEMPERATURE,
            },
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
        )
        task = asyncio.create_task(self._run(rag_run), name=f"wavelocalai-rag-{handle.run_id}")
        self._hub.attach_task(handle.run_id, task)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return handle

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
                guard=self._guard,
            )
            if leaf.status == "ok":
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
        """Embedding de la question, recherche, puis `sources` ; rend les sources et la durée de la
        recherche (embedding compris). Lève `rag_base_empty` si rien n'est interrogeable."""
        root = run.handle.run_id
        started = time.perf_counter()
        vectors = await embed_into_leaf(
            self._hub,
            run.embedding_leaf_id,
            run.embedder,
            [run.question],
            slot=self._slot,
            meter=self._meter,
            timeout_s=self._settings.delays.lane_timeout_s,
            secrets=secrets,
            on_leaf_closed=self._announce_carbon,
        )
        embedded = time.perf_counter()
        self._step(root, run.strategy, "embedding", embedded - started)
        rag = self._settings.rag
        found = await self._store.aread_with(
            lambda conn: repo.search_chunks(conn, self._index, vectors[0], rag.top_k),
            vec=self._store.vec_available,
        )
        searched = time.perf_counter()
        self._step(root, run.strategy, "search", searched - embedded)
        if not found:  # base vidée entre-temps, ou index perdu (repli numpy après un redémarrage)
            raise AppError("rag_base_empty", "La recherche n'a trouvé aucun extrait.")
        sources = build_sources(found, run.question, rag.relevance_very_close, rag.relevance_close)
        self._hub.publish(root, "sources", {"strategy": run.strategy, "sources": sources})
        return sources, round(searched - started, 6)

    def _step(self, run_id: str, strategy: str, step: str, duration_s: float) -> None:
        self._hub.publish(
            run_id,
            "retrieval_step",
            {"strategy": strategy, "step": step, "duration_s": round(duration_s, 6)},
        )

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
