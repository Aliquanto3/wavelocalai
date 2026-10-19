"""Calcul des trois notes de l'évaluation de la qualité, sur 100 (story 7.1). Fonctions pures.

Une note est toujours un entier de 0 à 100 ; « non évalué » n'est pas un score (`None`, avec sa
raison, jamais 0). Un 0 est une vraie note : aucune affirmation appuyée, ou aucun extrait utile.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from wavelocalai.evaluation import prompts


def percent(part: int, whole: int) -> int:
    """`part` sur `whole` en pourcentage entier, arrondi à la moitié supérieure."""
    return int(100 * part / whole + 0.5)


def faithfulness(verdicts: Sequence[dict[str, Any]]) -> int:
    """Part des affirmations appuyées par les extraits. Lève `ValueError` sans affirmation."""
    if not verdicts:
        raise ValueError("aucune affirmation à noter")
    return percent(sum(1 for v in verdicts if v["verdict"] == prompts.SUPPORTED), len(verdicts))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosinus de deux vecteurs ; 0 si l'un est nul (aucune proximité démontrée)."""
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 0.0 if norm == 0.0 else sum(x * y for x, y in zip(a, b, strict=True)) / norm


def relevance(question: Sequence[float], retrieved: Sequence[Sequence[float]]) -> tuple[int, float]:
    """`(note, cosinus moyen)` : proximité entre la question posée et les questions retrouvées depuis
    la réponse. Un cosinus négatif vaut 0. Lève `ValueError` sans question retrouvée."""
    if not retrieved:
        raise ValueError("aucune question retrouvée")
    mean = sum(cosine(question, vector) for vector in retrieved) / len(retrieved)
    return int(100 * min(max(mean, 0.0), 1.0) + 0.5), mean


def context_precision(useful: Sequence[int], source_count: int) -> int:
    """Part des extraits fournis qui servent à répondre."""
    return percent(len(useful), source_count)
