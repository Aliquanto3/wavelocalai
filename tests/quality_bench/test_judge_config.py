"""``judges.yaml`` (``config.load_judges``, AD-8), coût et estimation (``judge/pricing.py``),
gabarits (``judge/prompt.py``) et schéma ``qb.batch/1``."""

from __future__ import annotations

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.config import ConfigError, load_judges
from scripts.quality_bench.common.schemas import SchemaValidationError, validate
from scripts.quality_bench.judge.base import CostCapError, UnitError, parse_verdict, split_int
from scripts.quality_bench.judge.pricing import Budget, estimate_cost, request_cost
from scripts.quality_bench.judge.prompt import (
    final_answer,
    prompt_template_hash,
    render_instruction,
)

HAIKU = """\
judges:
  haiku:
    kind: anthropic_batch
    endpoint: https://api.anthropic.com
    model: claude-haiku-5-5
    max_tokens: 2048
    effort: low
    prices: {input_per_mtok: 0.1, output_per_mtok: 0.5, batch_discount: 0.5,
             source: test, checked: 2026-10-12}
"""


def _load(tmp_path, text):
    path = tmp_path / "judges.yaml"
    path.write_text(text, encoding="utf-8")
    return load_judges(path)


def test_versioned_judges_yaml_declares_the_four_judges():
    judges = load_judges(paths.judges_config_path())
    assert set(judges) == {"winnow", "haiku", "mimo", "decider"}
    assert judges["winnow"].local and judges["winnow"].prices is None
    assert judges["decider"].endpoint is None and judges["decider"].cloud
    assert judges["haiku"].settings["effort"] in ("low", "medium", "high", "xhigh", "max")
    assert judges["mimo"].endpoint == "https://api.xiaomimimo.com/v1"
    for judge in judges.values():
        if judge.cloud:
            assert judge.prices["source"] and judge.prices["checked"]
            assert judge.options["api_key_env"]


def test_defaults_are_applied(tmp_path):
    (haiku,) = _load(tmp_path, HAIKU).values()
    assert haiku.options["api_key_env"] == "ANTHROPIC_API_KEY"
    assert haiku.options["max_attempts"] == 3 and haiku.options["batch_size"] == 1000
    assert haiku.options["thinking"] is None
    assert haiku.settings == {
        "max_tokens": 2048,
        "thinking": None,
        "effort": "low",
        "max_attempts": 3,
    }


@pytest.mark.parametrize(
    "extra",
    ["    temperature: 0\n", "    top_p: 0.9\n", "    local: true\n", "    ollama_url: x\n"],
)
def test_unknown_keys_are_refused_by_kind(tmp_path, extra):
    with pytest.raises(ConfigError, match="clés inconnues"):
        _load(tmp_path, HAIKU + extra)


def test_haiku_thinking_with_budget_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="thinking.type"):
        _load(tmp_path, HAIKU + "    thinking: {type: enabled}\n")


def test_missing_required_key_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="effort"):
        _load(tmp_path, HAIKU.replace("    effort: low\n", ""))


def test_hosted_systemone_requires_key_and_prices(tmp_path):
    text = (
        "judges:\n  d:\n    kind: systemone\n    local: false\n    endpoint: null\n    model: m\n"
    )
    with pytest.raises(ConfigError, match="api_key_env"):
        _load(tmp_path, text)


def test_config_hash_ignores_prices_and_operational_keys(tmp_path):
    base = _load(tmp_path, HAIKU)["haiku"].config_hash
    cheaper = _load(tmp_path, HAIKU.replace("input_per_mtok: 0.1", "input_per_mtok: 0.05"))
    assert cheaper["haiku"].config_hash == base
    assert _load(tmp_path, HAIKU + "    poll_s: 5\n")["haiku"].config_hash == base
    assert (
        _load(tmp_path, HAIKU.replace("effort: low", "effort: high"))["haiku"].config_hash != base
    )


