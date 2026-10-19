"""La base documentaire vue par l'évaluation de la qualité (story 7.1, AD-4, AD-16).

`evaluation/` n'importe pas `rag/` (diagramme des couches) : l'application câble cette classe au
service d'évaluation, qui ne connaît que son port (`EvalBase`). Elle rend ce que l'évaluation demande
à la base : le modèle d'embedding et le `top_k` en vigueur (`prepare`), les extraits communs d'une
question (`search`, stratégie `naive`, une feuille `embedding` du run racine `eval`), l'embedding de
textes pour la pertinence (`embed`, une feuille `embedding` aussi) et l'invite de réponse du RAG
(`request`, celle de la Discussion : les modèles évalués reçoivent les mêmes extraits et la même
consigne). Les extraits sont ceux de `rag/query.py::build_sources`, `text` compris.

Aucun reclassement (story 4.7) : la comparaison porte sur les modèles, pas sur la recherche.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from wavelocalai.config import Settings
from wavelocalai.errors import AppError
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import CANCELLED_CO2
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import ChatRequest, Embedder
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.rag import repo
from wavelocalai.rag.embedding_leaf import embed_into_leaf
from wavelocalai.rag.index import VectorIndex
from wavelocalai.rag.query import build_request, build_sources, check_vectors
from wavelocalai.rag.settings import effective
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.system_bus import SystemBus
from wavelocalai.store.preferences import PreferenceStore

logger = logging.getLogger("wavelocalai.rag")

STRATEGY = "naive"


class EvalRetrieval:
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
        self._store = hub.store
        self._registry = registry
        self._factory = factory
        self._slot = slot
        self._settings = settings
        self._index = index
        self._meter = meter
        self._bus = bus
        self._preferences = preferences

    async def prepare(self) -> tuple[Embedder, int]:
        """Le modèle d'embedding de la base et le `top_k` en vigueur. Lève `rag_base_empty` (aucun
        document `ready`), `model_not_found` / `model_not_embedding` (modèle de la base) ou
        `vector_index_lost` : avant tout run."""
        base = await self._store.aread(repo.READY_BASE_SQL)
        if not base:
            raise AppError("rag_base_empty", "Aucun document `ready` dans la base.")
        embedder = self._factory.embedder(
            self._registry.resolve_embedder(base[0]["embedding_model"])
        )
        await check_vectors(self._store, self._index, base[0]["chunks"])
        return embedder, effective(self._settings.rag, self._preferences).top_k

    async def search(
        self, root_id: str, embedder: Embedder, top_k: int, question: str, question_index: int
    ) -> list[dict[str, Any]]:
        """Les `top_k` extraits les plus proches de `question` (étapes `embedding` et `search`,
        chacune avec son `question_index`) ; lève `rag_base_empty` si rien n'est trouvé (base vidée
        entre-temps, index perdu)."""
        secrets = self._settings.secret_values()
        leaf_id = await self._leaf(root_id, embedder)
        started = time.perf_counter()
        vectors = await embed_into_leaf(
            self._hub,
            leaf_id,
            embedder,
            [question],
            slot=self._slot,
            meter=self._meter,
            timeout_s=self._settings.delays.lane_timeout_s,
            secrets=secrets,
            on_leaf_closed=self._announce_carbon,
        )
        embedded = time.perf_counter()
        self._step(root_id, "embedding", embedded - started, question_index)
        found = await self._store.aread_with(
            lambda conn: repo.search_chunks(conn, self._index, vectors[0], top_k),
            vec=self._store.vec_available,
        )
        self._step(root_id, "search", time.perf_counter() - embedded, question_index)
        if not found:
            raise AppError("rag_base_empty", "La recherche n'a trouvé aucun extrait.")
        rag = self._settings.rag
        return build_sources(found, question, rag.relevance_very_close, rag.relevance_close)

    async def embed(self, root_id: str, embedder: Embedder, texts: list[str]) -> list[list[float]]:
        """Vecteurs de `texts` par le modèle d'embedding de la base, en feuille `embedding` du run."""
        leaf_id = await self._leaf(root_id, embedder)
        return await embed_into_leaf(
            self._hub,
            leaf_id,
            embedder,
            texts,
            slot=self._slot,
            meter=self._meter,
            timeout_s=self._settings.delays.lane_timeout_s,
            secrets=self._settings.secret_values(),
            on_leaf_closed=self._announce_carbon,
        )

    @staticmethod
    def request(question: str, sources: list[dict[str, Any]]) -> ChatRequest:
        """L'invite de réponse du RAG (consigne, extraits numérotés, question)."""
        return build_request(question, sources)

    async def _leaf(self, root_id: str, embedder: Embedder) -> str:
        """Une feuille `embedding` du run, annulée par défaut tant qu'elle n'est pas jouée (AD-10) ;
        le parent qui se clôt (annulation) interrompt l'évaluation."""
        try:
            leaf = await self._hub.create_run(
                "embedding", models=[embedder.ref.tag], parent_run_id=root_id
            )
        except ValueError:
            raise asyncio.CancelledError from None
        self._hub.declare_leaf(leaf.run_id, CANCELLED_CO2)
        return leaf.run_id

    def _step(self, root_id: str, step: str, duration_s: float, question_index: int) -> None:
        self._hub.publish(
            root_id,
            "retrieval_step",
            {
                "strategy": STRATEGY,
                "step": step,
                "duration_s": round(duration_s, 6),
                "question_index": question_index,
            },
        )

    async def _announce_carbon(self) -> None:
        """`carbon_updated` après chaque feuille (AD-10) ; un échec est journalisé, sans effet."""
        session_id = self._hub.app_session_id
        if self._bus is None or session_id is None:
            return
        try:
            await announce_carbon_updated(self._bus, self._store, session_id)
        except Exception as exc:  # noqa: BLE001 - une annonce manquée ne change pas le run
            logger.warning("carbon_updated non publié : %r", exc)
