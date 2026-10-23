"""Gérer la base documentaire : supprimer un document, la vider, régler (story 4.3, AD-13 à AD-16).

Supprimer un document retire ses `chunks` et, dans la même transaction, leurs lignes vec0 par
`rowid` (pas de cascade sur une table virtuelle), puis la file de l'écrivain enchaîne
`wal_checkpoint(TRUNCATE)`, `VACUUM`, `wal_checkpoint(TRUNCATE)` (`Store.write(purge=True)`) : le
texte supprimé ne reste ni dans le `.db` ni dans le `-wal`. « Vider » supprime tous les documents
puis **recrée** la table vec0 (`VectorIndex.clear`), avec la même purge ; `expected_count` (le
nombre d'extraits que l'utilisateur a vus) doit être celui de la base, sinon rien n'est supprimé.

Refus (409, AD-13 et AD-16) : `base_in_use` quand un run `rag` ou `eval` (évaluation de la qualité,
story 7.1) est actif, ou quand le document visé est encore `indexing` (son run `ingest` est actif),
et, pour « Vider » et un changement de modèle d'embedding, quand un run `ingest`, `rag` ou `eval`
est actif ; `base_count_stale` ; et
`embedding_change_needs_clear` pour un autre modèle sur une base non vide. Le contrôle des runs et
la mise en file de l'écriture se suivent sans `await` : aucun import ne peut démarrer entre les deux.

Les réglages (`GET`/`PUT /api/rag/settings`) vivent dans `preferences` (`rag/settings.py`) ; l'app
n'écrit jamais `wavelocalai.toml` (AD-15).
"""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any

from wavelocalai.config import Settings
from wavelocalai.errors import AppError
from wavelocalai.models.defaults import RAG_MIN_PARAMS_B
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.rag import repo
from wavelocalai.rag.index import SqliteVecIndex, VectorIndex
from wavelocalai.rag.rerank import RerankerService
from wavelocalai.rag.settings import (
    CHUNK_SIZE_RANGE,
    PREF_KEY,
    STRATEGIES,
    TOP_K_RANGE,
    effective,
    stored_overrides,
)
from wavelocalai.runs.hub import RunHub
from wavelocalai.store.db import Store
from wavelocalai.store.preferences import PreferenceStore
from wavelocalai.store.vec import vec_tables

BASE_COUNT_SQL = "SELECT count(*) AS n FROM chunks"
DOC_COUNT_SQL = "SELECT count(*) AS n FROM documents"
BASE_KINDS = ("ingest", "rag", "eval")  # les runs qui lisent ou écrivent la base (AD-16)


def _limits() -> dict[str, dict[str, int]]:
    return {
        "chunk_size": {"min": CHUNK_SIZE_RANGE[0], "max": CHUNK_SIZE_RANGE[1]},
        "top_k": {"min": TOP_K_RANGE[0], "max": TOP_K_RANGE[1]},
    }


def _erase_stray_vectors(
    conn: sqlite3.Connection, index: VectorIndex, ids: list[int] | None
) -> None:
    """Repli numpy sur un fichier qui garde des tables vec0 (écrites un jour avec sqlite-vec) :
    l'index en mémoire ne les touche pas, mais leurs vecteurs restent dans le fichier (AD-13). On
    les efface par `rowid` (`ids`) ou en recréant les tables (`None`, « Vider ») si la connexion
    connaît vec0 ; sinon (« no such module: vec0 ») on refuse, rien n'est supprimé, plutôt que de
    laisser un résidu. À appeler avant toute autre écriture (l'index en mémoire n'est pas
    transactionnel)."""
    if index.persistent or not vec_tables(conn):
        return
    try:
        if ids is None:
            SqliteVecIndex().clear(conn)
        elif ids:
            SqliteVecIndex().remove(conn, ids)
    except sqlite3.OperationalError as exc:
        if "no such module" not in str(exc):
            raise
        raise AppError(
            "vector_tables_unreachable",
            "Tables vec0 présentes dans le fichier, extension sqlite-vec non chargée.",
        ) from exc


