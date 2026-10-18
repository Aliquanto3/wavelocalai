"""Débit mesuré sur ce poste, tiré des feuilles de run (AD-15, D3).

Le débit d'un modèle est la médiane du `tps` des feuilles `ok` dont `tps_source` est
`ollama_eval`. Le registre lit `RunStats` ; la lecture de la table `runs` (store du hub) s'y
branchera, l'implémentation en mémoire suffit d'ici là.
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from collections.abc import Callable
from typing import Protocol

from wavelocalai.store.db import Store

logger = logging.getLogger("wavelocalai.models")

# Feuilles de run (un run enfant par appel de modèle, AD-5) dont le débit compte.
LEAF_KINDS = ("generation", "judge", "embedding")


class RunStats(Protocol):
    def medians(self) -> dict[str, float]:
        """Médiane du `tps` mesuré par tag ; un tag sans run est absent."""
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

    def medians(self) -> dict[str, float]:
        return {tag: statistics.median(values) for tag, values in self._tps.items() if values}


class SqliteRunStats:
    """Lit la table `runs` : feuilles `ok` en `ollama_eval` avec un `tps` positif, par `model`.

    Lecture courte sur une connexion en lecture seule ; sans store (avant le démarrage), vide.
    """

    def __init__(self, get_store: Callable[[], Store | None]) -> None:
        self._get_store = get_store

    def medians(self) -> dict[str, float]:
        store = self._get_store()
        if store is None:
            return {}
        placeholders = ", ".join("?" * len(LEAF_KINDS))
        try:
            rows = store.read(
                "SELECT model, tps FROM runs WHERE status = 'ok' AND tps_source = 'ollama_eval'"
                f" AND tps > 0 AND model IS NOT NULL AND kind IN ({placeholders})",  # noqa: S608
                LEAF_KINDS,
            )
        except Exception:  # noqa: BLE001 - une lecture de débit ne casse jamais la liste
            logger.warning("Lecture du débit mesuré impossible", exc_info=True)
            return {}
        by_tag: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            by_tag[row["model"]].append(float(row["tps"]))
        return {tag: statistics.median(values) for tag, values in by_tag.items()}
