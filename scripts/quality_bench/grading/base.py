"""Résultat d'un correcteur (AD-10) : ``Grade`` et ses constructeurs.

Un correcteur est une fonction pure ``grade(question, generation, verdicts=None) -> Grade``.
``reason`` n'est jamais écrite dans ``grading.jsonl`` : elle sert au journal et ne contient que
des identifiants ou des raisons rédigées par le banc, jamais un extrait de question ou de
réponse.

- ``passed`` / ``failed`` / ``from_success`` : réponse jugée (``ok``), score = success ;
- ``non_compliant`` : sortie hors contrat (JSON illisible ou hors schéma, appel d'outil mal
  formé, borne d'appels) : échec du modèle, score 0 ;
- ``bench_error`` : erreur du banc (vérificateur en défaut, cible illisible, rejeu divergent) :
  ni score ni success ;
- ``awaiting`` : rédaction dont un critère n'a pas encore de verdict.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# Correcteur de la rédaction : sans success binaire, noté sur les verdicts du juge (AD-10).
WRITING_GRADER = "judge_criteria"


@dataclass(frozen=True)
class Grade:
    status: str
    score: float | None
    success: bool | None
    metrics: Mapping[str, float] = field(default_factory=dict)
    reason: str | None = None


def passed(metrics: Mapping[str, float] | None = None) -> Grade:
    return Grade("ok", 1.0, True, dict(metrics or {}))


def failed(metrics: Mapping[str, float] | None = None, reason: str | None = None) -> Grade:
    return Grade("ok", 0.0, False, dict(metrics or {}), reason)


def from_success(success: bool, metrics: Mapping[str, float] | None = None) -> Grade:
    return passed(metrics) if success else failed(metrics)


def scored(score: float, metrics: Mapping[str, float] | None = None) -> Grade:
    """Note continue sans succès binaire (rédaction)."""
    return Grade("ok", float(score), None, dict(metrics or {}))


def non_compliant(reason: str, metrics: Mapping[str, float] | None = None) -> Grade:
    return Grade("non_compliant", 0.0, False, dict(metrics or {}), reason)


def bench_error(reason: str) -> Grade:
    return Grade("error", None, None, {}, reason)


def awaiting(reason: str | None = None) -> Grade:
    return Grade("awaiting_judgment", None, None, {}, reason)
