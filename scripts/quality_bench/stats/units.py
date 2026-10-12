"""Unité statistique (AD-17) : (``model``, ``track``, ``unit``).

Les questions d'une ``unit`` (variantes VAR-MATH) sont agrégées par minimum de ``score`` (une
unité n'est réussie que si toutes ses questions le sont), puis les seeds par moyenne. Une
question sans score (``None`` : erreur du banc, attente du juge, ligne écartée) rend l'unité
nulle (``None``) pour ce modèle.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence


def unit_scores(
    units: Sequence[Hashable],
    seeds: Sequence[int],
    scores: Sequence[float | None],
) -> dict[Hashable, float | None]:
    """Score de chaque unité depuis des lignes question par question (mêmes longueurs) :
    minimum par (unité, seed), puis moyenne sur les seeds ; ``None`` si une question de l'unité
    est sans score, quel que soit son seed."""
    if not len(units) == len(seeds) == len(scores):
        raise ValueError("units, seeds et scores de longueurs différentes")
    minima: dict[Hashable, dict[int, float]] = {}
    null_units: set[Hashable] = set()
    for unit, seed, score in zip(units, seeds, scores, strict=True):
        if score is None:
            null_units.add(unit)
            minima.setdefault(unit, {})
            continue
        by_seed = minima.setdefault(unit, {})
        value = float(score)
        by_seed[seed] = value if seed not in by_seed else min(by_seed[seed], value)
    result: dict[Hashable, float | None] = {}
    for unit, by_seed in minima.items():
        if unit in null_units or not by_seed:
            result[unit] = None
        else:
            result[unit] = sum(by_seed[seed] for seed in sorted(by_seed)) / len(by_seed)
    return result
