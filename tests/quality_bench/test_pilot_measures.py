"""Mesures pures du pilote (CAP-8), calculées à la main : ψ, plafonds et planchers, stabilité,
projection et dégradation, ordre des réductions, approximation de Connor."""

from __future__ import annotations

import dataclasses
import math

import pytest

from scripts.quality_bench.report.inputs import (
    AAReference,
    CampaignInputs,
    Completeness,
    Expected,
    Row,
)
from scripts.quality_bench.report.pilot import (
    CampaignData,
    OldBenchEntry,
    _cache,
    _context_exceeded,
    aa_consistency,
    ceiling_floor,
    common_units,
    discordance,
    join_replay,
    old_bench_by_tag,
    old_bench_values,
    order_consistency,
    pair_counts,
    pair_discordance,
    stability,
    tokens,
    writing,
)
from scripts.quality_bench.report.projection import (
    FullQuestion,
    Line,
    ModelRate,
    Warmup,
    degradation,
    merge_caps,
    overhead,
    project,
    reference_tier,
)
from scripts.quality_bench.stats.describe import describe
from scripts.quality_bench.stats.power import mcnemar_sample_size

DEFAULT_CAPS = {"think_on": {"reasoning": 4096, "default": 2048}, "think_off": {"default": 2048}}


# -- Fabriques ------------------------------------------------------------------------------


def _inputs(scores, *, campaign="c", usage_of=None, unit_of=None, k=1):
    """Entrées minimales : ``scores`` = {(modèle, piste, question) : score ou None}."""
    usage_of = usage_of or {}
    unit_of = unit_of or {}
    models = sorted({model for model, _, _ in scores})
    questions = {}
    for _, _, qid in scores:
        questions[qid] = {
            "id": qid,
            "usage": usage_of.get(qid, "reasoning"),
            "unit": unit_of.get(qid, qid),
            "group": unit_of.get(qid, qid),
        }
    expected, rows = [], {}
    for (model, track, qid), score in sorted(scores.items()):
        key = f"{campaign}|{model}|{track}|{qid}|0"
        expected.append(Expected(key, model, track, qid, 0))
        if score is not None:
            rows[key] = Row(key, model, "d", track, qid, 0, "ok", score, score == 1.0, {})
    tracks_by_model = {m: sorted({t for mm, t, _ in scores if mm == m}) for m in models}
    return CampaignInputs(
        campaign=campaign,
        partial=True,
        set_id="s",
        set_hash="h",
        manifest={},
        generation_hash="g",
        judgment_hash=None,
        k=k,
        models=tuple({"tag": m, "tracks": tracks_by_model[m]} for m in models),
        questions=questions,
        expected=tuple(expected),
        rows=rows,
        completeness=Completeness(),
        aa_reference=None,
    )


def _line(model="a", track="think_off", qid="q1", **overrides):
    fields = {
        "key": f"c|{model}|{track}|{qid}|0",
        "model": model,
        "digest": "d",
        "track": track,
        "question_id": qid,
        "usage": "reasoning",
        "source": "bbeh-mini",
        "num_ctx": 4096,
        "seed": 0,
        "status": "ok",
        "calls": 1,
        "attempts": 1,
        "prompt": 0,
        "prompt_cached": 0,
        "completion": 0,
        "thinking_est": 0,
        "wall_s": 0.0,
        "prompt_eval_ns": 0,
        "eval_ns": 0,
        "prompt_hash": "p",
        "output_hash": "o",
    }
    fields.update(overrides)
    return Line(**fields)


# -- Statistiques ---------------------------------------------------------------------------


# Repères exacts de statistiques.md (McNemar exact, α = 0,05 bilatéral, puissance 80 %).
TABLE = {(0.2, 0.1): 168, (0.3, 0.1): 249, (0.4, 0.1): 329}
TABLE |= {(0.2, 0.2): 39, (0.3, 0.2): 61, (0.4, 0.2): 84}


@pytest.mark.parametrize("psi, delta", sorted(TABLE))
def test_connor_is_just_under_the_exact_table(psi, delta):
    n = math.ceil(mcnemar_sample_size(psi, delta))
    assert 0.8 * TABLE[(psi, delta)] <= n <= TABLE[(psi, delta)]


def test_connor_formula_by_hand():
    # (1,959964·√0,2 + 0,841621·√0,19)² / 0,01
    expected = (1.959964 * math.sqrt(0.2) + 0.841621 * math.sqrt(0.19)) ** 2 / 0.01
    assert mcnemar_sample_size(0.2, 0.1) == pytest.approx(expected, rel=1e-5)


