"""
Tests du benchmark de ce poste (src/core/benchmark_results.py) : empreinte du poste,
fichier de résultats, précision et débit prudent par tag, lecture tolérante.

Résultats factices dans tmp_path : ni Ollama, ni réseau, ni mesure.
Usage: python -m pytest tests/unit/test_benchmark_results.py -v
"""

import json
import logging
import sys
from pathlib import Path

import pytest

from src.core import benchmark_results as br
from src.core import model_defaults as md

ROOT_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT_DIR / "benchmarks" / "results"

CATALOG = {
    "Gemma 4 E4B (QAT)": {"ollama_tag": "gemma4:e4b-it-qat"},
    "Granite 4.2 8B": {"ollama_tag": "granite4.2:8b"},
    "LFM 2.5 2.6B": {"ollama_tag": "LiquidAI/lfm2.5-2.6b"},
}


def _entry(reasoning=0.86, following=1.0, avg=71.08, mean=68.75) -> dict:
    """Entrée de la section `models` d'un fichier de résultats (champs utiles seulement)."""
    entry: dict = {"quality_scores": {}, "runs": {}}
    if reasoning is not None:
        entry["quality_scores"]["reasoning_avg"] = reasoning
    if following is not None:
        entry["quality_scores"]["instruction_following_avg"] = following
    if avg is not None:
        entry["avg_tokens_per_second"] = avg
    if mean is not None:
        entry["runs"]["tokens_per_second"] = {"n": 2, "mean": mean}
    return entry


def _write(directory: Path, name: str, content) -> Path:
    path = directory / name
    text = content if isinstance(content, str) else json.dumps(content)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Empreinte du poste
# ---------------------------------------------------------------------------


def test_digest_matches_machine_profile():
    """Même empreinte que scripts/machine_profile.machine_id (sans libellé)."""
    sys.path.insert(0, str(ROOT_DIR / "scripts"))
    try:
        import machine_profile
    finally:
        sys.path.remove(str(ROOT_DIR / "scripts"))

    assert br.machine_digest() == machine_profile.machine_id(None)
    assert machine_profile.machine_id("poste").endswith(f"-{br.machine_digest()}")


def test_results_file_found_by_digest(tmp_path):
    _write(tmp_path, "autre-poste-00000000.json", {"models": {}})
    labelled = _write(tmp_path, "poste-rtx3060-22601cd4.json", {"models": {}})
    assert br.find_results_file(tmp_path, "22601cd4") == labelled

    bare = tmp_path / "bare"
    bare.mkdir()
    path = _write(bare, "22601cd4.json", {"models": {}})
    assert br.find_results_file(bare, "22601cd4") == path


def test_unknown_machine_has_no_results(tmp_path):
    """Poste inconnu : aucun fichier à son empreinte, benchmark vide."""
    _write(tmp_path, "poste-rtx3060-22601cd4.json", {"models": {"x": _entry()}})
    assert br.find_results_file(tmp_path, "deadbeef") is None
    assert br.load_machine_benchmark(tmp_path, CATALOG, "deadbeef") == {}
    # Suffixe partiel : pas de correspondance.
    assert br.find_results_file(tmp_path, "601cd4") is None
    # Dossier absent : vide, sans exception.
    assert br.load_machine_benchmark(tmp_path / "absent", CATALOG, "22601cd4") == {}


def test_several_files_for_one_machine_latest_export_wins(tmp_path):
    _write(tmp_path, "a-22601cd4.json", {"exported_at": "2026-09-26T00:00:00+00:00"})
    newest = _write(tmp_path, "b-22601cd4.json", {"exported_at": "2026-09-27T00:00:00+00:00"})
    _write(tmp_path, "c-22601cd4.json", "{ illisible")
    assert br.find_results_file(tmp_path, "22601cd4") == newest


# ---------------------------------------------------------------------------
# Précision et débit prudent
# ---------------------------------------------------------------------------


def test_precision_and_cautious_speed():
    """Précision = moyenne raisonnement / consignes ; débit = le plus bas des deux mesures
    (Granite 4.2 8B : 10,41 puis 5,05)."""
    data = {
        "models": {
            "Gemma 4 E4B (QAT)": _entry(0.86, 1.0, 71.08, 68.75),
            "Granite 4.2 8B": _entry(0.71, 0.88, 10.41, 5.05),
        }
    }
    scores = br.parse_results(data, CATALOG)

    assert scores["gemma4:e4b-it-qat"].precision == pytest.approx(0.93)
    assert scores["gemma4:e4b-it-qat"].speed_tps == pytest.approx(68.75)
    assert scores["granite4.2:8b"].speed_tps == pytest.approx(5.05)
    # Une seule des deux mesures de débit : elle suffit.
    one = br.parse_results({"models": {"Granite 4.2 8B": _entry(mean=None)}}, CATALOG)
    assert one["granite4.2:8b"].speed_tps == pytest.approx(71.08)


def test_equal_precisions_are_exactly_equal():
    """0,86/1,0 et 0,93/0,93 donnent la même précision (départage par le débit ensuite)."""
    a = br.parse_results({"models": {"Gemma 4 E4B (QAT)": _entry(0.86, 1.0)}}, CATALOG)
    b = br.parse_results({"models": {"Gemma 4 E4B (QAT)": _entry(0.93, 0.93)}}, CATALOG)
    assert a["gemma4:e4b-it-qat"].precision == b["gemma4:e4b-it-qat"].precision


