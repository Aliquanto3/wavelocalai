"""Résolution de ``generation.selection`` (AD-8, AD-17) : seule implémentation, partagée par le
plan du runner (``generation/runner.py``) et par les clés attendues du rapport
(``report/inputs.py``), qui retrouvent ainsi exactement les mêmes questions.

- ``None`` : aucune restriction (``selected_ids`` rend ``None``) ;
- ``{ids: [...]}`` : ces questions, qui doivent toutes figurer dans le jeu ;
- ``{sample: {per_usage, seed}}`` : tirage de ``per_usage`` questions par usage parmi celles de
  la piste ``think_off``, à graine dérivée ``sha256_hex([seed, "selection", usage])`` : ajouter
  un usage au jeu ne change pas le tirage des autres. ``think_on`` en garde l'intersection.
"""

from __future__ import annotations

import logging
import random
from collections.abc import Mapping, Sequence
from typing import Any

from .canonical import sha256_hex

logger = logging.getLogger(__name__)


class SelectionError(ValueError):
    """Sélection qui cite une question hors du jeu."""


def sample_ids(
    ids: Sequence[str], questions: Mapping[str, Mapping[str, Any]], sample: Mapping[str, Any]
) -> set[str]:
    """Tirage de ``per_usage`` questions par usage parmi ``ids`` (piste ``think_off``), à graine
    dérivée par usage."""
    by_usage: dict[str, list[str]] = {}
    for qid in ids:
        by_usage.setdefault(questions[qid]["usage"], []).append(qid)
    chosen: set[str] = set()
    for usage in sorted(by_usage):
        pool = sorted(by_usage[usage])
        seed = int(sha256_hex([sample["seed"], "selection", usage]), 16)
        count = min(sample["per_usage"], len(pool))
        if count < sample["per_usage"]:
            logger.warning(
                "Sélection : %d questions %s seulement dans think_off (%d demandées), toutes prises",
                len(pool),
                usage,
                sample["per_usage"],
            )
        chosen.update(random.Random(seed).sample(pool, count))
    return chosen


def selected_ids(
    selection: Mapping[str, Any] | None,
    questions: Mapping[str, Mapping[str, Any]],
    think_off_ids: Sequence[str],
) -> set[str] | None:
    """Questions retenues par ``selection``, ou ``None`` sans restriction.

    ``SelectionError`` si ``selection.ids`` cite une question absente de ``questions``."""
    if selection is None:
        return None
    if "ids" in selection:
        unknown = [qid for qid in selection["ids"] if qid not in questions]
        if unknown:
            raise SelectionError(
                f"sélection : {len(unknown)} question(s) hors du jeu ({unknown[0]})"
            )
        return set(selection["ids"])
    return sample_ids(think_off_ids, questions, selection["sample"])