@pytest.mark.parametrize(
    "psi, delta", [(0.2, 0.0), (0.2, -0.1), (0.05, 0.1), (1.0, 0.1), (math.nan, 0.1)]
)
def test_connor_out_of_domain_is_nan(psi, delta):
    assert math.isnan(mcnemar_sample_size(psi, delta))


def test_describe():
    assert describe([4, 1, 3, 2]) == {"n": 4, "mean": 2.5, "p50": 2.5, "p90": 3.7, "max": 4.0}
    empty = describe([])
    assert empty["n"] == 0
    assert all(math.isnan(empty[key]) for key in ("mean", "p50", "p90", "max"))


# -- Discordance ----------------------------------------------------------------------------


def test_pair_discordance_counts_units_defined_for_both():
    a = {"u1": 1.0, "u2": 1.0, "u3": 0.0, "u4": 0.0, "u5": None}
    b = {"u1": 1.0, "u2": 0.0, "u3": 0.0, "u4": 1.0, "u5": 1.0}
    assert pair_discordance(a, b, ["u1", "u2", "u3", "u4", "u5"]) == (4, 2)


def test_discordance_by_scope_and_unit_minimum():
    scores = {}
    # Raisonnement : unité u1 de deux variantes (min), u2, u3.
    for model, values in {"a": (1, 0, 1, 1), "b": (1, 1, 1, 0)}.items():
        for qid, value in zip(("v1", "v2", "u2", "u3"), values, strict=True):
            scores[(model, "think_off", qid)] = float(value)
    # Consignes : i1, i2 ; i2 sans score pour b.
    scores[("a", "think_off", "i1")] = 1.0
    scores[("b", "think_off", "i1")] = 0.0
    scores[("a", "think_off", "i2")] = 1.0
    scores[("b", "think_off", "i2")] = None
    usage_of = {"i1": "instructions", "i2": "instructions"}
    unit_of = {"v1": "u1", "v2": "u1"}
    inputs = _inputs(scores, usage_of=usage_of, unit_of=unit_of)
    (block,) = discordance(inputs)
    scopes = {scope["scope"]: scope for scope in block["scopes"]}
    # u1 : a = min(1, 0) = 0, b = 1 → discordante ; u2 concordante ; u3 discordante.
    assert scopes["reasoning"]["pairs"][0] == {
        "a": "a",
        "b": "b",
        "n": 3,
        "discordant": 2,
        "psi": pytest.approx(2 / 3),
    }
    assert scopes["instructions"]["pairs"][0]["n"] == 1
    assert scopes["global"]["pairs"][0]["n"] == 4
    assert scopes["global"]["pairs"][0]["discordant"] == 3
    assert scopes["global"]["psi_mean"] == pytest.approx(0.75)
    n = {entry["delta"]: entry["n"] for entry in scopes["global"]["n_connor"]}
    assert n[0.1] == math.ceil(mcnemar_sample_size(0.75, 0.1))


def test_writing_is_excluded_from_binary_scopes():
    scores = {("a", "think_off", "w1"): 0.5, ("b", "think_off", "w1"): 0.75}
    scores |= {("a", "think_off", "r1"): 1.0, ("b", "think_off", "r1"): 1.0}
    inputs = _inputs(scores, usage_of={"w1": "writing"})
    (block,) = discordance(inputs)
    assert [scope["scope"] for scope in block["scopes"]] == ["global", "reasoning"]
    assert block["scopes"][0]["pairs"][0]["n"] == 1


# -- Plafonds et planchers ------------------------------------------------------------------


def test_ceiling_floor_and_single_models():
    scores = {}
    values = {
        "reasoning": {"a": (1, 1), "b": (1, 0)},  # a seul au plafond (1,0), b 0,5
        "tools": {"a": (1, 1), "b": (1, 1)},  # plafond
        "rag": {"a": (0, 0), "b": (0, 0)},  # plancher
    }
    usage_of = {}
    for usage, by_model in values.items():
        for model, pair in by_model.items():
            for i, value in enumerate(pair):
                qid = f"{usage}{i}"
                usage_of[qid] = usage
                scores[(model, "think_off", qid)] = float(value)
    result = {e["usage"]: e for e in ceiling_floor(_inputs(scores, usage_of=usage_of), 0.9, 0.1)}
    assert result["tools"]["status"] == "ceiling"
    assert result["rag"]["status"] == "floor"
    assert result["reasoning"]["status"] is None
    assert result["reasoning"]["at_ceiling"] == ["a"]
    assert result["reasoning"]["means"] == [
        {"model": "a", "mean": 1.0},
        {"model": "b", "mean": 0.5},
    ]


# -- Stabilité ------------------------------------------------------------------------------