def test_name_to_tag_by_catalog_or_entry():
    """Nom → tag par le catalogue versionné ; `ollama_tag` de l'entrée prioritaire ;
    clé sans `:latest`."""
    data = {
        "models": {
            "LFM 2.5 2.6B": _entry(),
            "Hors catalogue": {**_entry(), "ollama_tag": "hors:1b:latest"},
            "Inconnu": _entry(),
        }
    }
    scores = br.parse_results(data, CATALOG)
    assert set(scores) == {"LiquidAI/lfm2.5-2.6b", "hors:1b"}


def test_incomplete_entries_are_skipped_with_a_warning(caplog):
    """Champs absents : l'entrée est ignorée, les autres restent ; avertissement au journal."""
    data = {
        "models": {
            "Gemma 4 E4B (QAT)": _entry(following=None),
            "Granite 4.2 8B": _entry(avg=None, mean=None),
            "LFM 2.5 2.6B": _entry(),
            "Pas un objet": "?",
        }
    }
    with caplog.at_level(logging.WARNING, logger=br.__name__):
        scores = br.parse_results(data, CATALOG)
    assert set(scores) == {"LiquidAI/lfm2.5-2.6b"}
    assert "Granite 4.2 8B" in caplog.text and "Gemma 4 E4B (QAT)" in caplog.text


@pytest.mark.parametrize(
    "content",
    ["{ pas du json", json.dumps(["liste"]), json.dumps({"autre": {}}), json.dumps({"models": 3})],
)
def test_unreadable_file_gives_empty_benchmark_and_a_warning(tmp_path, caplog, content):
    """Fichier illisible : benchmark vide (règle de la story 7), avertissement, aucune
    exception."""
    _write(tmp_path, "poste-22601cd4.json", content)
    with caplog.at_level(logging.WARNING):
        assert br.load_machine_benchmark(tmp_path, CATALOG, "22601cd4") == {}
    assert caplog.records


def test_non_finite_numbers_are_ignored():
    """NaN et infini (acceptés par json.loads) : l'entrée ou la mesure est ignorée."""
    data = json.loads(
        '{"models": {"Gemma 4 E4B (QAT)": {"quality_scores": {"reasoning_avg": NaN, '
        '"instruction_following_avg": 1.0}, "avg_tokens_per_second": 70.0}, '
        '"Granite 4.2 8B": {"quality_scores": {"reasoning_avg": 0.7, '
        '"instruction_following_avg": 0.9}, "avg_tokens_per_second": Infinity, '
        '"runs": {"tokens_per_second": {"mean": 5.05}}}, '
        '"LFM 2.5 2.6B": {"quality_scores": {"reasoning_avg": 0.9, '
        '"instruction_following_avg": 0.9}, "avg_tokens_per_second": Infinity}}}'
    )
    scores = br.parse_results(data, CATALOG)
    assert set(scores) == {"granite4.2:8b"}
    assert scores["granite4.2:8b"].speed_tps == pytest.approx(5.05)


def test_empty_result_is_not_cached(tmp_path, monkeypatch):
    """Catalogue versionné illisible au premier passage (résultat vide) : relu ensuite."""
    _write(tmp_path, "poste-22601cd4.json", {"models": {"LFM 2.5 2.6B": _entry()}})
    catalogs = iter([{}, CATALOG])
    monkeypatch.setattr(md, "load_versioned_catalog", lambda path=None: next(catalogs))
    monkeypatch.setattr(br, "_CACHE", {})

    assert br.load_machine_benchmark(tmp_path, digest="22601cd4") == {}
    assert set(br.load_machine_benchmark(tmp_path, digest="22601cd4")) == {
        "LiquidAI/lfm2.5-2.6b"
    }


def test_load_never_raises(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("disque indisponible")

    monkeypatch.setattr(br, "find_results_file", broken)
    assert br.load_machine_benchmark(tmp_path, CATALOG, "22601cd4") == {}


def test_load_uses_versioned_catalog_and_caches(tmp_path, monkeypatch):
    """Sans catalogue fourni : catalogue versionné, résultat gardé pour le fichier."""
    path = _write(tmp_path, "poste-22601cd4.json", {"models": {"LFM 2.5 2.6B": _entry()}})
    calls = []

    def catalog(path=None):
        calls.append(path)
        return CATALOG

    monkeypatch.setattr(md, "load_versioned_catalog", catalog)
    monkeypatch.setattr(br, "_CACHE", {})
    first = br.load_machine_benchmark(tmp_path, digest="22601cd4")
    assert set(first) == {"LiquidAI/lfm2.5-2.6b"}
    path.write_text("{ modifié", encoding="utf-8")
    assert br.load_machine_benchmark(tmp_path, digest="22601cd4") == first
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Résultats versionnés réels (lecture seule) : invariants seulement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", sorted(RESULTS_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_versioned_results_are_readable(path):
    """Chaque fichier versionné se lit : précisions entre 0 et 1, débits positifs."""
    digest = path.stem.rsplit("-", 1)[-1]
    scores = br.load_machine_benchmark(RESULTS_DIR, md.load_versioned_catalog(), digest)
    assert scores
    for score in scores.values():
        assert 0.0 <= score.precision <= 1.0
        assert score.speed_tps > 0
