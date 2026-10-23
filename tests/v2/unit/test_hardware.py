"""`hardware/` : instantané CPU / mémoire, fiche machine, accélérateur, NVML dégradé, sans réseau."""

from __future__ import annotations

import socket
import sys
import types

import pytest

from wavelocalai.hardware import accelerator, machine_state, nvml
from wavelocalai.hardware.fiche import capture_fiche
from wavelocalai.hardware.monitor import HardwareMonitor


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("appel réseau interdit")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def _fake_pynvml(monkeypatch, *, names=("NVIDIA Test GPU",), init_error=False):
    module = types.ModuleType("pynvml")

    def init():
        if init_error:
            raise RuntimeError("pas de pilote")

    module.nvmlInit = init
    module.nvmlShutdown = lambda: None
    module.nvmlDeviceGetCount = lambda: len(names)
    module.nvmlDeviceGetHandleByIndex = lambda i: i
    module.nvmlDeviceGetName = lambda handle: names[handle].encode()  # `bytes` : cas réel
    monkeypatch.setitem(sys.modules, "pynvml", module)
    return module


def test_monitor_snapshot_is_plausible_and_serialisable():
    monitor = HardwareMonitor()
    metrics = monitor.snapshot().as_dict()
    assert 0.0 <= metrics["cpu_percent"] <= 100.0
    memory = metrics["memory"]
    assert 0 < memory["used_gb"] <= memory["total_gb"]
    assert 0 < memory["available_gb"] <= memory["total_gb"]  # libre pour un nouveau modèle (4.8)
    assert 0.0 <= memory["percent"] <= 100.0


def test_fiche_has_the_machine_fields_and_makes_no_network_call(no_network):
    fiche = capture_fiche()
    assert set(fiche) == {
        "os", "cpu", "cpu_cores_physical", "cpu_cores_logical", "ram_gb", "accelerator",
    }  # fmt: skip
    assert fiche["os"] and fiche["cpu"] and fiche["ram_gb"] > 0
    assert set(fiche["accelerator"]) >= {"kind", "name"}


def test_accelerator_reads_nvml_names_and_groups_identical_gpus(monkeypatch):
    _fake_pynvml(monkeypatch, names=("NVIDIA A", "NVIDIA A"))
    assert accelerator.detect_nvidia_gpu() == "2 × NVIDIA A"
    _fake_pynvml(monkeypatch, names=("NVIDIA A", "NVIDIA B"))
    assert accelerator.detect_nvidia_gpu() == "NVIDIA A + NVIDIA B"
    _fake_pynvml(monkeypatch)
    assert accelerator.detect_accelerator() == accelerator.AcceleratorInfo(
        "nvidia", "NVIDIA Test GPU"
    )


def test_accelerator_degrades_to_none_without_driver_or_module(monkeypatch):
    _fake_pynvml(monkeypatch, init_error=True)
    monkeypatch.setattr(accelerator, "is_apple_silicon", lambda: False)
    assert accelerator.detect_accelerator() is accelerator.NO_ACCELERATOR
    monkeypatch.setitem(sys.modules, "pynvml", None)  # import impossible
    assert accelerator.detect_nvidia_gpus() == []


def test_apple_silicon_is_reported_when_no_nvidia(monkeypatch):
    monkeypatch.setattr(accelerator, "detect_nvidia_gpu", lambda: None)
    monkeypatch.setattr(accelerator, "is_apple_silicon", lambda: True)
    assert accelerator.detect_accelerator() == accelerator.AcceleratorInfo("apple", "Apple Silicon")


def test_nvml_reads_degrade_to_unknown_without_pynvml(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", None)
    assert nvml.read_gpu_temperature_c(object()) is None
    assert nvml.read_clocks_event_reasons(object()) == []
    assert nvml.read_gpu_memory_gb(object()) is None
    assert nvml.decode_nvml_str(b"RTX") == "RTX" and nvml.decode_nvml_str("RTX") == "RTX"


def test_machine_state_never_raises_whatever_the_platform(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", None)
    state = machine_state.read_machine_state()
    assert set(state) == {"gpu_temp_c", "gpu_throttle_reasons", "cpu_temp_c", "cpu_temp_source"}
    assert state["gpu_temp_c"] is None and state["gpu_throttle_reasons"] == []
    assert state["cpu_temp_source"] in {"psutil", "unavailable"}


def test_clocks_event_reasons_are_decoded_from_the_bitmask(monkeypatch):
    module = types.ModuleType("pynvml")
    for bit, name in enumerate(
        [
            "nvmlClocksEventReasonGpuIdle",
            "nvmlClocksEventReasonApplicationsClocksSetting",
            "nvmlClocksEventReasonSwPowerCap",
            "nvmlClocksEventReasonHwSlowdown",
            "nvmlClocksEventReasonSyncBoost",
            "nvmlClocksEventReasonSwThermalSlowdown",
            "nvmlClocksEventReasonHwThermalSlowdown",
            "nvmlClocksEventReasonHwPowerBrakeSlowdown",
            "nvmlClocksEventReasonDisplayClockSetting",
        ]
    ):
        setattr(module, name, 1 << bit)
    monkeypatch.setitem(sys.modules, "pynvml", module)
    assert nvml.decode_clocks_event_reasons(0) == []
    assert nvml.decode_clocks_event_reasons(0b101) == ["gpu_idle", "sw_power_cap"]
