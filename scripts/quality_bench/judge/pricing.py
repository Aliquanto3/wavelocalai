"""Coût d'un appel de juge et plafond de dépense d'un lancement (AD-16).

Prix lus dans ``judges.yaml`` (``prices``) : USD par million de tokens, remise de lot
(``batch_discount``, 0,5 = −50 %) et palier de contexte long (``long_context`` : au-delà de
``threshold_tokens`` tokens d'entrée, toute la requête passe aux prix du palier).

Estimation prudente avant un envoi : tokens d'entrée = caractères ÷ ``chars_per_token`` (arrondi
au-dessus), tokens de sortie = ``max_tokens`` (le plafond, jamais moins).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .base import CostCapError

_MILLION = 1_000_000


def request_cost(
    prices: Mapping[str, Any] | None,
    input_tokens: int,
    output_tokens: int,
    *,
    batch: bool = False,
) -> float:
    """Coût en USD d'une requête ; 0 sans prix (juge local)."""
    if prices is None:
        return 0.0
    input_rate = prices["input_per_mtok"]
    output_rate = prices["output_per_mtok"]
    long_context = prices.get("long_context")
    if long_context is not None and input_tokens > long_context["threshold_tokens"]:
        input_rate = long_context["input_per_mtok"]
        output_rate = long_context["output_per_mtok"]
    cost = (input_tokens * input_rate + output_tokens * output_rate) / _MILLION
    if batch:
        cost *= 1 - prices.get("batch_discount", 0.0)
    return cost


def estimate_tokens(chars: int, chars_per_token: float) -> int:
    """Tokens estimés d'un texte de ``chars`` caractères (arrondi au-dessus)."""
    return math.ceil(chars / chars_per_token)


def estimate_cost(
    prices: Mapping[str, Any] | None,
    input_chars: int,
    max_tokens: int,
    chars_per_token: float,
    *,
    batch: bool = False,
) -> float:
    """Estimation prudente d'une requête : entrée estimée, sortie au plafond ``max_tokens``."""
    return request_cost(
        prices, estimate_tokens(input_chars, chars_per_token), max_tokens, batch=batch
    )


class Budget:
    """Plafond ``--max-cost-usd`` d'un lancement : avant chaque lot ou appel, dépense de ce
    lancement + estimation ≤ plafond, sinon ``CostCapError`` sans rien envoyer (code 3)."""

    def __init__(self, max_cost_usd: float | None) -> None:
        self.max_cost_usd = max_cost_usd
        self.spent = 0.0

    def check(self, estimate: float) -> None:
        if self.max_cost_usd is None:
            return
        if self.spent + estimate > self.max_cost_usd:
            raise CostCapError(
                f"plafond de {self.max_cost_usd:.4f} $ atteint : dépense de ce lancement "
                f"{self.spent:.4f} $ + estimation de l'envoi suivant {estimate:.4f} $ ; "
                "aucun appel de plus (reprenable par la même commande, plafond relevé)"
            )

    def spend(self, cost: float) -> None:
        self.spent += cost
