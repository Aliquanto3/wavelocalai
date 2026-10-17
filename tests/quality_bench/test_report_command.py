"""Commande ``report --campaign <c>`` (AD-6, AD-17) sur des JSONL synthétiques : matrice
entrées-sorties, deux passes identiques octet pour octet, aucun texte ni identifiant de
question dans les exports."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.canonical import pretty_bytes, sha256_bytes, sha256_hex
from scripts.quality_bench.common.jsonl import read_jsonl
from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.report.export import model_file_name

from .factories import model_resolved
from .report_factories import (
    CAMPAIGN,
    JUDGE_ID,
    PROFILES,
    SECRET_OUTPUT,
    SECRET_QUESTION,
    aa_reference,
    build_set,
    grade_for,
    make_campaign,
    write_aa_reference,
)
from .test_exports import export_problems

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    from scripts.quality_bench.common.logs import setup_logging

    setup_logging("test", None)


def _run(*extra):
    from scripts.quality_bench.__main__ import main

    return main(["report", "--campaign", CAMPAIGN, *extra])


def _export_dir():
    return paths.campaign_exports_dir(CAMPAIGN)


def _summary():
    return json.loads((_export_dir() / "summary.json").read_text(encoding="utf-8"))


def _scope(summary, track, usage):
    block = next(b for b in summary["tracks"] if b["track"] == track)
    return next(s for s in block["scopes"] if s["usage"] == usage)


def _entry(scope, model):
    return next(e for e in scope["models"] if e["model"] == model)


def _log():
    return paths.log_path(CAMPAIGN, "report").read_text(encoding="utf-8")


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    return make_campaign(
        tmp_path,
        monkeypatch,
        statuses={
            (1, "think_off", "reasoning/var-math/0005", 0): "error",
            (2, "think_off", "reasoning/var-math/0007", 0): "context_exceeded",  # limite du banc
            # Limite du modèle : échec compté (score 0), unité définie.
            (1, "think_off", "reasoning/var-math/0009", 0): "context_exceeded_model",
            (2, "think_off", "rag/piaf/0003", 0): "truncated",
            (2, "think_off", "instructions/ifbench/0004", 0): "truncated",
            (0, "think_off", "rag/piaf/0002", 0): "non_compliant",
            # Une variante VAR-MATH ratée sur trois : l'unité est ratée.
            (0, "think_off", "reasoning/var-math/0000-v1", 0): "non_compliant",
        },
    )


# -- Campagne complète ----------------------------------------------------------------------


def test_complete_campaign_writes_validated_exports(campaign):
    assert _run() == 0
    root = paths.exports_root()
    assert export_problems(root) == []
    tree = _tree(_export_dir())
    assert set(tree) == {
        "summary.json",
        "manifest.json",
        "report.md",
        *(f"scores/{model_file_name(m)}" for m in campaign.models),
        *(
            f"charts/{track}-{usage}.svg"
            for track, usages in (
                ("think_off", ("global", "reasoning", "instructions", "rag", "writing")),
                ("think_on", ("global", "reasoning", "writing")),
            )
            for usage in usages
        ),
    }
    assert "scores/model-0_4b.jsonl" in tree  # « : » remplacé par « _ »
    summary = _summary()
    validate(summary)
    assert summary["partial"] is False
    assert summary["completeness"]["expected"] == len(campaign.generation)
    assert summary["completeness"]["retained"] == len(campaign.generation)
    assert summary["judgment_manifest"] == campaign.judgment_hash
    # McNemar par usage binaire, test z en rédaction et en global (piste qui la contient).
    for usage in ("reasoning", "instructions", "rag"):
        scope = _scope(summary, "think_off", usage)
        assert scope["method"] == "mcnemar"
        assert all(
            c["b"] is not None and c["bootstrap_ci_low"] is None for c in scope["comparisons"]
        )
    for usage in ("writing", None):
        scope = _scope(summary, "think_off", usage)
        assert scope["method"] == "paired_z"
        assert all(c["b"] is None for c in scope["comparisons"])
        assert all(c["bootstrap_ci_low"] is not None for c in scope["comparisons"])
    # Le troisième modèle ne suit que think_off.
    assert [e["model"] for e in _scope(summary, "think_on", None)["models"]] == campaign.models[:2]
    # Manifeste copié tel quel ; scores triés et validés.
    assert json.loads(tree["manifest.json"]) == campaign.manifest
    rows = read_jsonl(_export_dir() / "scores" / model_file_name(campaign.models[0]))
    assert len(rows) == sum(1 for g in campaign.generation if g["model"] == campaign.models[0])
    assert rows == sorted(rows, key=lambda r: (r["track"], r["question_hash"], r["seed"]))
    log = _log()
    assert "Rapport écrit" in log


def test_exports_hold_no_question_text_nor_id(campaign):
    assert _run() == 0
    tree = _tree(_export_dir())
    for name, data in tree.items():
        text = data.decode("utf-8")
        assert SECRET_QUESTION not in text, name
        assert SECRET_OUTPUT not in text, name
        assert "question_id" not in text, name
        for qid in campaign.questions:
            assert qid not in text, (name, qid)
    log = _log()
    assert SECRET_QUESTION not in log and SECRET_OUTPUT not in log


def test_report_never_reads_judgment_lines(campaign):
    path = paths.judgment_path(CAMPAIGN, JUDGE_ID)
    path.write_text("ceci n'est pas du JSON\n", encoding="utf-8")
    assert _run() == 0


def test_two_cli_passes_are_byte_identical(campaign):
    """Deux processus distincts (graine de hachage différente) : arborescences identiques."""
    script = textwrap.dedent(
        f"""
        import sys
        from pathlib import Path
        from scripts.quality_bench.common import paths
        paths.campaign_config_path = lambda c: Path({str(campaign.config_dir)!r}) / f"{{c}}.yaml"
        from scripts.quality_bench.__main__ import main
        sys.exit(main(["report", "--campaign", {CAMPAIGN!r}]))
        """
    )
    trees = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, timeout=300
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")[-2000:]
        trees.append(_tree(_export_dir()))
    assert trees[0] == trees[1]
    assert not any(
        b"created_at" in data for name, data in trees[0].items() if name != "manifest.json"
    )
    leftovers = [p.name for p in paths.exports_root().iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_failed_swap_keeps_the_previous_export(campaign, monkeypatch):
    """Échec du renommage du dossier assemblé (fichier verrouillé sous Windows) : l'ancien
    export est remis en place, intact, sans dossier ``.tmp`` ni ``.old`` laissé."""
    from scripts.quality_bench.report import export

    assert _run() == 0
    before = _tree(_export_dir())
    staging = _export_dir().with_name(f".{_export_dir().name}.tmp")
    real_replace = os.replace

    def replace(src, dst):
        if Path(src) == staging:
            raise PermissionError("fichier verrouillé")
        return real_replace(src, dst)

    monkeypatch.setattr(export.os, "replace", replace)
    with pytest.raises(PermissionError):
        export.write_export_dir(CAMPAIGN, {"summary.json": b"{}"})
    assert _tree(_export_dir()) == before
    leftovers = {p.name for p in _export_dir().parent.iterdir() if p.name.startswith(".")}
    assert leftovers == set()


def test_rewrite_replaces_the_whole_directory(campaign):
    stale = _export_dir() / "charts" / "ancien.svg"
    stale.parent.mkdir(parents=True)
    stale.write_text("<svg/>", encoding="utf-8")
    assert _run() == 0
    assert not stale.exists()


# -- Unités, erreurs du banc, troncature -----------------------------------------------------


def _expected_unit_means(campaign, model, track, usage):
    by_unit: dict[str, list[float | None]] = {}
    for g in campaign.generation:
        if g["model"] != model or g["track"] != track or g["usage"] != usage:
            continue
        by_unit.setdefault(g["unit"], []).append(campaign.scores[g["key"]])
    values = [min(v) for v in by_unit.values() if None not in v]
    return sum(values) / len(values), len(values), len(by_unit) - len(values)


def test_unit_is_the_minimum_of_its_variants(campaign):
    first = campaign.models[0]
    variants = [
        campaign.scores[f"{CAMPAIGN}|{first}|think_off|reasoning/var-math/0000{suffix}|0"]
        for suffix in ("", "-v1", "-v2")
    ]
    assert variants == [1.0, 0.0, 1.0]  # unité mixte : le minimum la rend ratée
    assert _run() == 0
    summary = _summary()
    scope = _scope(summary, "think_off", "reasoning")
    common = _common_units(campaign, "think_off", "reasoning")
    for model in campaign.models:
        mean, n, excluded = _expected_unit_means(campaign, model, "think_off", "reasoning")
        entry = _entry(scope, model)
        # Toutes les unités définies du modèle, à côté des unités communes.
        assert entry["mean_all"] == pytest.approx(mean)
        assert (entry["n_all"], entry["excluded"]) == (n, excluded)
        units = _unit_scores(campaign, model, "think_off", "reasoning")
        assert entry["n"] == len(common)
        assert entry["mean"] == pytest.approx(sum(units[u] for u in common) / len(common))
    # 24 unités pour 26 questions : l'unité VAR-MATH réunit trois variantes.
    assert scope["units"] == 24 and scope["common_units"] == len(common) == 22


def test_bench_error_nulls_the_unit_and_is_counted(campaign):
    assert _run() == 0
    summary = _summary()
    scope = _scope(summary, "think_off", "reasoning")
    first, second, third = campaign.models
    assert _entry(scope, first)["excluded"] == 0
    assert _entry(scope, second)["excluded"] == 1  # error (limite du modèle : unité définie à 0)
    assert _entry(scope, third)["excluded"] == 1  # context_exceeded du banc
    # Comptes publiés séparément par cause.
    counts = {
        model: (
            _entry(scope, model)["context_exceeded_model"],
            _entry(scope, model)["context_exceeded_bench"],
        )
        for model in campaign.models
    }
    assert counts == {first: (0, 0), second: (1, 0), third: (0, 1)}
    # Comparaisons sur les unités communes à tous les modèles : 24 − error (second) − banc (third).
    assert scope["common_units"] == 22
    assert {p["n"] for p in scope["matrix"]} == {22}
    assert {c["n"] for c in scope["comparisons"]} == {22}
    # Limite du modèle : l'unité vaut 0 pour ce modèle (et non nulle).
    assert (
        _unit_scores(campaign, second, "think_off", "reasoning")["reasoning/var-math/0009"] == 0.0
    )


def test_truncation_rate_is_published_apart(campaign):
    assert _run() == 0
    summary = _summary()
    scope = _scope(summary, "think_off", "rag")
    entry = _entry(scope, campaign.models[2])
    assert (entry["truncated"], entry["graded"]) == (1, 18)
    assert entry["truncation_rate"] == pytest.approx(1 / 18)
    global_entry = _entry(_scope(summary, "think_off", None), campaign.models[2])
    assert global_entry["truncated"] == 2


def test_model_context_limit_rows_are_out_of_the_truncation_denominator(campaign):
    """Même nombre de lignes de raisonnement par modèle : le modèle 0 (un non_compliant, noté)
    les a toutes notées ; le modèle 1 en perd deux, son erreur du banc (sans score) et sa
    limite du modèle (score 0, mais hors du dénominateur du taux de troncature)."""
    assert _run() == 0
    scope = _scope(_summary(), "think_off", "reasoning")
    first, second = _entry(scope, campaign.models[0]), _entry(scope, campaign.models[1])
    assert second["context_exceeded_model"] == 1
    assert second["graded"] == first["graded"] - 2


def test_continuous_metrics_and_comparisons(campaign):
    assert _run() == 0
    summary = _summary()
    rag = _scope(summary, "think_off", "rag")["continuous"]
    assert rag["metric"] == "f1"
    # NIAH sans f1 : unités nulles pour tous ; non_compliant avec f1 = 0 ; tronquée : 0.
    for entry in rag["models"]:
        assert entry["n"] == 16 and entry["excluded"] == 2
    assert rag["leader"] is not None
    assert all(
        c["bootstrap_ci_low"] <= c["diff"] <= c["bootstrap_ci_high"] for c in rag["comparisons"]
    )
    instructions = _scope(summary, "think_off", "instructions")["continuous"]
    assert instructions["metric"] == "instructions_followed"
    assert _scope(summary, "think_off", "writing")["continuous"] is None
    assert _scope(summary, "think_off", "reasoning")["continuous"] is None


def test_leader_comparisons_use_holm_and_groups(campaign):
    assert _run() == 0
    scope = _scope(_summary(), "think_off", None)
    leader = scope["leader"]
    assert leader == campaign.models[0]
    assert [c["model"] for c in scope["comparisons"]] == campaign.models[1:]
    for comparison in scope["comparisons"]:
        assert comparison["p_holm"] >= comparison["p"]
        assert comparison["ci_low"] <= comparison["diff"] <= comparison["ci_high"]
    assert _entry(scope, leader)["group"] == 1 and _entry(scope, leader)["rank"] == 1
    assert len(scope["matrix"]) == 3
    block = next(b for b in _summary()["tracks"] if b["track"] == "think_off")
    assert block["k_bonferroni"]["usages"] == 4
    assert block["k_bonferroni"]["alpha_per_test"] == pytest.approx(0.0125)
    assert [m["model"] for m in block["k_bonferroni"]["models"]] == campaign.models[1:]
    # Gains recalculés depuis les périmètres d'usage du même résumé : p < α/m et différence
    # positive du meneur global.
    usage_scopes = [s for s in block["scopes"] if s["usage"] is not None]
    threshold = 0.05 / len(usage_scopes)
    for entry in block["k_bonferroni"]["models"]:
        wins = 0
        for usage_scope in usage_scopes:
            pair = next(
                p for p in usage_scope["matrix"] if {p["a"], p["b"]} == {leader, entry["model"]}
            )
            diff = pair["diff"] if pair["a"] == leader else -pair["diff"]
            wins += pair["p"] is not None and pair["p"] < threshold and diff > 0
        assert entry["wins"] == wins
        assert entry["tests"] == len(usage_scopes)


@pytest.mark.parametrize(
    "status, limit, expected",
    [
        ("context_exceeded", "model", 0.0),  # échec du modèle sans métrique : 0
        ("context_exceeded", "bench", None),  # erreur du banc : unité nulle
        ("truncated", None, 0.0),
        ("error", None, None),
    ],
)
def test_continuous_metric_of_a_context_exceeded_row(status, limit, expected):
    from scripts.quality_bench.report.campaign import _metric_value
    from scripts.quality_bench.report.inputs import Row

    row = Row("k", "m", "d", "think_off", "q", 0, status, None, None, {}, limit)
    assert _metric_value(row, "f1") == expected


def test_scores_export_carries_the_context_limit(campaign):
    assert _run() == 0
    first, second, third = campaign.models
    rows = {
        name: {
            r["question_hash"]: r
            for r in read_jsonl(_export_dir() / "scores" / model_file_name(tag))
            if r["status"] == "context_exceeded"
        }
        for name, tag in (("model", second), ("bench", third))
    }
    by_model = campaign.questions["reasoning/var-math/0009"]["question_hash"]
    by_bench = campaign.questions["reasoning/var-math/0007"]["question_hash"]
    row = rows["model"][by_model]
    assert (row["context_limit"], row["score"], row["success"]) == ("model", 0.0, False)
    row = rows["bench"][by_bench]
    assert (row["context_limit"], row["score"], row["success"]) == ("bench", None, None)
    assert len(rows["model"]) == len(rows["bench"]) == 1
    for path in (_export_dir() / "scores").glob("*.jsonl"):
        assert all(
            ("context_limit" in r) == (r["status"] == "context_exceeded") for r in read_jsonl(path)
        )


def _synthetic_unit_scores(tag, profile, track="think_off"):
    """Unité → score d'unité (minimum des questions) du jeu réduit, sans passer par le rapport."""
    questions, _ = build_set(small=True)
    by_unit: dict[str, list[float]] = {}
    for q in questions.values():
        by_unit.setdefault(q["unit"], []).append(grade_for(q, tag, profile, track, 0, "ok")[0])
    return {unit: min(values) for unit, values in by_unit.items()}


