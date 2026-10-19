"""`GET /api/references` : quel modèle pour quel usage (story 5.8, AD-22).

Servi depuis le fichier des résultats du banc (relu quand il change) et la liste du registre : aucun
appel d'Ollama avant de répondre (AD-15, budget de 300 ms).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from wavelocalai.models.usage_references import (
    InstalledModel,
    References,
    build_usage_references,
)

router = APIRouter(prefix="/api")


@router.get("/references")
async def references(request: Request) -> References:
    """Les références du banc par usage : groupe des meilleurs désigné par le serveur, débit sur le
    poste de référence, marques « installé » et « autre version », cibles de « Comparer ces modèles ».
    Fichier absent ou d'un autre format : `available: false` avec sa raison (jamais une erreur).
    Ollama arrêté : les références restent servies, sans marque."""
    registry = request.app.state.registry
    models = await registry.list_models(allow_cloud=False)
    bench = await asyncio.to_thread(registry.bench.current)
    installed = [
        InstalledModel(tag=m.tag, digest=m.digest)
        for m in models.models
        if m.origin == "local" and m.kind == "chat"
    ]
    return build_usage_references(bench, installed, ollama_up=models.ollama_up)
