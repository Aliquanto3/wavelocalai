"""Détection de l'accélérateur (GPU) du poste, pour l'affichage.

Copie adaptée de `src/core/accelerator.py` de la v1 (jamais importée, AD-2). Ordre : GPU NVIDIA par
NVML, puis Apple Silicon, sinon aucun. Une détection en échec vaut « aucun » : l'interface
n'annonce jamais un accélérateur qu'elle n'a pas trouvé. Aucun appel réseau.
"""

from __future__ import annotations

import contextlib
import logging
import platform
from dataclasses import dataclass

from wavelocalai.hardware.nvml import decode_nvml_str

logger = logging.getLogger("wavelocalai.hardware")

KIND_NVIDIA = "nvidia"
KIND_APPLE = "apple"


@dataclass(frozen=True)
class AcceleratorInfo:
    """Accélérateur détecté : `kind` (« nvidia », « apple ») et nom lisible, ou rien."""

    kind: str | None = None
    name: str | None = None

    @property
    def detected(self) -> bool:
        return self.kind is not None


NO_ACCELERATOR = AcceleratorInfo()


def detect_nvidia_gpus() -> list[str]:
    """Noms des GPU NVIDIA vus par NVML, dans l'ordre ; `[]` sans pilote, sans GPU ou en erreur."""
    try:
        import pynvml
    except ImportError:
        return []
    try:
        pynvml.nvmlInit()
    except Exception as exc:  # noqa: BLE001 - NVML absent ou pilote muet
        logger.debug("NVML indisponible : %s", exc)
        return []
    try:
        names = []
        for index in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            name = decode_nvml_str(pynvml.nvmlDeviceGetName(handle)).strip()
            if name:
                names.append(name)
        return names
    except Exception as exc:  # noqa: BLE001
        logger.debug("Lecture NVML impossible : %s", exc)
        return []
    finally:
        with contextlib.suppress(Exception):
            pynvml.nvmlShutdown()


def detect_nvidia_gpu() -> str | None:
    """Libellé des GPU NVIDIA : « NVIDIA GeForce RTX 3060 », « 2 × NVIDIA A100 » pour des GPU
    identiques, noms séparés par « + » sinon ; `None` si aucun."""
    names = detect_nvidia_gpus()
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    if len(set(names)) == 1:
        return f"{len(names)} × {names[0]}"
    return " + ".join(names)


def is_apple_silicon() -> bool:
    """Mac à puce Apple (arm64), dont le GPU sert à l'inférence via Metal."""
    try:
        return platform.system() == "Darwin" and platform.machine() == "arm64"
    except Exception:  # noqa: BLE001
        return False


def detect_accelerator() -> AcceleratorInfo:
    """Accélérateur réellement détecté ; `NO_ACCELERATOR` si aucun ou si la détection échoue."""
    gpu_name = detect_nvidia_gpu()
    if gpu_name:
        return AcceleratorInfo(KIND_NVIDIA, gpu_name)
    if is_apple_silicon():
        return AcceleratorInfo(KIND_APPLE, "Apple Silicon")
    return NO_ACCELERATOR
