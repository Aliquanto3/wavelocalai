"""Mesures pures de la calibration (``report/calibration_measures.py``) : heuristique de
comptage épinglée sur ``writing-fr.yaml``, accord, biais, coût, cascade, stabilité,
admissibilité, proposition et tirage de l'échantillon, valeurs calculées à la main."""

from __future__ import annotations

import pytest
import yaml

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.canonical import sha256_hex
from scripts.quality_bench.report.calibration_measures import (
    DEFAULT_MARGINS,
    JudgeData,
    Unit,
    Verdict,
    admissibility,
    agreement,
    cascade,
    cascade_decisions,
    cascade_id,
    configuration_order,
    draw_sample,
    is_counting,
    judge_cost,
    measures,
    proposal,
    qwen_bias,
    stability,
)
from scripts.quality_bench.stats.wilson import wilson_interval

WRITING_FR = paths.PACKAGE_DIR / "questions" / "writing" / "writing-fr.yaml"


def _unit(key, *, model="m:1b", qwen=False, counting=False, response=None):
    return Unit(
        key=key,
        generation_key=response or key.rsplit("|", 1)[0],
        model=model,
        qwen=qwen,
        question_id="writing/writing-fr/0001",
        track="think_off",
        criterion=key.rsplit("|", 1)[1],
        counting=counting,
        private=False,
    )


def _key(model, response, criterion):
    return f"c|{model}|think_off|writing/writing-fr/{response:04d}|0|c{criterion}"


# -- Heuristique de comptage ----------------------------------------------------------------


def test_counting_heuristic_count_on_writing_fr_is_pinned():
    document = yaml.safe_load(WRITING_FR.read_text(encoding="utf-8"))
    criteria = [c["question"] for q in document["questions"] for c in q["criteria"]]
    assert len(criteria) == 418
    assert sum(1 for text in criteria if is_counting(text)) == 84


@pytest.mark.parametrize(
    "text",
    [
        "Le corps du courriel fait-il moins de 120 mots ?",
        "Le texte comporte-t-il exactement trois paragraphes ?",
        "La synthèse tient-elle en un seul paragraphe ?",
        "La morale tient-elle en une seule phrase ?",
        "La liste comporte-t-elle exactement sept étapes ?",
        "Le dialogue comporte-t-il exactement huit répliques ?",
        "Le texte comporte-t-il trois courts paragraphes ?",
        "La FAQ comporte-t-elle exactement six questions ?",
        "Le texte compte-t-il entre 4 et 6 phrases ?",
        "La liste compte-t-elle dix-huit éléments ?",
        "Le message compte-t-il Cinq lignes ?",
    ],
)
def test_counting_criteria_are_detected(text):
    assert is_counting(text)


@pytest.mark.parametrize(
    "text",
    [
        "La réponse commence-t-elle par une ligne « Objet : » contenant le numéro MT-48213 ?",
        "Le courriel mentionne-t-il la date du 9 septembre et 400 barres d'inox ?",
        "Le courriel fixe-t-il une date limite au vendredi 26 septembre ?",
        "Le texte reste-t-il en français ?",
        "Le texte cite-t-il deux exemples concrets ?",
        "La conclusion compte-t-elle trois très longues phrases ?",  # deux mots intercalés
    ],
)
def test_other_criteria_are_not_counting(text):
    assert not is_counting(text)


# -- Accord et biais ------------------------------------------------------------------------


def test_agreement_counts_lenient_severe_without_line_and_errors():
    units = [_unit(f"k|{i}") for i in range(7)]
    labels = {"k|0": True, "k|1": True, "k|2": False, "k|3": False, "k|4": True, "k|5": False}
    decisions = {"k|0": True, "k|1": False, "k|2": True, "k|3": False, "k|5": None, "k|6": True}
    result = agreement(units, labels, decisions)
    low, high = wilson_interval(2, 4)
    assert result == {
        "labeled": 6,
        "n": 4,
        "agree": 2,
        "rate": 0.5,
        "ci_low": pytest.approx(low),
        "ci_high": pytest.approx(high),
        "lenient": 1,
        "lenient_rate": 0.25,
        "severe": 1,
        "severe_rate": 0.25,
        "labeled_without_line": 1,
        "labeled_error": 1,
    }


