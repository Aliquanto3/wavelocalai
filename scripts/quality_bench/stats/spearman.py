"""Validation externe (statistiques.md) : corrélation de Spearman entre le score global d'une
piste et l'indice Artificial Analysis mesuré de la variante appariée.

ρ et p unilatérale (``alternative="greater"``) par ``scipy.stats.spearmanr`` ; IC bootstrap de
ρ (paires de modèles tirées avec remise, graine fixée). Conclusion :

- moins de ``MIN_MODELS`` modèles : ``inconclusive`` (rapporté sans conclusion) ;
- ρ < 0 : ``investigate`` (enquête) ;
- p < α : ``concordant`` ;
- sinon : ``not_significant`` (ne disqualifie pas le banc).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.stats import rankdata, spearmanr

from .bootstrap import DEFAULT_RESAMPLES, DEFAULT_SEED

MIN_MODELS = 8
CONCLUSIONS = ("inconclusive", "investigate", "concordant", "not_significant")


@dataclass(frozen=True)
class SpearmanResult:
    n: int
    rho: float
    p: float
    ci_low: float
    ci_high: float
    conclusion: str


def conclusion(n: int, rho: float, p: float, alpha: float = 0.05) -> str:
    """Lecture de statistiques.md, dans cet ordre : effectif, signe, significativité."""
    if n < MIN_MODELS or not math.isfinite(rho):
        return "inconclusive"
    if rho < 0:
        return "investigate"
    if math.isfinite(p) and p < alpha:
        return "concordant"
    return "not_significant"


def _rank_correlations(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """ρ de Spearman de chaque ligne (``nan`` si une ligne est constante)."""
    rx = rankdata(x, axis=1)
    ry = rankdata(y, axis=1)
    rx -= rx.mean(axis=1, keepdims=True)
    ry -= ry.mean(axis=1, keepdims=True)
    numerator = (rx * ry).sum(axis=1)
    denominator = np.sqrt((rx * rx).sum(axis=1) * (ry * ry).sum(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(
            denominator > 0, numerator / np.where(denominator > 0, denominator, 1), np.nan
        )


def spearman_test(
    scores: Sequence[float],
    index: Sequence[float],
    *,
    alpha: float = 0.05,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> SpearmanResult:
    """ρ, p unilatérale, IC bootstrap de ρ et conclusion ; valeurs ``nan`` sous 3 modèles ou
    si une série est constante."""
    if len(scores) != len(index):
        raise ValueError("scores et index de longueurs différentes")
    n = len(scores)
    x = np.asarray(scores, dtype=float)
    y = np.asarray(index, dtype=float)
    if n < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return SpearmanResult(
            n, math.nan, math.nan, math.nan, math.nan, conclusion(n, math.nan, math.nan, alpha)
        )
    result = spearmanr(x, y, alternative="greater")
    rho, p = float(result.statistic), float(result.pvalue)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n, size=(resamples, n))
    rhos = _rank_correlations(x[draws], y[draws])
    rhos = rhos[np.isfinite(rhos)]
    if rhos.size:
        low, high = (float(v) for v in np.quantile(rhos, [alpha / 2.0, 1.0 - alpha / 2.0]))
    else:
        low = high = math.nan
    return SpearmanResult(n, rho, p, low, high, conclusion(n, rho, p, alpha))
