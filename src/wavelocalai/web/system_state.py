"""État du système publié sur le flux (AD-6) et fiche machine de `GET /api/system/identity`.

`SystemSampler.sample()` ne bloque jamais sur Ollama (AD-15) : l'état vient de la sonde (cache 5 s,
1 s au plus), les modèles chargés de `/api/ps` (1 s au plus, seulement si Ollama répond), CPU et
mémoire de psutil, les runs actifs du hub. Le GPU (NVML, lent à froid) est lu dans un fil, hors de la
boucle : l'échantillon rend la dernière lecture et n'attend la suivante que `GPU_WAIT_S` ; sans NVML,
le champ `gpu` est absent. La fiche machine ne fait aucun appel réseau : la version d'Ollama est
celle que la sonde a en cache.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Any

import httpx

from wavelocalai.hardware.fiche import Fiche, capture_fiche
from wavelocalai.hardware.machine_state import GpuState, read_gpu_state
from wavelocalai.hardware.monitor import HardwareMonitor
from wavelocalai.models.ollama_probe import OllamaProbe
from wavelocalai.models.ollama_ps import loaded_models
from wavelocalai.runs.hub import RunHub

_log = logging.getLogger(__name__)

GPU_WAIT_S = 0.05  # attente de la lecture du GPU dans un échantillon : au-delà, la précédente sert

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
        gpu_reader: Callable[[], GpuState | None] = read_gpu_state,
    ) -> None:
        self._probe = probe
        self._host = host
        self._hub = hub
        self._ps_timeout_s = ps_timeout_s
        self._ps_transport = ps_transport
        self._monitor = monitor or HardwareMonitor()  # amorce psutil dès la création
        self.ollama_version: str | None = None  # dernière version vue, pour la fiche machine
        self.gpu_reader = gpu_reader  # remplaçable : la route de test `POST /api/test/gpu`
        self._gpu: GpuState | None = None  # dernière lecture réussie
        self._gpu_task: asyncio.Task[None] | None = None

    async def _gpu_state(self) -> GpuState | None:
        """Dernier état du GPU : une lecture part dans un fil, l'échantillon l'attend `GPU_WAIT_S`
        au plus (ce qui suffit à une lecture tiède) puis rend ce qu'il a."""
        task = self._gpu_task
        if task is None or task.done():
            task = self._gpu_task = asyncio.get_running_loop().create_task(self._read_gpu())
        await asyncio.wait({task}, timeout=GPU_WAIT_S)
        return self._gpu

    async def _read_gpu(self) -> None:
        # Une lecture sans résultat (NVML absent, GPU disparu) efface la précédente : jamais un
        # état périmé présenté comme présent. Un lecteur qui lève vaut aussi « aucun GPU », journalisé :
        # sinon l'exception de la tâche n'est jamais récupérée et l'état précédent resterait publié.
        try:
            self._gpu = await asyncio.to_thread(self.gpu_reader)
        except Exception:  # noqa: BLE001 - lecture au mieux
            _log.warning("lecture de l'état du GPU en échec", exc_info=True)
            self._gpu = None

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
        gpu = await self._gpu_state()
        return {
            "ollama": {
                "up": ollama.up,
                "version": ollama.version,
                "latency_ms": ollama.latency_ms,
            },
            **self._monitor.snapshot().as_dict(),
            "models_loaded": None if models is None else [m.as_dict() for m in models],
            **({} if gpu is None else {"gpu": dict(gpu)}),
            "runs_active": [] if hub is None else hub.active_runs(),
        }

    async def identity(self) -> dict[str, Any]:
        """Fiche machine (mise en cache), capturée dans le pool de threads."""
        fiche = await asyncio.to_thread(cached_fiche)
        cached = self._probe.cached  # l'état en cache de la sonde, jamais un appel réseau
        version = cached.version if cached is not None and cached.up else self.ollama_version
        return {**fiche, "ollama_version": version}