def test_leader_groups_and_spearman_use_common_units(tmp_path, monkeypatch):
    """Un modèle sans score (limite du banc) sur les unités que le meneur réussit et que le
    deuxième rate retire ces unités à tous : le meneur sur unités communes change, la moyenne sur
    toutes les unités définies reste publiée avec son effectif. Valeurs calculées à la main."""
    tags = [model_resolved(i)["tag"] for i in range(3)]
    units = [_synthetic_unit_scores(tags[i], PROFILES[i]) for i in range(3)]
    won_by_a_only = sorted(u for u in units[0] if units[0][u] == 1.0 and units[1][u] == 0.0)
    # Jeu synthétique figé : 12 unités, A en réussit 10, B 9 ; A seul 3 fois, B seul 2 fois.
    assert (sum(units[0].values()), sum(units[1].values())) == (10.0, 9.0)
    assert len(won_by_a_only) == 3
    statuses = {(2, "think_off", unit, 0): "context_exceeded" for unit in won_by_a_only}
    make_campaign(tmp_path, monkeypatch, small=True, statuses=statuses)
    common = [u for u in units[0] if u not in won_by_a_only]
    assert len(common) == 9
    # A : 7 réussites sur les 9 unités communes ; B : 9 sur 9 ; C : ses réussites hors des 3 unités.
    means = [sum(units[i][u] for u in common) / 9 for i in range(3)]
    assert means[:2] == [7 / 9, 1.0] and means[2] < means[0]
    all_means = [10 / 12, 9 / 12, (sum(units[2][u] for u in common)) / 9]  # A, B (12), C (9)
    assert all_means[0] > all_means[1]  # sur toutes les unités définies, A mènerait

    index = {tags[1]: 30.0, tags[0]: 20.0, tags[2]: 10.0}  # ordre des unités communes : B, A, C
    entries = [
        {"tag": tag, "index": value, "status": "measured", "variant": "non_reasoning"}
        for tag, value in index.items()
    ]
    write_aa_reference(aa_reference("2026-10-01", entries))
    # Couverture de C : 9 / 12 = 0,75 ; seuil abaissé à 0,7 pour la classer.
    assert _run("--common-min-coverage", "0.7") == 0
    summary = _summary()
    assert summary["method"]["common_min_coverage"] == 0.7
    scope = _scope(summary, "think_off", None)
    assert (scope["units"], scope["common_units"]) == (12, 9)
    assert all(e["eligible"] for e in scope["models"])
    assert _entry(scope, tags[2])["coverage"] == pytest.approx(0.75)
    assert scope["leader"] == tags[1]
    for i, tag in enumerate(tags):
        entry = _entry(scope, tag)
        assert entry["n"] == 9 and entry["mean"] == pytest.approx(means[i])
    assert (_entry(scope, tags[0])["mean_all"], _entry(scope, tags[0])["n_all"]) == (
        pytest.approx(10 / 12),
        12,
    )
    assert (_entry(scope, tags[1])["mean_all"], _entry(scope, tags[1])["n_all"]) == (
        pytest.approx(9 / 12),
        12,
    )
    assert (_entry(scope, tags[2])["mean_all"], _entry(scope, tags[2])["n_all"]) == (
        pytest.approx(all_means[2]),
        9,
    )
    assert _entry(scope, tags[2])["context_exceeded_bench"] == 3
    assert [c["model"] for c in scope["comparisons"]] == [tags[0], tags[2]]
    assert {c["n"] for c in scope["comparisons"]} == {9}
    # Rang approché et groupes : le meneur de l'ordre commun est en tête, rang 1, groupe 1.
    leader_entry = _entry(scope, tags[1])
    assert leader_entry["rank"] == 1 and leader_entry["group"] == 1
    # Spearman : ordre des moyennes sur unités communes (B > A > C), ρ = 1 ; sur les moyennes
    # de toutes les unités définies (A > B > C), il aurait valu 0,5.
    spearman = next(b for b in summary["tracks"] if b["track"] == "think_off")["spearman"]
    assert spearman["n"] == 3 and math.isclose(spearman["rho"], 1.0)


