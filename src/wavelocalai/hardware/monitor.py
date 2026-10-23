"""Lecture instantanée du processeur et de la mémoire du poste (psutil).

Reprise adaptée de `HardwareMonitor` de la v1 (`src/core/green_monitor.py`, jamais importée) :
la v2 publie la mémoire du système entier (pas celle du seul processus de l'app), et ne lit pas
le GPU à chaque tick (la fiche d'identité s'en charge, une fois). Aucun appel réseau.
"""

from __future__ import annotations

from dataclasses import dataclass

GIB = 1024**3


@dataclass(frozen=True)
class SystemMetrics:
    cpu_percent: float
    memory_used_gb: float
    memory_total_gb: float
    memory_percent: float
    memory_available_gb: float  # libre pour un nouveau modèle (psutil `available`, caches compris)

    def as_dict(self) -> dict[str, object]:
        return {
            "cpu_percent": self.cpu_percent,
            "memory": {
                "used_gb": self.memory_used_gb,
                "total_gb": self.memory_total_gb,
                "percent": self.memory_percent,
                "available_gb": self.memory_available_gb,
            },
        }


class HardwareMonitor:
    """Instantané CPU / mémoire. `cpu_percent` mesure depuis l'appel précédent (non bloquant) :
    le premier appel est donc amorcé à la construction."""

    def __init__(self) -> None:
        import psutil

        self._psutil = psutil
        psutil.cpu_percent(interval=None)  # amorce : le premier appel rend toujours 0.0

    def snapshot(self) -> SystemMetrics:
        memory = self._psutil.virtual_memory()
        return SystemMetrics(
            cpu_percent=round(float(self._psutil.cpu_percent(interval=None)), 1),
            memory_used_gb=round(memory.used / GIB, 2),
            memory_total_gb=round(memory.total / GIB, 2),
            memory_percent=round(float(memory.percent), 1),
            memory_available_gb=round(memory.available / GIB, 2),
        )
