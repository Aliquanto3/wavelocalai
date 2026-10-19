"""Lecture des résultats du banc `qb.results/1` (story 5.6, AD-22) : fichier absent, format inattendu,
jointure sur `(model, digest)`, « autre version », précision, relecture à la modification. Les
résultats viennent de la fixture `tests/v2/fixtures/` ; aucun fichier de `benchmarks/` n'est lu."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from wavelocalai.models import bench_results
from wavelocalai.models.bench_results import BenchReferences, same_digest

FIXTURE = Path(__file__).parent.parent / "fixtures" / "slm-quality-results.sample.json"


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "slm-quality-results.json"
    shutil.copy(FIXTURE, target)
    return target


def _data() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_a_missing_file_gives_unavailable_references_with_a_reason(tmp_path):
    loaded = BenchReferences(tmp_path / "absent.json").current()
    assert not loaded.available
    assert loaded.reason_code == "missing"
    assert "pas synchronisé" in loaded.reason
    assert loaded.accuracy("mid:7b", "d-mid:7b") is None
    assert loaded.find("mid:7b") is None


def test_an_unreadable_file_is_unavailable(tmp_path):
    path = tmp_path / "r.json"
    path.write_text("{pas du json", encoding="utf-8")
    loaded = BenchReferences(path).current()
    assert loaded.reason_code == "unreadable"


def test_another_schema_makes_the_references_unavailable_with_the_expected_one_named(tmp_path):
    path = tmp_path / "r.json"
    data = _data()
    data["schema"] = "qb.results/2"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = BenchReferences(path).current()
    assert loaded.reason_code == "schema"
    assert "qb.results/1" in loaded.reason


def test_a_malformed_file_is_unavailable_not_a_crash(tmp_path):
    path = tmp_path / "r.json"
    data = _data()
    data["results"] = "pas une liste"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert BenchReferences(path).current().reason_code == "format"


def test_unknown_fields_are_ignored(tmp_path):
    path = tmp_path / "r.json"
    data = _data()
    data["champ_futur"] = {"a": 1}
    data["results"][0]["champ_futur"] = True
    data["results"][0]["speed"]["autre"] = 3
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = BenchReferences(path).current()
    assert loaded.available and loaded.bench_version == "1.4.0"


def test_the_file_is_read_once_and_again_when_it_changes(tmp_path, monkeypatch):
    path = _copy(tmp_path)
    reads = []
    original = bench_results.BenchReferences._load
    monkeypatch.setattr(
        bench_results.BenchReferences, "_load", lambda self: reads.append(1) or original(self)
    )
    refs = BenchReferences(path)
    first = refs.current()
    assert refs.current() is first and refs.current() is first
    assert len(reads) == 1  # lu une fois
    data = _data()
    data["bench_version"] = "1.5.0"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")  # taille différente
    assert refs.current().bench_version == "1.5.0"
    assert len(reads) == 2  # relu à sa modification
    path.unlink()
    assert refs.current().reason_code == "missing"  # supprimé après lecture


def test_results_join_models_on_tag_and_digest(tmp_path):
    loaded = BenchReferences(_copy(tmp_path)).current()
    match = loaded.find("mid:7b", "d-mid:7b")
    assert match is not None and match.version == "exact"
    assert {r.machine for r in match.results} == {"pc-pro", "portable", "station"}
    assert all(r.model == "mid:7b" and r.digest == "d-mid:7b" for r in match.results)


def test_an_installed_model_with_another_digest_matches_by_tag_as_another_version(tmp_path):
    loaded = BenchReferences(_copy(tmp_path)).current()
    match = loaded.find("other:4b", "d-other:4b-installee")
    assert match is not None and match.version == "other_version"
    assert [r.machine for r in match.results] == ["portable"]  # mesures de l'autre version


def test_a_model_not_installed_has_no_digest_to_compare(tmp_path):
    loaded = BenchReferences(_copy(tmp_path)).current()
    match = loaded.find("grand:14b")
    assert match is not None and match.version == "unknown" and match.results
    assert loaded.find("inconnu:1b", "x") is None


def test_the_latest_variant_of_a_tag_is_the_same_model(tmp_path):
    loaded = BenchReferences(_copy(tmp_path)).current()
    assert loaded.find("mid:7b:latest", "d-mid:7b") is not None  # `:latest` ignoré à la jointure


def test_digests_match_with_a_prefix_or_the_sha256_marker():
    full = "a" * 64
    assert same_digest(f"sha256:{full}", full.upper())
    assert same_digest(full[:12], full)  # l'identifiant court d'Ollama
    assert not same_digest(full[:8], full)  # trop court : aucune supposition
    assert not same_digest(None, full)
    assert not same_digest("a" * 12, "b" * 64)


def test_accuracy_is_the_median_of_the_global_scores_of_the_same_weights(tmp_path):
    loaded = BenchReferences(_copy(tmp_path)).current()
    # `think_off`, complets : 0,72 / 0,71 / 0,73 ; la piste `think_on` (0,60) ne compte pas.
    assert loaded.accuracy("mid:7b", "d-mid:7b") == 0.72


def test_accuracy_is_never_borrowed_from_another_version_or_missing_data(tmp_path):
    loaded = BenchReferences(_copy(tmp_path)).current()
    assert loaded.accuracy("other:4b", "d-other:4b-installee") is None  # autres poids : pas de score
    assert loaded.accuracy("small:1b", "d-small:1b") is None  # score `null` : jamais 0
    assert loaded.accuracy("mid:7b", None) is None
    assert loaded.accuracy("inconnu:1b", "x") is None


def test_the_preferred_result_of_a_machine_is_think_off_then_complete_then_recent(tmp_path):
    data = _data()
    extra = dict(data["results"][0], track="think_off", complete=False, campaign="c0")
    extra["speed"] = dict(extra["speed"], decode_tok_s=99.0)
    newer = dict(data["results"][0], track="think_off", complete=True, campaign="c2")
    newer["speed"] = dict(newer["speed"], decode_tok_s=7.7)
    data["campaigns"] += [{"id": "c0"}, {"id": "c2"}]
    data["results"] += [extra, newer]
    path = tmp_path / "r.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = BenchReferences(path).current()
    match = loaded.find("mid:7b", "d-mid:7b")
    best = loaded.best_result(match, "pc-pro")
    assert best.track == "think_off" and best.complete and best.campaign == "c2"
    assert best.speed.decode_tok_s == 7.7
    assert loaded.best_result(match, "inconnu") is None


def test_the_pc_pro_is_a_16_gb_machine_without_gpu(tmp_path):
    loaded = BenchReferences(_copy(tmp_path)).current()
    by_id = {m.id: m for m in loaded.machines}
    assert by_id["pc-pro"].is_pc_pro
    assert not by_id["portable"].is_pc_pro  # 16 Go mais avec une carte graphique
    assert not by_id["station"].is_pc_pro