def test_model_under_the_coverage_threshold_is_published_out_of_ranking(tmp_path, monkeypatch):
    """Même campagne, seuil par défaut (0,9) : C (couverture 9 / 12 = 0,75) est hors classement ;
    A et B sont classés sur leurs 12 unités communes. Valeurs calculées à la main : A 10 / 12,
    B 9 / 12, A mène ; C garde sa moyenne sur ses 9 unités définies, sans rang ni groupe."""
    tags = [model_resolved(i)["tag"] for i in range(3)]
    units = [_synthetic_unit_scores(tags[i], PROFILES[i]) for i in range(3)]
    won_by_a_only = sorted(u for u in units[0] if units[0][u] == 1.0 and units[1][u] == 0.0)
    statuses = {(2, "think_off", unit, 0): "context_exceeded" for unit in won_by_a_only}
    make_campaign(tmp_path, monkeypatch, small=True, statuses=statuses)
    entries = [
        {"tag": tag, "index": value, "status": "measured", "variant": "non_reasoning"}
        for tag, value in {tags[0]: 30.0, tags[1]: 20.0, tags[2]: 10.0}.items()
    ]
    write_aa_reference(aa_reference("2026-10-01", entries))
    assert _run() == 0
    summary = _summary()
    assert summary["method"]["common_min_coverage"] == 0.9
    scope = _scope(summary, "think_off", None)
    assert (scope["units"], scope["common_units"]) == (12, 12)
    assert scope["leader"] == tags[0]
    a, b, c = (_entry(scope, tag) for tag in tags)
    assert (a["mean"], a["n"], a["eligible"]) == (pytest.approx(10 / 12), 12, True)
    assert (b["mean"], b["n"], b["eligible"]) == (pytest.approx(9 / 12), 12, True)
    common_c = [u for u in units[2] if u not in won_by_a_only]
    assert (c["mean"], c["n"], c["rank"], c["group"], c["eligible"]) == (None, 0, None, None, False)
    assert c["mean_all"] == pytest.approx(sum(units[2][u] for u in common_c) / 9)
    assert (c["n_all"], c["coverage"], c["excluded"]) == (9, pytest.approx(0.75), 3)
    assert [cmp["model"] for cmp in scope["comparisons"]] == [tags[1]]
    assert {(m["a"], m["b"]) for m in scope["matrix"]} == {(tags[0], tags[1])}
    spearman = next(t for t in summary["tracks"] if t["track"] == "think_off")["spearman"]
    assert spearman["models"] == [tags[0], tags[1]]
    k_models = next(t for t in summary["tracks"] if t["track"] == "think_off")["k_bonferroni"]
    assert [m["model"] for m in k_models["models"]] == [tags[1]]
    # Avertissement nominatif : journal et rapport.
    assert f"{tags[2]} hors classement, couverture 75.0 %" in _log()
    report = (_export_dir() / "report.md").read_text(encoding="utf-8")
    assert "Avertissement : hors classement" in report and f"`{tags[2]}`" in report


