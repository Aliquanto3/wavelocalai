"""Service d'ingestion : un import de fichiers est un run `ingest` (AD-5, AD-14, AD-16).

Le service obtient le modèle d'embedding par `registry.resolve_embedder(tag)` seulement, demande
au hub de créer le run racine `ingest`, puis lance dans une tâche la lecture des fichiers, un par
un. Pour chaque fichier : contrôle du chemin, extraction (`pypdf`, `docx`) et découpe dans le pool
de threads, puis embedding par lots. Chaque lot est une feuille `embedding` du run, mesurée par
CodeCarbon dans la place du `LocalSlot` (AD-11), prise par lot et non par run : un chat local
s'intercale entre deux lots (AD-14). Le CO2 de chaque feuille compte dans la session (AD-10).

Un fichier qui échoue (protégé, vide, format refusé, panne d'Ollama) passe à `failed` avec sa
raison, ses extraits partiels sont retirés, et les autres fichiers continuent ; le run finit `ok`
tant que l'orchestration aboutit (AD-5). Une annulation laisse les documents `ready` intacts et
retire le document en cours. Un contenu déjà présent (même empreinte) n'est pas indexé deux fois.

Événements publiés (en plus de ceux du hub) :
- `ingest_progress {file, file_index, file_count, phase: extract|split|embed, done, total}` ;
  `extract` et `split` valent 0/1 puis 1/1, `embed` compte les extraits vectorisés ;
- `ingest_file_done {file, document_id, status: ready|failed|duplicate, chunks, error}` (ajout à
  `contrat-api.md`, à ratifier) ; `error` est l'enveloppe `ingest_failed` d'AD-18.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

from wavelocalai.config import Settings
from wavelocalai.errors import ERRORS, AppError, build_envelope
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import CANCELLED_CO2
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import Embedder, ModelRef
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.rag import repo
from wavelocalai.rag.embedding_leaf import embed_into_leaf
from wavelocalai.rag.extract import (
    SUPPORTED_SUFFIXES,
    IngestError,
    Page,
    extract_pages,
    validate_path,
)
from wavelocalai.rag.index import VectorIndex
from wavelocalai.rag.split import ChunkDraft, split_pages
from wavelocalai.rag.staging import StagedFile, discard_staging
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import RunHandle
from wavelocalai.runs.system_bus import SystemBus
from wavelocalai.store.db import Store, utc_now_iso

logger = logging.getLogger("wavelocalai.rag")

T = TypeVar("T")


class IngestService:
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
        fallback_model: str | None = None,
    ) -> None:
        self._hub = hub
        self._store: Store = hub.store
        self._registry = registry
        self._factory = factory
        self._slot = slot
        self._settings = settings
        self._index = index
        self._meter = meter  # sans compteur, le CO2 d'un lot n'est pas mesuré
        self._bus = bus  # sans bus, `carbon_updated` n'est pas publié
        self._fallback_model = fallback_model  # dernier recours (modèle `fake` des tests)
        self._tasks: set[asyncio.Task[None]] = set()  # références fortes jusqu'à la fin

    # --- démarrage ---------------------------------------------------------------------------

    async def recover(self) -> int:
        """Au démarrage : un document resté `indexing` (arrêt pendant un import) passe à `failed`,
        sans extraits (le run correspondant est déjà `interrupted`, AD-5). Rend leur nombre."""
        rows = await self._store.aread(repo.INTERRUPTED_SQL)
        recovered = 0
        for row in rows:
            error = self._envelope(row["source"], "indexation interrompue par l'arrêt du serveur")
            try:
                await self._store.awrite(
                    lambda conn, doc_id=row["id"], err=error: repo.mark_failed(
                        conn, self._index, doc_id, err
                    )
                )
            except Exception:  # noqa: BLE001 - le serveur démarre même si l'index est inutilisable
                logger.exception("Document %s resté en cours d'indexation", row["id"])
                continue
            recovered += 1
        return recovered

    async def start(
        self, files: Sequence[StagedFile], staging_dir: Path, embedding_model: str | None = None
    ) -> RunHandle:
        """Crée le run `ingest` et rend `{run_id}` aussitôt ; l'indexation suit en tâche.

        Lève `model_not_found`, `model_not_embedding` ou `cloud_not_allowed` (registre),
        `no_embedding_model`, `embedding_locked` (la base a un autre modèle, AD-16) ou `run_busy`
        (un import est déjà actif, AD-14). L'appelant supprime `staging_dir` si `start` lève ;
        sinon le service le supprime à la fin du run."""
        if not files:
            raise AppError("invalid_request", "Aucun fichier à indexer.")
        ref = await self._pick_model(embedding_model)
        embedder = self._factory.embedder(ref)
        rag = self._settings.rag
        handle = await self._hub.create_run(
            "ingest",
            models=[ref.tag],
            params={
                "embedding_model": ref.tag,
                "file_count": len(files),
                "batch_size": rag.embed_batch_size,
                "chunk_size": rag.chunk_size,
                "chunk_overlap": rag.chunk_overlap,
            },
        )
        task = asyncio.create_task(
            self._run(handle, list(files), staging_dir, embedder),
            name=f"wavelocalai-ingest-{handle.run_id}",
        )
        self._hub.attach_task(handle.run_id, task)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return handle

    async def _pick_model(self, requested: str | None) -> ModelRef:
        """Modèle d'embedding : celui demandé, sinon celui de la base (une base = un modèle,
        AD-16), sinon le défaut des réglages, sinon le premier installé."""
        rows = await self._store.aread(repo.BASE_MODEL_SQL)
        current = rows[0]["embedding_model"] if rows else None
        tag = requested or current or self._settings.rag.embedding_model
        if tag is None:
            installed = (await self._registry.list_models()).models
            tag = next((m.tag for m in installed if m.kind == "embedding"), self._fallback_model)
        if tag is None:
            raise AppError("no_embedding_model", "Aucun modèle d'embedding dans la liste d'Ollama.")
        ref = self._registry.resolve_embedder(tag)
        if current is not None and ref.tag != current:
            raise AppError(
                "embedding_locked",
                f"La base utilise {current}, l'import demande {ref.tag}.",
                current=current,
                requested=ref.tag,
            )
        return ref

    # --- le run ------------------------------------------------------------------------------

    async def _run(
        self, handle: RunHandle, files: list[StagedFile], staging_dir: Path, embedder: Embedder
    ) -> None:
        secrets = self._settings.secret_values()
        try:
            for position, staged in enumerate(files, 1):
                await self._ingest_file(handle, staged, position, len(files), embedder)
            await self._hub.finish_run(handle.run_id, "ok")
        except asyncio.CancelledError:
            raise  # `hub.cancel` a déjà fixé `cancelled` ; le document en cours est retiré
        except Exception as exc:  # noqa: BLE001 - ne jamais laisser le run actif
            logger.error("Import interrompu par une erreur", exc_info=exc)
            error = build_envelope("internal", f"{type(exc).__name__}: {exc}", secrets)
            await self._hub.finish_run(handle.run_id, "error", error=error)
        finally:
            discard_staging(staging_dir)
            await self._announce_carbon()

    async def _ingest_file(
        self,
        handle: RunHandle,
        staged: StagedFile,
        position: int,
        count: int,
        embedder: Embedder,
    ) -> None:
        run_id = handle.run_id
        meta = {"file": staged.name, "file_index": position, "file_count": count}
        present = await self._store.aread(repo.PRESENT_SQL, (staged.fingerprint,))
        doc_id = uuid.uuid4().hex
        if not present:
            try:
                await self._write_through(
                    lambda conn: repo.insert_document(
                        conn,
                        doc_id=doc_id,
                        source=staged.name,
                        fingerprint=staged.fingerprint,
                        size_bytes=staged.size,
                        embedding_model=embedder.ref.tag,
                        run_id=run_id,
                        now=utc_now_iso(),
                    )
                )
            except sqlite3.IntegrityError:  # même contenu inséré entre-temps
                present = await self._store.aread(repo.PRESENT_SQL, (staged.fingerprint,))
            except asyncio.CancelledError:
                await self._discard(doc_id)  # l'insertion a pu aboutir pendant l'annulation
                raise
        if present:
            self._done(run_id, meta, present[0]["id"], "duplicate", present[0]["chunk_count"])
            return
        try:
            chunks = await self._index_file(run_id, staged, meta, doc_id, embedder)
        except asyncio.CancelledError:
            await self._discard(doc_id)  # l'import annulé ne laisse aucun extrait (ni le document)
            raise
        except Exception as exc:  # noqa: BLE001 - un fichier en échec n'arrête pas les autres
            reason, technical = _failure(exc)
            if not isinstance(exc, (IngestError, AppError)):
                logger.error("Indexation de %s en erreur", staged.name, exc_info=exc)
            error = self._envelope(staged.name, reason, technical)
            # À l'abri d'une annulation : sinon le document resterait `indexing` avec ses extraits.
            await self._write_through(
                lambda conn: repo.mark_failed(conn, self._index, doc_id, error)
            )
            self._done(run_id, meta, doc_id, "failed", 0, error)
            return
        self._done(run_id, meta, doc_id, "ready", chunks)

    async def _index_file(
        self, run_id: str, staged: StagedFile, meta: dict[str, Any], doc_id: str, embedder: Embedder
    ) -> int:
        """Extraction, découpe, embedding, puis `ready` ; rend le nombre d'extraits."""
        rag = self._settings.rag
        if staged.rejected is not None:
            raise IngestError(staged.rejected)
        suffix = staged.path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            shown = Path(staged.name).suffix.lower() or "sans extension"
            raise IngestError(f"le format {shown} n'est pas pris en charge (PDF, TXT, MD ou DOCX)")
        self._progress(run_id, meta, "extract", 0, 1)
        path = await asyncio.to_thread(validate_path, staged.path, [self._settings.data_dir])
        pages: list[Page] = await asyncio.to_thread(extract_pages, path, suffix)
        self._progress(run_id, meta, "extract", 1, 1)
        self._progress(run_id, meta, "split", 0, 1)
        drafts: list[ChunkDraft] = await asyncio.to_thread(
            split_pages, pages, rag.chunk_size, rag.chunk_overlap
        )
        if not drafts:
            raise IngestError("le fichier ne contient aucun texte à indexer")
        self._progress(run_id, meta, "split", 1, 1)
        ids = await self._store.awrite(lambda conn: repo.insert_chunks(conn, doc_id, drafts))

        total, done, dim = len(drafts), 0, None
        self._progress(run_id, meta, "embed", 0, total)
        for start in range(0, total, rag.embed_batch_size):
            batch = drafts[start : start + rag.embed_batch_size]
            batch_ids = ids[start : start + len(batch)]
            vectors = await self._embed_batch(run_id, embedder, [d.text for d in batch])
            dim = dim or len(vectors[0])
            if len(vectors[0]) != dim:
                raise IngestError(
                    "les vecteurs du modèle ont changé de dimension en cours de route"
                )
            if start == 0:
                await self._check_base_dim(dim, embedder.ref.tag)
            await self._store.awrite(
                lambda conn, ids=batch_ids, vecs=vectors: self._index.add(conn, ids, vecs)
            )
            done += len(batch)
            self._progress(run_id, meta, "embed", done, total)
        page_count = len(pages) if pages[0].number is not None else None
        assert dim is not None
        await self._store.awrite(
            lambda conn: repo.mark_ready(
                conn, doc_id, dim=dim, chunk_count=total, page_count=page_count, now=utc_now_iso()
            )
        )
        return total

    async def _check_base_dim(self, dim: int, tag: str) -> None:
        """Une base = une dimension (AD-16) : un modèle republié avec une autre taille est refusé."""
        rows = await self._store.aread(repo.BASE_DIM_SQL)
        if rows and int(rows[0]["embedding_dim"]) != dim:
            raise IngestError(
                f"{tag} rend des vecteurs de dimension {dim}, la base en contient de dimension "
                f"{rows[0]['embedding_dim']} ; videz la base pour changer de modèle"
            )

    # --- un lot d'embedding = une feuille ----------------------------------------------------

    async def _embed_batch(
        self, run_id: str, embedder: Embedder, texts: list[str]
    ) -> list[list[float]]:
        leaf = await self._hub.create_run(
            "embedding",
            models=[embedder.ref.tag],
            parent_run_id=run_id,
            params={"batch_size": len(texts)},
        )
        # Annulée avant sa fin, la feuille garde un `co2` sans valeur (AD-10).
        self._hub.declare_leaf(leaf.run_id, CANCELLED_CO2)
        # La place est prise par lot, pas par run (AD-14) ; le tracker tourne dedans (AD-11).
        return await embed_into_leaf(
            self._hub,
            leaf.run_id,
            embedder,
            texts,
            slot=self._slot,
            meter=self._meter,
            timeout_s=self._settings.delays.lane_timeout_s,
            secrets=self._settings.secret_values(),
            on_leaf_closed=self._announce_carbon,
        )

    # --- publication et nettoyage ------------------------------------------------------------

    def _progress(
        self, run_id: str, meta: dict[str, Any], phase: str, done: int, total: int
    ) -> None:
        self._hub.publish(
            run_id, "ingest_progress", {**meta, "phase": phase, "done": done, "total": total}
        )

    def _done(
        self,
        run_id: str,
        meta: dict[str, Any],
        doc_id: str,
        status: str,
        chunks: int,
        error: dict[str, Any] | None = None,
    ) -> None:
        self._hub.publish(
            run_id,
            "ingest_file_done",
            {**meta, "document_id": doc_id, "status": status, "chunks": chunks, "error": error},
        )

    def _envelope(self, file: str, reason: str, technical: str | None = None) -> dict[str, Any]:
        return build_envelope(
            "ingest_failed",
            technical or reason,
            self._settings.secret_values(),
            file=file,
            reason=reason,
        )

    async def _discard(self, doc_id: str) -> None:
        """Retire le document en cours (annulation) ; la tâche est déjà annulée : l'écriture part
        dans la file de l'écrivain tout de suite et on l'attend à l'abri d'une seconde annulation.
        """
        await self._write_through(lambda conn: repo.delete_document(conn, self._index, doc_id))

    async def _write_through(self, func: Callable[[sqlite3.Connection], T]) -> T:
        """Écriture menée à terme même si la tâche est annulée pendant l'attente : le job part
        dans la file de l'écrivain tout de suite, et son futur n'est jamais annulé (une annulation
        ne saute donc pas un job encore en file). `CancelledError` remonte une fois le job fini
        ou pendant l'attente ; l'écriture, elle, a lieu."""
        future = self._store.write(func)
        return await asyncio.shield(asyncio.wrap_future(future))

    async def _announce_carbon(self) -> None:
        """`carbon_updated` après chaque feuille (AD-10) ; un échec est journalisé, sans effet."""
        session_id = self._hub.app_session_id
        if self._bus is None or session_id is None:
            return
        try:
            await announce_carbon_updated(self._bus, self._store, session_id)
        except Exception:  # noqa: BLE001 - aucune mesure n'interrompt un run
            logger.exception("Publication de carbon_updated en échec")


def _failure(exc: BaseException) -> tuple[str, str | None]:
    """(raison affichée, détail technique) d'un fichier en échec."""
    if isinstance(exc, IngestError):
        return exc.reason, exc.technical
    if isinstance(exc, AppError):
        return ERRORS[exc.code].message.rstrip("."), exc.technical or exc.code
    return "erreur interne pendant l'indexation", f"{type(exc).__name__}: {exc}"
