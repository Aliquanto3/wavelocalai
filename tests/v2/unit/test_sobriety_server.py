"""Écran Sobriété, côté serveur (story 5.1) : état du GPU, équivalence en voiture, réglage daté."""

from __future__ import annotations

import asyncio
import sys
import time
import types
from datetime import date

import pytest

from wavelocalai.config import ConfigError, load_settings
from wavelocalai.greenops.equivalence import car_equivalence
from wavelocalai.hardware import machine_state
from wavelocalai.models.ollama_probe import OllamaProbe
from wavelocalai.web.system_state import SystemSampler

from ..conftest import make_settings

GPU = {
    "name": "NVIDIA GeForce RTX 3050",
    "memory_used_gb": 2.1,
    "memory_total_gb": 6.0,
    "temperature_c": 62.0,
    "thermal_throttle": False,
    "throttle_reasons": [],
}


def sampler(gpu_reader, tmp_path):
    settings = make_settings(tmp_path)
    probe = OllamaProbe(settings.ollama.host, wait_s=0.01)
    return SystemSampler(probe, settings.ollama.host, lambda: None, gpu_reader=gpu_reader)


# --- GPU : lecture NVML -------------------------------------------------------------------------


def fake_nvml(monkeypatch, *, reasons=0, memory=(2 * 1024**3, 6 * 1024**3), temperature=62):
    module = types.ModuleType("pynvml")
    module.nvmlInit = lambda: None
    module.nvmlShutdown = lambda: None
    module.nvmlDeviceGetHandleByIndex = lambda index: object()
    module.nvmlDeviceGetName = lambda handle: b"NVIDIA RTX Test"
    module.NVML_TEMPERATURE_GPU = 0
    module.nvmlDeviceGetTemperature = lambda handle, sensor: temperature
    module.nvmlDeviceGetMemoryInfo = lambda handle: types.SimpleNamespace(
        used=memory[0], total=memory[1]
    )
    module.nvmlDeviceGetCurrentClocksEventReasons = lambda handle: reasons
    for bit, name in enumerate(
        [
            "GpuIdle",
            "ApplicationsClocksSetting",
            "SwPowerCap",
            "HwSlowdown",
            "SyncBoost",
            "SwThermalSlowdown",
            "HwThermalSlowdown",
            "HwPowerBrakeSlowdown",
            "DisplayClockSetting",
        ]
    ):
        setattr(module, f"nvmlClocksEventReason{name}", 1 << bit)
    monkeypatch.setitem(sys.modules, "pynvml", module)


def test_gpu_state_reads_name_memory_temperature_and_thermal_throttle(monkeypatch):
    fake_nvml(monkeypatch, reasons=(1 << 5))  # SwThermalSlowdown
    state = machine_state.read_gpu_state()
    assert state == {
        "name": "NVIDIA RTX Test",
        "memory_used_gb": 2.0,
        "memory_total_gb": 6.0,
        "temperature_c": 62.0,
        "thermal_throttle": True,
        "throttle_reasons": ["sw_thermal_slowdown"],
    }


@pytest.mark.parametrize("bit", [0, 2, 3])  # inactif, plafond de puissance, ralenti matériel
def test_a_power_cap_or_an_idle_gpu_is_not_a_thermal_throttle(monkeypatch, bit):
    fake_nvml(monkeypatch, reasons=1 << bit)
    assert machine_state.read_gpu_state()["thermal_throttle"] is False