def _unit_scores(campaign, model, track, usage):
    """Unité → score (minimum de ses questions, ``None`` si l'une est sans score)."""
    by_unit: dict[str, list[float | None]] = {}
    for g in campaign.generation:
        if g["model"] == model and g["track"] == track and g["usage"] == usage:
            by_unit.setdefault(g["unit"], []).append(campaign.scores[g["key"]])
    return {unit: None if None in v else min(v) for unit, v in by_unit.items()}


def _common_units(campaign, track, usage):
    """Unités définies pour tous les modèles de la piste (réponse calculée sans le rapport)."""
    models = [
        m
        for m in campaign.models
        if any(g["model"] == m and g["track"] == track for g in campaign.generation)
    ]
    scores = [_unit_scores(campaign, m, track, usage) for m in models]
    return sorted(u for u in scores[0] if all(s.get(u) is not None for s in scores))


def test_binary_scope_statistics_match_the_reference_functions(campaign):
    """Câblage de ``scope_stats`` : Wilson à α et à α/m, table de McNemar orientée (meneur
    seul, autre seul), Holm sur les comparaisons au meneur, BH sur la matrice."""
    from scripts.quality_bench.stats.mcnemar import mcnemar_exact
    from scripts.quality_bench.stats.multiple import benjamini_hochberg, holm
    from scripts.quality_bench.stats.wilson import wilson_interval

    assert _run() == 0
    scope = _scope(_summary(), "think_off", "reasoning")
    assert scope["method"] == "mcnemar"
    models = campaign.models
    units = {model: _unit_scores(campaign, model, "think_off", "reasoning") for model in models}
    common_ids = _common_units(campaign, "think_off", "reasoning")
    units = {model: {u: scores[u] for u in common_ids} for model, scores in units.items()}
    for model in models:
        values = list(units[model].values())
        entry = _entry(scope, model)
        ci = wilson_interval(sum(values), len(values), 0.05)
        sim = wilson_interval(sum(values), len(values), 0.05 / len(models))
        assert (entry["ci_low"], entry["ci_high"]) == pytest.approx(ci)
        assert (entry["sim_ci_low"], entry["sim_ci_high"]) == pytest.approx(sim)

    def table(a, b):
        common = [u for u in units[a] if units[a][u] is not None and units[b].get(u) is not None]
        only_a = sum(1 for u in common if units[a][u] >= 0.5 > units[b][u])
        only_b = sum(1 for u in common if units[b][u] >= 0.5 > units[a][u])
        return only_a, only_b

    leader = scope["leader"]
    raw = []
    for comparison in scope["comparisons"]:
        only_a, only_b = table(leader, comparison["model"])
        assert (comparison["b"], comparison["c"]) == (only_a, only_b)
        raw.append(mcnemar_exact(only_a, only_b))
        assert comparison["p"] == pytest.approx(raw[-1])
    assert any(c["b"] != c["c"] for c in scope["comparisons"])  # orientation observable
    assert [c["p_holm"] for c in scope["comparisons"]] == pytest.approx(holm(raw)[1])
    matrix_raw = [mcnemar_exact(*table(row["a"], row["b"])) for row in scope["matrix"]]
    assert [row["p"] for row in scope["matrix"]] == pytest.approx(matrix_raw)
    assert [row["p_bh"] for row in scope["matrix"]] == pytest.approx(
        benjamini_hochberg(matrix_raw)[1]
    )


