"""Fiche machine : OS, processeur, mémoire, accélérateur, pilote.

Copie adaptée de `capture_fiche` de `hardware.py` (ancienne v2, `docs/archive/ancienne-v2/`) : la
v2 n'en garde que la capture de la machine (ni empreinte, ni champs de lancement du banc). Chaque
champ dégrade à `None` au lieu de lever. Aucun appel réseau ; la version d'Ollama est ajoutée par
l'appelant, qui la connaît par la sonde.
"""

from __future__ import annotations

import platform
from typing import Any, TypedDict

from wavelocalai.hardware.accelerator import detect_accelerator
from wavelocalai.hardware.nvml import decode_nvml_str, nvml_device, read_gpu_memory_gb


class Fiche(TypedDict):
    os: str
    cpu: str
    cpu_cores_physical: int | None
    cpu_cores_logical: int | None
    ram_gb: float | None
    accelerator: dict[str, Any]


def _ram_gb() -> float | None:
    try:
        import psutil

        return round(psutil.virtual_memory().total / 1024**3, 1)
    except Exception:  # noqa: BLE001 - capture au mieux
        return None


def _cores() -> tuple[int | None, int | None]:
    try:
        import psutil

        return psutil.cpu_count(logical=False), psutil.cpu_count(logical=True)
    except Exception:  # noqa: BLE001
        return None, None


def _gpu_details() -> dict[str, Any]:
    """Pilote, plafond CUDA et mémoire du premier GPU NVIDIA ; `{}` au moindre échec."""
    try:
        import pynvml

        with nvml_device(0) as handle:
            cuda = pynvml.nvmlSystemGetCudaDriverVersion()
            details: dict[str, Any] = {
                "driver_version": decode_nvml_str(pynvml.nvmlSystemGetDriverVersion()),
                "cuda_ceiling": f"{cuda // 1000}.{(cuda % 1000) // 10}",
            }
            memory = read_gpu_memory_gb(handle)
            if memory is not None:
                details["memory_total_gb"] = memory[1]
            return details
    except Exception:  # noqa: BLE001
        return {}


def capture_fiche() -> Fiche:
    """Fiche de la machine. Appelée une fois puis mise en cache par l'appelant (NVML est lent)."""
    accelerator = detect_accelerator()
    gpu: dict[str, Any] = {"kind": accelerator.kind, "name": accelerator.name}
    if accelerator.kind == "nvidia":
        gpu.update(_gpu_details())
    physical, logical = _cores()
    return Fiche(
        os=f"{platform.system()} {platform.release()}",
        cpu=platform.processor() or platform.machine(),
        cpu_cores_physical=physical,
        cpu_cores_logical=logical,
        ram_gb=_ram_gb(),
        accelerator=gpu,
    )
