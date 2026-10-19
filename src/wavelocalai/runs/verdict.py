"""Verdict local/cloud d'une Arène terminée (story 3.5, AD-5, AD-10).

Fonctions pures : elles reçoivent les feuilles de l'instantané (`run_snapshot_row`), les notes lues
dans le flux (`judge_score`) et la table de prix de `Settings`, et rendent le champ `verdict` de
`GET /api/runs/{id}` ou `None`. Le front n'en calcule rien (AD-20).

Un inconnu n'est jamais un 0 : un coût cloud sans prix daté, ou sans tokens comptés, vaut `None`
avec sa raison.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from wavelocalai.config import PriceTable

REQUESTS = 1000  # taille de référence du coût : 1 000 requêtes de la même taille que la lane
TOKENS_PER_MTOK = 1_000_000

NO_PRICE_TABLE = "Aucune table de prix cloud n'est renseignée."
MODEL_NOT_PRICED = "Ce modèle ne figure pas dans la table de prix cloud."
TOKENS_NOT_COUNTED = "Le fournisseur n'a pas compté les tokens de cette réponse."


def _cost(lane: Mapping[str, Any], prices: PriceTable) -> dict[str, Any]:
    """Coût de `REQUESTS` requêtes de la taille de la lane : 0 en local, prix daté en cloud."""
    cost: dict[str, Any] = {"amount": None, "currency": prices.currency, "reason": None}
    if lane["origin"] != "cloud":
        cost["amount"] = 0.0
        return cost
    price = prices.models.get(lane["model"])
    metrics = lane["metrics"] or {}
    if not prices.models:
        cost["reason"] = NO_PRICE_TABLE
    elif price is None:
        cost["reason"] = MODEL_NOT_PRICED
    elif metrics.get("input_tokens") is None or metrics.get("output_tokens") is None:
        cost["reason"] = TOKENS_NOT_COUNTED
    else:
        per_request = (
            metrics["input_tokens"] * price.input_per_mtok
            + metrics["output_tokens"] * price.output_per_mtok
        )
        cost["amount"] = round(REQUESTS * per_request / TOKENS_PER_MTOK, 6)
    return cost


def _lane(child: Mapping[str, Any], scores: Mapping[str, float]) -> dict[str, Any]:
    metrics = child["metrics"]
    return {
        "model": child["model"],
        "origin": (metrics or {}).get("origin"),
        "score": scores.get(child["model"]),
        "metrics": metrics,
    }


def _best(lanes: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """La lane de plus haute note ; à égalité, la première lancée (`max` garde la première)."""
    scored = [lane for lane in lanes if lane["score"] is not None]
    return max(scored, key=lambda lane: lane["score"], default=None)


def _side(lane: dict[str, Any], prices: PriceTable) -> dict[str, Any]:
    metrics = lane["metrics"] or {}
    return {
        "model": lane["model"],
        "score": lane["score"],
        "co2": metrics.get("co2"),
        "cost": _cost(lane, prices),
    }


def build_verdict(
    children: Sequence[Mapping[str, Any]],
    scores: Mapping[str, float],
    prices: PriceTable,
) -> dict[str, Any] | None:
    """Verdict d'une Arène `ok`, ou `None` sans modèle local noté et modèle cloud noté.

    `children` : les feuilles de l'instantané, dans l'ordre de lancement ; `scores` : note /100
    par tag de modèle (les « non évalué » en sont absents).
    """
    lanes = [_lane(child, scores) for child in children if child["kind"] == "generation"]
    locals_ = [lane for lane in lanes if lane["origin"] == "local"]
    best_local = _best(locals_)
    best_cloud = _best([lane for lane in lanes if lane["origin"] == "cloud"])
    if best_local is None or best_cloud is None:
        return None
    gap = best_local["score"] - best_cloud["score"]
    judge_off_device = any(
        (child["metrics"] or {}).get("origin") == "cloud"
        for child in children
        if child["kind"] == "judge"
    )
    return {
        "leader": "tie" if gap == 0 else ("local" if gap > 0 else "cloud"),
        "score_gap": abs(gap),
        "local": _side(best_local, prices),
        "cloud": _side(best_cloud, prices),
        "requests": REQUESTS,
        "price_table": {
            "retrieved_at": prices.retrieved_at.isoformat() if prices.retrieved_at else None,
            "source": prices.source,
            "currency": prices.currency,
        },
        "data_on_device": {
            "models": [lane["model"] for lane in locals_],
            "count": len(locals_),
            "judge_off_device": judge_off_device,
        },
    }
