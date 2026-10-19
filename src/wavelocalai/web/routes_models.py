"""`GET /api/models` : liste unique des modèles, servie depuis le cache du registre (AD-15)."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Request
from pydantic import BaseModel

from wavelocalai.inference.unload import unload_idle_models
from wavelocalai.models.defaults import ModelDefault, Purpose
from wavelocalai.models.registry import ModelList
from wavelocalai.runs.system_bus import STATE_EVENT

router = APIRouter(prefix="/api")


@router.get("/models")
async def list_models(request: Request, allow_cloud: bool = False) -> ModelList:
    """Sans `allow_cloud`, aucun modèle cloud n'est listé (D1) ; Ollama arrêté, la dernière
    liste connue est rendue (`ollama_up: false`)."""
    return await request.app.state.registry.list_models(allow_cloud=allow_cloud)


@router.get("/models/defaults")
async def model_defaults(
    request: Request, purpose: Purpose = "chat", allow_cloud: bool = False
) -> ModelDefault:
    """Modèle(s) par défaut d'un usage et sa raison ; `no_model` sans modèle de conversation.
    Jamais de cloud sans `allow_cloud`."""
    return await request.app.state.defaults.get(purpose, allow_cloud)


class KeptModel(BaseModel):
    tag: str
    run_id: str  # le run racine actif qui l'emploie


class UnloadResult(BaseModel):
    unloaded: list[str]  # modèles déchargés
    kept: list[KeptModel]  # modèles gardés : un run actif les emploie
    failed: list[str]  # modèles qu'Ollama a refusé de décharger
    free_gb: float  # mémoire libre après le déchargement (Go)


@router.post("/models/unload")
async def unload_models(request: Request) -> UnloadResult:
    """Décharge les modèles Ollama qu'aucun run actif n'emploie (`keep_alive: 0`), puis publie sans
    attendre l'état du système : la mémoire libre se met à jour sur le flux (AD-6). `ollama_down`
    si Ollama ne répond pas."""
    app = request.app
    hub = app.state.hub
    report = await unload_idle_models(
        app.state.settings.ollama.host,
        (lambda: {}) if hub is None else hub.active_models,
        reader=app.state.memory_reader,
        transport=app.state.ollama_transport,
    )
    with contextlib.suppress(Exception):  # sinon le tick suivant (2 s) met le flux à jour
        app.state.system_feed.publish(STATE_EVENT, await app.state.system_sampler.sample())
    return UnloadResult(
        unloaded=report.unloaded,
        kept=[KeptModel(**item) for item in report.kept],
        failed=report.failed,
        free_gb=report.free_gb,
    )
