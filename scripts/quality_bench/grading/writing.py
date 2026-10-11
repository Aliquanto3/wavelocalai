"""Rédaction : ``judge_criteria`` (verdicts du juge retenu, AD-16).

``verdicts`` : ``{critère: {"verdict": bool | None, "error": str | None}}`` lu dans le seul
dossier ``judgment-<grading.judge>/``, ou ``None`` sans juge désigné ou sans dossier.

- un verdict en erreur : erreur du banc ;
- un critère sans verdict (ou aucun verdict) : ``awaiting_judgment`` ;
- sinon ``score`` = part des critères jugés vrais sur **tous** les ``criteria``,
  ``success = null``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .base import Grade, awaiting, bench_error, scored


def judge_criteria(
    question: Mapping[str, Any],
    generation: Mapping[str, Any],
    verdicts: Mapping[str, Mapping[str, Any]] | None = None,
) -> Grade:
    criteria = question.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return bench_error("question de rédaction sans critères")
    if verdicts is None:
        return awaiting("aucun jugement disponible")
    ids = [criterion["id"] for criterion in criteria]
    if any(
        verdicts[criterion].get("error") is not None or verdicts[criterion].get("verdict") is None
        for criterion in ids
        if criterion in verdicts
    ):
        return bench_error("verdict du juge en erreur")
    if any(criterion not in verdicts for criterion in ids):
        return awaiting("critère sans verdict")
    true_count = sum(1 for criterion in ids if verdicts[criterion]["verdict"] is True)
    return scored(true_count / len(ids))
