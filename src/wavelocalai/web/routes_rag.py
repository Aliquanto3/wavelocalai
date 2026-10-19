"""`POST /api/rag/documents` : importe des fichiers dans la base documentaire (run `ingest`).

La requête est multipart : un ou plusieurs champs `files` et, en option, `embedding_model` (sinon
le modèle de la base, puis le défaut des réglages, puis le premier installé). La route copie les
fichiers dans un dossier temporaire (la requête ne les garde pas), crée le run et rend
`{run_id}` aussitôt ; la progression se lit par `GET /api/runs/{id}/events` (événements
`ingest_progress` et `ingest_file_done`). Au plus `rag.max_files` fichiers et `rag.max_import_mb`
Mo par import. `GET /api/rag/documents` liste les documents (tous statuts), les totaux des
documents prêts et les plafonds de l'écran. Toute la logique est dans `rag/` (AD-4).

`POST /api/rag/runs` pose une question aux documents prêts (run `rag`) et rend `{run_id,
conversation_id}` ; les sources, puis la réponse, se lisent par `GET /api/runs/{id}/events`.
`GET /api/rag/chunks/{id}` rend un extrait en entier.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel, Field, field_validator

from wavelocalai.errors import AppError
from wavelocalai.rag import repo
from wavelocalai.rag.ingest import IngestService
from wavelocalai.rag.query import RagCommand, RagService, chunk_view
from wavelocalai.rag.staging import StagedFile, discard_staging, new_staging_dir, stage_upload

router = APIRouter(prefix="/api")

BYTES_PER_MB = 1024 * 1024


class IngestStarted(BaseModel):
    run_id: str


class DocumentOut(BaseModel):
    id: str
    source: str
    status: str  # indexing | ready | failed
    chunks: int  # 0 tant que le document n'est pas prêt
    pages: int | None
    size_bytes: int
    embedding_model: str
    created_at: str
    ready_at: str | None
    run_id: str | None  # le run `ingest` qui l'a créé (reprise de l'écran)
    error: dict[str, Any] | None  # enveloppe `ingest_failed` d'un document `failed`


class Totals(BaseModel):
    documents: int
    chunks: int


class Limits(BaseModel):
    max_file_mb: int
    max_files: int
    max_import_mb: int


class DocumentList(BaseModel):
    documents: list[DocumentOut]
    totals: Totals  # documents `ready` seulement
    limits: Limits


@router.get("/rag/documents")
async def list_documents(request: Request) -> DocumentList:
    state = request.app.state
    store = state.store
    rag = state.settings.rag
    if store is None:  # hors du cycle de vie de l'app : une base vide
        rows, totals = [], {"documents": 0, "chunks": 0}
    else:
        rows = await store.aread(repo.LIST_SQL)
        totals = (await store.aread(repo.TOTALS_SQL))[0]
    return DocumentList(
        documents=[
            DocumentOut(
                id=row["id"],
                source=row["source"],
                status=row["status"],
                chunks=row["chunk_count"],
                pages=row["page_count"],
                size_bytes=row["size_bytes"],
                embedding_model=row["embedding_model"],
                created_at=row["created_at"],
                ready_at=row["ready_at"],
                run_id=row["run_id"],
                error=json.loads(row["error"]) if row["error"] else None,
            )
            for row in rows
        ],
        totals=Totals(documents=totals["documents"], chunks=totals["chunks"]),
        limits=Limits(
            max_file_mb=rag.max_file_mb, max_files=rag.max_files, max_import_mb=rag.max_import_mb
        ),
    )


@router.post("/rag/documents")
async def import_documents(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    embedding_model: Annotated[str | None, Form()] = None,
) -> IngestStarted:
    service: IngestService | None = request.app.state.ingest
    if service is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le service d'ingestion n'est pas démarré.")
    rag = request.app.state.settings.rag
    if len(files) > rag.max_files:
        raise AppError("invalid_request", f"Trop de fichiers : {rag.max_files} au plus par import.")
    max_bytes = rag.max_file_mb * BYTES_PER_MB
    staging = new_staging_dir()
    try:
        staged: list[StagedFile] = []
        total = 0
        for index, upload in enumerate(files, 1):
            staged.append(await stage_upload(upload, staging, index, max_bytes))
            total += staged[-1].size
            if total > rag.max_import_mb * BYTES_PER_MB:
                raise AppError(
                    "invalid_request",
                    f"Import trop volumineux : {rag.max_import_mb} Mo au plus par import.",
                )
        handle = await service.start(staged, staging, (embedding_model or "").strip() or None)
    except BaseException:
        discard_staging(staging)  # le service ne prend le dossier qu'une fois le run créé
        raise
    return IngestStarted(run_id=handle.run_id)


MAX_QUESTION_CHARS = 20_000


class RagBody(BaseModel):
    conversation_id: str | None = None
    question: str = Field(max_length=MAX_QUESTION_CHARS)
    model: str = Field(min_length=1)
    strategy: Literal["naive"] = "naive"
    allow_cloud: bool = False

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("la question est vide")
        return value


class RagStarted(BaseModel):
    run_id: str
    conversation_id: str | None


@router.post("/rag/runs")
async def start_rag_run(body: RagBody, request: Request) -> RagStarted:
    service: RagService | None = request.app.state.rag
    if service is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le service de questions aux documents n'est pas démarré.")
    handle = await service.start(RagCommand(**body.model_dump()))
    return RagStarted(run_id=handle.run_id, conversation_id=handle.conversation_id)


@router.get("/rag/chunks/{chunk_id}")
async def get_chunk(chunk_id: int, request: Request) -> dict[str, Any]:
    return await chunk_view(request.app.state.store, chunk_id)
