"""Contexte des conversations multi-tours (AD-5), sans réseau.

Le runner renvoie au modèle tout l'historique à chaque appel. ``gold_history`` rejoue la cible
dans l'environnement simulé (``envs/``, seule dépendance de ``questions/`` vers ``envs/``) et
rend les messages qu'accumulerait un modèle qui la suit : par tour, un message ``assistant``
portant les appels, un message ``tool`` par résultat, puis une réponse de
``REPLY_ALLOWANCE_TOKENS`` tokens.

**Règle versionnée par le jeu :** ``reestimate_multi`` recalcule ``est_prompt_tokens``,
``num_ctx`` et les empreintes d'un candidat ``bfcl-multi`` selon l'option ``multi_turn_history``
du YAML de jeu : absente ou fausse (set-v1), le prompt seul ; vraie (set-v2), le prompt et
l'historique. ``set_builder`` l'applique à chaque candidat : le jeu ne dépend pas de la règle en
vigueur quand ``candidates.jsonl`` a été écrit, et set-v1 reste reconstructible à l'identique.
Module sans import des importeurs : ``set_builder`` l'utilise sans charger de code réseau.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..envs.base import CallExpressionError, parse_call
from ..envs.registry import make_env
from .build import CHARS_PER_TOKEN, choose_num_ctx, estimate_prompt_tokens
from .schema import with_hashes

# Réponse textuelle d'un modèle à la fin d'un tour (une ou deux phrases), comptée par tour.
REPLY_ALLOWANCE_TOKENS = 100


def gold_history(env: Mapping[str, Any], target: list[list[str]]) -> list[dict[str, Any]]:
    """Messages accumulés par un modèle qui suit la cible, tous tours compris (voir le module).

    Une cible dont un appel n'est pas analysable (``CallExpressionError``) donne un résultat
    vide : le correcteur la traitera en erreur du banc, l'estimation n'en dépend pas.
    """
    simulated = make_env(env)
    reply = {"role": "assistant", "content": "x" * (REPLY_ALLOWANCE_TOKENS * CHARS_PER_TOKEN)}
    history: list[dict[str, Any]] = []
    for expressions in target:
        calls: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        for expression in expressions:
            try:
                name, args, kwargs = parse_call(expression)
                content = simulated.invoke(name, args, kwargs)
            except CallExpressionError:
                name, args, kwargs, content = "unknown", (), {}, ""
            arguments = {**kwargs, **{f"arg{index}": value for index, value in enumerate(args)}}
            calls.append({"function": {"name": name, "arguments": arguments}})
            results.append({"role": "tool", "content": content, "tool_name": name})
        if calls:
            history.append({"role": "assistant", "content": "", "tool_calls": calls})
            history.extend(results)
        history.append(dict(reply))
    return history


def reestimate_multi(question: Mapping[str, Any], with_history: bool) -> dict[str, Any]:
    """Candidat ``bfcl-multi`` dont ``est_prompt_tokens``, ``num_ctx`` et les empreintes suivent
    la règle du jeu : prompt seul (``with_history`` faux, set-v1) ou prompt et historique de la
    cible (``gold_history``, set-v2). ``PromptTooLongError`` si aucun palier ne le contient."""
    prompt = {key: question[key] for key in ("messages", "turns", "tools", "format")}
    history = gold_history(question["env"], question["target"]) if with_history else None
    est = estimate_prompt_tokens(prompt, history)
    record = dict(question)
    record["est_prompt_tokens"] = est
    record["num_ctx"] = choose_num_ctx(est, question["usage"])
    return with_hashes(record)


__all__ = ["REPLY_ALLOWANCE_TOKENS", "gold_history", "reestimate_multi"]
