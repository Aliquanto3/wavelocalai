"""Totaux d'une tâche d'agent (story 6.4, AD-20) : ce que le pied de la réponse dit d'un run `agent`.

Le CO2 n'existe que par appel de modèle (une feuille `generation` par tour) et la racine n'a aucune
mesure : le front ne les additionne pas, le serveur le fait ici, à la lecture de l'instantané.
Fonctions pures : elles reçoivent les feuilles de l'instantané (`run_snapshot_row`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

PARTIAL_REASON = "Au moins un appel de modèle de cette tâche n'a pas pu être mesuré."


def _unmeasurable(reason: str) -> dict[str, Any]:
    return {
        "mg": None,
        "method": "unmeasurable",
        "estimated": False,
        "range_mg": None,
        "allocation": "direct",
        "reason": reason,
    }


def total_co2(leaves: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Somme des feuilles mesurées ; `unmeasurable` dès qu'une feuille ne l'est pas (jamais une somme
    partielle présentée comme le total) ; `None` sans feuille."""
    if not leaves:
        return None
    co2s = [(leaf["metrics"] or {}).get("co2") for leaf in leaves]
    if any(c is None or c["mg"] is None for c in co2s):
        return _unmeasurable(PARTIAL_REASON)
    estimated = any(c["estimated"] for c in co2s)
    ranges = [c["range_mg"] for c in co2s]
    bounds = (
        None
        if any(r is None for r in ranges)
        else {"low": sum(r["low"] for r in ranges), "high": sum(r["high"] for r in ranges)}
    )
    return {
        "mg": sum(c["mg"] for c in co2s),
        "method": "ecologits" if estimated else "codecarbon",
        "estimated": estimated,
        "range_mg": bounds,
        "allocation": "direct",
        "reason": None,
    }


def duration_s(started_at: str | None, ended_at: str | None) -> float | None:
    if not started_at or not ended_at:
        return None
    try:
        span = datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)
    except ValueError:
        return None
    return max(span.total_seconds(), 0.0)


def agent_totals(snapshot: dict[str, Any], steps: int) -> dict[str, Any]:
    """`{turns, steps, duration_s, co2}` d'un run `agent` : appels de modèle, étapes publiées, durée
    de la tâche (`null` tant qu'elle n'est pas finie), CO2 de ses appels."""
    leaves = [c for c in snapshot["children"] if c["kind"] == "generation"]
    return {
        "turns": len(leaves),
        "steps": steps,
        "duration_s": duration_s(snapshot["started_at"], snapshot["ended_at"]),
        "co2": total_co2(leaves),
    }
