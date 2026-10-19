"""Déchargement des modèles Ollama inactifs : « Décharger les modèles inactifs » (story 4.8).

Un modèle chargé (`/api/ps`) qu'aucun run actif n'emploie est déchargé (`keep_alive: 0`) ; ceux
qu'un run emploie sont gardés, avec le run qui les tient. Le service attend un instant que
`/api/ps` ne les liste plus (l'arrêt n'est pas instantané) avant de rendre la mémoire libre ; la
route publie ensuite l'état du système sans attendre le tick de 2 s.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from wavelocalai.errors import AppError
from wavelocalai.hardware.memory import MemoryReading, floor_tenth, read_memory
from wavelocalai.models.ollama_ps import loaded_models, unload_model

SETTLE_S = 3.0  # attente maximale de la libération (Ollama rend la main avant la mémoire)
POLL_S = 0.25


@dataclass(frozen=True)
class UnloadReport:
    unloaded: list[str] = field(default_factory=list)
    kept: list[dict[str, str]] = field(default_factory=list)  # [{tag, run_id}] : un run l'emploie
    failed: list[str] = field(default_factory=list)  # Ollama a refusé le déchargement
    free_gb: float = 0.0  # mémoire libre après le déchargement


async def unload_idle_models(
    host: str,
    active_models: Callable[[], dict[str, str]],
    *,
    reader: Callable[[], MemoryReading] = read_memory,
    transport: httpx.AsyncBaseTransport | None = None,
    settle_s: float = SETTLE_S,
) -> UnloadReport:
    """Décharge les modèles chargés que `active_models()` (tag -> run racine) ne cite pas.
    Lève `ollama_down` si Ollama ne répond pas."""
    loaded = await loaded_models(host, timeout_s=2.0, transport=transport)
    if loaded is None:
        raise AppError("ollama_down", "Ollama ne répond pas à /api/ps.")
    busy = active_models()
    unloaded: list[str] = []
    kept: list[dict[str, str]] = []
    failed: list[str] = []
    for model in loaded:
        if model.tag in busy:
            kept.append({"tag": model.tag, "run_id": busy[model.tag]})
        elif await unload_model(host, model.tag, transport=transport):
            unloaded.append(model.tag)
        else:
            failed.append(model.tag)
    if unloaded:
        await _settle(host, set(unloaded), transport, settle_s)
    return UnloadReport(
        unloaded=unloaded,
        kept=kept,
        failed=failed,
        free_gb=floor_tenth(reader().available_gb),
    )


async def _settle(
    host: str, tags: set[str], transport: httpx.AsyncBaseTransport | None, settle_s: float
) -> None:
    deadline = time.monotonic() + settle_s
    while time.monotonic() < deadline:
        loaded = await loaded_models(host, timeout_s=1.0, transport=transport)
        if loaded is None or not tags & {model.tag for model in loaded}:
            return
        await asyncio.sleep(POLL_S)
