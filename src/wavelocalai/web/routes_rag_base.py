"""Gérer la base documentaire : `DELETE /api/rag/documents/{id}`, `DELETE /api/rag/base`,
`GET` et `PUT /api/rag/settings` (story 4.3). Toute la logique est dans `rag/manage.py` (AD-4).

- `DELETE /api/rag/documents/{id}` rend `{document_id, source, status, chunks_removed}` ; `404
  not_found` si le document n'existe plus, `409 base_in_use` si son import ou une question tourne.
- `DELETE /api/rag/base?expected_count=N` vide la base ; `N` est le nombre d'extraits affiché :
  `409 base_count_stale` (rien n'est supprimé) s'il a changé, `409 base_in_use` si un import ou une
  question est actif.
- `GET /api/rag/settings` rend les réglages en vigueur (embedding, découpe, nombre d'extraits,
  stratégie par défaut), l'état de la base, les modèles d'embedding installés et les bornes ;
  `PUT` en enregistre une partie (les champs absents restent) dans `preferences`. Changer
  d'embedding sur une base non vide : `409 embedding_change_needs_clear`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from wavelocalai.errors import AppError
from wavelocalai.rag.manage import RagBaseService, offline_settings_view
from wavelocalai.rag.settings import CHUNK_SIZE_RANGE, STRATEGIES, TOP_K_RANGE

router = APIRouter(prefix="/api")


def _service(request: Request) -> RagBaseService:
    service: RagBaseService | None = request.app.state.rag_base
    if service is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le service de gestion de la base n'est pas démarré.")
    return service


class DocumentDeleted(BaseModel):
    document_id: str
    source: str
    status: str
    chunks_removed: int


class BaseCleared(BaseModel):
    documents_removed: int
    chunks_removed: int


class SettingsUpdate(BaseModel):
    """Les champs envoyés changent, les absents restent ; `null` rend le choix au `.toml`."""

    model_config = ConfigDict(extra="forbid")

    embedding_model: str | None = Field(default=None, min_length=1, max_length=200)
    chunk_size: int | None = Field(default=None, ge=CHUNK_SIZE_RANGE[0], le=CHUNK_SIZE_RANGE[1])
    chunk_overlap: int | None = Field(default=None, ge=0, le=CHUNK_SIZE_RANGE[1])
    top_k: int | None = Field(default=None, ge=TOP_K_RANGE[0], le=TOP_K_RANGE[1])
    strategy: str | None = Field(default=None)


@router.delete("/rag/documents/{doc_id}")
async def delete_document(doc_id: str, request: Request) -> DocumentDeleted:
    return DocumentDeleted(**await _service(request).delete_document(doc_id))


@router.delete("/rag/base")
async def clear_base(request: Request, expected_count: Annotated[int, Query(ge=0)]) -> BaseCleared:
    return BaseCleared(**await _service(request).clear(expected_count))


@router.get("/rag/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    state = request.app.state
    service: RagBaseService | None = state.rag_base
    if service is None:  # hors du cycle de vie de l'app : les défauts du `.toml`
        return await offline_settings_view(state.settings, state.preferences, state.registry)
    return await service.settings_view()


@router.put("/rag/settings")
async def put_settings(body: SettingsUpdate, request: Request) -> dict[str, Any]:
    update = {name: getattr(body, name) for name in body.model_fields_set}
    if "strategy" in update and update["strategy"] not in (*STRATEGIES, None):
        raise AppError(
            "invalid_request",
            f"strategy : {update['strategy']!r} n'est pas prise en charge ({', '.join(STRATEGIES)}).",
        )
    return await _service(request).update_settings(update)
