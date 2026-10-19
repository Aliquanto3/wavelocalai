"""Invites, lecture des sorties du juge, notes et résumé de l'évaluation de la qualité (story 7.1).

Fonctions pures : aucun modèle, aucune base, aucun réseau.
"""

from __future__ import annotations

import json

import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.evaluation import prompts, scoring
from wavelocalai.runs.eval_snapshot import (
    METRICS,
    NOT_EVALUATED_STOPPED,
    aggregate,
    missing_rows,
    summarize,
)

SOURCES = [
    {"n": 1, "document": "chats.txt", "page": None, "text": "Le chat dort sur le canapé."},
    {"n": 2, "document": "guide.pdf", "page": 3, "text": "La voiture recharge sa batterie."},
]


def _reply(**value) -> str:
    return json.dumps(value)


# --- invites -----------------------------------------------------------------------------------


def test_every_request_asks_for_a_structured_output_at_zero_temperature():
    requests = [
        (prompts.claims_request("Q ?", "R."), prompts.CLAIMS_SCHEMA),
        (prompts.verdict_request("Une affirmation.", SOURCES), prompts.VERDICT_SCHEMA),
        (prompts.questions_request("R."), prompts.QUESTIONS_SCHEMA),
        (prompts.useful_request("Q ?", "R.", SOURCES), prompts.USEFUL_SCHEMA),
    ]
    for request, schema in requests:
        assert request.response_schema is schema and request.temperature == 0.0
        assert [m.role for m in request.messages] == ["system", "user"]


def test_the_extracts_are_numbered_with_their_document_and_page():
    text = prompts.verdict_request("Le chat dort.", SOURCES).messages[-1].content
    assert "[1] (chats.txt)\nLe chat dort sur le canapé." in text
    assert "[2] (guide.pdf, page 3)\nLa voiture recharge sa batterie." in text
    assert text.endswith("Affirmation à vérifier :\nLe chat dort.")


def test_a_very_long_answer_is_cut_for_the_judge():
    shown = (
        prompts.claims_request("Q ?", "a" * (prompts.MAX_ANSWER_CHARS + 50)).messages[-1].content
    )
    assert "[…réponse tronquée]" in shown and "a" * (prompts.MAX_ANSWER_CHARS + 1) not in shown


# --- lecture des sorties -----------------------------------------------------------------------


def test_claims_are_cleaned_deduplicated_and_capped():
    many = [f"Affirmation {i}." for i in range(15)]
    claims = prompts.parse_claims(_reply(claims=["  Le chat   dort. ", "", "Le chat dort.", *many]))
    assert claims[0] == "Le chat dort." and len(claims) == prompts.MAX_CLAIMS
    assert prompts.parse_claims(_reply(claims=[])) == []
    long = prompts.parse_claims(_reply(claims=["x" * 1000]))
    assert len(long[0]) == prompts.MAX_CLAIM_CHARS


@pytest.mark.parametrize("text", ["pas du JSON", "[]", _reply(claims="oui"), _reply(autre=[])])
def test_unusable_claims_are_invalid_output(text):
    with pytest.raises(ProviderError) as error:
        prompts.parse_claims(text)
    assert error.value.code == "invalid_output"


def test_a_fenced_json_is_tolerated():
    fenced = "```json\n" + _reply(claims=["A."]) + "\n```"
    assert prompts.parse_claims(fenced) == ["A."]


def test_a_verdict_keeps_the_judge_word_and_drops_an_unknown_extract():
    ok = prompts.parse_verdict(_reply(verdict="appuyée", support=2, reason=" Dit. "), 2)
    assert ok == {"verdict": "appuyée", "support": 2, "reason": "Dit."}
    beyond = prompts.parse_verdict(_reply(verdict="appuyée", support=9, reason="x"), 2)
    assert beyond["verdict"] == "appuyée" and beyond["support"] is None  # le verdict reste
    unsupported = prompts.parse_verdict(_reply(verdict="non appuyée", support=1, reason="x"), 2)
    assert unsupported["support"] is None
    contradicted = prompts.parse_verdict(_reply(verdict="contredite", support=1, reason="x"), 2)
    assert contradicted["support"] == 1


@pytest.mark.parametrize(
    "value",
    [
        {"verdict": "peut-être", "support": 1, "reason": "x"},
        {"verdict": "appuyée", "support": "1", "reason": "x"},
        {"verdict": "appuyée", "reason": "x"},
        {"verdict": "appuyée", "support": None, "reason": "x", "extra": 1},
    ],
)
def test_an_invalid_verdict_is_invalid_output(value):
    with pytest.raises(ProviderError):
        prompts.parse_verdict(json.dumps(value), 2)


