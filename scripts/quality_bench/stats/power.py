"""Taille d'échantillon indicative d'un test de McNemar (statistiques.md, « Repères de taille
d'échantillon ») : approximation normale de Connor (1987), un peu sous les repères exacts."""

from __future__ import annotations

import math
from statistics import NormalDist


def mcnemar_sample_size(psi: float, delta: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Nombre d'unités appariées pour détecter un écart ``delta`` entre deux proportions quand
    la part d'unités discordantes vaut ``psi`` (test bilatéral à ``alpha``, puissance
    ``power``) : ``n = (z₁₋α/₂·√ψ + z₁₋β·√(ψ − δ²))² / δ²``.

    ``nan`` hors du domaine : ``delta ≤ 0``, ``psi < delta``, ``psi ≥ 1``, ou une valeur non
    finie. Le résultat n'est pas arrondi (l'appelant publie l'entier supérieur)."""
    values = (psi, delta, alpha, power)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        return math.nan
    if delta <= 0 or psi < delta or psi >= 1 or not 0 < alpha < 1 or not 0 < power < 1:
        return math.nan
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1.0 - alpha / 2.0)
    z_power = normal.inv_cdf(power)
    root = z_alpha * math.sqrt(psi) + z_power * math.sqrt(psi - delta * delta)
    return root * root / (delta * delta)
