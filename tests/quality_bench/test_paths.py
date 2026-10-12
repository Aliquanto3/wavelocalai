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


def test_set_paths(_isolated_data_root, tmp_path, monkeypatch):
    assert paths.set_config_path("set-v1") == paths.PACKAGE_DIR / "sets" / "set-v1.yaml"
    base = _isolated_data_root / "sets" / "set-v1"
    assert paths.set_dir("set-v1") == base
    assert paths.set_questions_path("set-v1") == base / "questions.jsonl"
    assert paths.set_tracks_path("set-v1") == base / "tracks.json"
    assert paths.sets_log_path("build-set") == _isolated_data_root / "sets" / "log-build-set.log"
    assert paths.private_dir() == _isolated_data_root / "private"
    assert paths.private_source_path("var-math-fr") == (
        _isolated_data_root / "private" / "var-math-fr.yaml"
    )
    assert paths.review_dir() == _isolated_data_root / "review"
    exports = tmp_path / "exports"
    monkeypatch.setenv("QUALITY_BENCH_EXPORTS", str(exports))
    assert paths.exports_root() == exports
    assert paths.set_index_path("set-v1") == exports / "sets" / "set-v1" / "index.jsonl"


def test_default_exports_root_is_repo_benchmarks(monkeypatch):
    monkeypatch.delenv("QUALITY_BENCH_EXPORTS")
    expected = Path(__file__).resolve().parents[2] / "benchmarks" / "quality"
    assert paths.exports_root() == expected


@pytest.mark.parametrize("bad", ["../x", "a/b", "a|b"])
def test_invalid_set_identifiers_refused(bad):
    with pytest.raises(ValueError):
        paths.set_dir(bad)


@pytest.mark.parametrize("name", ["sets", "references", "calibration", "References", "SETS"])
def test_reserved_export_dirs_are_refused_case_insensitively(name):
    """Sous Windows, « References » désigne le dossier réservé ``references/``."""
    with pytest.raises(ValueError, match="dossier réservé"):
        paths.campaign_exports_dir(name)


def test_campaign_exports_dir():
    assert paths.campaign_exports_dir("pilot-20261015") == paths.exports_root() / "pilot-20261015"