class RagBaseService:
    def __init__(
        self,
        hub: RunHub,
        registry: ModelRegistry,
        settings: Settings,
        index: VectorIndex,
        preferences: PreferenceStore,
        reranker: RerankerService | None = None,
        fallback_model: str | None = None,
    ) -> None:
        self._reranker = reranker  # son état figure dans les réglages (story 4.7)
        self._hub = hub
        self._store: Store = hub.store
        self._registry = registry
        self._settings = settings
        self._index = index
        self._preferences = preferences
        self._fallback_model = fallback_model  # dernier recours (modèle `fake` des tests)

    # --- supprimer, vider ----------------------------------------------------------------------

    def _busy(self, kinds: tuple[str, ...] = BASE_KINDS) -> tuple[str, str] | None:
        """`(run_id, kind)` du premier run racine actif de ces genres (AD-14), sinon `None`."""
        for kind in kinds:
            run_id = self._hub.active_root(kind)
            if run_id is not None:
                return run_id, kind
        return None

    def _refuse_if_busy(self, kinds: tuple[str, ...] = BASE_KINDS) -> None:
        busy = self._busy(kinds)
        if busy is not None:
            run_id, kind = busy
            raise AppError(
                "base_in_use", f"Un run {kind} est actif ({run_id}).", run_id=run_id, kind=kind
            )

    async def delete_document(self, doc_id: str) -> dict[str, Any]:
        """Supprime un document `ready` ou `failed` ; rend `{document_id, source, status,
        chunks_removed}`. Lève `not_found` (inconnu) ou `base_in_use`."""
        rows = await self._store.aread("SELECT 1 FROM documents WHERE id = ?", (doc_id,))
        if not rows:
            raise AppError("not_found", f"Document {doc_id} introuvable.")
        index = self._index

        def erase(conn: sqlite3.Connection) -> dict[str, Any]:
            row = conn.execute(
                "SELECT source, status, run_id FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            if row is None:  # supprimé par une autre fenêtre entre-temps
                raise AppError("not_found", f"Document {doc_id} introuvable.")
            if row[1] == "indexing":  # son import tourne : il s'arrête avec « Annuler l'import »
                raise AppError(
                    "base_in_use",
                    f"{row[0]} est en cours d'indexation.",
                    run_id=row[2] or self._hub.active_root("ingest"),
                    kind="ingest",
                )
            ids = [
                int(r[0])
                for r in conn.execute("SELECT id FROM chunks WHERE document_id = ?", (doc_id,))
            ]
            _erase_stray_vectors(conn, index, ids)
            removed = repo.delete_chunks(conn, index, doc_id)
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return {
                "document_id": doc_id,
                "source": row[0],
                "status": row[1],
                "chunks_removed": removed,
            }

        # Contrôle des runs et mise en file de l'écriture sans `await` entre les deux.
        self._refuse_if_busy(("rag", "eval"))
        future = self._store.write(erase, purge=True)
        return await asyncio.shield(asyncio.wrap_future(future))

    async def clear(self, expected_count: int) -> dict[str, int]:
        """Vide la base : documents (tous statuts), extraits et table vec0 recréée. Rend
        `{documents_removed, chunks_removed}`. Lève `base_in_use` ou `base_count_stale` (rien n'est
        supprimé)."""
        index = self._index

        def erase(conn: sqlite3.Connection) -> dict[str, int]:
            chunks = int(conn.execute(BASE_COUNT_SQL).fetchone()[0])
            if chunks != expected_count:
                raise AppError(
                    "base_count_stale",
                    f"{expected_count} extraits attendus, {chunks} dans la base.",
                    expected=expected_count,
                    actual=chunks,
                )
            documents = int(conn.execute(DOC_COUNT_SQL).fetchone()[0])
            _erase_stray_vectors(conn, index, None)
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM documents")
            index.clear(conn)  # en dernier : l'index en mémoire n'est pas transactionnel
            return {"documents_removed": documents, "chunks_removed": chunks}

        self._refuse_if_busy()
        future = self._store.write(erase, purge=True)
        return await asyncio.shield(asyncio.wrap_future(future))

    # --- réglages ------------------------------------------------------------------------------

    async def settings_view(self) -> dict[str, Any]:
        return await _settings_view(
            self._settings,
            self._preferences,
            self._store,
            self._registry,
            self._index,
            self._reranker,
            self._fallback_model,
        )

    def _toml_embedder(self) -> str | None:
        """Le modèle d'embedding du `.toml` (étiquette résolue si elle est installée)."""
        tag = self._settings.rag.embedding_model
        if tag is None:
            return None
        try:
            return self._registry.resolve_embedder(tag).tag
        except AppError:
            return tag

    async def update_settings(self, update: dict[str, Any]) -> dict[str, Any]:
        """Enregistre les réglages donnés (les autres restent) dans `preferences` ; une valeur
        `None` retire le choix et revient au `.toml`. Changer d'embedding alors que la base n'est
        pas vide lève `base_in_use` (run actif) ou `embedding_change_needs_clear` ; rien n'est
        écrit dans ce cas. `wavelocalai.toml` n'est jamais modifié (AD-15)."""
        overrides = stored_overrides(self._preferences)
        if "embedding_model" in update:
            requested = update["embedding_model"]
            if requested is not None:
                requested = self._registry.resolve_embedder(requested).tag  # local, embedding
            # `null` rend le choix au `.toml` : c'est son modèle qui servira, s'il en nomme un.
            target = requested if requested is not None else self._toml_embedder()
            rows = await self._store.aread(repo.BASE_MODEL_SQL)
            current = rows[0]["embedding_model"] if rows else None
            if target is not None and target != current:
                self._refuse_if_busy()  # un import ou une question en cours : 409 d'abord (AD-16)
                if current is not None:
                    raise AppError(
                        "embedding_change_needs_clear",
                        f"La base utilise {current}, le réglage demande {requested}.",
                        current=current,
                        requested=target,
                    )
            update = {**update, "embedding_model": requested}
        merged = {**overrides, **update}
        size = merged.get("chunk_size")  # absent ou `null` : le `.toml`
        size = self._settings.rag.chunk_size if size is None else size
        overlap = merged.get("chunk_overlap")
        overlap = self._settings.rag.chunk_overlap if overlap is None else overlap
        if overlap >= size:
            raise AppError(
                "invalid_request",
                f"chunk_overlap ({overlap}) doit rester inférieur à chunk_size ({size}).",
            )
        merged = {key: value for key, value in merged.items() if value is not None}
        self._preferences.put(PREF_KEY, merged)
        return await self.settings_view()


async def _settings_view(
    settings: Settings,
    preferences: PreferenceStore | None,
    store: Store | None,
    registry: ModelRegistry | None,
    index: VectorIndex | None,
    reranker: RerankerService | None,
    fallback_model: str | None = None,
) -> dict[str, Any]:
    tun = effective(settings.rag, preferences)
    rerank = reranker.status() if reranker is not None else None
    base: dict[str, Any] = {"embedding_model": None, "documents": 0, "chunks": 0}
    if store is not None:
        totals = (await store.aread(repo.TOTALS_SQL))[0]
        model = await store.aread(repo.BASE_MODEL_SQL)
        base = {
            "embedding_model": model[0]["embedding_model"] if model else None,
            "documents": totals["documents"],
            "chunks": totals["chunks"],
        }
    models: list[dict[str, str]] = []
    if registry is not None:
        listed = (await registry.list_models()).models
        models = [{"tag": m.tag, "name": m.name} for m in listed if m.kind == "embedding"]
    if not models and fallback_model:  # dernier recours (modèle `fake` des tests, story 9.4)
        models = [{"tag": fallback_model, "name": fallback_model}]
    return {
        "embedding_model": tun.embedding_model,
        "chunk_size": tun.chunk_size,
        "chunk_overlap": tun.chunk_overlap,
        "top_k": tun.top_k,
        "strategy": tun.strategy,
        "base": base,
        "embedding_models": models,
        "strategies": list(STRATEGIES),
        "limits": _limits(),
        # Paramètres actifs (milliards) sous lesquels la stratégie vérifiée (Self-RAG) est peu fiable.
        "verify_min_params_b": RAG_MIN_PARAMS_B,
        "index": {"persistent": index.persistent if index is not None else True},
        # Reclassement par un reranker local (story 4.7) : `reason` dit pourquoi il est indisponible.
        "reranker": {
            "model": settings.rag.reranker_model,
            "available": rerank.available if rerank is not None else False,
            "reason": rerank.reason if rerank is not None else "reranker non démarré",
        },
    }


async def offline_settings_view(
    settings: Settings,
    preferences: PreferenceStore | None,
    registry: ModelRegistry | None,
    reranker: RerankerService | None = None,
    fallback_model: str | None = None,
) -> dict[str, Any]:
    """La vue des réglages hors du cycle de vie de l'app (pas de store ni d'index)."""
    return await _settings_view(
        settings, preferences, None, registry, None, reranker, fallback_model
    )
