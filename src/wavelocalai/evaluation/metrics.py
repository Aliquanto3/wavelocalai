"""Les trois notes de l'évaluation de la qualité, calculées à partir d'un juge et d'un embedding
donnés en fonctions (story 7.1, extraites en 7.2).

Le service d'évaluation les appelle avec le juge du run (`EvaluationService._ask`) ; le jeu fixe de
cas (story 7.2, `tests/v2/eval_fixed_set.py`) les rejoue avec des sorties de juge enregistrées ou
avec un vrai modèle : c'est le même code, donc une modification de l'invite ou du découpage change
les notes du jeu fixe. Aucun accès à la base, au hub ni au réseau.

Une note jamais calculable vaut `score: None` avec sa raison, jamais 0. Une réponse que le juge n'a
vue qu'en partie (plus de `MAX_ANSWER_CHARS` caractères) ou dont seules les premières affirmations
ont été vérifiées (plus de `MAX_CLAIMS`) **le dit dans sa raison** (report de la revue 7.1).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from wavelocalai.errors import ProviderError
from wavelocalai.evaluation import prompts, scoring
from wavelocalai.evaluation.judge import JudgeReply
from wavelocalai.inference.judge_port import NOT_EVALUATED_INVALID
from wavelocalai.models.port import ChatRequest

logger = logging.getLogger("wavelocalai.evaluation")

NOT_EVALUATED_NO_CLAIM = "non évalué : aucune affirmation à vérifier"
NOT_EVALUATED_NO_QUESTION = "non évalué : aucune question retrouvée depuis la réponse"
NOT_EVALUATED_EMBEDDING = "non évalué : modèle d'embedding indisponible"

Ask = Callable[[ChatRequest], Awaitable[JudgeReply]]
Embed = Callable[[list[str]], Awaitable[list[list[float]]]]


@dataclass(frozen=True)
class Metric:
    """Une note calculée : `score` nul = non évalué, `reason` dit pourquoi ; `detail` : `verdicts`,
    `questions` ou `useful` selon la métrique."""

    score: int | None
    reason: str
    detail: dict[str, Any] | None = None


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count < 2 else many}"


def cut_notice(answer: str) -> str:
    """Phrase à ajouter à la raison d'une note quand le juge n'a vu que le début de la réponse."""
    if not prompts.answer_is_cut(answer):
        return ""
    limit = f"{prompts.MAX_ANSWER_CHARS:,}".replace(",", " ")
    return f" Réponse tronquée à {limit} caractères pour le juge : notée sur son début."


def with_notice(reason: str, notice: str) -> str:
    """`reason` suivie de `notice`, après un point final si la raison du juge n'en porte pas."""
    if not notice:
        return reason
    reason = reason.rstrip()
    return reason + ("" if reason[-1:] in ".!?…" else ".") + notice


def claims_notice(total: int) -> str:
    """Phrase à ajouter à la raison de la fidélité quand le plafond a écarté des affirmations."""
    if total <= prompts.MAX_CLAIMS:
        return ""
    return f" Notée sur les {prompts.MAX_CLAIMS} premières affirmations sur {total}."


async def faithfulness(
    ask: Ask, question: str, answer: str, sources: Sequence[dict[str, Any]]
) -> Metric:
    """Affirmations extraites (un appel), puis vérifiées une à une contre les extraits (un appel
    chacune) ; la note est la part d'affirmations appuyées."""
    reply = await ask(prompts.claims_request(question, answer))
    if reply.text is None:
        return Metric(None, reply.reason)
    try:
        claims, total = prompts.read_claims(reply.text)
    except ProviderError:
        return Metric(None, NOT_EVALUATED_INVALID)
    if not claims:
        return Metric(None, NOT_EVALUATED_NO_CLAIM)
    verdicts: list[dict[str, Any]] = []
    for claim in claims:
        reply = await ask(prompts.verdict_request(claim, sources))
        if reply.text is None:
            return Metric(None, reply.reason)
        try:
            verdicts.append({"claim": claim, **prompts.parse_verdict(reply.text, len(sources))})
        except ProviderError:
            return Metric(None, NOT_EVALUATED_INVALID)
    supported = sum(1 for v in verdicts if v["verdict"] == prompts.SUPPORTED)
    contradicted = sum(1 for v in verdicts if v["verdict"] == prompts.CONTRADICTED)
    reason = f"{plural(supported, 'affirmation', 'affirmations')} sur {len(verdicts)} "
    reason += "appuyée par les extraits" if supported < 2 else "appuyées par les extraits"
    if contradicted:
        reason += f", {plural(contradicted, 'contredite', 'contredites')}"
    reason += "." + claims_notice(total) + cut_notice(answer)
    return Metric(scoring.faithfulness(verdicts), reason, {"verdicts": verdicts})


async def relevance(ask: Ask, embed: Embed, question: str, answer: str) -> Metric:
    """Questions retrouvées depuis la réponse (un appel du juge), puis cosinus moyen avec la
    question posée, par l'embedding donné."""
    reply = await ask(prompts.questions_request(answer))
    if reply.text is None:
        return Metric(None, reply.reason)
    try:
        retrieved = prompts.parse_questions(reply.text)
    except ProviderError:
        return Metric(None, NOT_EVALUATED_INVALID)
    if not retrieved:
        return Metric(None, NOT_EVALUATED_NO_QUESTION)
    try:
        vectors = await embed([question, *retrieved])
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - embedding en panne : note impossible, pas 0
        logger.warning("Embedding de la pertinence en échec : %r", exc)
        return Metric(None, NOT_EVALUATED_EMBEDDING)
    score, mean = scoring.relevance(vectors[0], vectors[1:])
    reason = (
        f"Cosinus moyen de {f'{mean:.2f}'.replace('.', ',')} entre la question posée et "
        f"{plural(len(retrieved), 'question retrouvée', 'questions retrouvées')} "
        "depuis la réponse." + cut_notice(answer)
    )
    return Metric(score, reason, {"questions": retrieved})


async def context_precision(
    ask: Ask, question: str, answer: str, sources: Sequence[dict[str, Any]]
) -> Metric:
    """Les extraits utiles à la réponse, désignés par le juge (un appel)."""
    reply = await ask(prompts.useful_request(question, answer, sources))
    if reply.text is None:
        return Metric(None, reply.reason)
    try:
        useful, why = prompts.parse_useful(reply.text, len(sources))
    except ProviderError:
        return Metric(None, NOT_EVALUATED_INVALID)
    reason = why or (
        f"{plural(len(useful), 'extrait', 'extraits')} sur {len(sources)} "
        f"{'sert' if len(useful) < 2 else 'servent'} à répondre."
    )
    return Metric(
        scoring.context_precision(useful, len(sources)),
        with_notice(reason, cut_notice(answer)),
        {"useful": useful},
    )