def test_retrieved_questions_and_useful_extracts_are_read():
    assert prompts.parse_questions(_reply(questions=["Q1 ?", "Q1 ?", "Q2 ?", "Q3 ?", "Q4 ?"])) == [
        "Q1 ?",
        "Q2 ?",
        "Q3 ?",
    ]
    assert prompts.parse_questions(_reply(questions=[])) == []
    numbers, reason = prompts.parse_useful(_reply(useful=[2, 2, 7, 0, 1], reason=" Oui. "), 2)
    assert numbers == [1, 2] and reason == "Oui."
    assert prompts.parse_useful(_reply(useful=[], reason="Aucun."), 2) == ([], "Aucun.")


# --- notes -------------------------------------------------------------------------------------


def _verdicts(*words: str) -> list[dict]:
    return [{"claim": f"c{i}", "verdict": w, "support": None} for i, w in enumerate(words)]


def test_faithfulness_is_the_share_of_supported_claims_out_of_100():
    s, n, c = prompts.SUPPORTED, prompts.UNSUPPORTED, prompts.CONTRADICTED
    assert scoring.faithfulness(_verdicts(s, s, n)) == 67
    assert scoring.faithfulness(_verdicts(s, s, s, s, s, s, s, n)) == 88  # 7 sur 8 : 87,5 arrondi
    assert scoring.faithfulness(_verdicts(n, c)) == 0  # une vraie note, pas un « non évalué »
    assert scoring.faithfulness(_verdicts(s)) == 100
    with pytest.raises(ValueError):
        scoring.faithfulness([])


def test_relevance_is_the_mean_cosine_clamped_to_zero_and_one():
    assert scoring.cosine([1, 0], [1, 0]) == 1.0 and scoring.cosine([1, 0], [0, 1]) == 0.0
    assert scoring.cosine([0, 0], [1, 0]) == 0.0  # vecteur nul : aucune proximité démontrée
    assert scoring.relevance([1, 0], [[1, 0], [0, 1]]) == (50, 0.5)
    assert scoring.relevance([1, 0], [[-1, 0]])[0] == 0  # cosinus négatif : 0, jamais négatif
    with pytest.raises(ValueError):
        scoring.relevance([1, 0], [])


def test_context_precision_is_the_share_of_useful_extracts():
    assert scoring.context_precision([1, 3], 4) == 50
    assert scoring.context_precision([], 4) == 0
    assert scoring.context_precision([1, 2, 3, 4], 4) == 100


# --- résumé et notes manquantes ----------------------------------------------------------------


def test_the_mean_only_counts_the_scored_questions_and_says_how_many_are_missing():
    assert aggregate([80, None, 60], 3) == {
        "score": 70,
        "evaluated": 2,
        "not_evaluated": 1,
        "total": 3,
    }
    assert aggregate([None, None], 2)["score"] is None  # aucune note : pas de 0
    assert aggregate([80], 8) == {"score": 80, "evaluated": 1, "not_evaluated": 7, "total": 8}
    assert aggregate([0, 1], 2)["score"] == 1  # 0,5 arrondi à la moitié supérieure


def _row(lane: str, index: int, metric: str, score: int | None) -> dict:
    return {"lane": lane, "question_index": index, "metric": metric, "score": score, "reason": "r"}


def test_summary_and_missing_rows_cover_every_model_question_and_metric():
    rows = [_row("a", 0, "faithfulness", 90), _row("a", 0, "relevance", None)]
    summary = summarize(rows, ["a", "b"], 2)
    assert set(summary) == {"a", "b"} and set(summary["a"]) == set(METRICS)
    assert summary["a"]["faithfulness"]["score"] == 90
    assert summary["a"]["relevance"] == {
        "score": None, "evaluated": 0, "not_evaluated": 2, "total": 2
    }  # fmt: skip
    missing = missing_rows(rows, ["a", "b"], 2)
    assert len(missing) == 2 * 2 * 3 - 2
    assert all(m["score"] is None and m["reason"] == NOT_EVALUATED_STOPPED for m in missing)
    assert ("a", 0, "faithfulness") not in {
        (m["lane"], m["question_index"], m["metric"]) for m in missing
    }
