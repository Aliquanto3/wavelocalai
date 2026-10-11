"""Extraction JSON : ``json_schema`` (JSONSchemaBench, extraction FR).

La réponse est décodée (``decode_json``, clôtures Markdown comprises) puis vérifiée contre le
schéma de la question côté client (``conformity_error``) : JSON illisible ou hors schéma =
``non_compliant``, jamais supposé conforme parce que ``format`` a été envoyé.

Avec une cible (valeurs attendues), les feuilles des deux objets sont aplaties par chemin,
un tuple de segments (clés d'objet et indices de liste : ``{"a.b": 1}`` et ``{"a": {"b": 1}}``
ne se confondent pas) ; les listes se comparent par position. Chaînes en NFC, espaces réduits,
casse ignorée ; nombres comparés par valeur ; booléens distincts des nombres. ``success`` =
toutes les feuilles attendues retrouvées, ``metrics.f1`` = F1 sur les feuilles (0.0 pour une
sortie non conforme).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Any

from ..common.schemas import conformity_error
from .answer import JsonAnswerError, decode_floats, decode_json, final_answer
from .base import Grade, bench_error, from_success, non_compliant, passed


def _leaf(value: Any) -> tuple[str, Any]:
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return ("number", int(value))
        return ("number", value)
    if isinstance(value, str):
        text = " ".join(unicodedata.normalize("NFC", value).split())
        return ("string", text.casefold())
    if value is None:
        return ("null", None)
    if isinstance(value, Mapping):
        return ("object", None)  # objet vide
    return ("array", None)  # liste vide


LeafPath = tuple[str | int, ...]


def flatten(value: Any, path: LeafPath = ()) -> dict[LeafPath, tuple[str, Any]]:
    """Feuilles d'une valeur JSON par chemin (tuple de clés et d'indices, ``("a", 0, "b")``) ;
    objet ou liste vides : feuilles."""
    if isinstance(value, Mapping) and value:
        leaves: dict[LeafPath, tuple[str, Any]] = {}
        for key, item in value.items():
            leaves.update(flatten(item, (*path, str(key))))
        return leaves
    if isinstance(value, list) and value:
        leaves = {}
        for index, item in enumerate(value):
            leaves.update(flatten(item, (*path, index)))
        return leaves
    return {path: _leaf(value)}


def leaf_scores(expected: Any, predicted: Any) -> tuple[bool, float]:
    """(toutes les feuilles attendues retrouvées, F1 sur les feuilles)."""
    expected_leaves = flatten(expected)
    predicted_leaves = flatten(predicted)
    matched = sum(1 for path, leaf in expected_leaves.items() if predicted_leaves.get(path) == leaf)
    if matched == 0:
        return (not expected_leaves, 0.0 if expected_leaves else 1.0)
    precision = matched / len(predicted_leaves)
    recall = matched / len(expected_leaves)
    return matched == len(expected_leaves), 2 * precision * recall / (precision + recall)


def json_schema(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    schema = question["grader"]["params"].get("schema")
    if not isinstance(schema, (Mapping, bool)):
        return bench_error("schéma de la question illisible")
    target = question["target"]
    failure_metrics = {"f1": 0.0} if target is not None else {}
    try:
        instance = decode_json(final_answer(generation).text)
    except JsonAnswerError:
        return non_compliant("réponse JSON illisible", failure_metrics)
    try:
        problem = conformity_error(schema, instance)
    except Exception as exc:  # noqa: BLE001 (schéma invérifiable : erreur du banc)
        return bench_error(f"schéma invérifiable ({type(exc).__name__})")
    if problem is not None:
        return non_compliant("JSON non conforme au schéma", failure_metrics)
    if target is None:
        return passed()
    success, f1 = leaf_scores(decode_floats(target), instance)
    return from_success(success, {"f1": f1})
