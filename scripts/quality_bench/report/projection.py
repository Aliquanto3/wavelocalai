"""Projection de durée de la campagne complète (CAP-8, campagne-et-reprise.md « Pilote ») :
fonctions pures sur les lignes du pilote, ses chauffes et les débits de l'ancien banc.

- **Lignes requêtées** : ``calls ≥ 1`` et statut ``ok`` ou ``truncated``.
- **Moyennes mesurées**, tous modèles du pilote confondus : complétion ``C̄`` par (piste, usage),
  prompt évalué ``P̄ = moyenne(tokens.prompt)`` par (piste, usage, palier), repli sur la moyenne
  de la piste et de l'usage. Usage sans mesure : ``C̄`` = plafond, ``P̄`` = ``est_prompt_tokens``
  de la question, compté et signalé.
- **Palier de référence** : celui dont le ``prompt_tokens`` de chauffe (médiane des chauffes du
  palier) est le plus proche de la médiane des ``prefill_prompt_tokens`` de l'ancien banc des
  modèles du pilote. ``deg(palier)`` = médiane, sur les modèles du pilote, de
  ``prefill(palier) / prefill(référence)`` (maximum des chauffes d'un même couple : la première
  chauffe d'un modèle, à froid, sous-estime le préremplissage, 139 contre 1 872 tok/s mesurés
  sur la tour le 2026-10-12) ; 1,0 et signalé sans mesure.
- **Surcoût** ``f = Σ wall_s / Σ (prompt_eval + eval) / 1e9`` sur les lignes requêtées.
- **Durée d'un modèle et d'une piste** (jeu entier) :
  ``f × Σ_q [C̄/décodage + P̄/(préremplissage × deg(palier))]
  + Σ_paliers (chargement + palier/4 / préremplissage)``. La piste ``think_on`` n'est comptée
  que pour un modèle ``thinking`` au catalogue.
- **Réductions** (au-delà du budget seulement, cumulées dans l'ordre de SPEC.md) : chaque
  plafond candidat (``C̄`` recalculé avec ``min(completion, plafond × calls)``), constat du
  nombre de modèles ``thinking`` en piste activée, piste activée ramenée à ``think_on_n``.
  Publiées comme **proposition**, jamais appliquées.

Toute valeur indéfinie est rendue ``None`` : aucune division par zéro ne fait échouer le
rapport.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..common.schemas import TRACKS
from .campaign import number

REQUESTED_STATUSES = ("ok", "truncated")
SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True)
class Line:
    """Faits d'une ligne de génération concordante, sans texte de question ni de sortie."""

    key: str
    model: str
    digest: str
    track: str
    question_id: str
    usage: str
    source: str
    num_ctx: int
    seed: int
    status: str
    calls: int
    attempts: int
    prompt: int
    prompt_cached: int
    completion: int
    thinking_est: int
    wall_s: float
    prompt_eval_ns: int
    eval_ns: int
    prompt_hash: str
    output_hash: str
    context_limit: str | None = None  # cause d'un context_exceeded : model | bench

    @property
    def requested(self) -> bool:
        return self.calls >= 1 and self.status in REQUESTED_STATUSES


@dataclass(frozen=True)
class Warmup:
    """Chauffe consignée (``qb.warmup/1``)."""

    model: str
    num_ctx: int
    prompt_tokens: int
    prefill_tok_s: float | None


@dataclass(frozen=True)
class ModelRate:
    """Débits de l'ancien banc et capacité ``thinking`` du catalogue pour un tag Ollama ;
    ``reason`` dit pourquoi le débit est inconnu (``None`` s'il est connu)."""

    tag: str
    name: str | None
    decode: float | None
    prefill: float | None
    prefill_prompt_tokens: float | None
    load_s: float | None
    thinking: bool | None
    reason: str | None = None

    @property
    def known(self) -> bool:
        return self.reason is None


@dataclass(frozen=True)
class FullQuestion:
    """Question du jeu entier dans une piste : usage, palier et prompt estimé."""

    usage: str
    num_ctx: int
    est_prompt_tokens: int


def merge_caps(
    base: Mapping[str, Mapping[str, int]], partial: Mapping[str, Mapping[str, int]]
) -> dict[str, dict[str, int]]:
    """Plafond candidat partiel (``pilot.yaml``) fusionné sur les plafonds résolus de la
    campagne : un plafond non cité reste celui de la campagne."""
    return {
        track: dict(sorted({**base[track], **partial.get(track, {})}.items())) for track in TRACKS
    }


