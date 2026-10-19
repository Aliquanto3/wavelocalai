"""`POST /api/rag/documents` : importe des fichiers dans la base documentaire (run `ingest`).

La requête est multipart : un ou plusieurs champs `files` et, en option, `embedding_model` (sinon
le modèle de la base, puis le défaut des réglages, puis le premier installé). La route copie les
fichiers dans un dossier temporaire (la requête ne les garde pas), crée le run et rend
`{run_id}` aussitôt ; la progression se lit par `GET /api/runs/{id}/events` (événements
`ingest_progress` et `ingest_file_done`). Toute la logique est dans `rag/` (AD-4).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel

from wavelocalai.errors import AppError
from wavelocalai.rag.ingest import IngestService
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
