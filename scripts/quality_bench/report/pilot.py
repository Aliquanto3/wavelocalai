"""Mesures du pilote (CAP-8) : fonctions pures sur les entrées chargées du pilote et du rejeu.

- **Discordance ψ** par piste, par paire et par usage binaire (et « global » = tous les usages
  binaires) : part des unités définies pour les deux modèles où leurs scores diffèrent (scores
  d'unité par ``stats.units``). N indicatif par l'approximation de Connor (``stats.power``).
- **Plafond et plancher** : usage binaire où la moyenne de chaque modèle est ≥ ``ceiling`` (ou
  ≤ ``floor``) ; les modèles qui y sont seuls sont listés.
- **Stabilité au rejeu** (AD-4, AD-17) : jointure sur (``model``, ``digest``, ``track``,
  ``question_id``, ``seed``) à ``prompt_hash`` égal ; sortie changée (empreinte de ``output``)
  et score changé (deux scores définis différents, usages binaires ; rédaction à part),
  rapportés au ψ moyen global de la piste. Aucune conclusion sur K.
- **Tokens et troncature** sur les lignes requêtées (``projection.Line.requested``).
- **Cohérence d'ordre** avec l'ancien banc et l'indice AA : décompte de paires concordantes,
  discordantes et à égalité, sans Spearman ni test.
- **Rédaction** notée par ``grading.jsonl``, provisoire ; ``awaiting_judgment`` compté à part.
- **Points différés** (``deferred-work.md``) : ``context_exceeded`` par source et par palier,
  unités non communes et meneur sur unités communes, reprises non comptées, cache de préfixe.

Aucune fonction ne lit de fichier ; aucun texte de question ni de sortie n'entre dans le
résultat. Les flottants passent par ``campaign.number`` (finis ou ``None``).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..common.schemas import TRACKS, USAGES
from ..stats.describe import describe
from ..stats.groups import leader_order
from ..stats.power import mcnemar_sample_size
from ..stats.units import unit_scores
from .campaign import AA_VARIANT_BY_TRACK, WRITING, number
from .inputs import CampaignInputs
from .projection import (
    FullQuestion,
    Line,
    ModelRate,
    Warmup,
    cap_for,
    merge_caps,
    project,
    truncated_under,
)

GLOBAL = "global"
DELTAS = (0.10, 0.20)
BFCL_MULTI = "bfcl-multi"
# Usage → valeur de l'ancien banc comparée (``None`` : moyenne des trois premiers, « global »).
OLD_BENCH_USAGES = ("reasoning", "instructions", "tools", "extraction", "abstention", "rag")
# Usages du « global » de l'ancien banc, repris côté pilote pour comparer le même périmètre.
OLD_BENCH_GLOBAL_USAGES = ("reasoning", "instructions", "tools")


@dataclass(frozen=True)
class CampaignData:
    """Entrées d'une campagne pour le pilote : ``load_inputs`` plus les faits des lignes de
    génération concordantes, les statuts bruts de ``grading.jsonl``, les chauffes et le nombre
    de lignes « Ollama ne répond plus » du journal de génération (``None`` : journal absent)."""

    inputs: CampaignInputs
    lines: dict[str, Line]
    grading_status: dict[str, str]
    warmups: tuple[Warmup, ...]
    log_retries: int | None


@dataclass(frozen=True)
class OldBenchEntry:
    """Ancien banc d'un tag (par le nom du catalogue) : débits et valeurs par usage."""

    rate: ModelRate
    values: dict[str, float | None]


# -- Outils ---------------------------------------------------------------------------------


def track_models(inputs: CampaignInputs, track: str) -> list[str]:
    return [model["tag"] for model in inputs.models if track in model["tracks"]]


def track_usages(inputs: CampaignInputs, track: str) -> list[str]:
    present = {
        inputs.questions[item.question_id]["usage"]
        for item in inputs.expected
        if item.track == track
    }
    return [usage for usage in USAGES if usage in present]


def binary_usages(inputs: CampaignInputs, track: str) -> list[str]:
    return [usage for usage in track_usages(inputs, track) if usage != WRITING]


