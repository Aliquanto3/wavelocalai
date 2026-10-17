"""Comparaisons appariées (statistiques.md, « Entre modèles ») : McNemar exact sur la table 2×2
des réussites par unité, différence appariée avec erreur-type groupée, IC à 95 %, corrélation
entre modèles, et test z sur la différence quand le périmètre n'est pas binaire. Aucun test
non apparié."""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.stats import binomtest, norm

from .clustered import clustered_mean_se


@dataclass(frozen=True)
class PairedDifference:
    """Différence ``a − b`` sur les unités appariées."""

    n: int
    diff: float
    se: float
    ci_low: float
    ci_high: float
    correlation: float


def discordant_counts(a: Sequence[float], b: Sequence[float]) -> tuple[int, int]:
    """(b, c) de McNemar : unités réussies par ``a`` seul, puis par ``b`` seul (scores 0/1)."""
    if len(a) != len(b):
        raise ValueError("a et b de longueurs différentes")
    only_a = sum(1 for x, y in zip(a, b, strict=True) if x >= 0.5 > y)
    only_b = sum(1 for x, y in zip(a, b, strict=True) if y >= 0.5 > x)
    return only_a, only_b


def mcnemar_exact(b: int, c: int) -> float:
    """p bilatérale de McNemar exact : ``binomtest(b, b + c, 0,5)`` ; ``1`` si ``b + c = 0``."""
    if b + c == 0:
        return 1.0
    return float(binomtest(b, b + c, 0.5, alternative="two-sided").pvalue)


def correlation(a: Sequence[float], b: Sequence[float]) -> float:
    """Corrélation de Pearson entre les scores d'unité des deux modèles ; ``nan`` si l'un est
    constant ou si moins de deux unités."""
    if len(a) < 2:
        return math.nan
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    dx = x - x.mean()
    dy = y - y.mean()
    denominator = math.sqrt(float(dx @ dx) * float(dy @ dy))
    if denominator == 0.0:
        return math.nan
    return max(-1.0, min(1.0, float(dx @ dy) / denominator))


def paired_difference(
    a: Sequence[float], b: Sequence[float], groups: Sequence[Hashable], z: float
) -> PairedDifference:
    """Différence moyenne ``a − b``, erreur-type groupée des ``d_i``, IC ``diff ± z·ET``."""
    if not len(a) == len(b) == len(groups):
        raise ValueError("a, b et groups de longueurs différentes")
    d = [float(x) - float(y) for x, y in zip(a, b, strict=True)]
    diff, se = clustered_mean_se(d, groups)
    if math.isfinite(diff) and math.isfinite(se):
        low, high = diff - z * se, diff + z * se
    else:
        low = high = math.nan
    return PairedDifference(len(d), diff, se, low, high, correlation(a, b))


def z_test(diff: float, se: float) -> float:
    """p bilatérale du test z de ``diff / se`` ; ``nan`` si indéfinie, y compris quand l'ET
    est nulle avec une différence non nulle (le z n'a alors aucun sens : voir ``paired_test``) ;
    ET nulle et différence nulle : ``1``."""
    if not (math.isfinite(diff) and math.isfinite(se)):
        return math.nan
    if se == 0.0:
        return 1.0 if diff == 0.0 else math.nan
    return float(2.0 * norm.sf(abs(diff / se)))


def sign_test_exact(differences: Sequence[float]) -> float:
    """p bilatérale du test exact des signes sur les différences par unité : on écarte les
    différences nulles, puis ``binomtest(positives, non nulles, 0,5)`` ; ``1`` s'il n'en reste
    aucune."""
    positives = sum(1 for d in differences if d > 0)
    negatives = sum(1 for d in differences if d < 0)
    return mcnemar_exact(positives, negatives)


def paired_test(diff: float, se: float, differences: Sequence[float]) -> tuple[float, str]:
    """(p, méthode) du test sur la différence appariée : test z (``"z"``) ; quand l'ET groupée
    est nulle avec une différence non nulle, le z donnerait p = 0 quel que soit l'effectif :
    repli sur le test exact des signes sur les unités (``"sign"``). ET ou différence
    indéfinie : ``(nan, "z")``."""
    if math.isfinite(diff) and math.isfinite(se) and se == 0.0 and diff != 0.0:
        return sign_test_exact(differences), "sign"
    return z_test(diff, se), "z"