def test_join_replay_excludes_and_counts():
    pilot = {
        line.key: line
        for line in (
            _line(qid="q1"),
            _line(qid="q2"),
            _line(qid="q3"),
            _line(qid="q4", prompt_hash="autre"),
        )
    }
    replay = {
        line.key: line
        for line in (
            _line(qid="q1"),
            _line(qid="q2", digest="nouveau"),
            _line(qid="q4"),
            _line(qid="q9"),
        )
    }
    pairs, excluded = join_replay(pilot, replay)
    assert [(a.question_id, b.question_id) for a, b in pairs] == [("q1", "q1")]
    assert excluded == {"unmatched": 1, "digest": 1, "prompt_hash": 1}


def test_stability_counts_output_and_score_changes_apart():
    qids = ["q1", "q2", "q3", "q4", "w1"]
    usage_of = {"w1": "writing"}
    pilot_scores = {("a", "think_off", q): 1.0 for q in qids}
    replay_scores = dict(pilot_scores)
    replay_scores[("a", "think_off", "q2")] = 0.0  # score changé
    replay_scores[("a", "think_off", "q3")] = None  # score indéfini : paire non comptée
    replay_scores[("a", "think_off", "w1")] = 0.5  # rédaction à part
    pilot_inputs = _inputs(pilot_scores, campaign="p", usage_of=usage_of)
    replay_inputs = _inputs(replay_scores, campaign="r", usage_of=usage_of)

    def lines(campaign, changed=()):
        result = {}
        for qid in qids:
            line = _line(
                qid=qid,
                key=f"{campaign}|a|think_off|{qid}|0",
                usage=usage_of.get(qid, "reasoning"),
                output_hash="x" if qid in changed else "o",
            )
            result[line.key] = line
        return result

    pilot = CampaignData(pilot_inputs, lines("p"), {}, (), None)
    replay = CampaignData(replay_inputs, lines("r", changed=("q1",)), {}, (), None)
    result = stability(pilot, replay, {"think_off": 0.25})
    (block,) = result["tracks"]
    assert block["joined"] == 5
    assert block["output_changed"] == 1
    assert block["scored_pairs"] == 3  # q1, q2, q4
    assert block["score_changed"] == 1
    assert block["score_changed_rate"] == pytest.approx(1 / 3)
    assert block["ratio_to_psi"] == pytest.approx((1 / 3) / 0.25)
    assert (block["writing_scored_pairs"], block["writing_score_changed"]) == (1, 1)


def test_stability_without_replay():
    pilot = CampaignData(_inputs({("a", "think_off", "q1"): 1.0}), {}, {}, (), None)
    assert stability(pilot, None, {})["status"] == "absent"


# -- Projection -----------------------------------------------------------------------------


def test_overhead_reference_tier_and_degradation():
    lines = [
        _line(wall_s=3.3, prompt_eval_ns=1_000_000_000, eval_ns=2_000_000_000),
        _line(qid="q2", status="context_exceeded", calls=0, wall_s=50.0),
    ]
    assert overhead(lines) == (pytest.approx(1.1), True)
    assert overhead([_line()]) == (1.0, False)
    warmups = [
        Warmup("a", 4096, 1000, 1000.0),
        Warmup("a", 8192, 2000, 800.0),
        Warmup("a", 8192, 2000, 820.0),
        Warmup("b", 4096, 1000, 600.0),
        Warmup("b", 8192, 2000, 500.0),
    ]
    assert reference_tier(warmups, 1900) == 8192
    assert reference_tier(warmups, 1500) == 4096  # égalité : le plus petit palier
    assert reference_tier(warmups, None) is None
    deg = degradation(warmups, ["a", "b"], [4096, 8192, 16384], 8192)
    # a : 1000 / max(800, 820) = 1000 / 820 ; b : 600 / 500 ; médiane des deux.
    assert deg[4096][0] == pytest.approx((1000 / 820 + 1.2) / 2)
    assert deg[4096][1:] == (True, 2)
    assert deg[8192] == (1.0, True, 2)
    assert deg[16384] == (1.0, False, 0)


def test_degradation_ignores_cold_first_warmup():
    # Première chauffe à froid (139 tok/s) puis chauffe à chaud au même palier : seule la
    # seconde compte, sinon le préremplissage semblerait s'améliorer aux grands paliers.
    warmups = [
        Warmup("a", 4096, 800, 139.0),
        Warmup("a", 8192, 1600, 2550.0),
        Warmup("a", 4096, 800, 1872.0),
    ]
    deg = degradation(warmups, ["a"], [4096, 8192], 4096)
    assert deg[8192][0] == pytest.approx(2550.0 / 1872.0)


def _rate(tag="a", *, decode=100.0, prefill=1000.0, load_s=1.0, thinking=False, reason=None):
    return ModelRate(tag, tag, decode, prefill, 1900.0, load_s, thinking, reason)


