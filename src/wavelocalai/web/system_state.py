"""État du système publié sur le flux (AD-6) et fiche machine de `GET /api/system/identity`.

`SystemSampler.sample()` ne bloque jamais sur Ollama (AD-15) : l'état vient de la sonde (cache 5 s,
1 s au plus), les modèles chargés de `/api/ps` (1 s au plus, seulement si Ollama répond), CPU et
mémoire de psutil, les runs actifs du hub. La fiche machine ne fait aucun appel réseau : la version
d'Ollama est celle que la sonde a vue en dernier.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any

import httpx

from wavelocalai.hardware.fiche import Fiche, capture_fiche
from wavelocalai.hardware.monitor import HardwareMonitor
from wavelocalai.models.ollama_probe import OllamaProbe
from wavelocalai.models.ollama_ps import loaded_models
from wavelocalai.runs.hub import RunHub

_fiche: Fiche | None = None
_fiche_lock = threading.Lock()


def cached_fiche() -> Fiche:
    """Fiche de la machine, capturée une fois par processus (le matériel ne change pas ; NVML est
    lent). Bloquante : à appeler dans un fil (`asyncio.to_thread`)."""
    global _fiche
    with _fiche_lock:
        if _fiche is None:
            _fiche = capture_fiche()
        return _fiche


class SystemSampler:
    def __init__(
        self,
        probe: OllamaProbe,
        host: str,
        hub: Callable[[], RunHub | None],
        *,
        ps_timeout_s: float = 1.0,
        ps_transport: httpx.AsyncBaseTransport | None = None,
        monitor: HardwareMonitor | None = None,
    ) -> None:
        self._probe = probe
        self._host = host
        self._hub = hub
        self._ps_timeout_s = ps_timeout_s
        self._ps_transport = ps_transport
        self._monitor = monitor or HardwareMonitor()  # amorce psutil dès la création
        self.ollama_version: str | None = None  # dernière version vue, pour la fiche machine

    async def sample(self) -> dict[str, Any]:
        ollama = await self._probe.status()
        if ollama.up:
            self.ollama_version = ollama.version
        models = None
        if ollama.up:
            models = await loaded_models(
                self._host, timeout_s=self._ps_timeout_s, transport=self._ps_transport
            )
        hub = self._hub()
        return {
            "ollama": {
                "up": ollama.up,
                "version": ollama.version,
                "latency_ms": ollama.latency_ms,
            },
            **self._monitor.snapshot().as_dict(),
            "models_loaded": None if models is None else [m.as_dict() for m in models],
            "runs_active": [] if hub is None else hub.active_runs(),
            # tag -> run racine qui l'emploie : l'écran Modèles désactive « Supprimer » (story 5.4)
            "models_in_use": {} if hub is None else hub.active_models(),
        }

    async def identity(self) -> dict[str, Any]:
        """Fiche machine (mise en cache), capturée dans le pool de threads."""
        fiche = await asyncio.to_thread(cached_fiche)
        return {**fiche, "ollama_version": self.ollama_version}