def test_global_scope_without_writing_is_binary(tmp_path, monkeypatch):
    """k = 1 et piste sans rédaction : le score global est binaire (McNemar, table publiée)."""
    make_campaign(tmp_path, monkeypatch, small=True, think_off_only=())
    assert _run() == 0
    scope = _scope(_summary(), "think_off", None)
    assert scope["method"] == "mcnemar"
    assert all(c["b"] is not None and c["c"] is not None for c in scope["comparisons"])


def test_k2_averages_seeds_and_uses_the_z_test(tmp_path, monkeypatch):
    campaign = make_campaign(tmp_path, monkeypatch, k=2, small=True, think_off_only=())
    assert _run() == 0
    summary = _summary()
    assert summary["k"] == 2
    for block in summary["tracks"]:
        for scope in block["scopes"]:
            assert scope["method"] == "paired_z"
            assert all(c["b"] is None and c["c"] is None for c in scope["comparisons"])
    scope = _scope(summary, "think_off", "reasoning")
    for model in campaign.models:
        by_unit: dict[str, dict[int, list[float]]] = {}
        for g in campaign.generation:
            if g["model"] == model and g["track"] == "think_off":
                by_unit.setdefault(g["unit"], {}).setdefault(g["seed"], []).append(
                    campaign.scores[g["key"]]
                )
        means = [sum(min(v) for v in seeds.values()) / 2 for seeds in by_unit.values()]
        assert _entry(scope, model)["mean"] == pytest.approx(sum(means) / len(means))


