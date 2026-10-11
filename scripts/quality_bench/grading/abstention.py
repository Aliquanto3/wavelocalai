"""Abstention : ``abstention_marker`` (questions maison ``abstention-fr``).

La réponse, débarrassée en bordure des espaces, guillemets (droits, typographiques, chevrons),
astérisques, accents graves et du point final, doit égaler le marqueur imposé par la consigne,
débarrassé de la même façon, sans tenir compte de la casse. (``bfcl_irrelevance`` vit dans ``tools.py`` ; la variante sans
aiguille de OneRuler, dans ``rag.py``.)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .answer import final_answer
from .base import Grade, bench_error, from_success

_EDGE_CHARS = "\"'*`«»“”‘’„"


def strip_marker(text: str) -> str:
    """Retire, en bordure et jusqu'à stabilité, espaces, guillemets, ``*``, `` ` `` et point
    final."""
    previous = None
    while previous != text:
        previous = text
        text = text.strip().strip(_EDGE_CHARS).strip()
        if text.endswith("."):
            text = text[:-1]
    return text


def abstention_marker(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    marker = question["grader"]["params"].get("marker")
    if not isinstance(marker, str) or not strip_marker(marker):
        return bench_error("marqueur d'abstention absent")
    answer = strip_marker(final_answer(generation).text)
    return from_success(answer.casefold() == strip_marker(marker).casefold())
