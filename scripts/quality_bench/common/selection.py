"""Résolution de ``generation.selection`` (AD-8, AD-17) : seule implémentation, partagée par le
plan du runner (``generation/runner.py``) et par les clés attendues du rapport
(``report/inputs.py``), qui retrouvent ainsi exactement les mêmes questions.

- ``None`` : aucune restriction (``selected_ids`` rend ``None``) ;
- ``{ids: [...]}`` : ces questions, qui doivent toutes figurer dans le jeu ;
- ``{sample: {per_usage, seed}}`` : tirage de ``per_usage`` questions par usage parmi celles de
  la piste ``think_off``, à graine dérivée ``sha256_hex([seed, "selection", usage])`` : ajouter
  un usage au jeu ne change pas le tirage des autres. ``think_on`` en garde l'intersection ;
- ``{groups: {seed, per_usage: {<usage>: {think_off, think_on}}}}`` : tirage par **groupes
  entiers**, stratifié par source (``group_ids``). ``think_on`` groupes parmi ceux qui ont au
  moins une question en piste ``think_on``, ``think_off − think_on`` parmi les autres ; la
  sélection prend toutes les questions ``think_off`` des groupes retenus, ``think_on`` en garde
  l'intersection. Préfixe stable : même graine et effectifs plus petits donnent un
  sous-ensemble (rejeu du pilote, AD-4).
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


def _group_order(groups: Mapping[str, str], seed: int, usage: str) -> list[str]:
    """Ordre stratifié d'un ensemble de groupes (``groupe → source``) : dans chaque source,
    groupes triés par ``h(g) = sha256_hex([seed, "groups", usage, g])`` puis ``g`` ; le rang
    ``r`` d'une source de ``n`` groupes donne la position ``(r + 0.5) / n`` ; l'ensemble est
    trié par (position, ``h(g)``, ``g``). Un préfixe représente chaque source à peu près en
    proportion : exactement pour des sources de même taille, à moins d'une unité près sur
    ``set-v1`` (vérifié) ; l'écart peut dépasser une unité entre sources très inégales."""
    digest = {group: sha256_hex([seed, "groups", usage, group]) for group in groups}
    by_source: dict[str, list[str]] = {}
    for group, source in groups.items():
        by_source.setdefault(source, []).append(group)
    keyed: list[tuple[float, str, str]] = []
    for members in by_source.values():
        ordered = sorted(members, key=lambda g: (digest[g], g))
        for rank, group in enumerate(ordered):
            keyed.append(((rank + 0.5) / len(ordered), digest[group], group))
    return [group for _, _, group in sorted(keyed)]


def group_ids(
    think_off_ids: Sequence[str],
    think_on_ids: Sequence[str],
    questions: Mapping[str, Mapping[str, Any]],
    groups: Mapping[str, Any],
) -> set[str]:
    """Tirage par groupes entiers (mode ``groups``) : questions ``think_off`` des groupes
    retenus pour chaque usage de ``per_usage`` (un usage absent ne donne rien).

    La source d'un groupe est celle de sa première question par ``id``. ``G_on`` = groupes de
    l'usage qui ont au moins une question dans ``think_on_ids``, ``G_off`` = les autres ; sont
    retenus les ``think_on`` premiers de l'ordre de ``G_on`` et les ``think_off − think_on``
    premiers de ``G_off`` (avertissement journalisé si un ensemble est trop court : tout est
    pris)."""
    on = set(think_on_ids)
    seed = groups["seed"]
    chosen: set[str] = set()
    for usage in sorted(groups["per_usage"]):
        counts = groups["per_usage"][usage]
        members: dict[str, list[str]] = {}
        for qid in sorted(set(think_off_ids)):
            if questions[qid]["usage"] == usage:
                members.setdefault(questions[qid]["group"], []).append(qid)
        source = {group: questions[ids[0]]["source"] for group, ids in members.items()}
        g_on = {g: s for g, s in source.items() if any(qid in on for qid in members[g])}
        g_off = {g: s for g, s in source.items() if g not in g_on}
        wanted = (
            ("think_on", g_on, counts["think_on"]),
            ("think_off", g_off, counts["think_off"] - counts["think_on"]),
        )
        for label, pool, count in wanted:
            if count > len(pool):
                logger.warning(
                    "Sélection %s : %d groupes %s seulement (%d demandés), tous pris",
                    usage,
                    len(pool),
                    "avec une question think_on" if label == "think_on" else "sans think_on",
                    count,
                )
            for group in _group_order(pool, seed, usage)[:count]:
                chosen.update(members[group])
    return chosen


def selected_ids(
    selection: Mapping[str, Any] | None,
    questions: Mapping[str, Mapping[str, Any]],
    think_off_ids: Sequence[str],
    think_on_ids: Sequence[str],
) -> set[str] | None:
    """Questions retenues par ``selection``, ou ``None`` sans restriction.

    ``think_on_ids`` (piste ``think_on`` du jeu), obligatoire, ne sert qu'au mode ``groups``.
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
    if "groups" in selection:
        return group_ids(think_off_ids, think_on_ids, questions, selection["groups"])
    return sample_ids(think_off_ids, questions, selection["sample"])
