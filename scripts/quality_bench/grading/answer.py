"""Extraction de la réponse d'une ligne de génération (AD-10) : seul module qui lit ``output``.

- ``final_answer`` : contenu du dernier message ``assistant``, réflexion en ligne retirée ;
- ``decode_json`` : objet JSON de la réponse, clôture Markdown comprise ;
- ``tool_calls_by_turn`` et ``tool_steps`` : appels d'outils du modèle, ``ToolCallError`` si un
  appel est mal formé (échec du modèle, ``non_compliant``) ; ``answered_turns`` : tours où le
  modèle a répondu ;
- ``after_prefix`` : texte qui suit la dernière occurrence d'un préfixe de réponse ;
- ``decode_floats`` : flottants de cible encodés ``{"$float": repr}`` (``questions/build.py``).

Noyau pur : aucune I/O, aucune copie modifiée de l'entrée.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..questions.build import FLOAT_MARKER

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
_FENCE_RE = re.compile(r"^```[A-Za-z0-9_+-]*[ \t]*\r?\n(?P<body>.*?)\r?\n?```$", re.DOTALL)


class JsonAnswerError(ValueError):
    """Réponse qui n'est pas un JSON lisible (échec du modèle)."""


class ToolCallError(ValueError):
    """Appel d'outil mal formé : sans nom, ou arguments qui ne sont pas un objet."""


@dataclass(frozen=True)
class Answer:
    """Réponse finale et indicateur de réflexion en ligne (1.0 si une balise figurait)."""

    text: str
    inline_thinking: float


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolStep:
    """Un message ``assistant`` avec appels d'outils et les contenus ``tool`` qui le suivent."""

    turn: int
    calls: tuple[ToolCall, ...]
    contents: tuple[str, ...]


def strip_inline_thinking(content: str) -> Answer:
    """Texte après la dernière ``</think>`` ; balise ouvrante seule : texte avant elle."""
    if THINK_CLOSE in content:
        return Answer(content.rsplit(THINK_CLOSE, 1)[1].strip(), 1.0)
    if THINK_OPEN in content:
        return Answer(content.split(THINK_OPEN, 1)[0].strip(), 1.0)
    return Answer(content.strip(), 0.0)


def final_answer(generation: Mapping[str, Any]) -> Answer:
    """Réponse finale : dernier message ``assistant`` de ``output`` (chaîne vide s'il n'y en a
    aucun), réflexion en ligne retirée, espaces de bord retirés."""
    for message in reversed(generation.get("output") or []):
        if message.get("role") == "assistant":
            return strip_inline_thinking(message.get("content") or "")
    return Answer("", 0.0)


def _reject_constant(name: str) -> Any:
    raise JsonAnswerError(f"constante JSON non standard : {name}")


def decode_json(text: str) -> Any:
    """Valeur JSON de ``text`` : texte entier, ou bloc unique entre clôtures Markdown
    (```` ```json … ``` ````). ``NaN`` et ``Infinity`` sont refusés (JSON strict)."""
    body = text.strip()
    match = _FENCE_RE.match(body)
    if match:
        body = match["body"].strip()
    try:
        return json.loads(body, parse_constant=_reject_constant)
    except (ValueError, RecursionError):  # JSONDecodeError, entier de plus de 4300 chiffres
        raise JsonAnswerError("réponse JSON illisible") from None


def _parse_call(call: Any) -> ToolCall:
    function = call.get("function") if isinstance(call, Mapping) else None
    if not isinstance(function, Mapping):
        raise ToolCallError("appel d'outil sans champ function")
    name = function.get("name")
    if not isinstance(name, str) or not name:
        raise ToolCallError("appel d'outil sans nom")
    arguments = function.get("arguments")
    if not isinstance(arguments, Mapping):
        raise ToolCallError("arguments d'appel d'outil qui ne sont pas un objet")
    return ToolCall(name, dict(arguments))


def tool_steps(generation: Mapping[str, Any]) -> list[ToolStep]:
    """Pas d'outils dans l'ordre de ``output`` : chaque message ``assistant`` qui porte des
    appels, avec les contenus des messages ``tool`` consécutifs qui le suivent."""
    output = generation.get("output") or []
    steps = []
    for index, message in enumerate(output):
        if message.get("role") != "assistant" or not message.get("tool_calls"):
            continue
        calls = tuple(_parse_call(call) for call in message["tool_calls"])
        contents = []
        for follower in output[index + 1 :]:
            if follower.get("role") != "tool":
                break
            contents.append(follower.get("content", ""))
        steps.append(ToolStep(int(message.get("turn", 0)), calls, tuple(contents)))
    return steps


def answered_turns(generation: Mapping[str, Any]) -> set[int]:
    """Tours où le modèle a produit au moins un message ``assistant``."""
    return {
        message.get("turn")
        for message in generation.get("output") or []
        if message.get("role") == "assistant"
    }


def tool_calls_by_turn(generation: Mapping[str, Any]) -> dict[int, list[ToolCall]]:
    """Appels d'outils du modèle par tour (tous les pas du tour, dans l'ordre)."""
    by_turn: dict[int, list[ToolCall]] = {}
    for step in tool_steps(generation):
        by_turn.setdefault(step.turn, []).extend(step.calls)
    return by_turn


def _prefix_pattern(prefix: str) -> re.Pattern[str]:
    """Préfixe sans tenir compte de la casse ; entre deux mots, un ou plusieurs espaces ;
    avant « : », un espace facultatif (« La réponse est: » comme « La réponse est : »)."""
    words = re.split(r"(\s+|:)", prefix.strip())
    parts = []
    for token in words:
        if not token or token.isspace():
            continue
        if token == ":":
            parts.append(r"\s*:")
        else:
            if parts and parts[-1] != r"\s*:":
                parts.append(r"\s+")
            elif parts:
                parts.append(r"\s*")
            parts.append(re.escape(token))
    return re.compile("".join(parts), re.IGNORECASE)


def after_prefix(text: str, prefix: str) -> str | None:
    """Texte qui suit la dernière occurrence de ``prefix`` (casse et espaces libres), ou
    ``None`` si le préfixe est absent."""
    matches = list(_prefix_pattern(prefix).finditer(text))
    if not matches:
        return None
    return text[matches[-1].end() :]


def decode_floats(value: Any) -> Any:
    """Copie de ``value`` où chaque ``{"$float": repr}`` redevient un flottant."""
    if isinstance(value, Mapping):
        if set(value) == {FLOAT_MARKER} and isinstance(value[FLOAT_MARKER], str):
            return float(value[FLOAT_MARKER])
        return {key: decode_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_floats(item) for item in value]
    return value
