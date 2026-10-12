"""Classement (statistiques.md) : IC simultanés (Bonferroni sur les modèles du périmètre), rang
approché à la Chatbot Arena et groupes de modèles indiscernables."""

from __future__ import annotations

import math
from collections.abc import Sequence

from .multiple import holm


def bonferroni_alpha(alpha: float, m: int) -> float:
    """Niveau par modèle d'un IC simultané à ``1 - alpha`` sur ``m`` modèles."""
    return alpha / max(1, m)


def approximate_ranks(lows: Sequence[float], highs: Sequence[float]) -> list[int | None]:
    """Rang approché : 1 + nombre de modèles dont l'IC simultané est entièrement au-dessus
    (borne basse > borne haute de ce modèle) ; ``None`` pour un IC indéfini."""
    if len(lows) != len(highs):
        raise ValueError("lows et highs de longueurs différentes")
    ranks: list[int | None] = []
    for i, high in enumerate(highs):
        if not (math.isfinite(lows[i]) and math.isfinite(high)):
            ranks.append(None)
            continue
        above = sum(
            1
            for j, low in enumerate(lows)
            if j != i and math.isfinite(low) and math.isfinite(highs[j]) and low > high
        )
        ranks.append(1 + above)
    return ranks


def leader_order(means: Sequence[float]) -> list[int]:
    """Indices des modèles à moyenne définie, par moyenne décroissante ; à égalité, ordre
    d'entrée (ordre de la configuration)."""
    defined = [i for i, mean in enumerate(means) if math.isfinite(mean)]
    return sorted(defined, key=lambda i: (-means[i], i))


def indistinguishable_groups(
    means: Sequence[float],
    diffs: Sequence[Sequence[float]],
    pvalues: Sequence[Sequence[float]],
    alpha: float = 0.05,
) -> list[int | None]:
    """Numéro de groupe (1, 2…) de chaque modèle, ``None`` si sa moyenne est indéfinie.

    Meneurs successifs : le premier groupe réunit le meneur et les modèles que Holm (sur ses
    comparaisons aux modèles restants) ne distingue pas ; on retire ce groupe et on recommence
    sur le reste. ``diffs[i][j]`` = différence appariée ``i − j``, ``pvalues[i][j]`` = p
    bilatérale de la paire ; un modèle n'est distingué que si Holm rejette et que le meneur lui
    est supérieur."""
    remaining = leader_order(means)
    groups: list[int | None] = [None] * len(means)
    number = 0
    while remaining:
        number += 1
        leader, others = remaining[0], remaining[1:]
        reject, _ = holm([pvalues[leader][j] for j in others], alpha)
        members = [leader] + [
            j
            for j, rejected in zip(others, reject, strict=True)
            if not (rejected and diffs[leader][j] > 0)
        ]
        for j in members:
            groups[j] = number
        remaining = [j for j in remaining if j not in members]
    return groups