def cap_for(caps: Mapping[str, Mapping[str, int]], track: str, usage: str) -> int:
    """Plafond par appel : ``caps[piste][usage]``, sinon ``caps[piste].default``."""
    return int(caps[track].get(usage, caps[track]["default"]))


def _mean(values: Sequence[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def capped_completion(line: Line, cap: int | None) -> float:
    """Complétion de la ligne, bornée à ``cap × calls`` pour un plafond candidat."""
    if cap is None:
        return float(line.completion)
    return float(min(line.completion, cap * max(1, line.calls)))


def truncated_under(line: Line, cap: int) -> bool:
    """Ligne déjà tronquée, ou dont la complétion atteint ``cap × calls`` (approximation par
    appel)."""
    return line.status == "truncated" or line.completion >= cap * max(1, line.calls)


# -- Surcoût, palier de référence, dégradation ----------------------------------------------


def overhead(lines: Iterable[Line]) -> tuple[float, bool]:
    """``(f, mesuré)`` : ``Σ wall_s / Σ (prompt_eval + eval) / 1e9`` ; ``(1.0, False)`` sans
    durée mesurée."""
    wall = 0.0
    model_ns = 0
    for line in lines:
        if line.requested:
            wall += line.wall_s
            model_ns += line.prompt_eval_ns + line.eval_ns
    if model_ns <= 0 or wall <= 0:
        return 1.0, False
    return wall / (model_ns / 1e9), True


def reference_tier(warmups: Sequence[Warmup], target_prompt_tokens: float | None) -> int | None:
    """Palier dont le ``prompt_tokens`` de chauffe (médiane du palier) est le plus proche de
    ``target_prompt_tokens`` ; à égalité, le plus petit palier. ``None`` sans chauffe ou sans
    cible."""
    if target_prompt_tokens is None:
        return None
    by_tier: dict[int, list[float]] = {}
    for warmup in warmups:
        if warmup.prompt_tokens > 0:
            by_tier.setdefault(warmup.num_ctx, []).append(float(warmup.prompt_tokens))
    if not by_tier:
        return None
    return min(
        by_tier,
        key=lambda tier: (abs(statistics.median(by_tier[tier]) - target_prompt_tokens), tier),
    )


def degradation(
    warmups: Sequence[Warmup], models: Sequence[str], tiers: Iterable[int], reference: int | None
) -> dict[int, tuple[float, bool, int]]:
    """``palier → (deg, mesuré, modèles)`` : médiane sur ``models`` de
    ``prefill(palier) / prefill(référence)`` (maximum des chauffes d'un même couple, la chauffe à
    froid sous-estimant le préremplissage) ; ``(1.0, False, 0)`` sans mesure."""
    prefill: dict[tuple[str, int], list[float]] = {}
    for warmup in warmups:
        if warmup.prefill_tok_s is not None and warmup.prefill_tok_s > 0:
            prefill.setdefault((warmup.model, warmup.num_ctx), []).append(warmup.prefill_tok_s)
    result: dict[int, tuple[float, bool, int]] = {}
    for tier in sorted(set(tiers)):
        ratios = []
        if reference is not None:
            for model in models:
                at_tier = prefill.get((model, tier))
                at_reference = prefill.get((model, reference))
                if at_tier and at_reference:
                    ratios.append(max(at_tier) / max(at_reference))
        if ratios:
            result[tier] = (float(statistics.median(ratios)), True, len(ratios))
        else:
            result[tier] = (1.0, False, 0)
    return result


# -- Moyennes mesurées ----------------------------------------------------------------------


@dataclass(frozen=True)
class Means:
    """``C̄`` par (piste, usage) et ``P̄`` par (piste, usage, palier) et par (piste, usage)."""

    completion: dict[tuple[str, str], float]
    prompt_by_tier: dict[tuple[str, str, int], float]
    prompt: dict[tuple[str, str], float]
    lines: dict[tuple[str, str], int]


def measured_means(lines: Iterable[Line], caps: Mapping[str, Any] | None = None) -> Means:
    """Moyennes des lignes requêtées ; ``caps`` : plafonds candidats appliqués à la
    complétion (``min(completion, plafond × calls)``)."""
    completion: dict[tuple[str, str], list[float]] = {}
    prompt_tier: dict[tuple[str, str, int], list[float]] = {}
    prompt: dict[tuple[str, str], list[float]] = {}
    for line in lines:
        if not line.requested:
            continue
        cap = None if caps is None else cap_for(caps, line.track, line.usage)
        pair = (line.track, line.usage)
        completion.setdefault(pair, []).append(capped_completion(line, cap))
        prompt_tier.setdefault((line.track, line.usage, line.num_ctx), []).append(line.prompt)
        prompt.setdefault(pair, []).append(float(line.prompt))
    return Means(
        completion={pair: math.fsum(v) / len(v) for pair, v in completion.items()},
        prompt_by_tier={key: math.fsum(v) / len(v) for key, v in prompt_tier.items()},
        prompt={pair: math.fsum(v) / len(v) for pair, v in prompt.items()},
        lines={pair: len(v) for pair, v in completion.items()},
    )


def _question_tokens(
    means: Means, caps: Mapping[str, Any], track: str, question: FullQuestion
) -> tuple[float, float, bool]:
    """``(C̄, P̄, mesuré)`` d'une question du jeu entier."""
    pair = (track, question.usage)
    if pair not in means.completion:
        return float(cap_for(caps, track, question.usage)), float(question.est_prompt_tokens), False
    prompt = means.prompt_by_tier.get((track, question.usage, question.num_ctx))
    return means.completion[pair], means.prompt[pair] if prompt is None else prompt, True


def track_seconds(
    rate: ModelRate,
    track: str,
    questions: Sequence[FullQuestion],
    means: Means,
    caps: Mapping[str, Any],
    deg: Mapping[int, tuple[float, bool, int]],
    f: float,
) -> tuple[float, float]:
    """``(questions_s, chauffes_s)`` d'un modèle à débit connu sur une piste."""
    assert rate.decode and rate.prefill  # noqa: S101 (appelé pour un débit connu seulement)
    total = 0.0
    for question in questions:
        completion, prompt, _ = _question_tokens(means, caps, track, question)
        factor = deg.get(question.num_ctx, (1.0, False, 0))[0]
        total += completion / rate.decode + prompt / (rate.prefill * factor)
    load = rate.load_s or 0.0
    tiers = sorted({question.num_ctx for question in questions})
    warm = math.fsum(load + (tier / 4) / rate.prefill for tier in tiers)
    return f * total, warm


# -- Projection -----------------------------------------------------------------------------


def _hours(seconds: float | None) -> float | None:
    return None if seconds is None else number(seconds / SECONDS_PER_HOUR)


def _model_tracks(rate: ModelRate) -> list[str]:
    return [track for track in TRACKS if track == "think_off" or rate.thinking]


def _scenario_total(
    rates: Sequence[ModelRate],
    full: Mapping[str, Sequence[FullQuestion]],
    means: Means,
    caps: Mapping[str, Any],
    deg: Mapping[int, tuple[float, bool, int]],
    f: float,
) -> dict[str, float]:
    """Secondes par piste sur les modèles à débit connu."""
    totals = dict.fromkeys(TRACKS, 0.0)
    for rate in rates:
        if not rate.known:
            continue
        for track in _model_tracks(rate):
            questions_s, warm_s = track_seconds(rate, track, full[track], means, caps, deg, f)
            totals[track] += questions_s + warm_s
    return totals


def _projected_truncation(lines: Sequence[Line], caps: Mapping[str, Any]) -> float | None:
    requested = [line for line in lines if line.requested]
    if not requested:
        return None
    hits = sum(
        1 for line in requested if truncated_under(line, cap_for(caps, line.track, line.usage))
    )
    return number(hits / len(requested))


def project(
    *,
    lines: Sequence[Line],
    warmups: Sequence[Warmup],
    pilot_models: Sequence[str],
    pilot_questions: Mapping[tuple[str, str], Sequence[str]],
    questions_by_id: Mapping[str, FullQuestion],
    full: Mapping[str, Sequence[FullQuestion]],
    campaign_caps: Mapping[str, Any],
    rates: Sequence[ModelRate],
    pilot_rates: Mapping[str, ModelRate],
    budget_hours: float,
    reduction_caps: Sequence[Mapping[str, Any]],
    think_on_n: int,
) -> dict[str, Any]:
    """Section ``projection`` du rapport du pilote.

    ``pilot_questions`` : (modèle, piste) → questions de ses lignes requêtées (contrôle) ;
    ``full`` : piste → questions du jeu entier ; ``rates`` : les modèles de la campagne
    complète, dans l'ordre de ``pilot.yaml`` ; ``pilot_rates`` : débits des modèles du pilote
    (cible du palier de référence, contrôle, débit mesuré)."""
    f, f_measured = overhead(lines)
    rate_by_tag = dict(pilot_rates)
    pilot_prompt = [
        rate_by_tag[tag].prefill_prompt_tokens
        for tag in pilot_models
        if tag in rate_by_tag and rate_by_tag[tag].prefill_prompt_tokens is not None
    ]
    target = _median([float(value) for value in pilot_prompt if value is not None])
    reference = reference_tier(warmups, target)
    tiers = {question.num_ctx for track in TRACKS for question in full[track]}
    tiers |= {warmup.num_ctx for warmup in warmups}
    deg = degradation(warmups, pilot_models, tiers, reference)
    means = measured_means(lines)

    unmeasured = []
    for track in TRACKS:
        counts: dict[str, int] = {}
        for question in full[track]:
            if (track, question.usage) not in means.completion:
                counts[question.usage] = counts.get(question.usage, 0) + 1
        unmeasured += [
            {"track": track, "usage": usage, "questions": counts[usage]} for usage in sorted(counts)
        ]

    models = []
    totals = dict.fromkeys(TRACKS, 0.0)
    for rate in rates:
        entry: dict[str, Any] = {
            "tag": rate.tag,
            "name": rate.name,
            "thinking": rate.thinking,
            "known": rate.known,
            "reason": rate.reason,
            "think_off_hours": None,
            "think_on_hours": None,
            "total_hours": None,
        }
        if rate.known:
            seconds = 0.0
            for track in _model_tracks(rate):
                questions_s, warm_s = track_seconds(
                    rate, track, full[track], means, campaign_caps, deg, f
                )
                entry[f"{track}_hours"] = _hours(questions_s + warm_s)
                totals[track] += questions_s + warm_s
                seconds += questions_s + warm_s
            entry["total_hours"] = _hours(seconds)
        models.append(entry)
    total_s = totals["think_off"] + totals["think_on"]
    complete = all(rate.known for rate in rates)
    over_budget = total_s / SECONDS_PER_HOUR > budget_hours
    # Total incomplet sous le budget : rien ne permet de conclure (débits manquants).
    if over_budget:
        conclusion = "over_budget"
    elif complete:
        conclusion = "under_budget"
    else:
        conclusion = "undetermined"

    # Contrôle : la même formule sur les questions requêtées de chaque modèle du pilote ; la
    # durée murale de toutes ses lignes (erreurs et contextes dépassés compris) à côté.
    control = []
    for tag in pilot_models:
        rate = rate_by_tag.get(tag)
        for track in TRACKS:
            mine = [line for line in lines if line.model == tag and line.track == track]
            if not mine:
                continue
            ids = pilot_questions.get((tag, track)) or []
            measured = math.fsum(line.wall_s for line in mine if line.requested)
            measured_all = math.fsum(line.wall_s for line in mine)
            predicted = None
            if ids and rate is not None and rate.known:
                questions = [questions_by_id[qid] for qid in ids]
                predicted, _ = track_seconds(rate, track, questions, means, campaign_caps, deg, f)
            control.append(
                {
                    "model": tag,
                    "track": track,
                    "lines": len(ids),
                    "predicted_hours": _hours(predicted),
                    "measured_hours": _hours(measured),
                    "ratio": number(measured / predicted) if predicted else None,
                    "all_lines": len(mine),
                    "measured_all_hours": _hours(measured_all),
                }
            )

    decode = []
    for tag in pilot_models:
        mine = [line for line in lines if line.model == tag and line.requested]
        eval_s = math.fsum(line.eval_ns for line in mine) / 1e9
        measured_rate = math.fsum(line.completion for line in mine) / eval_s if eval_s > 0 else None
        rate = rate_by_tag.get(tag)
        old = rate.decode if rate is not None else None
        decode.append(
            {
                "model": tag,
                "measured_tok_s": number(measured_rate),
                "old_tok_s": number(old),
                "ratio": number(measured_rate / old) if measured_rate and old else None,
            }
        )

    reduction = None
    if over_budget:
        reduction = _reduction(
            lines=lines,
            full=full,
            rates=rates,
            deg=deg,
            f=f,
            budget_hours=budget_hours,
            reduction_caps=reduction_caps,
            think_on_n=think_on_n,
        )

    return {
        "budget_hours": number(budget_hours),
        "overhead": {"value": number(f), "measured": f_measured},
        "reference_tier": reference,
        "old_bench_prompt_tokens": number(target),
        "degradation": [
            {"num_ctx": tier, "factor": number(value), "measured": measured, "models": n}
            for tier, (value, measured, n) in sorted(deg.items())
        ],
        "means": [
            {
                "track": track,
                "usage": usage,
                "lines": means.lines[(track, usage)],
                "completion_mean": number(means.completion[(track, usage)]),
                "prompt_mean": number(means.prompt[(track, usage)]),
            }
            for track, usage in sorted(means.completion, key=_track_usage_key)
        ],
        "unmeasured": unmeasured,
        "models": models,
        "think_off_hours": _hours(totals["think_off"]),
        "think_on_hours": _hours(totals["think_on"]),
        "total_hours": _hours(total_s),
        "complete": complete,
        "over_budget": over_budget,
        "conclusion": conclusion,
        "control": control,
        "decode": decode,
        "reduction": reduction,
    }


def _track_usage_key(pair: tuple[str, str]) -> tuple[int, str]:
    return TRACKS.index(pair[0]), pair[1]


def _reduction(
    *,
    lines: Sequence[Line],
    full: Mapping[str, Sequence[FullQuestion]],
    rates: Sequence[ModelRate],
    deg: Mapping[int, tuple[float, bool, int]],
    f: float,
    budget_hours: float,
    reduction_caps: Sequence[Mapping[str, Any]],
    think_on_n: int,
) -> dict[str, Any]:
    """Scénarios cumulés dans l'ordre de SPEC.md ; le premier sous le budget est signalé."""
    scenarios: list[dict[str, Any]] = []
    last_totals: dict[str, float] | None = None
    last_caps: Mapping[str, Any] | None = None
    for index, caps in enumerate(reduction_caps, start=1):
        means = measured_means(lines, caps)
        last_totals = _scenario_total(rates, full, means, caps, deg, f)
        last_caps = caps
        scenarios.append(
            {
                "step": "caps",
                "index": index,
                "caps": {track: dict(sorted(caps[track].items())) for track in TRACKS},
                "projected_truncation": _projected_truncation(lines, caps),
                "totals": last_totals,
            }
        )
    thinking = [rate.tag for rate in rates if rate.known and rate.thinking]
    scenarios.append(
        {
            "step": "thinking_only",
            "thinking_models": len(thinking),
            "non_thinking_models": sum(1 for rate in rates if rate.known and not rate.thinking),
            "totals": dict(last_totals) if last_totals is not None else None,
        }
    )
    full_think_on = len(full["think_on"])
    factor = think_on_n / full_think_on if full_think_on else 1.0
    if last_totals is not None:
        scaled = {
            "think_off": last_totals["think_off"],
            "think_on": last_totals["think_on"] * min(1.0, factor),
        }
    else:
        scaled = None
    scenarios.append(
        {
            "step": "think_on_n",
            "think_on_n": think_on_n,
            "think_on_full": full_think_on,
            "projected_truncation": (
                _projected_truncation(lines, last_caps) if last_caps is not None else None
            ),
            "totals": scaled,
        }
    )
    first = None
    for position, scenario in enumerate(scenarios):
        totals = scenario.pop("totals")
        if totals is None:
            scenario.update(think_off_hours=None, think_on_hours=None, total_hours=None)
            scenario["under_budget"] = False
            continue
        total = totals["think_off"] + totals["think_on"]
        scenario["think_off_hours"] = _hours(totals["think_off"])
        scenario["think_on_hours"] = _hours(totals["think_on"])
        scenario["total_hours"] = _hours(total)
        scenario["under_budget"] = total / SECONDS_PER_HOUR <= budget_hours
        if first is None and scenario["under_budget"]:
            first = position
    return {"proposal": True, "scenarios": scenarios, "first_under_budget": first}
