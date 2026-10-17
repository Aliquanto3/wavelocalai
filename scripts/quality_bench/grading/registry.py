"""Registre des correcteurs (AD-10) et correction d'une ligne de génération.

``langdetect.DetectorFactory.seed`` est fixé à 0 ici, avant tout chargement du code emprunté
(détection de langue d'IFBench et de M-IFEval FR) : sans graine, ``langdetect`` tire au hasard.

``grade_line(question, generation, verdicts)`` applique l'ordre des statuts : statut de
génération différent de ``ok`` d'abord (``truncated`` : score 0, échec ; ``context_exceeded``
selon ``context_limit`` : ``model`` = score 0, échec compté, ``bench`` = ni score ni succès, comme
``error``), puis la borne d'appels (``non_compliant``), puis le
correcteur de la question. ``metrics.inline_thinking`` (1.0 ou 0.0) figure dans toute ligne
corrigée depuis une sortie ``ok``. Une exception imprévue d'un correcteur est une erreur du
banc. La ligne rendue est une ligne ``qb.grading/1`` sans ``generation_manifest`` ni
``judgment_manifest``, que la commande ``grade`` ajoute.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple

from langdetect import DetectorFactory

DetectorFactory.seed = 0

# Correcteurs : importés après la graine de langdetect (noqa: E402).
from ..questions.schema import GRADERS as GRADER_NAMES  # noqa: E402
from .abstention import abstention_marker  # noqa: E402
from .answer import final_answer  # noqa: E402
from .base import WRITING_GRADER, Grade, bench_error, non_compliant  # noqa: E402
from .extraction import json_schema  # noqa: E402
from .instructions import ifbench, mifeval_fr  # noqa: E402
from .rag import oneruler_cwe, oneruler_niah, squad_f1  # noqa: E402
from .reasoning import exact_answer  # noqa: E402
from .tools import bfcl_ast, bfcl_irrelevance, bfcl_state  # noqa: E402
from .writing import judge_criteria  # noqa: E402

GRADING_SCHEMA_ID = "qb.grading/1"

GraderFunction = Callable[[Mapping[str, Any], Mapping[str, Any], Any], Grade]


@dataclass(frozen=True)
class Registered:
    version: str  # « name@entier »
    function: GraderFunction


_FUNCTIONS: dict[str, GraderFunction] = {
    "exact_answer": exact_answer,
    "ifbench": ifbench,
    "mifeval_fr": mifeval_fr,
    "bfcl_ast": bfcl_ast,
    "bfcl_state": bfcl_state,
    "bfcl_irrelevance": bfcl_irrelevance,
    "json_schema": json_schema,
    "squad_f1": squad_f1,
    "oneruler_niah": oneruler_niah,
    "oneruler_cwe": oneruler_cwe,
    "abstention_marker": abstention_marker,
    "judge_criteria": judge_criteria,
}
# Version par défaut 2 : la sortie de tout correcteur change pour une génération en
# ``context_exceeded`` à ``context_limit = model`` (score 0 au lieu de nul, 2026-10-17).
# json_schema@2 : mots-clés `format` vérifiés ; judge_criteria@2 : critères de comptage
# vérifiés par le code. @3 pour ces deux-là : l'amendement du contexte s'ajoute.
_DEFAULT_VERSION = 2
_VERSIONS = {"json_schema": 3, "judge_criteria": 3}
GRADERS: dict[str, Registered] = {
    name: Registered(f"{name}@{_VERSIONS.get(name, _DEFAULT_VERSION)}", function)
    for name, function in _FUNCTIONS.items()
}
if set(GRADERS) != set(GRADER_NAMES):
    raise RuntimeError("Registre des correcteurs différent de questions/schema.GRADERS")


class GradedLine(NamedTuple):
    """Ligne ``qb.grading/1`` (sans champs de manifeste) et raison journalisable."""

    record: dict[str, Any]
    reason: str | None


def _grade(
    registered: Registered,
    question: Mapping[str, Any],
    generation: Mapping[str, Any],
    verdicts: Any,
) -> tuple[Grade, dict[str, float]]:
    status = generation["status"]
    writing = question["grader"]["name"] == WRITING_GRADER
    if status == "truncated":
        return Grade("truncated", 0.0, None if writing else False, {}, "sortie tronquée"), {}
    if status == "context_exceeded":
        if generation["context_limit"] == "model":
            # Limite du modèle (AD-10) : impropre à cet usage, échec compté comme une troncature.
            reason = "contexte du modèle dépassé"
            return Grade(status, 0.0, None if writing else False, {}, reason), {}
        # Limite du banc : unité nulle, retirée des comparaisons.
        return Grade(status, None, None, {}, "contexte du banc dépassé"), {}
    if status == "error":
        return Grade(status, None, None, {}, f"génération en {status}"), {}
    extra = {"inline_thinking": final_answer(generation).inline_thinking}
    if generation["call_cap_reached"]:
        return non_compliant("borne d'appels d'outils atteinte"), extra
    try:
        grade = registered.function(question, generation, verdicts)
    except Exception as exc:  # noqa: BLE001 (correcteur en défaut : erreur du banc)
        return bench_error(f"{registered.version} en défaut ({type(exc).__name__})"), extra
    return grade, extra


def grade_line(
    question: Mapping[str, Any],
    generation: Mapping[str, Any],
    verdicts: Mapping[str, Mapping[str, Any]] | None = None,
) -> GradedLine:
    """Corrige ``generation`` contre ``question`` (verdicts du juge pour la rédaction)."""
    registered = GRADERS[question["grader"]["name"]]
    grade, extra = _grade(registered, question, generation, verdicts)
    success = grade.success
    if question["grader"]["name"] == WRITING_GRADER:
        success = None  # rédaction : jamais de succès binaire (AD-10)
    record = {
        "schema": GRADING_SCHEMA_ID,
        "key": generation["key"],
        "grader": registered.version,
        "status": grade.status,
        "score": grade.score,
        "success": success,
        "metrics": {**grade.metrics, **extra},
    }
    if grade.status == "context_exceeded":
        record["context_limit"] = generation["context_limit"]
    return GradedLine(record, grade.reason)
