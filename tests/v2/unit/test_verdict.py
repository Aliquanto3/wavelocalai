"""Verdict local/cloud (story 3.5) : table de prix de `Settings` et calcul pur, sans serveur.

Les prix de ces tests sont fictifs (ils servent à vérifier l'arithmétique) : la vraie table de
`wavelocalai.toml` est vide tant qu'aucun prix sourcé n'est relevé.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wavelocalai.config import DEFAULT_TOML, ConfigError, PriceTable, load_settings
from wavelocalai.runs.verdict import (
    MODEL_NOT_PRICED,
    NO_PRICE_TABLE,
    REQUESTS,
    TOKENS_NOT_COUNTED,
    build_verdict,
)

PRICES = PriceTable.model_validate(
    {
        "currency": "EUR",
        "retrieved_at": "2026-03-04",
        "source": "https://exemple.invalid/prix",
        "models": {
            "fake/cloud": {"input_per_mtok": 2.0, "output_per_mtok": 10.0},
            "fake/cheap": {"input_per_mtok": 0.1, "output_per_mtok": 0.5},
        },
    }
)
CO2 = {
    "mg": 1.5,
    "method": "codecarbon",
    "estimated": False,
    "range_mg": None,
    "allocation": "direct",
    "reason": None,
}


def leaf(model, origin, kind="generation", input_tokens=4, output_tokens=12, co2=CO2):
    return {
        "kind": kind,
        "model": model,
        "metrics": {
            "origin": origin,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "co2": co2,
        },
    }


def children(*extra):
    return [leaf("fake:a", "local"), leaf("fake/cloud", "cloud"), *extra]


# --- Table de prix --------------------------------------------------------------------------------


def test_the_shipped_toml_loads_with_its_price_table():
    settings = load_settings(DEFAULT_TOML, env_file=Path("absent.env"), environ={})
    prices = settings.cloud.prices
    assert prices.currency == "USD"  # les quatre fournisseurs publient leurs prix en dollars
    assert prices.retrieved_at is not None and len(prices.models) == 8
    # Aucune entrée sans date ni source : soit la table est vide, soit elle est datée et sourcée.
    assert not prices.models or (prices.retrieved_at is not None and prices.source)


def test_a_price_table_is_read_from_the_toml_with_its_date(tmp_path):
    toml = tmp_path / "wavelocalai.toml"
    toml.write_text(
        '[cloud.prices]\ncurrency = "USD"\nretrieved_at = 2026-03-04\nsource = "https://x.invalid"\n'
        '[cloud.prices.models]\n"fake/cloud" = { input_per_mtok = 2.0, output_per_mtok = 10.0 }\n',
        encoding="utf-8",
    )
    prices = load_settings(toml, tmp_path / "absent.env", environ={}).cloud.prices
    assert (prices.currency, prices.retrieved_at.isoformat()) == ("USD", "2026-03-04")
    assert prices.models["fake/cloud"].output_per_mtok == 10.0


@pytest.mark.parametrize(
    "content",
    [
        # Une entrée sans date de relevé, ou sans source : refusée.
        '[cloud.prices]\nsource = "x"\n[cloud.prices.models]\n"a/b" = { input_per_mtok = 1, output_per_mtok = 1 }\n',
        "[cloud.prices]\nretrieved_at = 2026-03-04\n[cloud.prices.models]\n"
        '"a/b" = { input_per_mtok = 1, output_per_mtok = 1 }\n',
        # Un prix négatif, une devise qui n'est pas un code à trois lettres.
        '[cloud.prices]\nretrieved_at = 2026-03-04\nsource = "x"\n[cloud.prices.models]\n'
        '"a/b" = { input_per_mtok = -1, output_per_mtok = 1 }\n',
        '[cloud.prices]\ncurrency = "euro"\n',
        '[cloud.prices]\ncurrency = "978"\n',  # trois chiffres : `Intl.NumberFormat` lèverait
        '[cloud.prices]\ncurrency = "eur"\n',
    ],
)
def test_a_price_table_needs_a_date_and_a_source(tmp_path, content):
    toml = tmp_path / "wavelocalai.toml"
    toml.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError, match="Réglages invalides"):
        load_settings(toml, tmp_path / "absent.env", environ={})


# --- Calcul ---------------------------------------------------------------------------------------


def test_the_verdict_compares_the_best_local_with_the_best_cloud():
    lanes = [
        leaf("fake:a", "local"),
        leaf("fake:b", "local"),
        leaf("fake/cloud", "cloud"),
        leaf("fake/cheap", "cloud"),
    ]
    scores = {"fake:a": 61, "fake:b": 80, "fake/cloud": 90, "fake/cheap": 70}
    verdict = build_verdict(lanes, scores, PRICES)
    assert verdict["leader"] == "cloud" and verdict["score_gap"] == 10
    assert verdict["local"]["model"] == "fake:b" and verdict["local"]["score"] == 80
    assert verdict["cloud"]["model"] == "fake/cloud" and verdict["cloud"]["score"] == 90
    assert verdict["local"]["co2"] == CO2 and verdict["cloud"]["co2"] == CO2
    assert verdict["requests"] == REQUESTS == 1000
    # Les modèles locaux de la comparaison sont tous restés sur le poste.
    assert verdict["data_on_device"] == {
        "models": ["fake:a", "fake:b"],
        "count": 2,
        "judge_off_device": False,
    }


def test_a_local_model_ahead_and_a_tie_are_told_apart():
    ahead = build_verdict(children(), {"fake:a": 75, "fake/cloud": 70}, PRICES)
    assert (ahead["leader"], ahead["score_gap"]) == ("local", 5)
    tie = build_verdict(children(), {"fake:a": 70, "fake/cloud": 70}, PRICES)
    assert (tie["leader"], tie["score_gap"]) == ("tie", 0)


def test_the_cost_of_1000_requests_uses_the_dated_price_of_the_cloud_model():
    lanes = [
        leaf("fake:a", "local"),
        leaf("fake/cloud", "cloud", input_tokens=800, output_tokens=500),
    ]
    verdict = build_verdict(lanes, {"fake:a": 50, "fake/cloud": 60}, PRICES)
    # 1 000 x (800 x 2 + 500 x 10) / 1 000 000 = 6,6
    assert verdict["cloud"]["cost"] == {"amount": 6.6, "currency": "EUR", "reason": None}
    assert verdict["local"]["cost"] == {"amount": 0.0, "currency": "EUR", "reason": None}
    assert verdict["price_table"] == {
        "retrieved_at": "2026-03-04",
        "source": "https://exemple.invalid/prix",
        "currency": "EUR",
    }


def test_a_cloud_model_missing_from_the_price_table_has_an_unknown_cost_with_a_reason():
    lanes = [leaf("fake:a", "local"), leaf("fake/other", "cloud")]
    verdict = build_verdict(lanes, {"fake:a": 50, "fake/other": 60}, PRICES)
    cost = verdict["cloud"]["cost"]
    assert cost["amount"] is None and cost["reason"] == MODEL_NOT_PRICED  # jamais 0
    assert verdict["price_table"]["retrieved_at"] == "2026-03-04"  # la date reste dite


def test_an_empty_price_table_gives_an_unknown_cost():
    verdict = build_verdict(children(), {"fake:a": 50, "fake/cloud": 60}, PriceTable())
    assert verdict["cloud"]["cost"]["amount"] is None
    assert verdict["cloud"]["cost"]["reason"] == NO_PRICE_TABLE
    assert (
        verdict["price_table"]["retrieved_at"] is None and verdict["price_table"]["source"] is None
    )
    assert verdict["local"]["cost"]["amount"] == 0.0  # le local reste à 0


def test_a_cloud_model_without_counted_tokens_has_an_unknown_cost():
    lanes = [leaf("fake:a", "local"), leaf("fake/cloud", "cloud", output_tokens=None)]
    verdict = build_verdict(lanes, {"fake:a": 50, "fake/cloud": 60}, PRICES)
    cost = verdict["cloud"]["cost"]
    assert cost["amount"] is None and cost["reason"] == TOKENS_NOT_COUNTED


def test_no_verdict_without_a_scored_cloud_and_a_scored_local_model():
    only_local = [leaf("fake:a", "local"), leaf("fake:b", "local")]
    assert build_verdict(only_local, {"fake:a": 50, "fake:b": 60}, PRICES) is None
    # Un cloud non noté (juge sans note) ne fait pas de verdict, comme un local non noté.
    assert build_verdict(children(), {"fake:a": 50}, PRICES) is None
    assert build_verdict(children(), {"fake/cloud": 50}, PRICES) is None
    assert build_verdict(children(), {}, PRICES) is None


def test_a_cloud_judge_means_the_local_answers_left_the_device():
    judge = leaf("fake/judge", "cloud", kind="judge")
    verdict = build_verdict(children(judge), {"fake:a": 50, "fake/cloud": 60}, PRICES)
    assert verdict["data_on_device"]["judge_off_device"] is True
    local_judge = leaf("fake:j", "local", kind="judge")
    verdict = build_verdict(children(local_judge), {"fake:a": 50, "fake/cloud": 60}, PRICES)
    assert verdict["data_on_device"]["judge_off_device"] is False


def test_the_judge_leaf_is_never_taken_for_a_lane():
    # Un juge cloud noté (impossible en vrai, mais la feuille `judge` n'est jamais une lane).
    lanes = [leaf("fake:a", "local"), leaf("fake/judge", "cloud", kind="judge")]
    assert build_verdict(lanes, {"fake:a": 50, "fake/judge": 90}, PRICES) is None
