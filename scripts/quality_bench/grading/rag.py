"""RAG : ``squad_f1`` (PIAF), ``oneruler_niah`` et ``oneruler_cwe`` (OneRuler FR).

- ``squad_f1`` : normalisation française de la réponse et de chaque réponse admise
  (minuscules, apostrophes en espaces, ponctuation retirée, articles ``le la les l un une des
  du d`` retirés, espaces réduits ; une réponse admise vide après normalisation est écartée, et
  une cible sans réponse admise non vide est une erreur du banc) ; ``success`` = correspondance
  exacte avec une réponse
  admise ; ``metrics.f1`` = meilleur F1 de jetons (SQuAD).
- ``oneruler_niah`` : ``compare_numbers`` de OneRuler (langue ``fr``) sur la réponse finale ;
  cible nulle (``oneruler-fr-none``) : ``compare_none``, réponse attendue ``none_answer``.
- ``oneruler_cwe`` : ``is_correct_order`` de OneRuler (les 10 mots attendus présents).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from typing import Any

from .answer import final_answer
from .base import Grade, bench_error, from_success
from .vendored.oneruler.evaluate import compare_none, compare_numbers, is_correct_order

LANGUAGE = "fr"
ARTICLES = frozenset({"le", "la", "les", "l", "un", "une", "des", "du", "d"})
_APOSTROPHES = re.compile(r"['’‘ʼ`´]")


def normalize_fr(text: str) -> str:
    """Normalisation française des réponses PIAF (voir la docstring du module)."""
    text = unicodedata.normalize("NFC", text).lower()
    text = _APOSTROPHES.sub(" ", text)
    text = "".join(
        char
        for char in text
        if not unicodedata.category(char).startswith("P") and char not in "$+<=>^|~"
    )
    return " ".join(token for token in text.split() if token not in ARTICLES)


def token_f1(prediction: str, reference: str) -> float:
    """F1 de jetons (SQuAD) entre deux textes déjà normalisés."""
    predicted, expected = prediction.split(), reference.split()
    if not predicted or not expected:
        return float(predicted == expected)
    common = sum((Counter(predicted) & Counter(expected)).values())
    if common == 0:
        return 0.0
    precision, recall = common / len(predicted), common / len(expected)
    return 2 * precision * recall / (precision + recall)


def squad_f1(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    answers = question["target"]
    if not isinstance(answers, list) or not answers or not all(isinstance(a, str) for a in answers):
        return bench_error("cible PIAF illisible")
    prediction = normalize_fr(final_answer(generation).text)
    # Une réponse admise vide après normalisation (article seul, ponctuation) ne compte pas :
    # sinon une réponse vide du modèle serait une correspondance exacte.
    references = [reference for reference in map(normalize_fr, answers) if reference]
    if not references:
        return bench_error("cible PIAF vide après normalisation")
    exact = any(prediction == reference for reference in references)
    best = max(token_f1(prediction, reference) for reference in references)
    return from_success(exact, {"f1": best})


def oneruler_niah(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    target = question["target"]
    text = final_answer(generation).text
    if target is None:
        none_answer = question["grader"]["params"].get("none_answer")
        if not isinstance(none_answer, str) or not none_answer:
            return bench_error("none_answer absent pour une cible nulle")
        return from_success(bool(compare_none(LANGUAGE, [none_answer], text)))
    if not isinstance(target, list) or not target or not all(isinstance(v, str) for v in target):
        return bench_error("cible OneRuler NIAH illisible")
    return from_success(bool(compare_numbers(LANGUAGE, target, text)))


def oneruler_cwe(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    target = question["target"]
    if not isinstance(target, list) or not target or not all(isinstance(w, str) for w in target):
        return bench_error("cible OneRuler CWE illisible")
    return from_success(bool(is_correct_order(target, final_answer(generation).text)))
