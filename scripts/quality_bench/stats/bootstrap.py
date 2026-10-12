"""Bootstrap apparié par groupes, à graine fixée (statistiques.md : métriques non binaires).

On tire les groupes avec remise (les unités d'un même groupe partent ensemble), puis la
différence moyenne ``a − b`` sur les unités tirées ; IC par percentiles. Même graine, mêmes
entrées : même résultat.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence

import numpy as np

DEFAULT_RESAMPLES = 2000
DEFAULT_SEED = 20261011


def paired_bootstrap_ci(
    a: Sequence[float],
    b: Sequence[float],
    groups: Sequence[Hashable],
    *,
    alpha: float = 0.05,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float]:
    """IC percentile à ``1 - alpha`` de la différence moyenne appariée ``a − b`` ; ``(nan,
    nan)`` sans unité."""
    if not len(a) == len(b) == len(groups):
        raise ValueError("a, b et groups de longueurs différentes")
    if not a:
        return math.nan, math.nan
    order: dict[Hashable, int] = {}
    for group in groups:
        order.setdefault(group, len(order))
    index = np.fromiter((order[g] for g in groups), dtype=np.int64, count=len(groups))
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    sums = np.bincount(index, weights=d, minlength=len(order))
    counts = np.bincount(index, minlength=len(order)).astype(float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(order), size=(resamples, len(order)))
    means = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    low, high = np.quantile(means, [alpha / 2.0, 1.0 - alpha / 2.0])
    return float(low), float(high)
