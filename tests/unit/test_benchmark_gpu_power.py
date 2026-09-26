"""
Tests du relevé de puissance GPU du benchmark (scripts/benchmark_slm.py).
Usage: pytest tests/unit/test_benchmark_gpu_power.py -v

Les séries reprennent les relevés du poste RTX 3060 du 26/09/2026 : Qwen 3.5 4B
à 61 tok/s sous 80 W et à 71 tok/s sous 90 W, même chargement, même prompt.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import benchmark_slm as bs  # noqa: E402

# Montée en charge (2 100 MHz, 34 à 62 W) puis plateau au plafond.
RAMP = [(34.2, 2100), (45.6, 2100), (62.5, 2100)]
SLOW = RAMP + [(80.0, 1065), (79.6, 1222), (80.0, 1117), (79.8, 1042), (80.0, 1237),
               (79.8, 1050), (79.8, 1207), (80.0, 1200)]
FAST = RAMP + [(89.6, 1477), (90.1, 1492), (89.9, 1455), (89.8, 1507), (89.8, 1455),
               (90.0, 1515), (89.8, 1462), (90.0, 1477)]


class TestSummarizeGpuPower:
    def test_plateau_ignore_la_montee_en_charge(self):
        assert bs.summarize_gpu_power(SLOW)["gpu_power_plateau_w"] == 80.0
        assert bs.summarize_gpu_power(FAST)["gpu_power_plateau_w"] == 90.0

    def test_frequence_prise_au_plateau(self):
        # Les relevés de montée à 2 100 MHz ne doivent pas remonter la médiane.
        assert bs.summarize_gpu_power(SLOW)["gpu_sm_clock_gen_mhz"] < 1300
        assert bs.summarize_gpu_power(FAST)["gpu_sm_clock_gen_mhz"] > 1450

    def test_trop_peu_de_releves(self):
        assert bs.summarize_gpu_power([(80.0, 1200), (80.0, 1200)]) == {
            "gpu_power_plateau_w": 0.0, "gpu_sm_clock_gen_mhz": 0.0}


class TestGpuPowerSampler:
    def test_filtre_depuis_le_premier_token(self):
        sampler = bs.GpuPowerSampler()
        sampler.samples = [(t, w, c) for t, (w, c) in enumerate(RAMP + SLOW[3:])]
        # Depuis le premier token (t=3) : seuls les relevés du plateau comptent.
        assert sampler.summary(since=3)["gpu_power_plateau_w"] == 80.0
        assert sampler.summary(since=100) == {
            "gpu_power_plateau_w": 0.0, "gpu_sm_clock_gen_mhz": 0.0}

    def test_sans_nvml_le_contexte_ne_leve_pas(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "pynvml", None)  # import pynvml -> ImportError
        with bs.GpuPowerSampler() as sampler:
            pass
        assert sampler.samples == []
        assert sampler.summary()["gpu_power_plateau_w"] == 0.0
