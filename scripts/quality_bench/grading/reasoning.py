"""Raisonnement : ``exact_answer`` (BBEH mini, VAR-MATH FR).

- **Cible entière** (VAR-MATH FR) : réponse après le dernier préfixe ``answer_prefix`` (« La
  réponse est : », casse et espace avant « : » libres), première ligne qui suit ; astérisques,
  dollars, ``\\boxed{}``, espaces de milliers et point final retirés ; entier signé comparé
  exactement. Sans préfixe, ou sans entier lisible : échec.
- **Cible chaîne** (BBEH) : ``evaluate_correctness`` de BBEH, tel quel (code emprunté).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .answer import after_prefix, final_answer
from .base import Grade, bench_error, failed, from_success
from .vendored.bbeh.evaluate import evaluate_correctness

_BOXED = re.compile(r"\\boxed\s*\{([^{}]*)\}")
_THOUSANDS = re.compile(r"(?<=\d)[ \u00a0\u202f\u2009](?=\d{3}(?!\d))")
_INTEGER = re.compile(r"^[+-]?\d+$")


def parse_integer(text: str) -> int | None:
    """Entier signé d'une ligne de réponse, ou ``None``."""
    value = _BOXED.sub(r"\1", text)
    value = value.replace("*", "").replace("$", "").replace("\u2212", "-").strip()
    value = _THOUSANDS.sub("", value)
    value = value.rstrip(".").strip()
    if not _INTEGER.match(value):
        return None
    try:
        return int(value)
    except ValueError:  # plus de 4300 chiffres : réponse illisible, échec du modèle
        return None


def exact_answer(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    target = question["target"]
    text = final_answer(generation).text
    if isinstance(target, bool):
        return bench_error("cible exact_answer ni entière ni chaîne")
    if isinstance(target, int):
        prefix = question["grader"]["params"].get("answer_prefix")
        if not isinstance(prefix, str) or not prefix.strip():
            return bench_error("exact_answer : answer_prefix absent pour une cible entière")
        rest = after_prefix(text, prefix)
        if rest is None:
            return failed(reason="préfixe de réponse absent")
        lines = [line for line in rest.strip().splitlines() if line.strip()]
        value = parse_integer(lines[0]) if lines else None
        if value is None:
            return failed(reason="aucun entier lisible après le préfixe")
        return from_success(value == target)
    if isinstance(target, str):
        return from_success(bool(evaluate_correctness(text, target)))
    return bench_error("cible exact_answer ni entière ni chaîne")
