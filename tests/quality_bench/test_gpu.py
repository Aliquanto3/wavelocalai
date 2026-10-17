"""Vérification du GPU par ``nvidia-smi`` simulé (AD-13) : processus étrangers, mémoire à vide,
``[N/A]`` de WDDM, outil absent ou trop lent, réglage de campagne."""

from __future__ import annotations

import subprocess

import pytest
import yaml

from scripts.quality_bench.common import config, gpu
from scripts.quality_bench.common.gpu import (
    GpuCheckError,
    GpuCheckSettings,
    check_gpu,
    parse_compute_apps,
)

from .gpu_fakes import LLAMA_SERVER_LINE, OLLAMA_LINE, FakeSmi

SETTINGS = GpuCheckSettings()


def _install(monkeypatch, **kwargs):
    smi = FakeSmi(**kwargs)
    monkeypatch.setattr(gpu, "RUN", smi)
    return smi


def test_idle_gpu_is_accepted_and_recorded(monkeypatch):
    _install(monkeypatch, apps=[], used=[412])
    result = check_gpu(SETTINGS, [])
    assert result == {
        "enabled": True,
        "used_mib": 412,
        "max_idle_used_mib": 1024,
        "loaded_models": 0,
        "processes": [],
    }


def test_foreign_process_is_refused_with_its_name_and_memory(monkeypatch):
    _install(monkeypatch, apps=[LLAMA_SERVER_LINE], used=[6187])
    with pytest.raises(GpuCheckError) as error:
        check_gpu(SETTINGS, ["qwen3.5:4b"])  # même avec un modèle chargé
    message = str(error.value)
    assert "llama-server.exe (pid 22792, mémoire inconnue (WDDM))" in message
    assert "6187 MiB" in message


def test_foreign_process_with_known_memory(monkeypatch):
    _install(monkeypatch, apps=["777, C:\\x\\python.exe, 2048"], used=[2500])
    with pytest.raises(GpuCheckError, match=r"python\.exe \(pid 777, 2048 MiB\)"):
        check_gpu(SETTINGS, [])


def test_ollama_processes_are_accepted_when_models_are_loaded(monkeypatch):
    apps = [OLLAMA_LINE, "55, C:\\Ollama\\ollama_llama_server.exe, [N/A]"]
    _install(monkeypatch, apps=apps, used=[5200])
    result = check_gpu(SETTINGS, ["qwen3.5:4b"])
    assert result["used_mib"] == 5200 and result["loaded_models"] == 1
    assert result["processes"] == ["ollama.exe", "ollama_llama_server.exe"]


def test_idle_memory_above_threshold_without_loaded_model_is_refused(monkeypatch):
    _install(monkeypatch, apps=[], used=[3000])
    with pytest.raises(GpuCheckError, match=r"3000 MiB .*aucun modèle n'est chargé.*1024 MiB"):
        check_gpu(SETTINGS, [])
    # Seuil configurable, et modèle chargé : la règle de mémoire ne s'applique pas.
    assert check_gpu(GpuCheckSettings(max_idle_used_mib=4096), [])["used_mib"] == 3000
    assert check_gpu(SETTINGS, ["m:1b"])["used_mib"] == 3000


def test_idle_memory_error_names_ollama_processes(monkeypatch):
    _install(monkeypatch, apps=[OLLAMA_LINE], used=[3000])
    with pytest.raises(GpuCheckError, match=r"ollama\.exe \(pid 4012"):
        check_gpu(SETTINGS, [])


def test_memory_of_several_gpus_is_summed(monkeypatch):
    _install(monkeypatch, used=[600, 600])
    with pytest.raises(GpuCheckError, match="1200 MiB"):
        check_gpu(SETTINGS, [])


def test_missing_nvidia_smi_is_refused_with_the_way_out(monkeypatch):
    _install(monkeypatch, error=FileNotFoundError("nvidia-smi"))
    with pytest.raises(GpuCheckError, match=r"introuvable.*gpu_check: \{enabled: false\}"):
        check_gpu(SETTINGS, [])


def test_slow_nvidia_smi_is_refused(monkeypatch):
    _install(monkeypatch, error=subprocess.TimeoutExpired("nvidia-smi", gpu.TIMEOUT_S))
    with pytest.raises(GpuCheckError, match="sans réponse"):
        check_gpu(SETTINGS, [])


def test_failing_nvidia_smi_is_refused(monkeypatch):
    _install(monkeypatch, returncode=9, stderr="NVIDIA-SMI has failed\n")
    with pytest.raises(GpuCheckError, match=r"code 9 : NVIDIA-SMI has failed"):
        check_gpu(SETTINGS, [])


def test_disabled_check_never_runs_nvidia_smi(monkeypatch):
    smi = _install(monkeypatch, error=FileNotFoundError("nvidia-smi"))
    assert check_gpu(GpuCheckSettings(enabled=False), None) == {"enabled": False}
    assert smi.commands == []


def test_unreadable_output_is_refused():
    with pytest.raises(GpuCheckError, match="illisible"):
        parse_compute_apps(["pas du csv"])


def test_path_with_comma_and_slashes_is_parsed():
    (process,) = parse_compute_apps(["12, C:/Program Files/a,b/llama-server.exe, [N/A]"])
    assert (process.pid, process.name, process.used_mib) == (12, "llama-server.exe", None)


def test_gpu_check_setting_in_campaign_yaml(tmp_path):
    def load(extra):
        path = tmp_path / "camp.yaml"
        doc = {"set": "s", "generation": {"models": [_MODEL]}, **extra}
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")
        return config.load_campaign(path)

    base = load({})
    assert base.gpu_check == GpuCheckSettings(True, 1024)
    custom = load({"gpu_check": {"enabled": False, "max_idle_used_mib": 2048}})
    assert custom.gpu_check == GpuCheckSettings(False, 2048)
    # Hors section generation : l'empreinte de génération ne bouge pas.
    assert custom.generation_hash == base.generation_hash
    for bad in ({"enabled": "oui"}, {"max_idle_used_mib": -1}, {"autre": 1}):
        with pytest.raises(config.ConfigError):
            load({"gpu_check": bad})


_MODEL = {
    "tag": "m:1b",
    "family": "qwen",
    "tracks": ["think_off"],
    "think_off": None,
    "num_ctx_max": 8192,
}
