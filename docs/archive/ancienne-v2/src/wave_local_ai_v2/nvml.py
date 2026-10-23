"""Shared NVML session handling: init/handle/shutdown in one place.

Both `hardware.py` (fiche capture) and `gpu.py` (per-run stats) need a short-lived
NVML session around one or two queries. Neither leaves a global handle open across
the process lifetime -- NVML is initialized and shut down for each call site's use,
per the architecture memory's guidance to keep GPU measurement best-effort.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def nvml_device(device_index: int = 0) -> Iterator[Any]:
    """Yield the NVML device handle for `device_index`, init/shutdown scoped to the call."""
    import pynvml

    pynvml.nvmlInit()
    try:
        yield pynvml.nvmlDeviceGetHandleByIndex(device_index)
    finally:
        pynvml.nvmlShutdown()


def decode_nvml_str(value: bytes | str) -> str:
    """NVML string fields come back as bytes on some driver/binding combinations."""
    return value.decode() if isinstance(value, bytes) else value


def read_gpu_temperature_c(handle: Any) -> float | None:
    """Read the GPU die temperature in Celsius. Best-effort: `None` on any failure."""
    try:
        import pynvml

        return float(
            pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        )
    except Exception:  # noqa: BLE001 - best-effort measurement, must never crash the run
        return None


# `nvmlDeviceGetCurrentClocksEventReasons` is read here rather than the
# still-present `nvmlDeviceGetCurrentClocksThrottleReasons`: both exist on the
# pinned `nvidia-ml-py==13.610.43` and return the same bitmask (confirmed
# live), but NVML's own naming migration (R520+) retired the `ThrottleReasons`
# name in favour of `ClocksEventReasons` -- this reads the current one.
def clocks_event_reason_names() -> dict[int, str]:
    """The bit->name map, built from the installed `pynvml`'s constants.

    Not a module-level constant: `pynvml` is imported lazily everywhere in
    this codebase (it is an optional, best-effort dependency), so its
    constants cannot be read at import time.
    """
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
    """Decode a clocks-event-reasons bitmask into its sorted set of reason names.

    `0` (`nvmlClocksEventReasonNone`) decodes to `[]`.
    """
    names = clocks_event_reason_names()
    return sorted(name for bit, name in names.items() if bitmask & bit)


def read_clocks_event_reasons(handle: Any) -> list[str]:
    """Read and decode the GPU's current clocks event reasons. `[]` on any failure."""
    try:
        import pynvml

        bitmask = pynvml.nvmlDeviceGetCurrentClocksEventReasons(handle)
        return decode_clocks_event_reasons(bitmask)
    except Exception:  # noqa: BLE001 - best-effort measurement, must never crash the run
        return []