# -- Complétude et --partial -----------------------------------------------------------------


def _assert_refused(code, *extra):
    assert _run(*extra) == code
    assert not _export_dir().exists()


def test_missing_generation_key_is_refused_then_partial(campaign):
    campaign.write_generation(campaign.generation[1:])
    campaign.write_grading(
        [g for g in campaign.grading if g["key"] != campaign.generation[0]["key"]]
    )
    _assert_refused(1)
    log = _log()
    assert "clé absente de generation.jsonl" in log and "1 manquantes" in log
    assert _run("--partial") == 0
    summary = _summary()
    assert summary["partial"] is True
    assert summary["completeness"]["generation_missing"] == 1
    assert summary["completeness"]["retained"] == len(campaign.generation) - 1
    assert export_problems(paths.exports_root()) == []
    assert "Rapport partiel" in (_export_dir() / "report.md").read_text(encoding="utf-8")


def test_missing_grading_key_is_refused_then_partial(campaign):
    campaign.write_grading(campaign.grading[1:])
    _assert_refused(1)
    assert "clé absente de grading.jsonl" in _log()
    assert _run("--partial") == 0
    assert _summary()["completeness"]["grading_missing"] == 1


def test_awaiting_judgment_is_refused_then_partial(campaign):
    lines = [dict(g) for g in campaign.grading]
    index = next(i for i, g in enumerate(lines) if g["grader"] == "judge_criteria@1")
    lines[index].update(status="awaiting_judgment", score=None, judgment_manifest=None, metrics={})
    validate(lines[index])
    campaign.write_grading(lines)
    _assert_refused(1)
    assert "awaiting_judgment" in _log()
    assert _run("--partial") == 0
    summary = _summary()
    assert summary["completeness"]["awaiting_judgment"] == 1
    # Écartée et comptée : ni retenue, ni publiée dans les scores.
    assert summary["completeness"]["retained"] == summary["completeness"]["expected"] - 1
    for path in (_export_dir() / "scores").glob("*.jsonl"):
        assert all(row["status"] != "awaiting_judgment" for row in read_jsonl(path))
    writing = _scope(summary, lines[index]["key"].split("|")[2], "writing")
    model = lines[index]["key"].split("|")[1]
    assert _entry(writing, model)["excluded"] == 1


def test_generation_line_of_another_manifest(campaign):
    lines = [dict(g) for g in campaign.generation]
    lines[3]["manifest"] = "f" * 64
    campaign.write_generation(lines)
    _assert_refused(1)
    assert "generation.jsonl ligne 4 : produite par un autre manifeste" in _log()
    assert _run("--partial") == 0
    assert _summary()["completeness"]["generation_discordant"] == 1


def test_grading_with_another_judgment_manifest(campaign):
    lines = [dict(g) for g in campaign.grading]
    index = next(i for i, g in enumerate(lines) if g["judgment_manifest"] is not None)
    lines[index]["judgment_manifest"] = "e" * 64
    campaign.write_grading(lines)
    _assert_refused(1)
    assert "judgment_manifest différent du juge retenu" in _log()
    assert _run("--partial") == 0
    assert _summary()["completeness"]["grading_discordant"] == 1


def test_grading_with_another_generation_manifest(campaign):
    lines = [dict(g) for g in campaign.grading]
    lines[0]["generation_manifest"] = "d" * 64
    campaign.write_grading(lines)
    _assert_refused(1)
    assert _run("--partial") == 0
    assert _summary()["completeness"]["grading_discordant"] == 1


def test_modified_configuration(campaign):
    path = campaign.config_dir / f"{CAMPAIGN}.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("k: 1}", "k: 1}\n  max_attempts: 4"),
        encoding="utf-8",
    )
    _assert_refused(1)
    assert "configuration modifiée" in _log()
    assert _run("--partial") == 0
    assert _summary()["completeness"]["config_discordant"] is True


# -- Entrées incohérentes et configuration ---------------------------------------------------


def test_missing_manifest_is_refused_even_partial(campaign):
    paths.generation_manifest_path(CAMPAIGN).unlink()
    _assert_refused(1, "--partial")


def test_set_hash_mismatch_is_refused_even_partial(campaign):
    tracks = dict(campaign.tracks)
    tracks["think_on"] = tracks["think_on"][1:]
    paths.set_tracks_path("small-report").write_text(json.dumps(tracks), encoding="utf-8")
    _assert_refused(1, "--partial")
    assert "empreinte du jeu" in _log()