def test_agreement_without_measured_unit_is_undefined():
    result = agreement([_unit("k|0")], {}, {"k|0": True})
    assert result["n"] == 0 and result["rate"] is None and result["ci_low"] is None


def test_qwen_bias_is_qwen_minus_other_and_undefined_for_an_empty_group():
    units = [_unit("q|0", qwen=True), _unit("q|1", qwen=True), _unit("o|0"), _unit("o|1")]
    labels = {u.key: True for u in units}
    decisions = {"q|0": True, "q|1": True, "o|0": True, "o|1": False}
    result = qwen_bias(units, labels, decisions)
    assert result["bias"] == pytest.approx(0.5)
    assert result["qwen"]["n"] == 2 and result["non_qwen"]["severe"] == 1
    assert qwen_bias(units[:2], labels, decisions)["bias"] is None


def test_counting_agreement_is_published_apart():
    units = [_unit("a|0", counting=True), _unit("a|1", counting=True), _unit("a|2")]
    labels = {"a|0": True, "a|1": True, "a|2": False}
    block = measures(units, labels, {"a|0": False, "a|1": True, "a|2": False})
    assert block["counting"]["counting"]["rate"] == 0.5
    assert block["counting"]["other"]["rate"] == 1.0
    assert block["agreement"]["agree"] == 2


# -- Coût -----------------------------------------------------------------------------------


def _judge(verdicts, *, batch_costs=(), judge_id="haiku", status="present", **block):
    return JudgeData(
        judge_id,
        status,
        manifest_hash="h",
        judge={
            "endpoint": "e",
            "model": "m",
            "settings": {"effort": "low"},
            "prompt_template_hash": "p",
            "weights_sha256": None,
            "server_version": None,
            **block,
        },
        generation_manifest="g",
        verdicts=verdicts,
        batch_costs=tuple(batch_costs),
    )


def test_cost_reads_collected_batches_first_then_judgment_lines():
    verdicts = {f"k|{i}": Verdict(True, None, 0.001) for i in range(4)}
    from_batches = judge_cost(_judge(verdicts, batch_costs=(0.01, 0.006)), 1000)
    assert from_batches["source"] == "batches"
    assert from_batches["total_usd"] == pytest.approx(0.016)
    assert from_batches["per_judgment_usd"] == pytest.approx(0.004)
    assert from_batches["projected_usd"] == pytest.approx(4.0)
    from_lines = judge_cost(_judge(verdicts), 1000)
    assert from_lines["source"] == "judgments"
    assert from_lines["total_usd"] == pytest.approx(0.004)
    assert from_lines["projected_usd"] == pytest.approx(1.0)
    empty = judge_cost(_judge({}), 1000)
    assert empty["per_judgment_usd"] is None and empty["projected_usd"] is None


# -- Cascade --------------------------------------------------------------------------------


def test_default_margins_and_cascade_identifier():
    assert pytest.approx([0.05 * i for i in range(11)]) == DEFAULT_MARGINS
    assert cascade_id(0.15) == "winnow-cascade-haiku@0.35-0.65"
    assert cascade_id(0.0) == "winnow-cascade-haiku@0.50-0.50"
    assert cascade_id(0.5) == "winnow-cascade-haiku@0.00-1.00"


def test_cascade_decides_at_the_bounds_and_escalates_the_rest():
    winnow = {
        "a": Verdict(True, 0.65, 0.0),  # = haut : vrai
        "b": Verdict(False, 0.35, 0.0),  # = bas : faux
        "c": Verdict(True, 0.64, 0.0),  # escaladée
        "d": Verdict(None, None, 0.0),  # error : escaladée
        "e": Verdict(True, None, 0.0),  # probabilité nulle : escaladée
        "f": Verdict(False, 0.4, 0.0),  # escaladée, sans ligne de Haiku
    }
    haiku = {key: Verdict(key != "c", None, 0.0) for key in "abcde"}
    decisions, escalated, without = cascade_decisions(winnow, haiku, 0.15)
    assert decisions == {"a": True, "b": False, "c": False, "d": True, "e": True}
    assert escalated == 4 and without == 1