def _project(lines, warmups, full, rates, *, budget=144.0, caps=(), think_on_n=330, pilot=None):
    pilot_rates = {rate.tag: rate for rate in rates}
    if pilot is not None:
        pilot_rates = {rate.tag: rate for rate in pilot}
    return project(
        lines=lines,
        warmups=warmups,
        pilot_models=list(pilot_rates),
        pilot_questions={},
        questions_by_id={},
        full=full,
        campaign_caps=DEFAULT_CAPS,
        rates=rates,
        pilot_rates=pilot_rates,
        budget_hours=budget,
        reduction_caps=list(caps),
        think_on_n=think_on_n,
    )


def test_projection_by_hand_with_degradation_and_unmeasured_usage():
    lines = [
        _line(
            completion=200,
            prompt=1000,
            wall_s=3.3,
            prompt_eval_ns=1_000_000_000,
            eval_ns=2_000_000_000,
        )
    ]
    warmups = [Warmup("a", 4096, 1000, 1000.0), Warmup("a", 8192, 2000, 800.0)]
    full = {
        "think_off": [
            FullQuestion("reasoning", 4096, 120),
            FullQuestion("reasoning", 4096, 120),
            FullQuestion("reasoning", 8192, 120),  # palier sans ligne : P̄ de l'usage
            FullQuestion("rag", 8192, 300),  # usage sans mesure : C̄ = 2048, P̄ = 300
        ],
        "think_on": [],
    }
    result = _project(lines, warmups, full, [_rate()])
    f = 1.1
    deg_4096 = 1000 / 800
    questions = 2 * (200 / 100 + 1000 / (1000 * deg_4096))
    questions += 200 / 100 + 1000 / 1000
    questions += 2048 / 100 + 300 / 1000
    warm = (1 + 1024 / 1000) + (1 + 2048 / 1000)
    expected = f * questions + warm
    assert result["reference_tier"] == 8192
    assert result["models"][0]["think_off_hours"] == pytest.approx(expected / 3600)
    assert result["models"][0]["think_on_hours"] is None  # modèle sans thinking
    assert result["total_hours"] == pytest.approx(expected / 3600)
    assert result["unmeasured"] == [{"track": "think_off", "usage": "rag", "questions": 1}]
    assert result["over_budget"] is False
    assert result["reduction"] is None
    assert result["complete"] is True


def test_unknown_rate_is_listed_and_the_total_incomplete():
    lines = [_line(completion=100, eval_ns=1_000_000_000, wall_s=1.0)]
    full = {"think_off": [FullQuestion("reasoning", 4096, 10)], "think_on": []}
    unknown = ModelRate("x", None, None, None, None, None, None, "absent du catalogue")
    result = _project(lines, [], full, [_rate(), unknown])
    assert result["complete"] is False
    assert result["models"][1]["known"] is False
    assert result["models"][1]["total_hours"] is None
    assert result["total_hours"] == result["models"][0]["total_hours"]


def test_reduction_order_and_first_scenario_under_budget():
    lines = [
        _line(completion=100, eval_ns=1_000_000_000, wall_s=1.0),
        _line(track="think_on", completion=1000, eval_ns=10_000_000_000, wall_s=10.0),
    ]
    full = {
        "think_off": [FullQuestion("reasoning", 4096, 0)] * 10,
        "think_on": [FullQuestion("reasoning", 4096, 0)] * 10,
    }
    caps = [
        {"think_on": {"reasoning": 500, "default": 2048}, "think_off": {"default": 2048}},
        {"think_on": {"reasoning": 200, "default": 2048}, "think_off": {"default": 2048}},
    ]
    rate = _rate(load_s=0.0, thinking=True)
    warm = 1024 / 1000
    base = (10 + warm) + (100 + warm)
    result = _project(lines, [], full, [rate], budget=40 / 3600, caps=caps, think_on_n=5)
    assert result["total_hours"] == pytest.approx(base / 3600)
    assert result["over_budget"] is True
    reduction = result["reduction"]
    assert reduction["proposal"] is True
    steps = reduction["scenarios"]
    assert [s["step"] for s in steps] == ["caps", "caps", "thinking_only", "think_on_n"]
    totals = [s["total_hours"] * 3600 for s in steps]
    assert totals[0] == pytest.approx((10 + warm) + (50 + warm))
    assert totals[1] == pytest.approx((10 + warm) + (20 + warm))
    assert totals[2] == pytest.approx(totals[1])
    assert totals[3] == pytest.approx((10 + warm) + (20 + warm) * 0.5)
    assert steps[0]["projected_truncation"] == pytest.approx(0.5)
    assert steps[2]["thinking_models"] == 1
    assert reduction["first_under_budget"] == 1
    assert [s["under_budget"] for s in steps] == [False, True, True, True]