@pytest.mark.parametrize("target", ["manifest", "generation", "grading"])
def test_campaign_before_context_limit_is_refused_with_code_2(campaign, target):
    """Campagne écrite avant context_limit (pilot-20261012) : refus clair, code 2."""
    if target == "manifest":
        manifest_path = paths.generation_manifest_path(CAMPAIGN)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for model in manifest["blocking"]["models_resolved"]:
            del model["context_length"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        lines = [dict(g) for g in getattr(campaign, target)]
        lines[0]["status"] = "context_exceeded"
        lines[0].pop("context_limit", None)
        getattr(campaign, f"write_{target}")(lines)
    _assert_refused(2)
    assert "campagne antérieure à context_limit" in _log()


def test_line_out_of_schema_is_refused_even_partial(campaign):
    lines = [dict(g) for g in campaign.grading]
    lines[0]["extra"] = 1
    campaign.write_grading(lines)
    _assert_refused(1, "--partial")
    assert "hors schéma" in _log()


def test_unknown_grading_key_is_refused_even_partial(campaign):
    campaign.write_generation(campaign.generation[1:])
    _assert_refused(1, "--partial")
    assert "inconnue de generation.jsonl" in _log()


def test_question_missing_from_set_is_refused(campaign):
    lines = [dict(g) for g in campaign.generation]
    lines[0]["question_id"] = "reasoning/var-math/9999"
    campaign.write_generation(lines)
    _assert_refused(1, "--partial")


def test_missing_configuration_exits_2(campaign):
    (campaign.config_dir / f"{CAMPAIGN}.yaml").unlink()
    _assert_refused(2)


def test_invalid_configuration_exits_2(campaign):
    (campaign.config_dir / f"{CAMPAIGN}.yaml").write_text("set: [\n", encoding="utf-8")
    _assert_refused(2)


@pytest.mark.parametrize("name", ["references", "References", "SETS"])
def test_reserved_campaign_name_is_refused(campaign, name):
    """La garde des dossiers réservés est atteinte (configuration présente) : code 1, et le
    dossier réservé reste intact."""
    from scripts.quality_bench.__main__ import main

    source = campaign.config_dir / f"{CAMPAIGN}.yaml"
    (campaign.config_dir / f"{name}.yaml").write_text(
        source.read_text(encoding="utf-8"), encoding="utf-8"
    )
    reserved = paths.exports_root() / name.lower()
    reserved.mkdir(parents=True)
    (reserved / "témoin.txt").write_text("x", encoding="utf-8")
    assert main(["report", "--campaign", name]) == 1
    assert (reserved / "témoin.txt").exists()
    assert "dossier réservé" in paths.log_path(name, "report").read_text(encoding="utf-8")


def test_invalid_aa_date_exits_2(campaign):
    with pytest.raises(SystemExit) as excinfo:
        _run("--aa-date", "2026-1-1")
    assert excinfo.value.code == 2


# -- Références AA et Spearman ---------------------------------------------------------------


def _entries(campaign, indices, variant="non_reasoning", status="measured"):
    return [
        {"tag": tag, "index": float(value), "status": status, "variant": variant}
        for tag, value in zip(campaign.models, indices, strict=False)
    ]


def test_without_aa_reference_the_section_is_absent(campaign):
    assert _run() == 0
    summary = _summary()
    assert summary["aa_reference"] is None
    for block in summary["tracks"]:
        assert block["spearman"]["status"] == "absent"
    assert "Indice AA absent" in (_export_dir() / "report.md").read_text(encoding="utf-8")


def test_spearman_with_nine_measured_models(tmp_path, monkeypatch):
    campaign = make_campaign(tmp_path, monkeypatch, n_models=10, small=True, think_off_only=())
    profiles = [0.85, 0.6, 0.3, 0.75, 0.5, 0.45, 0.65, 0.2, 0.55, 0.4]
    entries = _entries(campaign, [p * 40 for p in profiles])
    entries[9]["status"] = "estimated"  # ignoré
    entries.append(
        {"tag": campaign.models[0], "index": 1.0, "status": "measured", "variant": "reasoning"}
    )
    write_aa_reference(aa_reference("2026-09-01", _entries(campaign, [1] * 10)))
    path = write_aa_reference(aa_reference("2026-10-01", entries))
    assert _run() == 0
    summary = _summary()
    assert summary["aa_reference"] == {
        "path": "references/aa-2026-10-01.json",
        "sha256": sha256_bytes(path.read_bytes()),
        "date": "2026-10-01",
    }
    spearman = next(b for b in summary["tracks"] if b["track"] == "think_off")["spearman"]
    assert spearman["status"] == "computed" and spearman["n"] == 9
    assert spearman["models"] == campaign.models[:9]
    assert spearman["rho"] > 0.5
    assert spearman["ci_low"] <= spearman["rho"] <= spearman["ci_high"]
    assert spearman["conclusion"] in ("concordant", "not_significant")
    think_on = next(b for b in summary["tracks"] if b["track"] == "think_on")["spearman"]
    assert think_on["variant"] == "reasoning" and think_on["n"] == 1
    assert think_on["conclusion"] == "inconclusive" and think_on["rho"] is None
    # Date explicite : le fichier plus ancien, constant, rend ρ indéfini.
    assert _run("--aa-date", "2026-09-01") == 0
    assert _summary()["aa_reference"]["date"] == "2026-09-01"
    old = next(b for b in _summary()["tracks"] if b["track"] == "think_off")["spearman"]
    assert old["rho"] is None and old["conclusion"] == "inconclusive"


def test_spearman_with_fewer_than_eight_models_has_no_conclusion(campaign):
    write_aa_reference(aa_reference("2026-10-01", _entries(campaign, [30, 20, 10])))
    assert _run() == 0
    spearman = next(b for b in _summary()["tracks"] if b["track"] == "think_off")["spearman"]
    assert spearman["n"] == 3 and spearman["conclusion"] == "inconclusive"
    assert math.isclose(spearman["rho"], 1.0)


def test_missing_aa_date_is_refused(campaign):
    _assert_refused(1, "--aa-date", "2026-01-01")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["entries"][0].update(status="guessed"),
        lambda d: d.update(extra=1),
        lambda d: d.update(date="2026-10-02"),
        lambda d: d["entries"].append(dict(d["entries"][0])),
    ],
    ids=["status", "extra", "date", "duplicate"],
)
def test_aa_reference_out_of_schema_is_refused_even_partial(campaign, mutate):
    document = aa_reference("2026-10-01", _entries(campaign, [3, 2, 1]))
    mutate(document)
    write_aa_reference(document, "aa-2026-10-01.json")
    _assert_refused(1, "--partial")


# -- Sélection (même plan que le runner) -----------------------------------------------------


