"""Environnement BFCL multi-tours (``bfcl_multi_turn@1``) : classes de BFCL figées
(``envs/vendored/bfcl/``), exécutées comme le fait ``execute_multi_turn_func_call`` de BFCL,
sans ``eval``.

- **État initial** (``question["env"]["initial_state"]``) : ``{involved_classes,
  initial_config}``. Chaque classe engagée est instanciée, puis ``_load_scenario`` reçoit une
  copie profonde de sa configuration (sauf ``MathAPI``, sans état), sans contexte long.
- **Table méthode → instance** : méthodes publiques de chaque instance, dans l'ordre des classes
  engagées, une classe plus tardive l'emportant sur un nom partagé (comme BFCL).
- **Résultat** : chaîne telle quelle ; dictionnaire en ``json.dumps`` par défaut, ou ``str``
  s'il n'est pas sérialisable ; tout autre type en ``str``.
- **Erreur** : jamais levée, rendue « Error during execution: <message> ». Un nom inconnu
  donne le message de ``NameError`` que produirait l'``eval`` de BFCL ; les noms que BFCL
  refuse (``kill``, ``exit``…) donnent son message de refus.

Le contexte décimal est isolé autour de chaque appel (``MathAPI.square_root`` en change la
précision) ; ``mpmath.mp.dps`` est fixé par chaque appel de ``MathAPI.logarithm`` avant usage.
"""

from __future__ import annotations

import copy
import decimal
import inspect
from collections.abc import Mapping
from typing import Any

from ..common.canonical import plain_json
from .base import EnvError, ToolEnv
from .vendored.bfcl import (
    gorilla_file_system,
    math_api,
    message_api,
    posting_api,
    ticket_api,
    trading_bot,
    travel_booking,
    vehicle_control,
)

NAME = "bfcl_multi_turn"
VERSION = f"{NAME}@1"

# Classes de la suite multi-tours (CLASS_FILE_PATH_MAPPING de BFCL, sans recherche web ni
# mémoire, hors du banc).
CLASSES: dict[str, type] = {
    "GorillaFileSystem": gorilla_file_system.GorillaFileSystem,
    "MathAPI": math_api.MathAPI,
    "MessageAPI": message_api.MessageAPI,
    "TwitterAPI": posting_api.TwitterAPI,
    "TicketAPI": ticket_api.TicketAPI,
    "TradingBot": trading_bot.TradingBot,
    "TravelAPI": travel_booking.TravelAPI,
    "VehicleControlAPI": vehicle_control.VehicleControlAPI,
}
STATELESS_CLASSES = ("MathAPI",)
# Noms que BFCL refuse d'exécuter (execute_multi_turn_func_call).
FORBIDDEN_CALLS = ("kill", "exit", "quit", "remove", "unlink", "popen", "Popen", "run")
ERROR_PREFIX = "Error during execution: "


def render_result(result: Any) -> str:
    """Résultat d'un appel converti comme BFCL."""
    if type(result) is str:
        return result
    if type(result) is dict:
        try:
            return plain_json(result)
        except (TypeError, ValueError):
            return str(result)
    return str(result)


class BfclMultiTurnEnv(ToolEnv):
    """Instances des classes engagées d'une conversation BFCL, gardées d'un tour à l'autre."""

    version = VERSION

    def __init__(self, initial_state: Mapping[str, Any]) -> None:
        if not isinstance(initial_state, Mapping):
            raise EnvError("bfcl_multi_turn : état initial qui n'est pas un objet")
        involved = initial_state.get("involved_classes")
        config = initial_state.get("initial_config")
        if (
            not isinstance(involved, list)
            or not involved
            or not all(isinstance(name, str) for name in involved)
            or not isinstance(config, Mapping)
        ):
            raise EnvError("bfcl_multi_turn : involved_classes ou initial_config illisible")
        unknown = sorted(name for name in involved if name not in CLASSES)
        if unknown:
            raise EnvError(f"bfcl_multi_turn : classes inconnues {unknown}")
        self._instances: dict[str, Any] = {}
        self._methods: dict[str, Any] = {}
        for class_name in involved:
            instance = CLASSES[class_name]()
            if class_name not in STATELESS_CLASSES:
                scenario = copy.deepcopy(dict(config.get(class_name, {})))
                instance._load_scenario(scenario, long_context=False)
            self._instances[class_name] = instance
            for method_name, method in inspect.getmembers(instance, predicate=inspect.ismethod):
                if not method_name.startswith("_"):
                    self._methods[method_name] = method

    @property
    def instances(self) -> dict[str, Any]:
        return dict(self._instances)

    def invoke(self, name: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> str:
        if name in FORBIDDEN_CALLS:
            return f"{ERROR_PREFIX}Function call {name} is not allowed."
        method = self._methods.get(name)
        if method is None:
            return f"{ERROR_PREFIX}name '{name}' is not defined"
        try:
            with decimal.localcontext():
                result = method(*args, **dict(kwargs))
                # Rendu dans le try, comme BFCL : un résultat irreprésentable (entier de plus de
                # 4300 chiffres) est une erreur rendue, jamais levée.
                return render_result(result)
        except Exception as exc:  # noqa: BLE001 (erreur de l'appel rendue au modèle, comme BFCL)
            return f"{ERROR_PREFIX}{exc}"