def test_gpu_state_is_none_without_nvml_and_when_the_memory_is_unreadable(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", None)
    assert machine_state.read_gpu_state() is None
    fake_nvml(monkeypatch)
    monkeypatch.setattr(machine_state, "read_gpu_memory_gb", lambda handle: None)
    assert machine_state.read_gpu_state() is None


# --- GPU : l'échantillon du flux ----------------------------------------------------------------


async def test_the_sample_carries_the_gpu_fields_when_there_is_one(tmp_path):
    state = await sampler(lambda: dict(GPU), tmp_path).sample()
    assert state["gpu"] == GPU


async def test_the_gpu_field_is_absent_without_nvml(tmp_path):
    state = await sampler(lambda: None, tmp_path).sample()
    assert "gpu" not in state


async def test_a_slow_gpu_read_never_slows_the_sample(tmp_path):
    def slow():
        time.sleep(0.3)  # NVML à froid
        return dict(GPU)

    instance = sampler(slow, tmp_path)
    loop = asyncio.get_running_loop()
    started = loop.time()
    first = await instance.sample()
    assert loop.time() - started < 0.25  # l'échantillon n'attend la lecture que 50 ms
    assert "gpu" not in first  # rien de lu encore : le champ est absent, pas inventé
    await asyncio.sleep(0.5)
    assert (await instance.sample())["gpu"] == GPU  # la lecture partie plus tôt est servie
    await asyncio.sleep(0.4)  # laisse finir la lecture relancée


async def test_a_gpu_that_disappears_is_not_published_from_a_stale_read(tmp_path):
    readings = [dict(GPU), None]
    instance = sampler(lambda: readings.pop(0) if len(readings) > 1 else None, tmp_path)
    assert "gpu" in await instance.sample()
    await asyncio.sleep(0.1)
    await instance.sample()  # la lecture « aucun GPU » part
    await asyncio.sleep(0.1)
    assert "gpu" not in await instance.sample()


async def test_a_gpu_reader_that_raises_clears_the_state_and_logs_it(tmp_path, caplog):
    readings = [dict(GPU)]

    def reader():
        if readings:
            return readings.pop(0)
        raise RuntimeError("NVML perdu")

    instance = sampler(reader, tmp_path)
    assert "gpu" in await instance.sample()
    await asyncio.sleep(0.1)
    await instance.sample()  # la lecture qui lève part
    await asyncio.sleep(0.1)
    assert "gpu" not in await instance.sample()  # jamais l'état précédent, périmé
    assert "GPU" in caplog.text


# --- Équivalence en voiture ---------------------------------------------------------------------


def toml_with(tmp_path, body: str):
    path = tmp_path / "wavelocalai.toml"
    path.write_text(body, encoding="utf-8")
    return load_settings(toml_path=path, env_file=tmp_path / "absent.env", environ={})


def test_the_versioned_toml_carries_a_dated_and_sourced_factor():
    from wavelocalai.config import DEFAULT_TOML

    settings = load_settings(toml_path=DEFAULT_TOML, environ={})
    factor = settings.carbon.car_equivalence
    assert factor is not None and factor.g_per_km > 0
    assert factor.source.strip() and isinstance(factor.retrieved_at, date)


def test_the_factor_needs_a_source_and_a_date_and_a_positive_value(tmp_path):
    valid = 'g_per_km = 142\nsource = "ADEME"\nretrieved_at = 2026-10-19\n'
    assert toml_with(tmp_path, f"[carbon.car_equivalence]\n{valid}").carbon.car_equivalence
    for body in (
        'g_per_km = 142\nsource = "ADEME"\n',  # sans date
        "g_per_km = 142\nretrieved_at = 2026-10-19\n",  # sans source
        'g_per_km = 142\nsource = "  "\nretrieved_at = 2026-10-19\n',  # source vide
        'g_per_km = 0\nsource = "ADEME"\nretrieved_at = 2026-10-19\n',  # facteur nul
    ):
        with pytest.raises(ConfigError):
            toml_with(tmp_path, f"[carbon.car_equivalence]\n{body}")


def test_the_server_computes_the_distance_one_milligram_per_g_per_km_in_metres():
    setting = make_settings_factor(111)
    result = car_equivalence(setting, 412.0, measured_runs=3)
    assert result["distance_m"] == pytest.approx(412 / 111)  # D-38 : 412 mg, environ 3,7 m
    assert result["g_per_km"] == 111 and result["total_mg"] == 412.0
    assert result["source"] and result["retrieved_at"] == "2026-10-19"


def test_no_measured_response_means_no_distance_never_zero_metres():
    result = car_equivalence(make_settings_factor(111), 0.0, measured_runs=0)
    assert result["distance_m"] is None and result["total_mg"] is None


def test_without_a_setting_there_is_no_equivalence():
    assert car_equivalence(None, 412.0, measured_runs=1) is None


def make_settings_factor(g_per_km: float):
    from wavelocalai.config import CarEquivalence

    return CarEquivalence(g_per_km=g_per_km, source="essai", retrieved_at=date(2026, 10, 19))
