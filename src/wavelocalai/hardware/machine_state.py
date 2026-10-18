"""État thermique instantané : température et bridage du GPU, température du processeur.

Copie adaptée de `machine_state.py` (ancienne v2, `docs/archive/ancienne-v2/`). Lecture au mieux :
chaque champ dégrade en `None`, `[]` ou « unavailable » plutôt que de lever. Sert à l'export de
preuve de « Sobriété et matériel » (stories suivantes) ; aucun appel réseau.
"""

from __future__ import annotations

from typing import TypedDict

from wavelocalai.hardware.nvml import (
    nvml_device,
    read_clocks_event_reasons,
    read_gpu_temperature_c,
)

CPU_TEMP_SOURCE_PSUTIL = "psutil"
CPU_TEMP_SOURCE_UNAVAILABLE = "unavailable"

# Clés de puce de `psutil.sensors_temperatures()` pour la capsule du processeur.
_CPU_PACKAGE_SENSOR_KEYS = ("coretemp", "k10temp", "cpu_thermal")


class MachineState(TypedDict):
    gpu_temp_c: float | None
    gpu_throttle_reasons: list[str]
    cpu_temp_c: float | None
    cpu_temp_source: str


def read_machine_state(device_index: int = 0) -> MachineState:
    gpu_temp_c, reasons = _read_gpu_fields(device_index)
    cpu_temp_c, source = _read_cpu_package_temp_c()
    return MachineState(
        gpu_temp_c=gpu_temp_c,
        gpu_throttle_reasons=reasons,
        cpu_temp_c=cpu_temp_c,
        cpu_temp_source=source,
    )


def _read_gpu_fields(device_index: int) -> tuple[float | None, list[str]]:
    try:
        with nvml_device(device_index) as handle:
            return read_gpu_temperature_c(handle), read_clocks_event_reasons(handle)
    except Exception:  # noqa: BLE001
        return None, []


def _read_cpu_package_temp_c() -> tuple[float | None, str]:
    try:
        import psutil

        # Absent de `psutil` sous Windows : on teste l'attribut plutôt que de l'appeler.
        if not hasattr(psutil, "sensors_temperatures"):
            return None, CPU_TEMP_SOURCE_UNAVAILABLE
        temps = psutil.sensors_temperatures()
        for key in _CPU_PACKAGE_SENSOR_KEYS:
            # Seul un capteur « package » est pris : une température de cœur n'est pas celle de la
            # capsule, et la publier sous `psutil` la ferait passer pour ce qu'elle n'est pas.
            package = next(
                (e for e in temps.get(key) or [] if "package" in (e.label or "").lower()), None
            )
            if package is not None:
                return float(package.current), CPU_TEMP_SOURCE_PSUTIL
        return None, CPU_TEMP_SOURCE_UNAVAILABLE
    except Exception:  # noqa: BLE001
        return None, CPU_TEMP_SOURCE_UNAVAILABLE
