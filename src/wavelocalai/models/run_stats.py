"""Débit mesuré sur ce poste, tiré des feuilles de run (AD-15, D3).

Le débit d'un modèle est la médiane du `tps` des feuilles `ok` dont `tps_source` est
`ollama_eval`. Le registre lit `RunStats` ; la lecture de la table `runs` (store du hub) s'y
branchera, l'implémentation en mémoire suffit d'ici là.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Protocol


class RunStats(Protocol):
    def median_tps(self, tag: str) -> float | None:
        """Médiane du `tps` mesuré pour ce tag ; `None` sans run."""
        ...


class InMemoryRunStats:
    def __init__(self) -> None:
        self._tps: dict[str, list[float]] = defaultdict(list)

    def record_leaf(
        self, tag: str, tps: float | None, *, status: str = "ok", tps_source: str = "ollama_eval"
    ) -> None:
        """Ne retient que les feuilles `ok` en `ollama_eval` avec un débit positif."""
        if status == "ok" and tps_source == "ollama_eval" and tps is not None and tps > 0:
            self._tps[tag].append(float(tps))

    def median_tps(self, tag: str) -> float | None:
        values = self._tps.get(tag)
        return statistics.median(values) if values else None
