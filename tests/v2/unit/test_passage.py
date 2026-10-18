"""Règles de présentation d'une source (story 4.4) : libellé de pertinence et passage à surligner.

Fonctions pures de `rag/passage.py` : chaque règle écrite dans la story est ici une assertion.
"""

from __future__ import annotations

import pytest

from wavelocalai.config import RagSettings
from wavelocalai.rag.passage import (
    LABEL_CLOSE,
    LABEL_FAR,
    LABEL_VERY_CLOSE,
    LABELS,
    pick_passage,
    relevance_label,
    sentence_spans,
    similarity,
    terms,
)

VERY_CLOSE, CLOSE = 0.75, 0.5  # valeurs exactes en binaire : les bornes se testent sans arrondi


@pytest.mark.parametrize(
    ("distance", "label"),
    [
        (0.0, LABEL_VERY_CLOSE),  # même direction
        (0.1, LABEL_VERY_CLOSE),
        (0.25, LABEL_VERY_CLOSE),  # s = 0,75 : le seuil est inclus dans la classe haute
        (0.2501, LABEL_CLOSE),
        (0.5, LABEL_CLOSE),  # s = 0,5 : seuil inclus
        (0.5001, LABEL_FAR),
        (1.0, LABEL_FAR),  # orthogonal
        (1.7, LABEL_FAR),  # similarité négative ramenée à 0
        (2.0, LABEL_FAR),  # direction opposée
    ],
)
def test_the_label_follows_the_cosine_similarity_thresholds(distance, label):
    assert relevance_label(distance, VERY_CLOSE, CLOSE) == label


def test_a_lower_rank_never_gets_a_better_label():
    order = {label: i for i, label in enumerate(LABELS)}
    labels = [relevance_label(d / 100, VERY_CLOSE, CLOSE) for d in range(0, 201)]
    assert [order[label] for label in labels] == sorted(order[label] for label in labels)
    assert set(labels) == set(LABELS)


def test_the_similarity_is_one_minus_the_cosine_distance():
    assert similarity(0.0) == 1.0 and similarity(0.25) == 0.75 and similarity(1.5) == -0.5


def test_the_default_thresholds_come_from_the_settings_and_stay_ordered():
    rag = RagSettings()
    assert (rag.relevance_very_close, rag.relevance_close) == (0.70, 0.60)
    very, close = rag.relevance_very_close, rag.relevance_close
    assert relevance_label(1 - 0.80, very, close) == LABEL_VERY_CLOSE  # similarité 0,80
    assert relevance_label(1 - 0.65, very, close) == LABEL_CLOSE  # 0,65
    assert relevance_label(1 - 0.50, very, close) == LABEL_FAR  # 0,50
    with pytest.raises(ValueError, match="relevance_close"):
        RagSettings(relevance_very_close=0.5, relevance_close=0.6)


def test_terms_are_folded_without_stopwords_and_cut_at_six_characters():
    assert terms("Où dort le CHAT domestique ?") == {"dort", "chat", "domest"}
    assert terms("Les voitures électriques") == terms("une voiture électrique")  # pluriel
    assert terms("Éléphant, éléphants") == {"elepha"}  # accents retirés
    assert terms("de la le et un") == set()  # mots vides et mots courts


def test_sentences_end_at_a_stop_followed_by_a_space_or_at_a_newline():
    text = "Un premier.  Un deuxième ! Et un troisième ?\nQuatrième ligne\n\n  Cinquième…"
    assert [text[s:e] for s, e in sentence_spans(text)] == [
        "Un premier.", "Un deuxième !", "Et un troisième ?", "Quatrième ligne", "Cinquième…",
    ]  # fmt: skip
    assert sentence_spans("") == [] and sentence_spans("  \n ") == []
    number = "Il consomme 3.5 litres aux cent."  # un point sans espace ne coupe pas
    assert [number[s:e] for s, e in sentence_spans(number)] == [number]


def test_the_passage_is_the_sentence_that_shares_the_most_terms_with_the_question():
    text = (
        "La voiture électrique recharge sa batterie. "
        "Le chat domestique dort sur le canapé du salon. "
        "Le chat chasse la nuit."
    )
    passage = pick_passage("Où dort le chat domestique ?", text)
    assert (
        text[passage["start"] : passage["end"]] == "Le chat domestique dort sur le canapé du salon."
    )
    assert set(passage) == {"start", "end"}


def test_a_tie_goes_to_the_sentence_nearest_the_start_of_the_extract():
    text = "Le chat dort. Le chat mange. Le chien court."
    passage = pick_passage("chat", text)
    assert text[passage["start"] : passage["end"]] == "Le chat dort."


def test_accents_and_plurals_do_not_hide_a_match():
    text = "Rien ici. Les voitures électriques se rechargent la nuit."
    passage = pick_passage("Quelle voiture électrique ?", text)
    assert (
        text[passage["start"] : passage["end"]] == "Les voitures électriques se rechargent la nuit."
    )


def test_no_shared_term_means_no_passage():
    assert pick_passage("Quel est le prix du pétrole ?", "Le chat dort. Le chien court.") is None
    assert (
        pick_passage("Où est-il ?", "Le chat dort. Le chien court.") is None
    )  # que des mots vides
    assert pick_passage("", "Le chat dort.") is None
    assert pick_passage("chat", "") is None


def test_a_sentence_that_is_the_whole_extract_is_not_highlighted():
    assert pick_passage("chat", "Le chat dort sur le canapé.") is None
    assert pick_passage("chat", "  Le chat dort sur le canapé.\n") is None  # espaces de bord
    one_of_two = pick_passage("chat", "Le chat dort sur le canapé. Il fait beau.")
    assert one_of_two == {"start": 0, "end": 27}


def test_positions_are_python_indices_with_the_end_excluded_and_edge_spaces_dropped():
    text = "  \nIntro sans rapport.\n   Le chat dort ici.   Fin."
    passage = pick_passage("chat", text)
    assert text[passage["start"] : passage["end"]] == "Le chat dort ici."


def test_positions_count_code_points_not_utf16_units():
    text = "Fête 🎉🎉 terminée. Le chat dort ici."  # chaque emoji vaut 1 en Python, 2 en JavaScript
    passage = pick_passage("chat", text)
    assert text[passage["start"] : passage["end"]] == "Le chat dort ici."
    assert passage["start"] == len("Fête 🎉🎉 terminée. ")


def test_the_choice_is_deterministic():
    text = "Alpha beta. Gamma delta. Beta gamma."
    assert pick_passage("beta gamma", text) == pick_passage("beta gamma", text)
