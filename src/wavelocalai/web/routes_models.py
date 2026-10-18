"""`GET /api/models` : liste unique des modèles, servie depuis le cache du registre (AD-15)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from wavelocalai.models.registry import ModelList

router = APIRouter(prefix="/api")


@router.get("/models")
async def list_models(request: Request, allow_cloud: bool = False) -> ModelList:
    """Sans `allow_cloud`, aucun modèle cloud n'est listé (D1) ; Ollama arrêté, la dernière
    liste connue est rendue (`ollama_up: false`)."""
    return await request.app.state.registry.list_models(allow_cloud=allow_cloud)
