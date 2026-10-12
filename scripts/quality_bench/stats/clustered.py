"""Moyenne et erreur-type groupée (Miller, « Adding Error Bars to Evals ») :
``ET = sqrt(Σ_g (Σ_{i∈g} (x_i − x̄))²) / n``, groupes = ``group`` des questions. Appliquée
aussi aux différences appariées ``d_i = a_i − b_i``."""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence

import numpy as np


def clustered_mean_se(values: Sequence[float], groups: Sequence[Hashable]) -> tuple[float, float]:
    """(moyenne, erreur-type groupée) ; ``(nan, nan)`` sans valeur ; ET ``nan`` avec moins de
    deux groupes distincts."""
    if len(values) != len(groups):
        raise ValueError("values et groups de longueurs différentes")
    n = len(values)
    if n == 0:
        return math.nan, math.nan
    x = np.asarray(values, dtype=float)
    mean = float(x.mean())
    sums: dict[Hashable, float] = {}
    for value, group in zip(x - mean, groups, strict=True):
        sums[group] = sums.get(group, 0.0) + float(value)
    if len(sums) < 2:
        # Un seul groupe : Σ(x − x̄) y vaut 0 ; l'erreur-type groupée est indéfinie, pas nulle.
        return mean, math.nan
    total = math.fsum(s * s for s in sums.values())
    return mean, math.sqrt(total) / n


def mean_interval(mean: float, se: float, z: float) -> tuple[float, float]:
    """Moyenne ± z·ET, bornée à [0, 1] (scores) ; ``(nan, nan)`` si indéfinie."""
    if not (math.isfinite(mean) and math.isfinite(se)):
        return math.nan, math.nan
    return max(0.0, mean - z * se), min(1.0, mean + z * se)
