"""Mémoire du poste et estimation du besoin d'un modèle : « tient en mémoire ? » (AD-15).

Copie adaptée de la règle de la v1 (`src/core/model_defaults.py`, jamais importée) : besoin
estimé = empreinte mesurée, à défaut taille du téléchargement × `SIZE_TO_LOADED` ; le modèle tient
si besoin × `FIT_MARGIN` ≤ mémoire disponible − `SYSTEM_RAM_BUFFER_GB`. La fiche machine, le GPU
(NVML) et la mémoire déjà occupée par les modèles chargés viennent avec la story 1.7. Module sans
dépendance au reste du paquet ; `psutil` est importé au premier appel.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# Mêmes valeurs que la v1 (`scripts/bench_here.py`, `src/core/config.py`).
FIT_MARGIN = 1.10  # marge de sécurité sur l'empreinte
SIZE_TO_LOADED = 1.25  # empreinte chargée estimée / taille du téléchargement
SYSTEM_RAM_BUFFER_GB = 0.5  # mémoire laissée au système
BYTES_PER_GB = 1024**3


@dataclass(frozen=True)
class MemoryReading:
    total_gb: float
    available_gb: float


@dataclass(frozen=True)
class FitAssessment:
    """`needed_gb` et `fits` valent `None` quand aucune taille n'est connue : jamais inventés."""

    needed_gb: float | None
    fits: bool | None
    available_gb: float


def read_memory() -> MemoryReading:
    """Mémoire vive totale et disponible, lues par psutil."""
    import psutil

    memory = psutil.virtual_memory()
    return MemoryReading(
        total_gb=memory.total / BYTES_PER_GB, available_gb=memory.available / BYTES_PER_GB
    )


def estimate_needed_gb(
    *,
    measured_loaded_gb: float | None = None,
    download_gb: float | None = None,
    download_bytes: int | None = None,
) -> float | None:
    """Empreinte chargée : mesure, sinon taille du catalogue, sinon taille d'Ollama, × 1,25."""
    if measured_loaded_gb and measured_loaded_gb > 0:
        return float(measured_loaded_gb)
    if download_gb and download_gb > 0:
        return download_gb * SIZE_TO_LOADED
    if download_bytes and download_bytes > 0:
        return download_bytes / BYTES_PER_GB * SIZE_TO_LOADED
    return None


def fits_in_memory(needed_gb: float | None, available_gb: float) -> bool | None:
    """`None` si le besoin est inconnu ; sinon besoin × marge ≤ disponible − réserve système."""
    if needed_gb is None:
        return None
    return needed_gb * FIT_MARGIN <= available_gb - SYSTEM_RAM_BUFFER_GB


class MemoryAdvisor:
    """Évalue un modèle contre la mémoire libre du moment (lecture injectable pour les tests)."""

    def __init__(self, reader: Callable[[], MemoryReading] = read_memory) -> None:
        self._reader = reader

    def assess(
        self,
        *,
        measured_loaded_gb: float | None = None,
        download_gb: float | None = None,
        download_bytes: int | None = None,
    ) -> FitAssessment:
        available = self._reader().available_gb
        needed = estimate_needed_gb(
            measured_loaded_gb=measured_loaded_gb,
            download_gb=download_gb,
            download_bytes=download_bytes,
        )
        return FitAssessment(needed, fits_in_memory(needed, available), available)