def test_request_cost_batch_discount_and_long_context():
    prices = load_judges(paths.judges_config_path())["haiku"].prices
    assert request_cost(prices, 100_000, 0) == pytest.approx(0.01)  # seuil : palier normal
    assert request_cost(prices, 100_000, 100_000, batch=True) == pytest.approx(0.03)
    # Au-delà de 100 000 tokens d'entrée, toute la requête passe au palier long.
    assert request_cost(prices, 200_000, 1_000) == pytest.approx(
        (200_000 * 0.50 + 1_000 * 2.50) / 1_000_000
    )
    assert request_cost(None, 10_000, 10_000) == 0.0


def test_estimate_is_prudent():
    prices = {"input_per_mtok": 1.0, "output_per_mtok": 2.0}
    # 10 caractères à 3 par token : 4 tokens (arrondi au-dessus) ; sortie au plafond.
    assert estimate_cost(prices, 10, 100, 3.0) == pytest.approx((4 * 1.0 + 100 * 2.0) / 1e6)


def test_budget_refuses_before_exceeding():
    budget = Budget(1.0)
    budget.check(1.0)
    budget.spend(0.6)
    with pytest.raises(CostCapError):
        budget.check(0.5)
    Budget(None).check(1e9)


def test_split_int_keeps_total():
    assert split_int(10, 4) == [3, 3, 2, 2] and sum(split_int(801, 4)) == 801


@pytest.mark.parametrize(
    ("text", "verdict"),
    [('{"verdict": true}', True), ('```json\n{"verdict": false}\n```', False)],
)
def test_parse_verdict(text, verdict):
    assert parse_verdict(text) is verdict


@pytest.mark.parametrize("text", ["oui", '{"verdict": "true"}', "[true]", ""])
def test_parse_verdict_refuses_without_quoting(text):
    with pytest.raises(UnitError) as info:
        parse_verdict(text)
    assert text not in info.value.reason or not text


def test_prompt_rendering_is_verbatim():
    messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "U $x {y}"}]
    assert render_instruction(messages) == "system : S\n\nuser : U $x {y}"
    output = [
        {"role": "assistant", "content": "brouillon", "turn": 0},
        {"role": "user", "content": "suite", "turn": 1},
        {"role": "assistant", "content": "  <think>x</think> finale ", "turn": 1},
    ]
    assert final_answer(output) == "  <think>x</think> finale "
    assert final_answer([]) == ""
    assert prompt_template_hash("systemone") != prompt_template_hash("anthropic_batch")


def _batch(status, **fields):
    record = {
        "schema": "qb.batch/1",
        "key": f"msgbatch_1|{status}",
        "batch_id": "msgbatch_1",
        "judge": "haiku",
        "manifest": "a" * 64,
        "status": status,
        "created_at": "2026-10-12T08:00:00Z",
    }
    record.update(fields)
    return record


def test_batch_schema():
    validate(_batch("submitted", keys=["k|c1"], estimate_usd=0.01))
    validate(
        _batch(
            "collected",
            counts={"succeeded": 1, "errored": 0, "canceled": 0, "expired": 0},
            tokens={"input": 1, "output": 1},
            cost_usd=0.0,
            outcomes={"k|c1": "ok"},
        )
    )
    with pytest.raises(SchemaValidationError):
        validate(_batch("submitted", keys=[], estimate_usd=0.01))
    with pytest.raises(SchemaValidationError):
        validate(_batch("collected", keys=["k|c1"], estimate_usd=0.0))


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        (
            "    prices: {input_per_mtok: 0.1, output_per_mtok: 0.5, batch_discount: 0.5,\n"
            "             source: test, checked: 2026-10-12}\n",
            "    prices: null\n",
            "prices",
        ),
        ("    effort: low\n", "    effort: low\n    api_key_env: null\n", "api_key_env"),
        ("checked: 2026-10-12", "checked: '2026-13-45'", "checked"),
        ("    effort: low\n", "    effort: low\n    poll_s: 0\n", "poll_s"),
    ],
)
def test_cloud_judge_values_are_checked(tmp_path, old, new, field):
    """Prix et clé nuls pour un juge cloud (coût et plafond nuls sinon), date impossible,
    attente nulle entre deux lectures de lot : refusés."""
    with pytest.raises(ConfigError, match=field):
        _load(tmp_path, HAIKU.replace(old, new))