def unit_table(
    inputs: CampaignInputs, track: str, usages: Sequence[str]
) -> tuple[list[str], dict[str, dict[str, float | None]]]:
    """Unités du périmètre (piste, usages) et score d'unité de chaque modèle de la piste."""
    wanted = set(usages)
    items = [
        item
        for item in inputs.expected
        if item.track == track and inputs.questions[item.question_id]["usage"] in wanted
    ]
    units = sorted({inputs.questions[item.question_id]["unit"] for item in items})
    scores: dict[str, dict[str, float | None]] = {}
    for model in track_models(inputs, track):
        mine = [item for item in items if item.model == model]
        values = []
        for item in mine:
            row = inputs.rows.get(item.key)
            values.append(None if row is None else row.score)
        by_unit = unit_scores(
            [inputs.questions[item.question_id]["unit"] for item in mine],
            [item.seed for item in mine],
            values,
        )
        scores[model] = {unit: by_unit.get(unit) for unit in units}
    return units, scores


def _model_mean(units: Sequence[str], scores: Mapping[str, float | None]) -> float:
    values = [scores[unit] for unit in units if scores.get(unit) is not None]
    return math.fsum(values) / len(values) if values else math.nan  # type: ignore[arg-type]


def _scopes(inputs: CampaignInputs, track: str) -> list[tuple[str, list[str]]]:
    usages = binary_usages(inputs, track)
    return ([(GLOBAL, usages)] if usages else []) + [(usage, [usage]) for usage in usages]


# -- Discordance ψ --------------------------------------------------------------------------


def pair_discordance(
    a: Mapping[str, float | None], b: Mapping[str, float | None], units: Sequence[str]
) -> tuple[int, int]:
    """``(unités définies pour les deux, unités où les scores diffèrent)``."""
    both = [unit for unit in units if a.get(unit) is not None and b.get(unit) is not None]
    return len(both), sum(1 for unit in both if a[unit] != b[unit])


def discordance(inputs: CampaignInputs) -> list[dict[str, Any]]:
    """Section ``discordance`` : ψ par piste, périmètre et paire, ψ moyen et N de Connor."""
    tracks = []
    for track in TRACKS:
        models = track_models(inputs, track)
        if not models:
            continue
        scopes = []
        for name, usages in _scopes(inputs, track):
            units, scores = unit_table(inputs, track, usages)
            pairs, psis = [], []
            for i, a in enumerate(models):
                for b in models[i + 1 :]:
                    n, discordant = pair_discordance(scores[a], scores[b], units)
                    psi = discordant / n if n else None
                    if psi is not None:
                        psis.append(psi)
                    pairs.append(
                        {"a": a, "b": b, "n": n, "discordant": discordant, "psi": number(psi)}
                    )
            psi_mean = math.fsum(psis) / len(psis) if psis else None
            psi_max = max(psis) if psis else None
            scopes.append(
                {
                    "scope": name,
                    "units": len(units),
                    "pairs": pairs,
                    "psi_mean": number(psi_mean),
                    "psi_min": number(min(psis)) if psis else None,
                    "psi_max": number(psi_max),
                    # N de Connor au ψ moyen et au ψ maximal ; None : ψ < δ (hors domaine).
                    "n_connor": [
                        {
                            "delta": delta,
                            "n": _connor(psi_mean, delta),
                            "n_psi_max": _connor(psi_max, delta),
                        }
                        for delta in DELTAS
                    ],
                }
            )
        tracks.append({"track": track, "scopes": scopes})
    return tracks


def _connor(psi: float | None, delta: float) -> int | None:
    """N de Connor arrondi à l'entier supérieur ; ``None`` sans ψ ou hors domaine (ψ < δ)."""
    if psi is None:
        return None
    value = mcnemar_sample_size(psi, delta)
    return math.ceil(value) if math.isfinite(value) else None


