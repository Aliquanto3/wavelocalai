"""Rédaction : ``judge_criteria@2`` (verdicts du code et du juge retenu, AD-10, AD-16).

Un critère qui porte un ``check`` (comptage, ``questions/checks.py``) est vérifié par le code sur
la réponse finale (``grading/counting.py``) : le juge ne le voit pas. Les autres critères sont
jugés. ``verdicts`` : ``{critère: {"verdict": bool | None, "error": str | None}}`` lu dans le seul
dossier ``judgment-<grading.judge>/``, ou ``None`` sans juge désigné ou sans dossier.

- un critère de comptage mal formé : erreur du banc ;
- un verdict du juge en erreur : erreur du banc ;
- un critère jugé sans verdict (ou aucun verdict) : ``awaiting_judgment`` ; sans critère jugé,
  aucun verdict n'est attendu ;
- sinon ``score`` = part des critères vrais (code et juge) sur **tous** les ``criteria``,
  ``success = null``.

``judge_criteria@1`` (jeu ``set-v1``) ne connaissait que le juge : la version change avec le
code de vérification.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .answer import final_answer
from .base import Grade, awaiting, bench_error, scored
from .counting import CheckError, evaluate_checks


def code_verdicts(question: Mapping[str, Any], answer: str) -> dict[str, bool]:
    """Verdicts par critère vérifié par le code (``CheckError`` si un ``check`` est mal formé)."""
    return {
        criterion["id"]: evaluate_checks(criterion["check"], answer)
        for criterion in question["criteria"]
        if criterion.get("check") is not None
    }


def judge_criteria(
    question: Mapping[str, Any],
    generation: Mapping[str, Any],
    verdicts: Mapping[str, Mapping[str, Any]] | None = None,
) -> Grade:
    criteria = question.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return bench_error("question de rédaction sans critères")
    try:
        by_code = code_verdicts(question, final_answer(generation).text)
    except CheckError:
        return bench_error("critère de comptage mal formé")
    judged = [criterion["id"] for criterion in criteria if criterion["id"] not in by_code]
    if judged and verdicts is None:
        return awaiting("aucun jugement disponible")
    verdicts = verdicts or {}
    if any(
        verdicts[criterion].get("error") is not None or verdicts[criterion].get("verdict") is None
        for criterion in judged
        if criterion in verdicts
    ):
        return bench_error("verdict du juge en erreur")
    if any(criterion not in verdicts for criterion in judged):
        return awaiting("critère sans verdict")
    true_count = sum(by_code.values()) + sum(
        1 for criterion in judged if verdicts[criterion]["verdict"] is True
    )
    return scored(true_count / len(criteria))