def test_cascade_cost_is_haiku_cost_per_judgment_times_escalations():
    units = [_unit(f"u|{i}", qwen=i < 2) for i in range(4)]
    labels = {u.key: True for u in units}
    winnow = _judge(
        {u.key: Verdict(True, p, 0.0) for u, p in zip(units, (0.9, 0.55, 0.45, 0.1), strict=True)},
        judge_id="winnow",
    )
    haiku = _judge({u.key: Verdict(True, None, 0.0) for u in units}, batch_costs=(0.02,))
    (entry,) = cascade(units, labels, winnow, haiku, [0.1], 11_000)
    # Haiku : 0,02 $ / 4 jugements ; deux escalades (0,55 et 0,45) ; 0,1 → faux.
    assert entry["escalated"] == 2 and entry["escalated_share"] == 0.5
    assert entry["cost"]["total_usd"] == pytest.approx(0.01)
    assert entry["cost"]["projected_usd"] == pytest.approx(0.01 / 4 * 11_000)
    assert entry["agreement"]["agree"] == 3 and entry["agreement"]["severe"] == 1
    assert entry["qwen_bias"]["bias"] == pytest.approx(0.5)


# -- Stabilité ------------------------------------------------------------------------------


def test_stability_counts_identical_and_changed_verdicts():
    base = _judge(
        {
            "a": Verdict(True, None, 0),
            "b": Verdict(True, None, 0),
            "c": Verdict(False, None, 0),
            "d": Verdict(None, None, 0),
            "e": Verdict(True, None, 0),
        }
    )
    replay = _judge(
        {
            "a": Verdict(True, None, 0),
            "b": Verdict(False, None, 0),
            "c": Verdict(True, None, 0),
            "d": Verdict(True, None, 0),
            "f": Verdict(True, None, 0),
        },
        judge_id="haiku-replay",
    )
    entry = stability(base, replay)
    assert entry["status"] == "computed"
    assert (entry["n"], entry["identical"], entry["changed"]) == (3, 1, 2)
    assert entry["true_to_false"] == 1 and entry["false_to_true"] == 1
    assert entry["judge_only"] == 1 and entry["replay_only"] == 1
    assert entry["rate"] == pytest.approx(1 / 3)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("settings", {"effort": "high"}, "settings.effort"),
        ("model", "other", "model"),
        ("prompt_template_hash", "q", "prompt_template_hash"),
        ("weights_sha256", "w", "weights_sha256"),
        ("server_version", "v2", "server_version"),
        ("endpoint", "x", "endpoint"),
    ],
)
def test_stability_names_the_first_different_field(field, value, expected):
    base = _judge({"a": Verdict(True, None, 0)})
    replay = _judge({"a": Verdict(True, None, 0)}, judge_id="haiku-replay", **{field: value})
    entry = stability(base, replay)
    assert entry["status"] == "not_comparable" and entry["field"] == expected


def test_stability_of_another_generation_or_without_replay():
    base = _judge({"a": Verdict(True, None, 0)})
    other = JudgeData(
        "haiku-replay", "discordant", manifest_hash="h", judge=base.judge, generation_manifest="z"
    )
    assert stability(base, other)["field"] == "generation_manifest"
    assert stability(base, None)["status"] == "replay_absent"
    assert stability(base, JudgeData("haiku-replay", "absent"))["status"] == "replay_absent"
    discordant = JudgeData(
        "haiku", "discordant", manifest_hash="h", judge=base.judge, generation_manifest="z"
    )
    present = _judge({"a": Verdict(True, None, 0)}, judge_id="haiku-replay")
    assert stability(discordant, present)["status"] == "judge_discordant"
    absent = JudgeData("haiku", "absent")
    assert stability(absent, _judge({}, judge_id="haiku-replay"))["status"] == "judge_absent"


# -- Admissibilité et proposition -----------------------------------------------------------


def _block(rate, bias):
    return {"agreement": {"rate": rate}, "qwen_bias": {"bias": bias}}


def test_admissibility_without_thresholds_and_with_undefined_bias():
    assert admissibility(_block(0.9, 0.0), None, None) == {
        "agreement": None,
        "qwen_bias": None,
        "admissible": None,
    }
    assert admissibility(_block(0.9, None), 0.8, 0.1)["admissible"] is False
    # Arrondis binaires : 0,8 atteint, |−0,1| toléré.
    assert admissibility(_block(4 / 5, 0.7 - 0.8), 0.8, 0.1)["admissible"] is True
    assert admissibility(_block(0.79, 0.0), 0.8, 0.1)["agreement"] is False


