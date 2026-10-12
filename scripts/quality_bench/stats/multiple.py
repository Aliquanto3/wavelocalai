"""Comparaisons multiples (statistiques.md) : Holm sur les k−1 comparaisons au meneur
(``method="holm"`` explicite : la valeur par défaut de ``multipletests`` est Holm-Šidák), BH
(``"fdr_bh"``) réservé à la matrice exploratoire, et k̂_Bonferroni pour une conclusion
transversale."""

from __future__ import annotations

import math
from collections.abc import Sequence

from statsmodels.stats.multitest import multipletests


def _corrected(
    pvalues: Sequence[float], alpha: float, method: str
) -> tuple[list[bool], list[float]]:
    """Correction ``method`` sur les seules p définies ; une p ``nan`` reste ``nan``, sans
    rejet, et ne compte pas dans le nombre de tests."""
    defined = [i for i, p in enumerate(pvalues) if math.isfinite(p)]
    reject = [False] * len(pvalues)
    corrected = [math.nan] * len(pvalues)
    if defined:
        rejected, adjusted, _, _ = multipletests(
            [pvalues[i] for i in defined], alpha=alpha, method=method
        )
        for index, flag, value in zip(defined, rejected, adjusted, strict=True):
            reject[index] = bool(flag)
            corrected[index] = float(value)
    return reject, corrected


def holm(pvalues: Sequence[float], alpha: float = 0.05) -> tuple[list[bool], list[float]]:
    """(rejets, p corrigées) de Holm (``method="holm"``, jamais Holm-Šidák)."""
    return _corrected(pvalues, alpha, "holm")


def benjamini_hochberg(
    pvalues: Sequence[float], alpha: float = 0.05
) -> tuple[list[bool], list[float]]:
    """(rejets, p corrigées) de Benjamini-Hochberg (``"fdr_bh"``) : matrice exploratoire
    seulement."""
    return _corrected(pvalues, alpha, "fdr_bh")


def bonferroni_wins(pvalues: Sequence[float], diffs: Sequence[float], alpha: float = 0.05) -> int:
    """k̂_Bonferroni : nombre de tests (un par usage) où ``p < alpha / m`` et la différence est
    positive, ``m`` = nombre de tests."""
    if len(pvalues) != len(diffs):
        raise ValueError("pvalues et diffs de longueurs différentes")
    m = len(pvalues)
    if m == 0:
        return 0
    threshold = alpha / m
    return sum(
        1
        for p, d in zip(pvalues, diffs, strict=True)
        if math.isfinite(p) and math.isfinite(d) and p < threshold and d > 0
    )
