"""Session NVML à la demande : initialisation et arrêt dans un même bloc (AD-21).

Copie adaptée de `nvml.py` de l'ancienne v2 (`docs/archive/ancienne-v2/`). `pynvml` (paquet
`nvidia-ml-py`) est importé dans la fonction qui s'en sert, jamais au niveau du module : sans
GPU NVIDIA ni pilote, chaque lecture dégrade en « inconnu » sans lever d'erreur.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def nvml_device(device_index: int = 0) -> Iterator[Any]:
    """Poignée NVML du GPU `device_index`, session ouverte et refermée par le bloc."""
    import pynvml

    pynvml.nvmlInit()
    try:
        yield pynvml.nvmlDeviceGetHandleByIndex(device_index)
    finally:
        pynvml.nvmlShutdown()


def decode_nvml_str(value: bytes | str) -> str:
    """Les champs texte de NVML sont des `bytes` selon le couple pilote / module."""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def read_gpu_temperature_c(handle: Any) -> float | None:
    """Température du GPU en °C ; `None` au moindre échec."""
    try:
        import pynvml

        return float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
    except Exception:  # noqa: BLE001 - lecture au mieux : ne casse jamais l'appelant
        return None


def clocks_event_reason_names() -> dict[int, str]:
    """Table bit -> nom, construite depuis les constantes du `pynvml` installé (import
    paresseux : elles ne se lisent pas à l'import du module)."""
    import pynvml

    return {
        pynvml.nvmlClocksEventReasonGpuIdle: "gpu_idle",
        pynvml.nvmlClocksEventReasonApplicationsClocksSetting: "applications_clocks_setting",
        pynvml.nvmlClocksEventReasonSwPowerCap: "sw_power_cap",
        pynvml.nvmlClocksEventReasonHwSlowdown: "hw_slowdown",
        pynvml.nvmlClocksEventReasonSyncBoost: "sync_boost",
        pynvml.nvmlClocksEventReasonSwThermalSlowdown: "sw_thermal_slowdown",
        pynvml.nvmlClocksEventReasonHwThermalSlowdown: "hw_thermal_slowdown",
        pynvml.nvmlClocksEventReasonHwPowerBrakeSlowdown: "hw_power_brake_slowdown",
        pynvml.nvmlClocksEventReasonDisplayClockSetting: "display_clock_setting",
    }


def decode_clocks_event_reasons(bitmask: int) -> list[str]:
    """Noms triés des raisons de bridage contenues dans `bitmask` (`0` donne `[]`)."""
    names = clocks_event_reason_names()
    return sorted(name for bit, name in names.items() if bitmask & bit)


def read_clocks_event_reasons(handle: Any) -> list[str]:
    """Raisons de bridage actuelles du GPU ; `[]` au moindre échec."""
    try:
        import pynvml

        return decode_clocks_event_reasons(pynvml.nvmlDeviceGetCurrentClocksEventReasons(handle))
    except Exception:  # noqa: BLE001 - lecture au mieux
        return []


def read_gpu_memory_gb(handle: Any) -> tuple[float, float] | None:
    """(utilisée, totale) en Gio de la mémoire du GPU ; `None` au moindre échec."""
    try:
        import pynvml

        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return round(info.used / 1024**3, 2), round(info.total / 1024**3, 2)
    except Exception:  # noqa: BLE001 - lecture au mieux
        return None