# -- Ancien banc et ordre -------------------------------------------------------------------


def test_old_bench_values_and_bridge():
    entry = {
        "avg_tokens_per_second": 50,
        "prefill_tokens_per_second": 2000,
        "prefill_prompt_tokens": 4500,
        "load_time_ms": 1500,
        "quality_scores": {
            "reasoning_avg": 0.6,
            "instruction_following_avg": 0.9,
            "abstention_avg": 1.0,
        },
        "tool_capability": {"success_rate": 0.75},
        "json_capability": {"schema_compliance_rate": 0.5},
        "needle_in_haystack": {"ctx_4k": True, "ctx_8k": True, "ctx_16k": False, "ctx_32k": False},
    }
    values = old_bench_values(entry)
    assert values["rag"] == 0.5
    assert values["global"] == pytest.approx((0.6 + 0.9 + 0.75) / 3)
    old = {"models": {"Nom A": entry, "Nom B": {"avg_tokens_per_second": 0}}}
    catalog = {
        "models": {
            "Nom A": {"ollama_tag": "a:1b", "capabilities": ["chat", "thinking"]},
            "Nom B": {"ollama_tag": "b:1b", "capabilities": ["chat"]},
            "Nom C": {"ollama_tag": "c:1b", "capabilities": ["chat"]},
            "Nom E": {"ollama_tag": "e:1b", "capabilities": ["chat"]},
        }
    }
    no_load = {key: value for key, value in entry.items() if key != "load_time_ms"}
    old["models"]["Nom E"] = no_load
    bridge = old_bench_by_tag(old, catalog, ["a:1b", "b:1b", "c:1b", "d:1b", "e:1b"])
    rate = bridge["a:1b"].rate
    assert (rate.name, rate.decode, rate.prefill, rate.load_s, rate.thinking) == (
        "Nom A",
        50.0,
        2000.0,
        1.5,
        True,
    )
    assert rate.known
    assert bridge["b:1b"].rate.reason == "débit absent de l'ancien banc"
    assert bridge["b:1b"].rate.thinking is False
    assert bridge["c:1b"].rate.reason == "absent de l'ancien banc"
    assert bridge["d:1b"].rate.reason == "absent du catalogue"
    # Durée de chargement absente : traitée comme un débit inconnu (jamais 0 s).
    assert bridge["e:1b"].rate.reason == "durée de chargement absente de l'ancien banc"
    assert not bridge["e:1b"].rate.known


def test_pair_counts():
    models = ["a", "b", "c", "d"]
    pilot = {"a": 0.9, "b": 0.7, "c": 0.7, "d": None}
    reference = {"a": 0.8, "b": 0.9, "c": 0.5, "d": 1.0}
    # (a, b) discordante, (a, c) concordante, (b, c) à égalité ; d indéfini.
    assert pair_counts(models, pilot, reference) == {
        "models": 3,
        "concordant": 1,
        "discordant": 1,
        "tied": 1,
    }


# -- Discordance : bornes et domaine de Connor ---------------------------------------------


def test_discordance_publishes_min_max_and_connor_at_max():
    scores = {}
    for u in range(20):
        qid = f"u{u:02d}"
        scores[("a", "think_off", qid)] = 1.0
        scores[("b", "think_off", qid)] = 0.0 if u == 0 else 1.0
        scores[("c", "think_off", qid)] = 0.0 if u < 10 else 1.0
    (block,) = discordance(_inputs(scores))
    scope = block["scopes"][0]
    # ψ(a, b) = 1/20, ψ(a, c) = 10/20, ψ(b, c) = 9/20.
    assert scope["psi_min"] == pytest.approx(0.05)
    assert scope["psi_max"] == pytest.approx(0.5)
    assert scope["psi_mean"] == pytest.approx((0.05 + 0.5 + 0.45) / 3)
    connor = {entry["delta"]: entry for entry in scope["n_connor"]}
    assert connor[0.1]["n_psi_max"] == math.ceil(mcnemar_sample_size(0.5, 0.1))
    assert connor[0.2]["n"] == math.ceil(mcnemar_sample_size(1 / 3, 0.2))


def test_connor_is_none_when_psi_is_under_delta():
    scores = {}
    for u in range(20):
        scores[("a", "think_off", f"u{u:02d}")] = 1.0
        scores[("b", "think_off", f"u{u:02d}")] = 0.0 if u == 0 else 1.0
    (block,) = discordance(_inputs(scores))
    connor = block["scopes"][0]["n_connor"]
    assert [(entry["n"], entry["n_psi_max"]) for entry in connor] == [(None, None), (None, None)]


