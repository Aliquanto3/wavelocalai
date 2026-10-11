"""Chemins des données (AD-2) : racine ``$QUALITY_BENCH_DATA``."""

from pathlib import Path

import pytest

from scripts.quality_bench.common import paths


def test_data_root_follows_environment(_isolated_data_root):
    assert paths.data_root() == _isolated_data_root
    assert paths.machine_lock_path() == _isolated_data_root / "machine.lock"


def test_default_data_root_is_repo_data(monkeypatch):
    monkeypatch.delenv("QUALITY_BENCH_DATA")
    expected = Path(__file__).resolve().parents[2] / "data" / "quality_bench"
    assert paths.data_root() == expected


def test_campaign_paths(_isolated_data_root):
    base = _isolated_data_root / "campaigns" / "pilot-20261015"
    assert paths.campaign_dir("pilot-20261015") == base
    assert paths.generation_path("pilot-20261015") == base / "generation.jsonl"
    assert paths.generation_manifest_path("pilot-20261015") == base / "manifest.json"
    assert paths.warmups_path("pilot-20261015") == base / "warmups.jsonl"
    assert paths.generation_lock_path("pilot-20261015") == base / "generation.lock"
    assert paths.generation_stop_path("pilot-20261015") == base / "STOP"
    assert paths.grading_path("pilot-20261015") == base / "grading.jsonl"
    assert paths.log_path("pilot-20261015", "generate") == base / "log-generate.log"


def test_judgment_paths(_isolated_data_root):
    base = _isolated_data_root / "campaigns" / "c1" / "judgment-haiku"
    assert paths.judgment_dir("c1", "haiku") == base
    assert paths.judgment_path("c1", "haiku") == base / "judgment.jsonl"
    assert paths.judgment_manifest_path("c1", "haiku") == base / "manifest.json"
    assert paths.batches_path("c1", "haiku") == base / "batches.jsonl"
    assert paths.judgment_lock_path("c1", "haiku") == base / "judgment.lock"
    assert paths.judgment_stop_path("c1", "haiku") == base / "STOP"


def test_campaign_config_path_in_package():
    assert paths.campaign_config_path("pilot-20261015") == (
        paths.PACKAGE_DIR / "campaigns" / "pilot-20261015.yaml"
    )


@pytest.mark.parametrize("bad", ["", "../x", "a/b", "a\\b", "a|b", "..", ".hidden", "a b", "abc\n"])
def test_invalid_identifiers_refused(bad):
    with pytest.raises(ValueError):
        paths.campaign_dir(bad)
