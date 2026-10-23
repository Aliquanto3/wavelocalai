"""État thermique instantané : température et bridage du GPU, température du processeur.

Copie adaptée de `machine_state.py` (ancienne v2, `docs/archive/ancienne-v2/`). Lecture au mieux :
chaque champ dégrade en `None`, `[]` ou « unavailable » plutôt que de lever. Sert à l'export de
preuve de « Sobriété et matériel » et à l'état du GPU publié par le flux système (story 5.1) ; aucun
appel réseau.
"""

from __future__ import annotations

from typing import TypedDict

from wavelocalai.hardware.nvml import (
    decode_nvml_str,
    nvml_device,
    read_clocks_event_reasons,
    read_gpu_memory_gb,
    read_gpu_temperature_c,
)

CPU_TEMP_SOURCE_PSUTIL = "psutil"
CPU_TEMP_SOURCE_UNAVAILABLE = "unavailable"

# Clés de puce de `psutil.sensors_temperatures()` pour la capsule du processeur.
_CPU_PACKAGE_SENSOR_KEYS = ("coretemp", "k10temp", "cpu_thermal")


# Raisons de bridage que l'écran Sobriété dit « thermique » : une limite de puissance ou un ralenti
# volontaire du GPU n'en sont pas.
THERMAL_THROTTLE_REASONS = frozenset({"sw_thermal_slowdown", "hw_thermal_slowdown"})


class GpuState(TypedDict):
    """État instantané du premier GPU NVIDIA, tel que le flux système le publie (story 5.1)."""

    name: str
    memory_used_gb: float
    memory_total_gb: float
    temperature_c: float | None
    thermal_throttle: bool
    throttle_reasons: list[str]


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


def read_gpu_state(device_index: int = 0) -> GpuState | None:
    """Nom, mémoire, température et bridage du GPU en une seule session NVML ; `None` sans NVML,
    sans GPU ou si la mémoire n'est pas lisible (le flux n'invente aucun champ). Bloquante : à
    appeler hors de la boucle d'événements."""
    try:
        import pynvml

        with nvml_device(device_index) as handle:
            memory = read_gpu_memory_gb(handle)
            if memory is None:
                return None
            reasons = read_clocks_event_reasons(handle)
            return GpuState(
                name=decode_nvml_str(pynvml.nvmlDeviceGetName(handle)).strip(),
                memory_used_gb=memory[0],
                memory_total_gb=memory[1],
                temperature_c=read_gpu_temperature_c(handle),
                thermal_throttle=bool(THERMAL_THROTTLE_REASONS.intersection(reasons)),
                throttle_reasons=reasons,
            )
    except Exception:  # noqa: BLE001 - lecture au mieux
        return None