# -- Stabilité : paires non requêtées et statuts ------------------------------------------


def test_stability_counts_unrequested_pairs_and_status_changes():
    qids = ["q1", "q2"]
    pilot_inputs = _inputs({("a", "think_off", q): 1.0 for q in qids}, campaign="p")
    replay_inputs = _inputs(
        {("a", "think_off", "q1"): 1.0, ("a", "think_off", "q2"): None}, campaign="r"
    )
    pilot_lines = {f"p|a|think_off|{q}|0": _line(qid=q, key=f"p|a|think_off|{q}|0") for q in qids}
    replay_lines = {
        "r|a|think_off|q1|0": _line(qid="q1", key="r|a|think_off|q1|0"),
        "r|a|think_off|q2|0": _line(
            qid="q2",
            key="r|a|think_off|q2|0",
            status="context_exceeded",
            calls=0,
            output_hash="vide",
        ),
    }
    result = stability(
        CampaignData(pilot_inputs, pilot_lines, {}, (), None),
        CampaignData(replay_inputs, replay_lines, {}, (), None),
        {"think_off": 0.5},
    )
    (block,) = result["tracks"]
    assert (block["joined"], block["requested_pairs"], block["not_requested"]) == (2, 1, 1)
    assert block["status_changed"] == 1
    assert block["output_changed"] == 0  # la sortie vide du contexte dépassé n'est pas comptée
    assert block["output_changed_rate"] == 0.0
    assert block["scored_pairs"] == 1


# -- Tokens et plafonds candidats ---------------------------------------------------------


CAMPAIGN_CAPS = {"think_on": {"reasoning": 4096, "default": 2048}, "think_off": {"default": 1024}}


def test_candidate_caps_keep_the_campaign_caps_they_do_not_cite():
    merged = merge_caps(CAMPAIGN_CAPS, {"think_on": {"reasoning": 500}})
    assert merged == {
        "think_on": {"default": 2048, "reasoning": 500},
        "think_off": {"default": 1024},  # plafond think_off de la campagne, non remis à 2048
    }
    lines = {"k": _line(completion=1500)}
    (entry,) = tokens(lines, ["a"], [merged])["by_usage"]
    assert entry["candidates"] == [{"index": 1, "cap": 1024, "projected_truncation": 1.0}]


def test_tokens_distributions_truncation_and_candidates():
    lines = [
        _line(model="a", track="think_on", completion=1000, thinking_est=600, status="truncated"),
        _line(model="b", track="think_on", completion=600, thinking_est=100),
        _line(model="a", track="think_off", completion=100),
        _line(model="b", track="think_off", qid="q2", status="context_exceeded", calls=0),
    ]
    candidate = merge_caps(DEFAULT_CAPS, {"think_on": {"reasoning": 500}})
    section = tokens({line.key: line for line in lines}, ["a", "b"], [candidate])
    assert section["requested_lines"] == 3
    on = next(e for e in section["by_usage"] if e["track"] == "think_on")
    assert on["thinking_est"] == {"n": 2, "mean": 350.0, "p50": 350.0, "p90": 550.0, "max": 600.0}
    assert on["completion"]["mean"] == 800.0
    assert (on["truncated"], on["truncation_rate"]) == (1, 0.5)
    # Plafond 500 : la ligne tronquée et celle de 600 tokens.
    assert on["candidates"] == [{"index": 1, "cap": 500, "projected_truncation": 1.0}]
    by_model = {(e["track"], e["model"]): e for e in section["by_model"]}
    assert by_model[("think_on", "a")]["completion_mean"] == 1000.0
    assert by_model[("think_on", "a")]["truncation_rate"] == 1.0
    assert by_model[("think_on", "b")]["truncation_rate"] == 0.0
    assert by_model[("think_off", "a")]["completion_mean"] == 100.0
    assert ("think_off", "b") not in by_model  # ligne non requêtée


# -- Cohérence d'ordre --------------------------------------------------------------------


def _old(values):
    return OldBenchEntry(_rate(), values)


