"""`GET /api/health` : version, instance, état d'Ollama, fournisseurs cloud configurés.

Lecture seule et sans attente : l'état d'Ollama vient de la sonde en cache (AD-15), les
fournisseurs cloud de `Settings` (jamais appelés).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from wavelocalai.config import get_version

router = APIRouter(prefix="/api")


class OllamaHealth(BaseModel):
    up: bool
    version: str | None
    latency_ms: int | None


class CloudProvider(BaseModel):
    id: str
    configured: bool


class Health(BaseModel):
    version: str
    instance_id: str
    ollama: OllamaHealth
    cloud_providers: list[CloudProvider]


@router.get("/health")
async def health(request: Request) -> Health:
    state = request.app.state
    ollama = await state.probe.status()
    return Health(
        version=get_version(),
        instance_id=state.instance_id,
        ollama=OllamaHealth(up=ollama.up, version=ollama.version, latency_ms=ollama.latency_ms),
        cloud_providers=[CloudProvider(**item) for item in state.settings.cloud_providers()],
    )
