"""Règles pures des stratégies HyDE et Self-RAG et de la vérification des citations (story 4.6)."""

from __future__ import annotations

import pytest

from wavelocalai.rag.strategies import (
    GRADE_EXCERPT_CHARS,
    HYDE_MAX_TOKENS,
    REWRITE_MAX_CHARS,
    clean_query,
    grade_request,
    hyde_request,
    merge_best,
    parse_grade,
    rewrite_request,
    verify_citations,
)


def _item(chunk_id: int, distance: float, text: str = "texte") -> dict:
    return {"chunk_id": chunk_id, "distance": distance, "text": text}


def test_the_hyde_request_asks_for_a_passage_and_carries_the_question_only_once():
    request = hyde_request("Où dort le chat ?")
    assert [m.role for m in request.messages] == ["system", "user"]
    assert request.messages[1].content == "Question : Où dort le chat ?"
    assert "passage" in request.messages[0].content
    assert request.max_tokens == HYDE_MAX_TOKENS and request.temperature < 0.5


def test_the_grade_request_numbers_every_excerpt_and_cuts_a_long_one():
    long = "x" * (GRADE_EXCERPT_CHARS + 500)
    request = grade_request("Q ?", [_item(1, 0.1, "premier"), _item(2, 0.2, long)])
    user = request.messages[1].content
    assert "[1]\npremier" in user and "[2]\n" + "x" * GRADE_EXCERPT_CHARS in user
    assert "x" * (GRADE_EXCERPT_CHARS + 1) not in user
    assert user.endswith("Question : Q ?") and request.temperature == 0.0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 : oui\n2 : non\n3 : oui", {1: True, 2: False, 3: True}),
        ("1: Oui\n2: NON", {1: True, 2: False}),
        ("[1] : oui\n[2] : non", {1: True, 2: False}),
        ("1. oui, 2) non", {1: True, 2: False}),
        ("1 - yes\n2 = no", {1: True, 2: False}),
        ("1 : oui\n1 : non", {1: True}),  # le premier verdict d'un numéro l'emporte
        ("L'extrait 1 n'est pas pertinent.", {}),  # de la prose n'est pas un verdict
        ("", {}),
        ("12 : oui", {12: True}),
        ("2023 : oui", {}),  # une année n'est pas un numéro d'extrait
    ],
)
def test_a_grade_is_read_line_by_line_and_prose_gives_no_verdict(text, expected):
    assert parse_grade(text) == expected


def test_a_rewrite_names_the_last_formulation_only_when_it_differs():
    first = rewrite_request("Q ?", "Q ?").messages[1].content
    assert "Question d'origine : Q ?" in first and "Dernière formulation" not in first
    again = rewrite_request("Q ?", "Autre question ?").messages[1].content
    assert "Dernière formulation essayée : Autre question ?" in again


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Où le chat dort-il ?", "Où le chat dort-il ?"),
        ("  « Où le chat dort-il ? »  \nExplication.", "Où le chat dort-il ?"),
        ('\n\n"Une question"\n', "Une question"),
        ("a   b \t c", "a b c"),
        ("", ""),
        ("   \n  ", ""),
        ("x" * (REWRITE_MAX_CHARS + 50), "x" * REWRITE_MAX_CHARS),
    ],
)
def test_a_rewritten_question_is_the_first_clean_line(text, expected):
    assert clean_query(text) == expected


def test_the_best_excerpts_keep_one_per_chunk_with_its_smallest_distance_and_the_closest_first():
    first = [_item(1, 0.40), _item(2, 0.30), _item(3, 0.50)]
    second = [_item(2, 0.10), _item(4, 0.35), _item(5, 0.60)]
    merged = merge_best([first, second], 4)
    assert [(m["chunk_id"], m["distance"]) for m in merged] == [
        (2, 0.10), (4, 0.35), (1, 0.40), (3, 0.50),
    ]  # fmt: skip
    assert merge_best([], 4) == []
    assert [m["chunk_id"] for m in merge_best([first], 2)] == [2, 1]


def test_only_the_markers_that_name_a_source_are_verified_in_order_of_first_appearance():
    answer = "Le chat dort [2], puis [1] ; [2] encore. Inventé [7] et [0]. Tout [1][2]."
    assert verify_citations(answer, {1, 2, 3}) == [
        {"marker": 2, "n": 2},
        {"marker": 1, "n": 1},
    ]
    assert verify_citations("Aucune source citée.", {1, 2}) == []
    assert verify_citations("Hors liste [4].", {1, 2}) == []
    assert verify_citations("[1] [01] [ 1 ] [1, 2] [a]", {1, 2}) == [{"marker": 1, "n": 1}]
    assert verify_citations("[1]", set()) == []