def test_order_consistency_uses_the_old_bench_global_scope():
    pilot = {
        "a": {"r1": 1, "r2": 1, "i1": 1, "t1": 0, "g1": 0},
        "b": {"r1": 1, "r2": 0, "i1": 0, "t1": 1, "g1": 1},
        "c": {"r1": 0, "r2": 0, "i1": 1, "t1": 1, "g1": 1},
    }
    usage_of = {"r1": "reasoning", "r2": "reasoning", "i1": "instructions", "t1": "tools"}
    usage_of["g1"] = "rag"
    scores = {
        (m, "think_off", q): float(v) for m, values in pilot.items() for q, v in values.items()
    }
    old = {
        "a": _old({"reasoning": 0.9, "global": 0.8, "rag": None}),
        "b": _old({"reasoning": 0.5, "global": 0.7, "rag": None}),
        "c": _old({"reasoning": 0.6, "global": 0.6, "rag": None}),
    }
    (block,) = order_consistency(_inputs(scores, usage_of=usage_of), old)
    scopes = {scope["scope"]: scope for scope in block["scopes"]}
    glob = scopes["global"]
    # Global sur raisonnement, consignes, outils : a 3/4, b 2/4, c 2/4 (RAG exclu).
    assert glob["usages"] == ["reasoning", "instructions", "tools"]
    assert [e["mean"] for e in glob["pilot"]] == [0.75, 0.5, 0.5]
    assert glob["pilot_order"] == ["a", "b", "c"]
    assert glob["old_order"] == ["a", "b", "c"]
    assert (glob["concordant"], glob["discordant"], glob["tied"]) == (2, 0, 1)
    reasoning = scopes["reasoning"]
    assert reasoning["pilot_order"] == ["a", "b", "c"]
    assert reasoning["old_order"] == ["a", "c", "b"]
    assert (reasoning["concordant"], reasoning["discordant"], reasoning["tied"]) == (2, 1, 0)
    assert scopes["rag"]["models"] == 0  # aucune valeur de l'ancien banc


def test_aa_pair_counts_on_measured_entries_only():
    scores = {("a", "think_off", "r1"): 1.0, ("a", "think_off", "r2"): 1.0}
    scores |= {("b", "think_off", "r1"): 1.0, ("b", "think_off", "r2"): 0.0}
    scores |= {("c", "think_off", "r1"): 0.0, ("c", "think_off", "r2"): 0.0}
    entries = (
        {"tag": "a", "index": 10.0, "status": "measured", "variant": "non_reasoning"},
        {"tag": "b", "index": 20.0, "status": "measured", "variant": "non_reasoning"},
        {"tag": "c", "index": 5.0, "status": "estimated", "variant": "non_reasoning"},
        {"tag": "c", "index": 50.0, "status": "measured", "variant": "reasoning"},
    )
    aa = AAReference("references/aa-2026-10-01.json", "f" * 64, "2026-10-01", entries)
    inputs = dataclasses.replace(_inputs(scores), aa_reference=aa)
    result = aa_consistency(inputs)
    (block,) = result["tracks"]
    assert block["variant"] == "non_reasoning"
    assert [e["status"] for e in block["entries"]] == ["measured", "measured", "estimated"]
    # Pilote a (1,0) > b (0,5) ; AA a (10) < b (20) : une paire discordante.
    assert (block["models"], block["concordant"], block["discordant"], block["tied"]) == (
        2,
        0,
        1,
        0,
    )
    assert block["pilot_order"] == ["a", "b"]
    assert block["aa_order"] == ["b", "a"]


# -- Points différés ----------------------------------------------------------------------


def test_common_units_leaders_differ_when_a_model_misses_a_hard_unit():
    scores = {("a", "think_off", "u1"): 0.0, ("a", "think_off", "u2"): 1.0}
    scores |= {("a", "think_off", "u3"): 1.0}
    scores |= {("b", "think_off", "u1"): None, ("b", "think_off", "u2"): 1.0}
    scores |= {("b", "think_off", "u3"): 1.0}
    (entry, _) = common_units(_inputs(scores))
    assert (entry["units"], entry["common_units"], entry["non_common_units"]) == (3, 2, 1)
    # b : 1,0 sur ses deux unités, a : 2/3 sur trois ; à égalité sur les communes, a mène.
    assert entry["leader_all_units"] == "b"
    assert entry["leader_common_units"] == "a"
    assert entry["same_leader"] is False


def test_common_units_without_any_common_unit_is_undetermined():
    scores = {("a", "think_off", "u1"): 1.0, ("a", "think_off", "u2"): None}
    scores |= {("b", "think_off", "u1"): None, ("b", "think_off", "u2"): 1.0}
    (entry, _) = common_units(_inputs(scores))
    assert entry["common_units"] == 0
    assert entry["leader_common_units"] is None
    assert entry["same_leader"] is None


