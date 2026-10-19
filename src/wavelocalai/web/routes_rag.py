"""`POST /api/rag/documents` : importe des fichiers dans la base documentaire (run `ingest`).

La requête est multipart : un ou plusieurs champs `files` et, en option, `embedding_model` (sinon
le modèle de la base, puis le défaut des réglages, puis le premier installé). La route copie les
fichiers dans un dossier temporaire (la requête ne les garde pas), crée le run et rend
`{run_id}` aussitôt ; la progression se lit par `GET /api/runs/{id}/events` (événements
`ingest_progress` et `ingest_file_done`). Toute la logique est dans `rag/` (AD-4).

`POST /api/rag/runs` pose une question aux documents prêts (run `rag`) et rend `{run_id,
conversation_id}` ; les sources, puis la réponse, se lisent par `GET /api/runs/{id}/events`.
`GET /api/rag/chunks/{id}` rend un extrait en entier.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel, Field, field_validator

from wavelocalai.errors import AppError
from wavelocalai.rag.ingest import IngestService
from wavelocalai.rag.query import RagCommand, RagService, chunk_view
from wavelocalai.rag.staging import discard_staging, new_staging_dir, stage_upload

router = APIRouter(prefix="/api")

BYTES_PER_MB = 1024 * 1024


class IngestStarted(BaseModel):
    run_id: str


@router.post("/rag/documents")
async def import_documents(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    embedding_model: Annotated[str | None, Form()] = None,
) -> IngestStarted:
    service: IngestService | None = request.app.state.ingest
    if service is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le service d'ingestion n'est pas démarré.")
    max_bytes = request.app.state.settings.rag.max_file_mb * BYTES_PER_MB
    staging = new_staging_dir()
    try:
        staged = [await stage_upload(f, staging, i, max_bytes) for i, f in enumerate(files, 1)]
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
