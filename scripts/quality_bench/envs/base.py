"""Contrat d'un environnement d'outils (AD-11).

Le runner (story 5) appelle ``make_env(question["env"])``, puis ``env.call(name, arguments)``
pour chaque appel d'outil du modèle, dans l'ordre des appels, et écrit la chaîne rendue telle
quelle comme ``content`` du message ``tool`` suivant. Le correcteur rejoue ces appels sur un
environnement neuf et doit retrouver chaque contenu.

``call`` ne lève jamais pour un appel du modèle : une méthode inconnue ou en erreur est rendue en
chaîne (« Error during execution: … »), comme dans BFCL. ``call_expression`` exécute une cible
BFCL (``"cd(folder='document')"``) analysée par ``ast``, jamais par ``eval`` : toute autre forme
qu'un appel d'un nom à arguments littéraux lève ``CallExpressionError`` (erreur du banc).
"""

from __future__ import annotations

import ast
import copy
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class EnvError(ValueError):
    """État initial ou spécification d'environnement illisible (erreur du banc)."""


class CallExpressionError(ValueError):
    """Cible d'appel illisible : autre chose qu'un appel d'un nom à arguments littéraux."""


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        raise CallExpressionError("argument non littéral dans une cible d'appel") from None


def parse_call(text: str) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
    """Analyse ``nom(arg, clé=valeur)`` : nom, arguments positionnels, arguments nommés.

    Seuls un appel d'un nom simple et des arguments littéraux (``ast.literal_eval``) sont admis :
    ni attribut, ni appel imbriqué, ni ``*args`` ou ``**kwargs``.
    """
    if not isinstance(text, str):
        raise CallExpressionError("cible d'appel qui n'est pas une chaîne")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        raise CallExpressionError("cible d'appel illisible") from None
    node = tree.body
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        raise CallExpressionError("cible qui n'est pas l'appel d'un nom")
    args = []
    for arg in node.args:
        if isinstance(arg, ast.Starred):
            raise CallExpressionError("argument étoilé dans une cible d'appel")
        args.append(_literal(arg))
    kwargs: dict[str, Any] = {}
    for keyword in node.keywords:
        if keyword.arg is None or keyword.arg in kwargs:
            raise CallExpressionError("argument nommé invalide dans une cible d'appel")
        kwargs[keyword.arg] = _literal(keyword.value)
    return node.func.id, tuple(args), kwargs


class ToolEnv(ABC):
    """Environnement d'outils : état propre à une conversation, rejouable à l'identique."""

    #: ``name@version`` du registre (``envs/registry.py``).
    version: str = ""

    @property
    @abstractmethod
    def instances(self) -> Mapping[str, Any]:
        """Objets d'état par nom de classe (comparés par le correcteur, comme dans BFCL)."""

    @abstractmethod
    def invoke(self, name: str, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> str:
        """Exécute l'outil ``name`` et rend son résultat en chaîne ; ne lève jamais pour une
        erreur de l'appel (rendue en chaîne)."""

    def call(self, name: str, arguments: Mapping[str, Any]) -> str:
        """Appel d'outil du modèle : nom et arguments nommés (objet JSON). Les arguments sont
        copiés en profondeur : l'état de l'environnement ne partage jamais d'objet avec le
        message du modèle (comme BFCL, qui réévalue une chaîne à chaque appel)."""
        return self.invoke(name, (), copy.deepcopy(dict(arguments)))

    def call_expression(self, text: str) -> str:
        """Appel d'une cible BFCL (``"nom(…)"``), analysée par ``parse_call``."""
        name, args, kwargs = parse_call(text)
        return self.invoke(name, args, kwargs)