def test_selection_sample_gives_a_complete_campaign(tmp_path, monkeypatch):
    campaign = make_campaign(
        tmp_path, monkeypatch, selection={"sample": {"per_usage": 3, "seed": 7}}
    )
    assert 0 < len(campaign.generation) < 3 * len(campaign.questions)
    assert _run() == 0
    completeness = _summary()["completeness"]
    assert completeness["expected"] == completeness["retained"] == len(campaign.generation)
    assert completeness["generation_missing"] == completeness["grading_missing"] == 0
    assert export_problems(paths.exports_root()) == []


def test_selection_groups_gives_a_complete_campaign(tmp_path, monkeypatch):
    """Sélection par groupes entiers (pilote) : le runner (plan de la fabrique, même
    ``selected_ids``) et le rapport résolvent les mêmes clés."""
    selection = {
        "groups": {
            "seed": 8,
            "per_usage": {
                "reasoning": {"think_off": 5, "think_on": 2},
                "rag": {"think_off": 3, "think_on": 0},
                "writing": {"think_off": 3, "think_on": 2},
            },
        }
    }
    campaign = make_campaign(tmp_path, monkeypatch, selection=selection)
    assert 0 < len(campaign.generation) < 3 * len(campaign.questions)
    assert any("|think_on|" in line["key"] for line in campaign.generation)
    assert _run() == 0
    completeness = _summary()["completeness"]
    assert completeness["expected"] == completeness["retained"] == len(campaign.generation)
    assert completeness["generation_missing"] == completeness["grading_missing"] == 0


def test_selection_ids_never_leak_into_the_exported_manifest(tmp_path, monkeypatch):
    ids = ["reasoning/var-math/0000", "reasoning/var-math/0000-v1", "writing/writing-fr/0001"]
    campaign = make_campaign(tmp_path, monkeypatch, selection={"ids": ids})
    assert {g["question_id"] for g in campaign.generation} == set(ids)
    assert _run() == 0
    completeness = _summary()["completeness"]
    assert completeness["expected"] == completeness["retained"] == len(campaign.generation)
    text = (_export_dir() / "manifest.json").read_text(encoding="utf-8")
    for qid in campaign.questions:
        assert qid not in text, qid
    exported = json.loads(text)
    assert exported["blocking"]["generation"]["resolved"]["selection"] == {
        "ids_count": 3,
        "ids_sha256": sha256_hex(sorted(ids)),
    }
    validate(exported)
    # Le manifeste de la campagne, lui, n'est pas modifié.
    assert campaign.manifest["blocking"]["generation"]["resolved"]["selection"] == {"ids": ids}
    assert export_problems(paths.exports_root()) == []


# -- Incohérences refusées même avec --partial -----------------------------------------------


def _duplicate_generation(campaign):
    campaign.write_generation(campaign.generation + [campaign.generation[0]])


def _duplicate_grading(campaign):
    campaign.write_grading(campaign.grading + [campaign.grading[0]])


def _mutate_generation(**changes):
    def mutate(campaign):
        lines = [dict(g) for g in campaign.generation]
        lines[0].update(changes)
        campaign.write_generation(lines)

    return mutate


@pytest.mark.parametrize(
    "mutate, message",
    [
        (_duplicate_generation, "clé en double"),
        (_duplicate_grading, "clé en double"),
        (_mutate_generation(prompt_hash="f" * 64), "prompt_hash différent"),
        (_mutate_generation(unit="reasoning/var-math/9999"), "unit différent"),
        (_mutate_generation(seed=5), "clé incohérente avec ses champs"),
        (_mutate_generation(digest="sha256:" + "9" * 64), "hors des clés attendues"),
    ],
    ids=["generation-double", "grading-double", "prompt_hash", "unit", "key", "digest"],
)
def test_incoherent_lines_are_refused_even_partial(campaign, mutate, message):
    mutate(campaign)
    _assert_refused(1, "--partial")
    assert message in _log()


def test_judgment_manifest_of_another_generation_is_refused(campaign):
    path = paths.judgment_manifest_path(CAMPAIGN, JUDGE_ID)
    judgment = json.loads(path.read_text(encoding="utf-8"))
    judgment["blocking"]["generation_manifest"] = "f" * 64
    validate(judgment)
    path.write_bytes(pretty_bytes(judgment))
    _assert_refused(1)
    assert "jugement d'un autre manifeste de génération" in _log()


@pytest.mark.parametrize("index", ["NaN", "Infinity", "1e999"])
def test_non_finite_aa_index_is_refused_even_partial(campaign, index):
    path = paths.references_dir() / "aa-2026-10-01.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"schema": "qb.aa_reference/1", "date": "2026-10-01", "source": "test", "entries": '
        f'[{{"tag": "model-0:4b", "index": {index}, "status": "measured", '
        '"variant": "non_reasoning"}]}',
        encoding="utf-8",
    )
    _assert_refused(1, "--partial")
    assert "référence AA illisible" in _log()


def test_case_insensitive_score_file_collision_is_refused(campaign):
    from scripts.quality_bench.report.export import score_files
    from scripts.quality_bench.report.inputs import CampaignInputs, Completeness, ReportError

    models = ({"tag": "Model:1b", "digest": "sha256:a"}, {"tag": "model:1b", "digest": "sha256:b"})
    inputs = CampaignInputs(
        campaign=CAMPAIGN,
        partial=False,
        set_id="s",
        set_hash="0" * 64,
        manifest={},
        generation_hash="0" * 64,
        judgment_hash=None,
        k=1,
        models=models,
        questions={},
        expected=(),
        rows={},
        completeness=Completeness(),
        aa_reference=None,
    )
    with pytest.raises(ReportError, match="même fichier de scores"):
        score_files(inputs)
