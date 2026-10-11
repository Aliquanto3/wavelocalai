"""Outils : ``bfcl_ast``, ``bfcl_state`` et ``bfcl_irrelevance`` (BFCL v4).

- ``bfcl_ast`` : appels du tour 0 au format BFCL ``[{nom: arguments}]``, cible décodée
  (``$float``), ``ast_checker`` amont (langage Python, catégorie de la question,
  ``underscore_to_dot``) ;
- ``bfcl_irrelevance`` : succès si le modèle n'appelle aucun outil ;
- ``bfcl_state`` : rejeu des pas d'outils (messages ``assistant`` avec appels) sur un
  environnement neuf, chaque contenu ``tool`` devant être retrouvé (sinon erreur du banc), puis
  ``multi_turn_checker`` amont avec un exécuteur injecté au lieu d'``eval`` : instances du
  modèle et de la cible dans deux environnements neufs du même état initial, gardés d'un tour à
  l'autre comme dans BFCL. Un tour absent de la sortie est une erreur du banc.

Un appel d'outil mal formé est ``non_compliant`` ; une cible illisible ou une exception du code
emprunté est une erreur du banc.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from ..envs.base import CallExpressionError, EnvError
from ..envs.registry import make_env
from .answer import ToolCallError, answered_turns, decode_floats, tool_calls_by_turn, tool_steps
from .base import Grade, bench_error, from_success, non_compliant
from .vendored.bfcl.ast_eval.ast_checker import ast_checker
from .vendored.bfcl.constants.enums import Language
from .vendored.bfcl.multi_turn_eval.multi_turn_checker import multi_turn_checker

AST_CATEGORIES = ("live_simple", "live_multiple", "live_parallel", "live_parallel_multiple")


def bfcl_ast(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    params = question["grader"]["params"]
    if params.get("category") not in AST_CATEGORIES:
        return bench_error("catégorie BFCL AST inconnue")
    target = decode_floats(question["target"])
    if not isinstance(target, list) or not all(isinstance(item, Mapping) for item in target):
        return bench_error("cible BFCL illisible")
    try:
        calls = tool_calls_by_turn(generation).get(0, [])
    except ToolCallError as exc:
        return non_compliant(str(exc))
    model_output = [{call.name: copy.deepcopy(call.arguments)} for call in calls]
    try:
        result = ast_checker(
            copy.deepcopy(params["functions"]),
            model_output,
            target,
            Language.PYTHON,
            params["category"],
            bool(params.get("underscore_to_dot", False)),
        )
    except Exception as exc:  # noqa: BLE001 (code emprunté en défaut : erreur du banc)
        return bench_error(f"ast_checker en défaut ({type(exc).__name__})")
    return from_success(bool(result.get("valid")))


def bfcl_irrelevance(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    try:
        by_turn = tool_calls_by_turn(generation)
    except ToolCallError as exc:
        return non_compliant(str(exc))
    return from_success(not any(by_turn.values()))


def _replay_matches(spec: Mapping[str, Any], steps: list[Any]) -> bool:
    """Rejoue chaque pas sur un environnement neuf : chaque contenu ``tool`` doit être celui que
    rend ``env.call`` (même nombre, même texte, même ordre)."""
    env = make_env(spec)
    for step in steps:
        if len(step.contents) != len(step.calls):
            return False
        for call, content in zip(step.calls, step.contents, strict=True):
            if env.call(call.name, call.arguments) != content:
                return False
    return True


def bfcl_state(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    params = question["grader"]["params"]
    spec = question.get("env")
    target = question["target"]
    if not isinstance(spec, Mapping):
        return bench_error("bfcl_state sans environnement")
    if (
        not isinstance(target, list)
        or not all(isinstance(turn, list) for turn in target)
        or not all(isinstance(call, str) for turn in target for call in turn)
    ):
        return bench_error("cible BFCL illisible")
    turn_count = 1 + len(question.get("turns") or [])
    if len(target) != turn_count:
        return bench_error("cible BFCL : nombre de tours différent de la question")
    try:
        steps = tool_steps(generation)
    except ToolCallError as exc:
        return non_compliant(str(exc))
    answered = answered_turns(generation)
    if any(turn not in answered for turn in range(turn_count)):
        return bench_error("tours manquants dans la sortie")
    try:
        if not _replay_matches(spec, steps):
            return bench_error("rejeu divergent : contenu d'outil différent de l'environnement")
        model_env, target_env = make_env(spec), make_env(spec)
    except EnvError as exc:
        return bench_error(f"environnement illisible ({exc})")

    def executor(func_call_list: list[Any], ground_truth: bool) -> tuple[list[str], dict]:
        if ground_truth:
            results = [target_env.call_expression(call) for call in func_call_list]
            return results, target_env.instances
        results = [model_env.call(call.name, call.arguments) for call in func_call_list]
        return results, model_env.instances

    model_steps: list[list[list[Any]]] = [[] for _ in range(turn_count)]
    for step in steps:
        if 0 <= step.turn < turn_count:
            model_steps[step.turn].append(list(step.calls))
    initial_state = spec.get("initial_state") or {}
    test_entry = {
        "id": params.get("bfcl_id", ""),
        "initial_config": initial_state.get("initial_config", {}),
        "involved_classes": initial_state.get("involved_classes", []),
    }
    try:
        result = multi_turn_checker(
            model_steps, target, test_entry, params.get("category", ""), executor
        )
    except CallExpressionError:
        return bench_error("cible BFCL illisible (appel non analysable)")
    except Exception as exc:  # noqa: BLE001 (code emprunté en défaut : erreur du banc)
        return bench_error(f"multi_turn_checker en défaut ({type(exc).__name__})")
    return from_success(bool(result.get("valid")))