def test_context_exceeded_by_source_and_tier():
    lines = [
        _line(qid="q1", num_ctx=4096),
        _line(qid="q2", num_ctx=4096, status="context_exceeded", calls=0, context_limit="bench"),
        _line(
            qid="q3",
            num_ctx=8192,
            status="context_exceeded",
            calls=0,
            source="piaf",
            context_limit="model",
        ),
        _line(
            qid="q4",
            num_ctx=8192,
            status="context_exceeded",
            calls=1,
            source="piaf",
            context_limit="model",
        ),
    ]
    result = _context_exceeded(lines, ["a"])
    # Comptes séparés par cause : « model » (échec compté) et « bench » (unité écartée).
    assert result["by_tier"] == [
        {
            "num_ctx": 4096,
            "lines": 2,
            "context_exceeded": 1,
            "context_exceeded_model": 0,
            "context_exceeded_bench": 1,
            "rate": 0.5,
        },
        {
            "num_ctx": 8192,
            "lines": 2,
            "context_exceeded": 2,
            "context_exceeded_model": 2,
            "context_exceeded_bench": 0,
            "rate": 1.0,
        },
    ]
    by_source = {e["source"]: e for e in result["by_source"]}
    assert by_source["bbeh-mini"]["rate"] == 0.5
    assert by_source["bbeh-mini"]["context_exceeded_bench"] == 1
    assert by_source["piaf"]["context_exceeded"] == 2
    piaf = by_source["piaf"]
    assert (piaf["context_exceeded_model"], piaf["context_exceeded_bench"]) == (2, 0)
    assert by_source["bfcl-multi"] == {
        "track": "think_off",
        "model": "a",
        "source": "bfcl-multi",
        "lines": 0,
        "context_exceeded": 0,
        "context_exceeded_model": 0,
        "context_exceeded_bench": 0,
        "rate": None,
    }


def test_prefix_cache_share():
    lines = [
        _line(qid="q1", prompt=100, prompt_cached=50),
        _line(qid="q2", prompt=200, prompt_cached=0),
        _line(qid="q3", usage="rag", prompt=0, prompt_cached=0),
    ]
    result = {e["usage"]: e for e in _cache(lines)}
    assert result["reasoning"] == {
        "track": "think_off",
        "usage": "reasoning",
        "lines": 2,
        "lines_with_cache": 1,
        "cached_share": pytest.approx(50 / 350),
    }
    assert result["rag"]["cached_share"] is None


def test_writing_is_provisional_and_counts_awaiting_apart():
    qids = ["w1", "w2", "w3"]
    usage_of = dict.fromkeys(qids, "writing")
    scores = {("a", "think_off", "w1"): 0.5, ("a", "think_off", "w2"): 1.0}
    scores[("a", "think_off", "w3")] = None
    inputs = _inputs(scores, usage_of=usage_of)
    lines = {f"c|a|think_off|{q}|0": _line(qid=q, usage="writing") for q in qids}
    statuses = {"c|a|think_off|w3|0": "awaiting_judgment"}
    result = writing(CampaignData(inputs, lines, statuses, (), None))
    assert result["status"] == "provisional"
    (entry,) = result["tracks"][0]["models"]
    assert entry == {
        "model": "a",
        "expected": 3,
        "available": 3,
        "scored": 2,
        "awaiting_judgment": 1,
        "mean": 0.75,
    }
    nothing = _inputs(dict.fromkeys(scores), usage_of=usage_of)
    assert writing(CampaignData(nothing, lines, {}, (), None))["status"] == "not_graded"


# -- Contrôle de la projection ------------------------------------------------------------


def test_projection_control_and_measured_decode_by_hand():
    lines = [
        _line(
            completion=200,
            prompt=1000,
            wall_s=3.3,
            prompt_eval_ns=1_000_000_000,
            eval_ns=2_000_000_000,
        ),
        _line(qid="q2", status="context_exceeded", calls=0, wall_s=0.5),
    ]
    full = {"think_off": [FullQuestion("reasoning", 4096, 120)], "think_on": []}
    result = project(
        lines=lines,
        warmups=[],
        pilot_models=["a"],
        pilot_questions={("a", "think_off"): ["q1"]},
        questions_by_id={"q1": FullQuestion("reasoning", 4096, 120)},
        full=full,
        campaign_caps=DEFAULT_CAPS,
        rates=[_rate()],
        pilot_rates={"a": _rate()},
        budget_hours=144.0,
        reduction_caps=[],
        think_on_n=330,
    )
    (control,) = result["control"]
    # f = 3,3 / 3 = 1,1 ; prévu = 1,1 × (200/100 + 1000/1000) = 3,3 s ; mesuré 3,3 s.
    assert control["predicted_hours"] == pytest.approx(3.3 / 3600)
    assert control["measured_hours"] == pytest.approx(3.3 / 3600)
    assert control["ratio"] == pytest.approx(1.0)
    assert control["lines"] == 1
    assert control["all_lines"] == 2
    assert control["measured_all_hours"] == pytest.approx(3.8 / 3600)
    (decode,) = result["decode"]
    assert decode == {"model": "a", "measured_tok_s": 100.0, "old_tok_s": 100.0, "ratio": 1.0}
    assert result["conclusion"] == "under_budget"