def _candidate(entry_id, rate, cost, admissible=True):
    return {
        "id": entry_id,
        "agreement": rate,
        "qwen_bias": 0.0,
        "projected_usd": cost,
        "admissibility": {"admissible": admissible},
    }


def test_proposal_picks_max_agreement_then_min_cost_then_order():
    candidates = [
        _candidate("winnow", 0.9, 0.0, admissible=False),
        _candidate("cascade-a", 0.85, 3.0),
        _candidate("mimo", 0.85, 2.0),
        _candidate("haiku", 0.85, 2.0),
        _candidate("other", 0.8, 0.0),
    ]
    result = proposal(candidates, 0.8, 0.1)
    assert result["status"] == "proposed" and result["id"] == "mimo"
    assert result["admissible"] == ["cascade-a", "mimo", "haiku", "other"]
    candidates[2]["projected_usd"] = None  # coût inconnu : en dernier
    assert proposal(candidates, 0.8, 0.1)["id"] == "haiku"
    assert proposal(candidates, 0.8, None) is None
    none = proposal([_candidate("winnow", 0.5, 0.0, admissible=False)], 0.8, 0.1)
    assert none["status"] == "none_admissible" and none["id"] is None


def test_configuration_order():
    ids = ["haiku-replay", "zeta", "haiku", "decider", "mimo-replay"]
    assert configuration_order(ids) == [
        "winnow",
        "winnow-cascade-haiku",
        "mimo",
        "haiku",
        "decider",
        "zeta",
    ]


# -- Échantillon ----------------------------------------------------------------------------


def _pool(models, responses, criteria, *, qwen=()):
    return [
        _unit(_key(model, r, c), model=model, qwen=model in qwen)
        for model in models
        for r in range(responses)
        for c in range(1, criteria + 1)
    ]


def test_sample_quotas_split_groups_and_models_with_rest_to_first_tags():
    units = _pool(["q:1b", "a:1b", "b:1b", "c:1b"], 10, 3, qwen=("q:1b",))
    sample = draw_sample(units, 11, 5)
    assert sample.groups == {"qwen": 6, "non_qwen": 5}
    assert sample.quotas == {"q:1b": 6, "a:1b": 2, "b:1b": 2, "c:1b": 1}
    assert sample.drawn == sample.quotas
    assert len({u.generation_key for u in sample.items}) == 11


def test_sample_goes_to_one_group_when_the_other_is_empty():
    units = _pool(["a:1b", "b:1b"], 5, 2)
    sample = draw_sample(units, 7, 1)
    assert sample.groups == {"qwen": 0, "non_qwen": 7}
    assert sample.quotas == {"a:1b": 4, "b:1b": 3}


def test_sample_takes_a_second_criterion_only_after_every_response():
    units = _pool(["a:1b"], 3, 3)
    sample = draw_sample(units, 5, 0)
    responses = [u.generation_key for u in sample.items]
    assert len(sample.items) == 5 and len(set(responses)) == 3
    assert sorted(responses.count(r) for r in set(responses)) == [1, 2, 2]
    whole = draw_sample(units, 50, 0)
    assert whole.drawn == {"a:1b": 9} and whole.quotas == {"a:1b": 50}


def test_sample_follows_the_hash_rules_and_is_deterministic():
    units = _pool(["q:1b", "a:1b"], 4, 2, qwen=("q:1b",))
    sample = draw_sample(units, 4, 9)
    keys = [u.key for u in sample.items]
    assert keys == sorted(keys, key=lambda k: sha256_hex([9, "calibration-order", k]))
    for model in ("q:1b", "a:1b"):
        own = [u for u in units if u.model == model]
        first_response = min(
            {u.generation_key for u in own}, key=lambda g: sha256_hex([9, "calibration", g])
        )
        criteria = [u.key for u in own if u.generation_key == first_response]
        first = min(criteria, key=lambda k: sha256_hex([9, "calibration", k]))
        assert first in keys
    assert [u.key for u in draw_sample(units, 4, 9).items] == keys
    assert [u.key for u in draw_sample(units, 4, 10).items] != keys
