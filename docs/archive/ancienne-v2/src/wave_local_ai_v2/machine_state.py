"""Per-repetition machine state: GPU temperature/throttle reasons, CPU package temperature.

Sampled once per repetition, immediately after the completion returns -- same
timing and the same best-effort discipline as `gpu.read_gpu_stats` and
`hardware.capture_fiche`'s GPU fields. A machine-state read must never fail a
repetition: every field degrades to `None` / `[]` / `"unavailable"` rather
than raising.
"""

from __future__ import annotations

from typing import TypedDict

from wave_local_ai_v2.nvml import (
    nvml_device,
    read_clocks_event_reasons,
    read_gpu_temperature_c,
)

CPU_TEMP_SOURCE_PSUTIL = "psutil"
CPU_TEMP_SOURCE_UNAVAILABLE = "unavailable"

# `psutil.sensors_temperatures()` groups sensors by chip key; these are the
# label conventions psutil's own docs name for a CPU package sensor across
# platforms. Confirmed live on this Windows build: the attribute does not
# exist at all (`hasattr(psutil, "sensors_temperatures")` is `False`), so
# this list is exercised only where the platform actually has it.
_CPU_PACKAGE_SENSOR_KEYS = ("coretemp", "k10temp", "cpu_thermal")


class MachineState(TypedDict):
    gpu_temp_c: float | None
    gpu_throttle_reasons: list[str]
    cpu_temp_c: float | None
    cpu_temp_source: str


def read_machine_state(device_index: int = 0) -> MachineState:
    """Read the current GPU temperature/throttle reasons and CPU package temperature.

    GPU fields degrade to `None` / `[]` on any NVML failure; CPU package
    temperature degrades to `None` / `"unavailable"` when no admin-free
    reader exists on this platform (the story's spike conclusion here).
    """
    gpu_temp_c, gpu_throttle_reasons = _read_gpu_fields(device_index)

    cpu_temp_c, cpu_temp_source = _read_cpu_package_temp_c()

    return MachineState(
        gpu_temp_c=gpu_temp_c,
        gpu_throttle_reasons=gpu_throttle_reasons,
        cpu_temp_c=cpu_temp_c,
        cpu_temp_source=cpu_temp_source,
    )


def _read_gpu_fields(device_index: int) -> tuple[float | None, list[str]]:
    try:
        with nvml_device(device_index) as handle:
            return read_gpu_temperature_c(handle), read_clocks_event_reasons(handle)
    except Exception:  # noqa: BLE001 - best-effort measurement, must never crash the run
        return None, []


def _read_cpu_package_temp_c() -> tuple[float | None, str]:
    try:
        import psutil

        # The attribute does not exist on this platform's psutil build
        # (confirmed live) -- guarded rather than called directly, since
        # calling a missing attribute raises `AttributeError`, not an empty
        # mapping.
        if not hasattr(psutil, "sensors_temperatures"):
            return None, CPU_TEMP_SOURCE_UNAVAILABLE

        temps = psutil.sensors_temperatures()
        for key in _CPU_PACKAGE_SENSOR_KEYS:
            entries = temps.get(key)
            if not entries:
                continue
            # Only a package-labelled sensor is taken. A per-core reading is
            # not the package temperature, and publishing one under
            # `cpu_temp_source: "psutil"` would name it as something it is
            # not -- the field degrades to "unavailable" instead.
            package = next(
                (
                    entry
                    for entry in entries
                    if "package" in (entry.label or "").lower()
                ),
                None,
            )
            if package is not None:
                return float(package.current), CPU_TEMP_SOURCE_PSUTIL

        return None, CPU_TEMP_SOURCE_UNAVAILABLE
    except Exception:  # noqa: BLE001 - best-effort measurement, must never crash the run
        return None, CPU_TEMP_SOURCE_UNAVAILABLE
