"""Conversation d'une question (AD-7, AD-11, contrat d'outils de ``questions/SOURCES.md``).

``run_conversation(question, chat, *, num_ctx, num_predict, max_tool_calls_per_turn)`` déroule
les tours d'une question avec ``chat(messages, tools) -> ChatResult`` injecté (le runner y lie
modèle, graine, ``num_ctx``, ``num_predict``, ``format`` et ``think``), et rend un ``Outcome``
brut : ni score, ni réponse analysée (AD-3).

- **Sortie :** ``output`` = messages postérieurs à ``messages``, chacun annoté ``turn`` :
  réponses ``assistant`` (``content``, ``thinking`` ou ``None``, ``tool_calls``), messages
  ``tool`` et messages des tours suivants (``turns[t-1]``, ``turn = t``).
- **Statut :** ``context_exceeded`` si un appel donne ``prompt_eval_count +
  prompt_eval_cached_count ≥ num_ctx − num_predict`` ; sinon ``truncated`` dès qu'un appel rend
  ``done_reason == "length"`` ; la question s'arrête alors. Sinon ``ok``.
- **Outils, ``env`` non nul :** ``make_env(env)`` neuf par essai ; ``env.call(name,
  arguments)`` pour chaque appel, dans l'ordre, contenu rendu tel quel dans un message ``tool``,
  puis nouvel appel du modèle ; le tour s'achève sur une réponse sans appel. Un pas dont les
  appels porteraient le total du tour au-delà de ``max_tool_calls_per_turn`` n'est pas exécuté :
  ``call_cap_reached``, la question s'arrête.
- **Outils, ``env`` nul :** le tour s'achève sur la première réponse, appels compris, sans
  message ``tool`` (BFCL ne lit que la première réponse).
- **Appel mal formé** (sans nom, arguments qui ne sont pas un objet) : la question s'arrête,
  sortie gardée (``grade`` le compte ``non_compliant``).

Une exception de ``chat`` est relevée dans ``ChatFailedError`` avec la sortie partielle de l'essai :
c'est au runner de décider (AD-13).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..envs.registry import make_env

STATUS_OK = "ok"
STATUS_TRUNCATED = "truncated"
STATUS_CONTEXT_EXCEEDED = "context_exceeded"

ChatFunction = Callable[[list[dict[str, Any]], "Sequence[Mapping[str, Any]] | None"], Any]


def empty_tokens() -> dict[str, int]:
    return {"prompt": 0, "prompt_cached": 0, "completion": 0, "thinking_est": 0, "answer_est": 0}


def empty_durations() -> dict[str, int]:
    return {"total": 0, "load": 0, "prompt_eval": 0, "eval": 0}


@dataclass
class Outcome:
    """Résultat brut d'un essai : statut, sortie et compteurs sommés sur les appels."""

    status: str = STATUS_OK
    output: list[dict[str, Any]] = field(default_factory=list)
    call_cap_reached: bool = False
    calls: int = 0
    tokens: dict[str, int] = field(default_factory=empty_tokens)
    durations_ns: dict[str, int] = field(default_factory=empty_durations)
    wall_s: float = 0.0
    # Prompt mesuré de l'appel en dépassement (``context_exceeded``) : fonde sa cause (AD-7).
    context_prompt: int = 0

    def add_call(self, result: Any) -> None:
        self.calls += 1
        self.tokens["prompt"] += result.prompt_eval_count
        self.tokens["prompt_cached"] += result.prompt_eval_cached_count
        self.tokens["completion"] += result.eval_count
        self.tokens["thinking_est"] += result.chunks.get("thinking", 0)
        self.tokens["answer_est"] += result.chunks.get("content", 0)
        for name in self.durations_ns:
            self.durations_ns[name] += int(result.durations_ns.get(name, 0))
        self.wall_s += float(result.wall_s)


class ChatFailedError(Exception):
    """Un appel de ``chat`` a levé ``cause`` ; ``partial`` porte la sortie de l'essai."""

    def __init__(self, cause: BaseException, partial: Outcome) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.partial = partial


def well_formed(call: Any) -> bool:
    """Appel d'outil lisible : ``function.name`` chaîne non vide, ``function.arguments`` objet."""
    function = call.get("function") if isinstance(call, Mapping) else None
    if not isinstance(function, Mapping):
        return False
    name = function.get("name")
    return isinstance(name, str) and bool(name) and isinstance(function.get("arguments"), Mapping)


def _assistant_output(result: Any, turn: int) -> dict[str, Any]:
    return {
        "turn": turn,
        "role": "assistant",
        "content": result.content,
        "thinking": result.thinking or None,
        "tool_calls": [dict(call) for call in result.tool_calls],
    }


def _assistant_message(result: Any) -> dict[str, Any]:
    """Réponse renvoyée au modèle telle qu'Ollama l'a rendue (réflexion et appels compris)."""
    message: dict[str, Any] = {"role": "assistant", "content": result.content}
    if result.thinking:
        message["thinking"] = result.thinking
    if result.tool_calls:
        message["tool_calls"] = [dict(call) for call in result.tool_calls]
    return message


def run_conversation(
    question: Mapping[str, Any],
    chat: ChatFunction,
    *,
    num_ctx: int,
    num_predict: int,
    max_tool_calls_per_turn: int,
) -> Outcome:
    """Déroule tous les tours de ``question`` (voir la docstring du module)."""
    outcome = Outcome()
    messages: list[dict[str, Any]] = [dict(message) for message in question["messages"]]
    tools = question.get("tools") or None
    env = make_env(question["env"]) if question.get("env") is not None else None
    turns = list(question.get("turns") or [])
    for turn in range(1 + len(turns)):
        if turn > 0:
            for message in turns[turn - 1]:
                messages.append(dict(message))
                outcome.output.append(
                    {"turn": turn, "role": message["role"], "content": message["content"]}
                )
        turn_calls = 0
        while True:
            try:
                result = chat(messages, tools)
            except Exception as exc:
                raise ChatFailedError(exc, outcome) from exc
            outcome.add_call(result)
            outcome.output.append(_assistant_output(result, turn))
            messages.append(_assistant_message(result))
            prompt = result.prompt_eval_count + result.prompt_eval_cached_count
            if prompt >= num_ctx - num_predict:
                outcome.status = STATUS_CONTEXT_EXCEEDED
                outcome.context_prompt = prompt
                return outcome
            if result.done_reason == "length":
                outcome.status = STATUS_TRUNCATED
                return outcome
            calls = result.tool_calls
            if not calls:
                break  # réponse sans appel : fin du tour
            if not all(well_formed(call) for call in calls):
                return outcome  # appel mal formé : la question s'arrête, sortie gardée
            if env is None:
                break  # outils non exécutés : la première réponse clôt le tour
            if turn_calls + len(calls) > max_tool_calls_per_turn:
                outcome.call_cap_reached = True
                return outcome
            turn_calls += len(calls)
            for call in calls:
                name = call["function"]["name"]
                content = env.call(name, call["function"]["arguments"])
                outcome.output.append({"turn": turn, "role": "tool", "content": content})
                messages.append({"role": "tool", "content": content, "tool_name": name})
    return outcome
