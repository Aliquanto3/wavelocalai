"""Construction d'une question ``qb.question/1`` : noyau pur, sans réseau ni I/O.

``build_question`` normalise les chaînes en NFC, estime la taille du prompt, choisit le plus
petit palier ``num_ctx`` par défaut qui respecte la règle d'AD-5, encode les flottants de la
cible, calcule les empreintes et valide la question. Les importeurs (``importers/``), les
générateurs (``generators/``) et le chargeur des questions maison (``house.py``) passent tous
par ici. ``build_questions`` écarte et compte les prompts trop longs. ``set_builder`` refait le
contrôle de palier sur chaque question du jeu.

**Multi-tours (AD-5) :** le runner renvoie au modèle tout l'historique à chaque appel (messages,
appels d'outils, résultats d'outils et réponses des tours précédents). L'estimation du prompt
d'une conversation compte donc cet historique : l'appelant passe ``history``, les messages que
produirait un modèle qui suit la cible (``importers/bfcl.py``), jusqu'au dernier tour.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ..common.canonical import canonical_bytes, nfc
from ..common.config import DEFAULT_GENERATION
from .schema import QUESTION_SCHEMA_ID, SOURCES, validate_question, with_hashes

logger = logging.getLogger(__name__)

# Estimation prudente : 3 caractères par token (le français et le JSON en comptent moins de 4).
CHARS_PER_TOKEN = 3
CONTEXT_MARGIN = 1.25
FLOAT_MARKER = "$float"


class PromptTooLongError(ValueError):
    """Aucun palier ``num_ctx`` par défaut ne contient le prompt et le plafond de réponse."""


def normalize(value: Any) -> Any:
    """Copie de ``value`` dont chaque chaîne (clés comprises) est normalisée en NFC."""
    if isinstance(value, str):
        return nfc(value)
    if isinstance(value, Mapping):
        return {nfc(str(key)): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value


def encode_floats(value: Any) -> Any:
    """Remplace chaque flottant d'une cible par ``{"$float": repr(x)}`` (AD-4 : une cible
    numérique n'est jamais un flottant). Le correcteur (story 4) le décode par ``float()``,
    sans perte : ``repr`` est la forme la plus courte qui redonne le même flottant."""
    if isinstance(value, float):
        return {FLOAT_MARKER: repr(value)}
    if isinstance(value, Mapping):
        return {key: encode_floats(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode_floats(item) for item in value]
    return value


def max_cap(usage: str, caps: Mapping[str, Mapping[str, int]] | None = None) -> int:
    """Plafond maximal de ``num_predict`` de l'usage sur les deux pistes (valeurs par défaut
    d'AD-8, sauf ``caps`` explicite)."""
    caps = DEFAULT_GENERATION["caps"] if caps is None else caps
    return max(track_caps.get(usage, track_caps["default"]) for track_caps in caps.values())


def estimate_prompt_tokens(
    prompt: Mapping[str, Any], history: Sequence[Mapping[str, Any]] | None = None
) -> int:
    """Estimation du nombre de tokens du prompt (messages, tours, outils, format) et, pour une
    conversation multi-tours, de l'historique accumulé jusqu'au dernier tour (``history``)."""
    payload = dict(prompt)
    if history:
        payload["history"] = [dict(message) for message in history]
    chars = len(canonical_bytes(payload).decode("utf-8"))
    return max(1, math.ceil(chars / CHARS_PER_TOKEN))


def required_num_ctx(est_prompt_tokens: int, usage: str) -> float:
    """Contexte minimal d'AD-5 : ``est × 1,25 + plafond maximal de num_predict``."""
    return est_prompt_tokens * CONTEXT_MARGIN + max_cap(usage)


def choose_num_ctx(est_prompt_tokens: int, usage: str) -> int:
    """Plus petit palier par défaut tel que ``num_ctx ≥ est × 1,25 + plafond`` (AD-5)."""
    needed = required_num_ctx(est_prompt_tokens, usage)
    for tier in DEFAULT_GENERATION["num_ctx_tiers"]:
        if tier >= needed:
            return tier
    raise PromptTooLongError(f"prompt estimé à {est_prompt_tokens} tokens : aucun palier")


def question_id(usage: str, source: str, number: int) -> str:
    """Identifiant opaque ``<usage>/<source>/<numéro>`` (AD-4), numéro sur 4 chiffres au moins."""
    return f"{usage}/{source}/{number:04d}"


def build_question(
    *,
    source: str,
    number: int,
    group: str,
    messages: list[dict[str, Any]],
    grader_params: Mapping[str, Any],
    target: Any,
    turns: list[list[dict[str, Any]]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    format: Mapping[str, Any] | None = None,  # noqa: A002 (nom du champ d'AD-5)
    env: Mapping[str, Any] | None = None,
    unit: str | None = None,
    criteria: list[dict[str, Any]] | None = None,
    generator: str | None = None,
    generator_seed: int | None = None,
    history: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construit et valide une question de ``source`` (importée, générée ou maison).

    ``history`` : messages accumulés par les tours d'une conversation (voir la docstring du
    module) ; ils entrent dans l'estimation du prompt, donc dans le palier ``num_ctx``, mais ne
    sont pas écrits dans la question."""
    spec = SOURCES[source]
    qid = question_id(spec.usage, source, number)
    prompt = normalize({"messages": messages, "turns": turns, "tools": tools, "format": format})
    est = estimate_prompt_tokens(prompt, history)
    record = {
        "schema": QUESTION_SCHEMA_ID,
        "id": qid,
        "usage": spec.usage,
        "group": nfc(group),
        "unit": nfc(unit) if unit else qid,
        "source": source,
        "license": spec.license,
        "private": spec.private,
        "generator": generator,
        "generator_seed": generator_seed,
        "num_ctx": choose_num_ctx(est, spec.usage),
        "est_prompt_tokens": est,
        **prompt,
        "env": normalize(env) if env is not None else None,
        "grader": {"name": spec.grader, "params": normalize(dict(grader_params))},
        "target": normalize(encode_floats(target)),
        "criteria": normalize(criteria) if criteria is not None else None,
    }
    return validate_question(with_hashes(record))


def build_questions(source: str, items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Construit les questions d'une source (arguments de ``build_question`` sans ``source``).

    Un prompt qu'aucun palier par défaut ne contient est écarté, et le compte est journalisé.
    Le numéro de chaque question est fixé par son producteur, écartées comprises : une question
    écartée ne décale pas les identifiants des suivantes.
    """
    questions = []
    skipped = 0
    for item in items:
        try:
            questions.append(build_question(source=source, **item))
        except PromptTooLongError:
            skipped += 1
    if skipped:
        logger.warning(
            "%s : %d questions écartées, prompt trop long pour le plus grand palier",
            source,
            skipped,
        )
    return questions
