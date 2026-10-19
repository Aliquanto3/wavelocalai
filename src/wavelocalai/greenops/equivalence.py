"""Équivalence parlante du CO2 de la session en distance en voiture (story 5.1, décision D-38).

Le serveur fait le calcul : le front ne reçoit que la valeur, le facteur, sa source et sa date, et
ne contient aucune constante (AD-20). Un facteur sans réglage daté et sourcé (`CarEquivalence`) n'est
pas inventé : l'équivalence est alors absente. Sans réponse mesurée dans la session, il n'y a pas de
distance à dire (jamais 0 m).
"""

from __future__ import annotations

from typing import Any

from wavelocalai.config import CarEquivalence


def car_equivalence(
    setting: CarEquivalence | None, total_mg: float, measured_runs: int
) -> dict[str, Any] | None:
    """`{g_per_km, source, retrieved_at, total_mg, distance_m}` ; `distance_m` nul sans réponse
    mesurée. `None` sans réglage. 1 mg à `g_per_km` g/km = `1 / g_per_km` m."""
    if setting is None:
        return None
    measured = measured_runs > 0
    return {
        "g_per_km": setting.g_per_km,
        "source": setting.source,
        "retrieved_at": setting.retrieved_at.isoformat(),
        "total_mg": total_mg if measured else None,
        "distance_m": total_mg / setting.g_per_km if measured else None,
    }