def global_psi(discordance_tracks: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    """ψ moyen du périmètre global de chaque piste."""
    result: dict[str, float | None] = {}
    for block in discordance_tracks:
        scope = next((s for s in block["scopes"] if s["scope"] == GLOBAL), None)
        result[block["track"]] = None if scope is None else scope["psi_mean"]
    return result


# -- Plafonds et planchers ------------------------------------------------------------------


def ceiling_floor(inputs: CampaignInputs, ceiling: float, floor: float) -> list[dict[str, Any]]:
    """Usages binaires de chaque piste : moyenne de chaque modèle, statut plafond ou plancher
    (tous les modèles au-delà du seuil), modèles seuls au-delà du seuil."""
    result = []
    for track in TRACKS:
        models = track_models(inputs, track)
        for usage in binary_usages(inputs, track) if models else []:
            units, scores = unit_table(inputs, track, [usage])
            means = {model: _model_mean(units, scores[model]) for model in models}
            defined = {model: mean for model, mean in means.items() if math.isfinite(mean)}
            high = [model for model in models if model in defined and defined[model] >= ceiling]
            low = [model for model in models if model in defined and defined[model] <= floor]
            status = None
            if defined and len(high) == len(models):
                status = "ceiling"
            elif defined and len(low) == len(models):
                status = "floor"
            result.append(
                {
                    "track": track,
                    "usage": usage,
                    "means": [{"model": m, "mean": number(means[m])} for m in models],
                    "status": status,
                    "at_ceiling": high,
                    "at_floor": low,
                }
            )
    return result


# -- Stabilité au rejeu ---------------------------------------------------------------------


def join_replay(
    pilot_lines: Mapping[str, Line], replay_lines: Mapping[str, Line]
) -> tuple[list[tuple[Line, Line]], dict[str, int]]:
    """Paires (pilote, rejeu) jointes sur (``model``, ``digest``, ``track``, ``question_id``,
    ``seed``) à ``prompt_hash`` égal ; exclusions comptées par cause."""
    index = {
        (line.model, line.track, line.question_id, line.seed): line for line in pilot_lines.values()
    }
    pairs: list[tuple[Line, Line]] = []
    excluded = {"unmatched": 0, "digest": 0, "prompt_hash": 0}
    for key in sorted(replay_lines):
        replay = replay_lines[key]
        pilot = index.get((replay.model, replay.track, replay.question_id, replay.seed))
        if pilot is None:
            excluded["unmatched"] += 1
        elif pilot.digest != replay.digest:
            excluded["digest"] += 1
        elif pilot.prompt_hash != replay.prompt_hash:
            excluded["prompt_hash"] += 1
        else:
            pairs.append((pilot, replay))
    return pairs, excluded


def stability(
    pilot: CampaignData,
    replay: CampaignData | None,
    psi_by_track: Mapping[str, float | None],
) -> dict[str, Any]:
    """Section ``stability`` : taux de sorties et de scores changés au rejeu, par piste, sur
    les paires requêtées des deux côtés ; les autres (contexte dépassé, aucun appel) sont
    comptées à part (``not_requested``), et les changements de statut aussi."""
    if replay is None:
        return {"status": "absent", "campaign": None, "tracks": [], "excluded": None}
    pairs, excluded = join_replay(pilot.lines, replay.lines)
    tracks = []
    for track in TRACKS:
        joined = [(a, b) for a, b in pairs if a.track == track]
        if not joined and track not in {line.track for line in replay.lines.values()}:
            continue
        mine = [(a, b) for a, b in joined if a.requested and b.requested]
        status_changed = sum(1 for a, b in joined if a.status != b.status)
        output_changed = sum(1 for a, b in mine if a.output_hash != b.output_hash)
        scored = changed = writing_scored = writing_changed = 0
        for a, b in mine:
            row_a = pilot.inputs.rows.get(a.key)
            row_b = replay.inputs.rows.get(b.key)
            if row_a is None or row_b is None or row_a.score is None or row_b.score is None:
                continue
            if a.usage == WRITING:
                writing_scored += 1
                writing_changed += int(row_a.score != row_b.score)
            else:
                scored += 1
                changed += int(row_a.score != row_b.score)
        score_rate = changed / scored if scored else None
        psi = psi_by_track.get(track)
        tracks.append(
            {
                "track": track,
                "joined": len(joined),
                "requested_pairs": len(mine),
                "not_requested": len(joined) - len(mine),
                "status_changed": status_changed,
                "output_changed": output_changed,
                "output_changed_rate": number(output_changed / len(mine)) if mine else None,
                "scored_pairs": scored,
                "score_changed": changed,
                "score_changed_rate": number(score_rate),
                "psi_mean_global": psi,
                "ratio_to_psi": (
                    number(score_rate / psi) if score_rate is not None and psi else None
                ),
                "writing_scored_pairs": writing_scored,
                "writing_score_changed": writing_changed,
            }
        )
    return {
        "status": "computed",
        "campaign": replay.inputs.campaign,
        "replay_lines": len(replay.lines),
        "joined": len(pairs),
        "excluded": excluded,
        "tracks": tracks,
    }


# -- Tokens et troncature -------------------------------------------------------------------


def _describe(values: Sequence[float]) -> dict[str, Any]:
    stats = describe(values)
    return {
        "n": int(stats["n"]),
        "mean": number(stats["mean"]),
        "p50": number(stats["p50"]),
        "p90": number(stats["p90"]),
        "max": number(stats["max"]),
    }


def tokens(
    lines: Mapping[str, Line],
    models: Sequence[str],
    candidate_caps: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Section ``tokens`` : distributions par (piste, usage), troncature par (piste, modèle,
    usage) et troncature projetée par plafond candidat."""
    requested = [line for line in lines.values() if line.requested]
    by_usage = []
    for track in TRACKS:
        for usage in USAGES:
            mine = [line for line in requested if line.track == track and line.usage == usage]
            if not mine:
                continue
            truncated = sum(1 for line in mine if line.status == "truncated")
            by_usage.append(
                {
                    "track": track,
                    "usage": usage,
                    "lines": len(mine),
                    "thinking_est": _describe([line.thinking_est for line in mine]),
                    "completion": _describe([line.completion for line in mine]),
                    "truncated": truncated,
                    "truncation_rate": number(truncated / len(mine)),
                    "candidates": [
                        {
                            "index": index,
                            "cap": cap_for(caps, track, usage),
                            "projected_truncation": number(
                                sum(
                                    1
                                    for line in mine
                                    if truncated_under(line, cap_for(caps, track, usage))
                                )
                                / len(mine)
                            ),
                        }
                        for index, caps in enumerate(candidate_caps, start=1)
                    ],
                }
            )
    by_model = []
    for track in TRACKS:
        for model in models:
            for usage in USAGES:
                mine = [
                    line
                    for line in requested
                    if line.track == track and line.model == model and line.usage == usage
                ]
                if not mine:
                    continue
                truncated = sum(1 for line in mine if line.status == "truncated")
                by_model.append(
                    {
                        "track": track,
                        "model": model,
                        "usage": usage,
                        "lines": len(mine),
                        "completion_mean": number(
                            math.fsum(line.completion for line in mine) / len(mine)
                        ),
                        "truncated": truncated,
                        "truncation_rate": number(truncated / len(mine)),
                    }
                )
    return {"requested_lines": len(requested), "by_usage": by_usage, "by_model": by_model}


# -- Cohérence d'ordre ----------------------------------------------------------------------


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def old_bench_values(entry: Mapping[str, Any]) -> dict[str, float | None]:
    """Valeurs par usage d'une entrée de l'ancien banc (``global`` = moyenne des trois
    premiers : raisonnement, consignes, outils)."""

    def section(name: str) -> Mapping[str, Any]:
        value = entry.get(name)
        return value if isinstance(value, Mapping) else {}

    quality = section("quality_scores")
    needles = [v for v in section("needle_in_haystack").values() if isinstance(v, bool)]
    values = {
        "reasoning": _number_or_none(quality.get("reasoning_avg")),
        "instructions": _number_or_none(quality.get("instruction_following_avg")),
        "tools": _number_or_none(section("tool_capability").get("success_rate")),
        "extraction": _number_or_none(section("json_capability").get("schema_compliance_rate")),
        "abstention": _number_or_none(quality.get("abstention_avg")),
        "rag": sum(needles) / len(needles) if needles else None,
    }
    first = [values[usage] for usage in ("reasoning", "instructions", "tools")]
    values[GLOBAL] = math.fsum(first) / 3 if all(v is not None for v in first) else None  # type: ignore[misc]
    return values


def old_bench_by_tag(
    old_bench: Mapping[str, Any], catalog: Mapping[str, Any], tags: Sequence[str]
) -> dict[str, OldBenchEntry]:
    """Pont tag → nom par ``config/models_catalog.json``, puis débits et valeurs de l'ancien
    banc ; débit inconnu (``reason``) si le tag manque au catalogue, le nom à l'ancien banc, si
    un débit n'est pas un nombre positif ou si ``load_time_ms`` manque."""
    catalog_models = catalog.get("models") if isinstance(catalog, Mapping) else None
    old_models = old_bench.get("models") if isinstance(old_bench, Mapping) else None
    catalog_models = catalog_models if isinstance(catalog_models, Mapping) else {}
    old_models = old_models if isinstance(old_models, Mapping) else {}
    names: dict[str, tuple[str, Any]] = {}
    for name in sorted(catalog_models):
        info = catalog_models[name]
        if isinstance(info, Mapping) and isinstance(info.get("ollama_tag"), str):
            names.setdefault(info["ollama_tag"], (name, info.get("capabilities")))
    result: dict[str, OldBenchEntry] = {}
    for tag in tags:
        if tag not in names:
            rate = ModelRate(tag, None, None, None, None, None, None, "absent du catalogue")
            result[tag] = OldBenchEntry(rate, {})
            continue
        name, capabilities = names[tag]
        thinking = isinstance(capabilities, list) and "thinking" in capabilities
        entry = old_models.get(name)
        if not isinstance(entry, Mapping):
            rate = ModelRate(tag, name, None, None, None, None, thinking, "absent de l'ancien banc")
            result[tag] = OldBenchEntry(rate, {})
            continue
        decode = _number_or_none(entry.get("avg_tokens_per_second"))
        prefill = _number_or_none(entry.get("prefill_tokens_per_second"))
        load_ms = _number_or_none(entry.get("load_time_ms"))
        reason = None
        if not decode or decode <= 0 or not prefill or prefill <= 0:
            reason = "débit absent de l'ancien banc"
        elif load_ms is None or load_ms < 0:
            reason = "durée de chargement absente de l'ancien banc"
        rate = ModelRate(
            tag=tag,
            name=name,
            decode=decode,
            prefill=prefill,
            prefill_prompt_tokens=_number_or_none(entry.get("prefill_prompt_tokens")),
            load_s=None if load_ms is None else load_ms / 1000.0,
            thinking=thinking,
            reason=reason,
        )
        result[tag] = OldBenchEntry(rate, old_bench_values(entry))
    return result


def pair_counts(
    models: Sequence[str], a: Mapping[str, float | None], b: Mapping[str, float | None]
) -> dict[str, int]:
    """Paires de modèles (définis des deux côtés) concordantes, discordantes et à égalité."""
    defined = [m for m in models if a.get(m) is not None and b.get(m) is not None]
    counts = {"models": len(defined), "concordant": 0, "discordant": 0, "tied": 0}
    for i, x in enumerate(defined):
        for y in defined[i + 1 :]:
            product = (a[x] - a[y]) * (b[x] - b[y])  # type: ignore[operator]
            key = "concordant" if product > 0 else "discordant" if product < 0 else "tied"
            counts[key] += 1
    return counts


def _order(models: Sequence[str], values: Mapping[str, float | None]) -> list[str]:
    means = [values[m] if values.get(m) is not None else math.nan for m in models]
    return [models[i] for i in leader_order(means)]  # type: ignore[arg-type]


def order_consistency(
    inputs: CampaignInputs,
    old: Mapping[str, OldBenchEntry],
) -> list[dict[str, Any]]:
    """Section ``order`` : ordre du pilote (moyenne des unités définies) face à l'ancien banc,
    par piste et périmètre. Le « global » porte, des deux côtés, sur raisonnement, consignes et
    outils (``OLD_BENCH_GLOBAL_USAGES``), le périmètre du global de l'ancien banc."""
    result = []
    for track in TRACKS:
        models = track_models(inputs, track)
        if not models:
            continue
        scopes = []
        for name, usages in _scopes(inputs, track):
            if name == GLOBAL:
                usages = [u for u in usages if u in OLD_BENCH_GLOBAL_USAGES]
                if not usages:
                    continue
            elif name not in OLD_BENCH_USAGES:
                continue
            units, scores = unit_table(inputs, track, usages)
            pilot = {m: number(_model_mean(units, scores[m])) for m in models}
            reference = {m: old[m].values.get(name) if m in old else None for m in models}
            scopes.append(
                {
                    "scope": name,
                    "usages": list(usages),
                    "pilot": [{"model": m, "mean": pilot[m]} for m in models],
                    "old_bench": [{"model": m, "value": number(reference[m])} for m in models],
                    "pilot_order": _order(models, pilot),
                    "old_order": _order(models, reference),
                    **pair_counts(models, pilot, reference),
                }
            )
        result.append({"track": track, "scopes": scopes})
    return result


def aa_consistency(inputs: CampaignInputs) -> dict[str, Any]:
    """Section ``aa`` : entrées AA des tags du pilote (variante appariée à la piste) et
    décompte de paires sur les seules ``measured``, face au global hors rédaction."""
    aa = inputs.aa_reference
    if aa is None:
        return {"status": "absent", "path": None, "sha256": None, "date": None, "tracks": []}
    tracks = []
    for track in TRACKS:
        models = track_models(inputs, track)
        if not models:
            continue
        variant = AA_VARIANT_BY_TRACK[track]
        entries = {entry["tag"]: entry for entry in aa.entries if entry["variant"] == variant}
        usages = binary_usages(inputs, track)
        units, scores = unit_table(inputs, track, usages)
        pilot = {m: number(_model_mean(units, scores[m])) for m in models}
        measured = {
            m: float(entries[m]["index"])
            for m in models
            if m in entries and entries[m]["status"] == "measured"
        }
        tracks.append(
            {
                "track": track,
                "variant": variant,
                "entries": [
                    {
                        "model": m,
                        "index": number(float(entries[m]["index"])) if m in entries else None,
                        "status": entries[m]["status"] if m in entries else "absent",
                    }
                    for m in models
                ],
                "pilot": [{"model": m, "mean": pilot[m]} for m in models],
                "pilot_order": _order([m for m in models if m in measured], pilot),
                "aa_order": _order([m for m in models if m in measured], measured),
                **pair_counts(models, pilot, measured),
            }
        )
    return {
        "status": "computed",
        "path": aa.path,
        "sha256": aa.sha256,
        "date": aa.date,
        "tracks": tracks,
    }


# -- Rédaction provisoire -------------------------------------------------------------------


def writing(data: CampaignData) -> dict[str, Any]:
    """Section ``writing`` : moyenne provisoire sur les seules lignes notées, ``awaiting_judgment``
    et réponses disponibles (génération ``ok``) comptées à part."""
    inputs = data.inputs
    tracks = []
    any_scored = False
    for track in TRACKS:
        models = track_models(inputs, track)
        items = [
            item
            for item in inputs.expected
            if item.track == track and inputs.questions[item.question_id]["usage"] == WRITING
        ]
        if not models or not items:
            continue
        entries = []
        for model in models:
            mine = [item for item in items if item.model == model]
            available = sum(
                1 for item in mine if item.key in data.lines and data.lines[item.key].status == "ok"
            )
            awaiting = sum(
                1 for item in mine if data.grading_status.get(item.key) == "awaiting_judgment"
            )
            scores: list[float] = []
            for item in mine:
                row = inputs.rows.get(item.key)
                if row is not None and row.score is not None:
                    scores.append(row.score)
            any_scored = any_scored or bool(scores)
            entries.append(
                {
                    "model": model,
                    "expected": len(mine),
                    "available": available,
                    "scored": len(scores),
                    "awaiting_judgment": awaiting,
                    "mean": number(math.fsum(scores) / len(scores)) if scores else None,
                }
            )
        tracks.append({"track": track, "models": entries})
    return {
        "status": "provisional" if any_scored else "not_graded",
        "judgment_manifest": inputs.judgment_hash,
        "awaiting_judgment": inputs.completeness.awaiting_judgment,
        "tracks": tracks,
    }


# -- Points différés ------------------------------------------------------------------------


def _context_exceeded(lines: Sequence[Line], models: Sequence[str]) -> dict[str, Any]:
    by_source = []
    sources = sorted({line.source for line in lines} | {BFCL_MULTI})
    for track in TRACKS:
        for model in models:
            mine = [line for line in lines if line.track == track and line.model == model]
            if not mine:
                continue
            for source in sources:
                of_source = [line for line in mine if line.source == source]
                if not of_source and source != BFCL_MULTI:
                    continue
                exceeded = sum(1 for line in of_source if line.status == "context_exceeded")
                by_source.append(
                    {
                        "track": track,
                        "model": model,
                        "source": source,
                        "lines": len(of_source),
                        "context_exceeded": exceeded,
                        "rate": number(exceeded / len(of_source)) if of_source else None,
                    }
                )
    by_tier = []
    for tier in sorted({line.num_ctx for line in lines}):
        of_tier = [line for line in lines if line.num_ctx == tier]
        exceeded = sum(1 for line in of_tier if line.status == "context_exceeded")
        by_tier.append(
            {
                "num_ctx": tier,
                "lines": len(of_tier),
                "context_exceeded": exceeded,
                "rate": number(exceeded / len(of_tier)),
            }
        )
    return {"by_source": by_source, "by_tier": by_tier}


def common_units(inputs: CampaignInputs) -> list[dict[str, Any]]:
    """Par périmètre binaire : unités non communes à tous les modèles de la piste, meneur sur
    toutes ses unités face au meneur sur les unités communes (AD-10)."""
    result = []
    for track in TRACKS:
        models = track_models(inputs, track)
        if not models:
            continue
        for name, usages in _scopes(inputs, track):
            units, scores = unit_table(inputs, track, usages)
            common = [u for u in units if all(scores[m].get(u) is not None for m in models)]
            own = [_model_mean(units, scores[m]) for m in models]
            shared = [_model_mean(common, scores[m]) for m in models]
            leader_own = leader_order(own)
            leader_shared = leader_order(shared)
            leader_all = models[leader_own[0]] if leader_own else None
            # Aucune unité commune : meneur et comparaison indéterminés (None).
            leader_common = models[leader_shared[0]] if common and leader_shared else None
            same = (
                None if leader_common is None or leader_all is None else leader_all == leader_common
            )
            result.append(
                {
                    "track": track,
                    "scope": name,
                    "units": len(units),
                    "common_units": len(common),
                    "non_common_units": len(units) - len(common),
                    "leader_all_units": leader_all,
                    "leader_common_units": leader_common,
                    "same_leader": same,
                }
            )
    return result


def _cache(lines: Sequence[Line]) -> list[dict[str, Any]]:
    result = []
    for track in TRACKS:
        for usage in USAGES:
            mine = [line for line in lines if line.track == track and line.usage == usage]
            if not mine:
                continue
            cached = sum(line.prompt_cached for line in mine)
            total = sum(line.prompt + line.prompt_cached for line in mine)
            result.append(
                {
                    "track": track,
                    "usage": usage,
                    "lines": len(mine),
                    "lines_with_cache": sum(1 for line in mine if line.prompt_cached > 0),
                    "cached_share": number(cached / total) if total else None,
                }
            )
    return result


def deferred(pilot: CampaignData, replay: CampaignData | None) -> dict[str, Any]:
    """Section ``deferred`` : mesures des points « à trancher au pilote » de deferred-work.md."""
    lines = sorted(pilot.lines.values(), key=lambda line: line.key)
    models = [model["tag"] for model in pilot.inputs.models]
    retries = [
        {
            "campaign": data.inputs.campaign,
            "log_lines": data.log_retries,
            "attempts_over_one": sum(1 for line in data.lines.values() if line.attempts > 1),
            "error_lines": sum(1 for line in data.lines.values() if line.status == "error"),
        }
        for data in (pilot, replay)
        if data is not None
    ]
    return {
        "context_exceeded": _context_exceeded(lines, models),
        "common_units": common_units(pilot.inputs),
        "retries": retries,
        "prefix_cache": _cache([line for line in lines if line.requested]),
    }


# -- Rapport --------------------------------------------------------------------------------


def _completeness(data: CampaignData) -> dict[str, Any]:
    record = data.inputs.completeness.as_record()
    record["complete"] = not data.inputs.completeness.has_issues
    return {"campaign": data.inputs.campaign, **record}


def build_pilot_report(
    *,
    pilot: CampaignData,
    replay: CampaignData | None,
    replay_campaign: str,
    full_tracks: Mapping[str, Sequence[str]],
    old: Mapping[str, OldBenchEntry],
    full_models: Sequence[str],
    settings: Any,
    references: Mapping[str, Any],
) -> dict[str, Any]:
    """Rapport du pilote (dictionnaire déterministe, sans date ni texte de question).

    ``full_tracks`` : pistes du jeu entier (``tracks.json``) ; ``old`` : ancien banc par tag,
    pour tous les modèles de la campagne complète (et ceux du pilote, s'ils en manquent) ;
    ``settings`` : ``config.PilotSettings`` (plafonds candidats partiels, fusionnés ici sur
    ceux de la campagne) ; ``references`` : chemins et empreintes de l'ancien banc, du
    catalogue et de ``pilot.yaml``."""
    inputs = pilot.inputs
    disc = discordance(inputs)
    psi_by_track = global_psi(disc)
    caps = inputs.manifest["blocking"]["generation"]["resolved"]["caps"]
    questions = inputs.questions
    by_id = {
        qid: FullQuestion(q["usage"], q["num_ctx"], q["est_prompt_tokens"])
        for qid, q in questions.items()
    }
    full = {track: [by_id[qid] for qid in dict.fromkeys(full_tracks[track])] for track in TRACKS}
    pilot_models = [model["tag"] for model in inputs.models]
    pilot_questions: dict[tuple[str, str], list[str]] = {}
    for line in sorted(pilot.lines.values(), key=lambda item: item.key):
        if line.requested:
            pilot_questions.setdefault((line.model, line.track), []).append(line.question_id)
    lines = sorted(pilot.lines.values(), key=lambda line: line.key)
    candidates = [merge_caps(caps, partial) for partial in settings.reduction_caps]
    projection = project(
        lines=lines,
        warmups=pilot.warmups,
        pilot_models=pilot_models,
        pilot_questions=pilot_questions,
        questions_by_id=by_id,
        full=full,
        campaign_caps=caps,
        rates=[old[tag].rate for tag in full_models],
        pilot_rates={tag: old[tag].rate for tag in pilot_models if tag in old},
        budget_hours=settings.budget_hours,
        reduction_caps=candidates,
        think_on_n=settings.think_on_n,
    )
    return {
        "campaign": inputs.campaign,
        "set": {"id": inputs.set_id, "hash": inputs.set_hash},
        "generation_manifest": inputs.generation_hash,
        "judgment_manifest": inputs.judgment_hash,
        "k": inputs.k,
        "models": pilot_models,
        "settings": {
            "budget_hours": number(settings.budget_hours),
            "ceiling": number(settings.ceiling),
            "floor": number(settings.floor),
            "candidate_caps": candidates,
            "think_on_n": settings.think_on_n,
            "full_models": list(full_models),
        },
        "completeness": {
            "pilot": _completeness(pilot),
            "replay": None if replay is None else _completeness(replay),
        },
        "replay_campaign": replay_campaign,
        "discordance": disc,
        "ceiling_floor": ceiling_floor(inputs, settings.ceiling, settings.floor),
        "stability": stability(pilot, replay, psi_by_track),
        "tokens": tokens(pilot.lines, pilot_models, candidates),
        "projection": projection,
        "order": order_consistency(inputs, old),
        "aa": aa_consistency(inputs),
        "writing": writing(pilot),
        "deferred": deferred(pilot, replay),
        "references": {
            **references,
            "replay_generation_manifest": (
                None if replay is None else replay.inputs.generation_hash
            ),
        },
    }
