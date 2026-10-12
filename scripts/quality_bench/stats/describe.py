"""Résumé d'une distribution (pilote, CAP-8) : effectif, moyenne, médiane, 90ᵉ centile, maximum
(tokens de réflexion et de complétion par usage)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def describe(values: Sequence[float]) -> dict[str, float]:
    """``{n, mean, p50, p90, max}`` de ``values`` (centiles par interpolation linéaire de
    ``numpy.percentile``) ; sans valeur : ``n = 0`` et ``nan`` ailleurs."""
    if len(values) == 0:
        return {"n": 0, "mean": math.nan, "p50": math.nan, "p90": math.nan, "max": math.nan}
    array = np.asarray(values, dtype=float)
    p50, p90 = np.percentile(array, [50, 90], method="linear")
    return {
        "n": int(array.size),
        "mean": float(math.fsum(array.tolist()) / array.size),
        "p50": float(p50),
        "p90": float(p90),
        "max": float(array.max()),
    }
