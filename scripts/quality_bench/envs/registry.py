"""Registre des environnements d'outils (AD-11) : ``name@version`` par nom de
``question["env"]["name"]``, et ``make_env``, seule façon d'en créer un."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from . import bfcl_multi_turn
from .base import EnvError, ToolEnv


@dataclass(frozen=True)
class RegisteredEnv:
    version: str
    factory: Callable[[Mapping[str, Any]], ToolEnv]


ENVS: dict[str, RegisteredEnv] = {
    bfcl_multi_turn.NAME: RegisteredEnv(bfcl_multi_turn.VERSION, bfcl_multi_turn.BfclMultiTurnEnv),
}


def make_env(spec: Mapping[str, Any]) -> ToolEnv:
    """Environnement neuf pour ``spec`` = ``question["env"]`` (``{name, initial_state}``)."""
    if not isinstance(spec, Mapping) or not isinstance(spec.get("name"), str):
        raise EnvError("spécification d'environnement illisible")
    registered = ENVS.get(spec["name"])
    if registered is None:
        raise EnvError(f"environnement inconnu : {spec['name']!r}")
    return registered.factory(spec.get("initial_state"))
