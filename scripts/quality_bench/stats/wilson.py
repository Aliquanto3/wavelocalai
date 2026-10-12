"""Intervalle de Wilson d'une proportion (statistiques.md, « Par modèle »)."""

from __future__ import annotations

import math

from scipy.stats import norm


def z_value(alpha: float) -> float:
    """Quantile bilatéral ``z`` tel que ``P(|Z| > z) = alpha``."""
    return float(norm.ppf(1.0 - alpha / 2.0))


def wilson_interval(successes: float, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """IC de Wilson à ``1 - alpha`` de ``successes / n`` ; ``(nan, nan)`` si ``n == 0``."""
    if n <= 0:
        return math.nan, math.nan
    if successes < 0 or successes > n:
        raise ValueError("successes hors de [0, n]")
    z = z_value(alpha)
    p = successes / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
    return max(0.0, center - half), min(1.0, center + half)
