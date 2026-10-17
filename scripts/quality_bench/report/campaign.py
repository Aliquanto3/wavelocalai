"""Agrégats d'une campagne (AD-17, statistiques.md) : périmètres, statistiques, résumé
``qb.report/1``.

- **Unité statistique** : (``model``, ``track``, ``unit``), score d'unité par ``stats.units``
  (minimum des questions, puis moyenne des seeds). Une question sans score (erreur du banc,
  ``context_exceeded`` à limite du banc, attente du juge sous ``--partial``, ligne écartée) rend
  l'unité nulle pour ce modèle, et comptée (``excluded``). Un ``context_exceeded`` à limite du
  modèle vaut 0 (échec compté) ; les deux causes sont comptées à part par modèle.
- **Unités communes** (AD-17, 2026-10-17) : un modèle est **éligible** sur un périmètre si sa
  couverture (unités définies / unités du périmètre définies pour au moins un modèle) atteint
  ``common_min_coverage`` (0,9 par
  défaut, option ``--common-min-coverage`` de ``report``). Score, ET, IC, rang approché, groupes
  indiscernables, meneur, comparaisons, matrice, k̂_Bonferroni et Spearman portent sur les seuls
  modèles éligibles et sur les unités définies pour **chacun** d'eux. Un modèle non éligible
  reste publié (``mean_all``, ``n_all``, ``coverage``, ``eligible = false``) sans score commun,
  rang, groupe ni comparaison, et il est nommé dans le journal et le rapport. La moyenne de
  chaque modèle sur toutes ses unités définies est publiée à côté (``mean_all``, ``n_all``).
- **Périmètres** : chaque piste en global, puis chaque usage de la piste.
- **Méthode** : choisie sur ``generation.request.k`` du manifeste et les usages du périmètre,
  jamais sur les valeurs observées. Binaire (``k == 1`` et aucun usage ``writing``) : McNemar
  exact et intervalle de Wilson. Sinon : test z sur la différence appariée à erreur-type
  groupée, intervalle moyenne ± z·ET borné à [0, 1], IC bootstrap apparié de la différence.
- **Métriques continues** (``instructions_followed``, ``f1``) : valeur 0 pour ``truncated`` et
  ``non_compliant`` sans métrique, unité nulle sinon ; moyenne par modèle et IC bootstrap
  apparié de la différence au meneur de la métrique.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..common.schemas import TRACKS, USAGES
from ..stats import ALPHA
from ..stats.bootstrap import DEFAULT_RESAMPLES, DEFAULT_SEED, paired_bootstrap_ci
from ..stats.clustered import clustered_mean_se, mean_interval
from ..stats.groups import (
    approximate_ranks,
    bonferroni_alpha,
    indistinguishable_groups,
    leader_order,
)
from ..stats.mcnemar import discordant_counts, mcnemar_exact, paired_difference, paired_test
from ..stats.multiple import benjamini_hochberg, bonferroni_wins, holm
from ..stats.spearman import spearman_test
from ..stats.units import unit_scores
from ..stats.wilson import wilson_interval, z_value
from .inputs import CampaignInputs, Row

WRITING = "writing"
# Usage → métrique continue publiée à côté du score binaire.
CONTINUOUS_BY_USAGE = {"instructions": "instructions_followed", "extraction": "f1", "rag": "f1"}
# Piste → variante de l'indice AA appariée (statistiques.md, « Validation externe »).
AA_VARIANT_BY_TRACK = {"think_on": "reasoning", "think_off": "non_reasoning"}
MODEL_FAILURES = ("truncated", "non_compliant")
SIGNIFICANT_DIGITS = 12
# Couverture minimale (unités définies / unités du périmètre) d'un modèle classé (AD-17).
COMMON_MIN_COVERAGE = 0.9

logger = logging.getLogger(__name__)


def number(value: float | None) -> float | None:
    """Flottant fini publié (12 chiffres significatifs), ``None`` si indéfini."""
    if value is None or not math.isfinite(value):
        return None
    return float(f"{value:.{SIGNIFICANT_DIGITS}g}")


@dataclass(frozen=True)
class Scope:
    """Unités d'un périmètre et score d'unité de chaque modèle."""

    usage: str | None
    binary: bool
    units: tuple[str, ...]
    groups: dict[str, str]
    scores: dict[str, dict[str, float | None]]  # modèle → unité → score

    def common(self, models: Sequence[str]) -> Scope:
        """Périmètre restreint aux unités définies pour **chacun** des ``models`` (AD-17)."""
        kept = tuple(
            unit
            for unit in self.units
            if all(self.scores[model][unit] is not None for model in models)
        )
        return Scope(self.usage, self.binary, kept, self.groups, self.scores)


@dataclass(frozen=True)
class Pair:
    n: int
    diff: float
    se: float
    ci_low: float
    ci_high: float
    correlation: float
    b: int | None
    c: int | None
    p: float
    p_method: str
    a_values: tuple[float, ...]
    b_values: tuple[float, ...]
    groups: tuple[str, ...]


def _paired_values(scope: Scope, a: str, b: str) -> tuple[list[float], list[float], list[str]]:
    a_values, b_values, groups = [], [], []
    for unit in scope.units:
        x, y = scope.scores[a].get(unit), scope.scores[b].get(unit)
        if x is None or y is None:
            continue
        a_values.append(x)
        b_values.append(y)
        groups.append(scope.groups[unit])
    return a_values, b_values, groups


def _pair(scope: Scope, a: str, b: str, z: float) -> Pair:
    """Comparaison appariée ``a − b`` sur les unités définies pour les deux modèles."""
    a_values, b_values, groups = _paired_values(scope, a, b)
    paired = paired_difference(a_values, b_values, groups, z)
    if scope.binary:
        if a_values:
            only_a, only_b = discordant_counts(a_values, b_values)
            p = mcnemar_exact(only_a, only_b)
            p_method = "mcnemar"
        else:  # aucune unité appariée : ni table ni test
            only_a = only_b = None
            p = math.nan
            p_method = "mcnemar"
    else:
        only_a = only_b = None
        differences = [x - y for x, y in zip(a_values, b_values, strict=True)]
        p, p_method = paired_test(paired.diff, paired.se, differences, groups)
    return Pair(
        paired.n,
        paired.diff,
        paired.se,
        paired.ci_low,
        paired.ci_high,
        paired.correlation,
        only_a,
        only_b,
        p,
        p_method,
        tuple(a_values),
        tuple(b_values),
        tuple(groups),
    )


def _truncation(rows: Sequence[Row]) -> tuple[int, int]:
    """(lignes notées, lignes ``truncated``) : taux de troncature publié à part. Les lignes
    ``context_exceeded`` à limite du modèle (score 0) sont hors du dénominateur, comptées à part
    (``context_exceeded_model``) : aucune génération n'y a été tronquée."""
    graded = sum(
        1
        for row in rows
        if row.score is not None
        and not (row.status == "context_exceeded" and row.context_limit == "model")
    )
    truncated = sum(1 for row in rows if row.status == "truncated")
    return graded, truncated


def _context_exceeded(rows: Sequence[Row], limit: str) -> int:
    """Lignes ``context_exceeded`` de cause ``limit`` (``model`` ou ``bench``)."""
    return sum(1 for row in rows if row.status == "context_exceeded" and row.context_limit == limit)


def _mean_all(scope: Scope, model: str) -> tuple[float, int]:
    """Moyenne du modèle sur toutes ses unités définies, et leur effectif."""
    values = [scope.scores[model][u] for u in scope.units if scope.scores[model][u] is not None]
    return (math.fsum(values) / len(values) if values else math.nan), len(values)


def _scorable(scope: Scope, models: Sequence[str]) -> int:
    """Unités du périmètre définies pour au moins un des ``models`` : une unité nulle pour tous
    (NIAH sans ``f1``, erreur du banc partout) ne pèse sur la couverture d'aucun modèle."""
    return sum(
        1 for unit in scope.units if any(scope.scores[model][unit] is not None for model in models)
    )


def _coverage(scope: Scope, model: str, models: Sequence[str]) -> float | None:
    """Unités définies du modèle / unités évaluables du périmètre (``None`` si aucune)."""
    scorable = _scorable(scope, models)
    if not scorable:
        return None
    return _mean_all(scope, model)[1] / scorable


def eligible_models(
    scope: Scope, models: Sequence[str], min_coverage: float = COMMON_MIN_COVERAGE
) -> list[str]:
    """Modèles dont la couverture atteint ``min_coverage`` (tous sur un périmètre vide)."""
    return [
        model
        for model in models
        if (coverage := _coverage(scope, model, models)) is None or coverage >= min_coverage
    ]


def _warn_ineligible(
    scope: Scope, models: Sequence[str], eligible: Sequence[str], min_coverage: float, what: str
) -> None:
    for model in models:
        if model not in eligible:
            logger.warning(
                "%s, périmètre %s : %s hors classement, couverture %.1f %% sous le seuil de "
                "%.1f %% (unités définies %d sur %d)",
                what,
                scope.usage or "global",
                model,
                100 * (_coverage(scope, model, models) or 0.0),
                100 * min_coverage,
                _mean_all(scope, model)[1],
                _scorable(scope, models),
            )


def scope_stats(
    full_scope: Scope,
    models: Sequence[str],
    rows_by_model: Mapping[str, Sequence[Row]],
    *,
    min_coverage: float = COMMON_MIN_COVERAGE,
) -> tuple[dict[str, Any], dict[tuple[str, str], Pair]]:
    """Bloc ``scopes[]`` du résumé et comparaisons appariées des paires de modèles éligibles.

    Tout est calculé sur les modèles **éligibles** (couverture ≥ ``min_coverage``) et sur les
    **unités communes** à chacun d'eux (``Scope.common``) : score, ET, IC, rang approché,
    groupes indiscernables, meneur, comparaisons et matrice. La moyenne de chaque modèle sur
    toutes ses unités définies est publiée à côté (``mean_all``, ``n_all``) ; un modèle non
    éligible n'a que celle-là, sa couverture et ses comptes.
    """
    eligible = eligible_models(full_scope, models, min_coverage)
    _warn_ineligible(full_scope, models, eligible, min_coverage, "score")
    scope = full_scope.common(eligible)
    z = z_value(ALPHA)
    m = len(eligible)
    z_sim = z_value(bonferroni_alpha(ALPHA, m))
    means, lows, highs, entries, ranked = [], [], [], [], []
    for model in models:
        mean_all, n_all = _mean_all(full_scope, model)
        graded, truncated = _truncation(rows_by_model[model])
        counts = {
            "mean_all": number(mean_all),
            "n_all": n_all,
            "coverage": number(_coverage(full_scope, model, models)),
            "eligible": model in eligible,
            "excluded": len(full_scope.units) - n_all,
        }
        tail = {
            "graded": graded,
            "truncated": truncated,
            "truncation_rate": number(truncated / graded) if graded else None,
            "context_exceeded_model": _context_exceeded(rows_by_model[model], "model"),
            "context_exceeded_bench": _context_exceeded(rows_by_model[model], "bench"),
        }
        if model not in eligible:
            entries.append(
                {
                    "model": model,
                    "mean": None,
                    "n": 0,
                    **counts,
                    "se": None,
                    "ci_low": None,
                    "ci_high": None,
                    "sim_ci_low": None,
                    "sim_ci_high": None,
                    **tail,
                    "rank": None,
                    "group": None,
                }
            )
            continue
        values = [scope.scores[model][u] for u in scope.units]
        groups = [scope.groups[u] for u in scope.units]
        mean, se = clustered_mean_se(values, groups)
        n = len(values)
        if scope.binary:
            successes = sum(values)
            ci = wilson_interval(successes, n, ALPHA)
            sim = wilson_interval(successes, n, bonferroni_alpha(ALPHA, m))
        else:
            ci = mean_interval(mean, se, z)
            sim = mean_interval(mean, se, z_sim)
        means.append(mean)
        lows.append(sim[0])
        highs.append(sim[1])
        entry = {
            "model": model,
            "mean": number(mean),
            "n": n,
            **counts,
            "se": number(se),
            "ci_low": number(ci[0]),
            "ci_high": number(ci[1]),
            "sim_ci_low": number(sim[0]),
            "sim_ci_high": number(sim[1]),
            **tail,
            "rank": None,
            "group": None,
        }
        entries.append(entry)
        ranked.append(entry)

    pairs: dict[tuple[str, str], Pair] = {}
    for i, a in enumerate(eligible):
        for b in eligible[i + 1 :]:
            pairs[(a, b)] = _pair(scope, a, b, z)
            pairs[(b, a)] = _pair(scope, b, a, z)
    diffs = [[pairs[(a, b)].diff if a != b else 0.0 for b in eligible] for a in eligible]
    pvalues = [[pairs[(a, b)].p if a != b else 1.0 for b in eligible] for a in eligible]
    groups = indistinguishable_groups(means, diffs, pvalues, ALPHA)
    ranks = approximate_ranks(lows, highs)
    for entry, rank, group in zip(ranked, ranks, groups, strict=True):
        entry["rank"] = rank
        entry["group"] = group

    order = leader_order(means)
    leader = eligible[order[0]] if order else None
    comparisons = []
    if leader is not None:
        others = [model for model in eligible if model != leader]
        reject, corrected = holm([pairs[(leader, other)].p for other in others], ALPHA)
        for other, rejected, p_holm in zip(others, reject, corrected, strict=True):
            pair = pairs[(leader, other)]
            if scope.binary or pair.n == 0:
                boot = (math.nan, math.nan)
            else:
                boot = paired_bootstrap_ci(pair.a_values, pair.b_values, pair.groups, alpha=ALPHA)
            comparisons.append(
                {
                    "model": other,
                    "n": pair.n,
                    "diff": number(pair.diff),
                    "se": number(pair.se),
                    "ci_low": number(pair.ci_low),
                    "ci_high": number(pair.ci_high),
                    "bootstrap_ci_low": number(boot[0]),
                    "bootstrap_ci_high": number(boot[1]),
                    "correlation": number(pair.correlation),
                    "b": pair.b,
                    "c": pair.c,
                    "p": number(pair.p),
                    "p_method": pair.p_method,
                    "p_holm": number(p_holm),
                    "reject": rejected,
                }
            )

    # Matrice exploratoire « qui bat qui » : toutes les paires, corrigées par BH.
    matrix_pairs = [(a, b) for i, a in enumerate(eligible) for b in eligible[i + 1 :]]
    reject, corrected = benjamini_hochberg([pairs[pair].p for pair in matrix_pairs], ALPHA)
    matrix = [
        {
            "a": a,
            "b": b,
            "n": pairs[(a, b)].n,
            "diff": number(pairs[(a, b)].diff),
            "p": number(pairs[(a, b)].p),
            "p_method": pairs[(a, b)].p_method,
            "p_bh": number(p_bh),
            "reject": rejected,
        }
        for (a, b), rejected, p_bh in zip(matrix_pairs, reject, corrected, strict=True)
    ]
    block = {
        "usage": scope.usage,
        "method": "mcnemar" if scope.binary else "paired_z",
        "units": len(full_scope.units),
        "common_units": len(scope.units),
        "leader": leader,
        "models": entries,
        "comparisons": comparisons,
        "matrix": matrix,
        "continuous": None,
    }
    return block, pairs


def continuous_stats(
    full_scope: Scope,
    metric: str,
    models: Sequence[str],
    *,
    min_coverage: float = COMMON_MIN_COVERAGE,
) -> dict[str, Any]:
    """Bloc ``continuous`` : moyenne par modèle et IC bootstrap apparié au meneur, sur les
    modèles éligibles et leurs unités communes (``mean_all`` et ``n_all`` : toutes les unités
    définies du modèle ; un modèle non éligible n'a que celles-là)."""
    eligible = eligible_models(full_scope, models, min_coverage)
    _warn_ineligible(full_scope, models, eligible, min_coverage, metric)
    scope = full_scope.common(eligible)
    entries, means = [], []
    for model in models:
        mean_all, n_all = _mean_all(full_scope, model)
        if model in eligible:
            values = [scope.scores[model][u] for u in scope.units]
            mean = math.fsum(values) / len(values) if values else math.nan
            means.append(mean)
        else:
            values, mean = [], math.nan
        entries.append(
            {
                "model": model,
                "mean": number(mean),
                "n": len(values),
                "mean_all": number(mean_all),
                "n_all": n_all,
                "coverage": number(_coverage(full_scope, model, models)),
                "eligible": model in eligible,
                "excluded": len(full_scope.units) - n_all,
            }
        )
    order = leader_order(means)
    leader = eligible[order[0]] if order else None
    comparisons = []
    if leader is not None:
        for other in eligible:
            if other == leader:
                continue
            a_values, b_values, groups = _paired_values(scope, leader, other)
            diff = math.fsum(x - y for x, y in zip(a_values, b_values, strict=True))
            diff = diff / len(a_values) if a_values else math.nan
            boot = paired_bootstrap_ci(a_values, b_values, groups, alpha=ALPHA)
            comparisons.append(
                {
                    "model": other,
                    "n": len(a_values),
                    "diff": number(diff),
                    "bootstrap_ci_low": number(boot[0]),
                    "bootstrap_ci_high": number(boot[1]),
                }
            )
    return {"metric": metric, "leader": leader, "models": entries, "comparisons": comparisons}


def _metric_value(row: Row | None, metric: str) -> float | None:
    """Métrique continue d'une question : valeur publiée, 0 pour un échec du modèle sans
    métrique (dont un contexte du modèle dépassé), ``None`` sinon (unité nulle : ligne absente,
    erreur du banc, contexte du banc dépassé, NIAH sans ``f1``)."""
    if row is None:
        return None
    if metric in row.metrics:
        return row.metrics[metric]
    if row.status in MODEL_FAILURES or (
        row.status == "context_exceeded" and row.context_limit == "model"
    ):
        return 0.0
    return None


def _scope(
    inputs: CampaignInputs,
    track: str,
    models: Sequence[str],
    usages: Sequence[str],
    *,
    usage: str | None,
    metric: str | None = None,
) -> Scope:
    """Périmètre ``usage`` (``None`` : global) de la piste : scores d'unité de chaque modèle
    (score, ou métrique continue ``metric``)."""
    expected = [
        item
        for item in inputs.expected
        if item.track == track
        and (usage is None or inputs.questions[item.question_id]["usage"] == usage)
    ]
    units = sorted({inputs.questions[item.question_id]["unit"] for item in expected})
    groups = {
        inputs.questions[item.question_id]["unit"]: inputs.questions[item.question_id]["group"]
        for item in expected
    }
    by_model: dict[str, list[Any]] = {model: [] for model in models}
    for item in expected:
        if item.model in by_model:
            by_model[item.model].append(item)
    scores: dict[str, dict[str, float | None]] = {}
    for model in models:
        mine = by_model[model]
        values = []
        for item in mine:
            row = inputs.rows.get(item.key)
            if metric is None:
                values.append(None if row is None else row.score)
            else:
                values.append(_metric_value(row, metric))
        by_unit = unit_scores(
            [inputs.questions[item.question_id]["unit"] for item in mine],
            [item.seed for item in mine],
            values,
        )
        scores[model] = {unit: by_unit.get(unit) for unit in units}
    binary = inputs.k == 1 and WRITING not in usages and metric is None
    return Scope(usage, binary, tuple(units), groups, scores)


def _spearman(
    inputs: CampaignInputs, track: str, global_block: Mapping[str, Any]
) -> dict[str, Any]:
    variant = AA_VARIANT_BY_TRACK[track]
    absent = {
        "status": "absent",
        "variant": variant,
        "n": 0,
        "models": [],
        "rho": None,
        "p": None,
        "ci_low": None,
        "ci_high": None,
        "conclusion": None,
    }
    if inputs.aa_reference is None:
        return absent
    index = {
        entry["tag"]: float(entry["index"])
        for entry in inputs.aa_reference.entries
        if entry["variant"] == variant and entry["status"] == "measured"
    }
    paired = [
        (entry["model"], entry["mean"], index[entry["model"]])
        for entry in global_block["models"]
        if entry["mean"] is not None and entry["model"] in index
    ]
    result = spearman_test(
        [score for _, score, _ in paired],
        [value for _, _, value in paired],
        alpha=ALPHA,
        resamples=DEFAULT_RESAMPLES,
        seed=DEFAULT_SEED,
    )
    return {
        **absent,
        "status": "computed",
        "n": result.n,
        "models": [tag for tag, _, _ in paired],
        "rho": number(result.rho),
        "p": number(result.p),
        "ci_low": number(result.ci_low),
        "ci_high": number(result.ci_high),
        "conclusion": result.conclusion,
    }


def track_stats(
    inputs: CampaignInputs, track: str, *, min_coverage: float = COMMON_MIN_COVERAGE
) -> dict[str, Any] | None:
    """Bloc ``tracks[]`` d'une piste, ou ``None`` si aucun modèle ne la suit."""
    models = [model["tag"] for model in inputs.models if track in model["tracks"]]
    if not models:
        return None
    track_rows = [row for row in inputs.rows.values() if row.track == track]
    usages = [
        usage
        for usage in USAGES
        if any(
            item.track == track and inputs.questions[item.question_id]["usage"] == usage
            for item in inputs.expected
        )
    ]

    def rows_for(usage: str | None) -> dict[str, list[Row]]:
        result: dict[str, list[Row]] = {model: [] for model in models}
        for row in track_rows:
            if usage is None or inputs.questions[row.question_id]["usage"] == usage:
                result[row.model].append(row)
        return result

    global_scope = _scope(inputs, track, models, usages, usage=None)
    global_block, _ = scope_stats(global_scope, models, rows_for(None), min_coverage=min_coverage)
    scopes = [global_block]
    usage_pairs: dict[str, dict[tuple[str, str], Pair]] = {}
    for usage in usages:
        scope = _scope(inputs, track, models, [usage], usage=usage)
        block, pairs = scope_stats(scope, models, rows_for(usage), min_coverage=min_coverage)
        metric = CONTINUOUS_BY_USAGE.get(usage)
        if metric is not None:
            continuous_scope = _scope(inputs, track, models, [usage], usage=usage, metric=metric)
            block["continuous"] = continuous_stats(
                continuous_scope, metric, models, min_coverage=min_coverage
            )
        scopes.append(block)
        usage_pairs[usage] = pairs

    # k̂_Bonferroni : usages où le meneur global bat chaque modèle éligible à α/m. Un usage où
    # l'un des deux n'est pas éligible compte comme un test sans victoire (p indéfini) : le
    # seuil reste α / nombre d'usages.
    leader = global_block["leader"]
    global_eligible = {entry["model"] for entry in global_block["models"] if entry["eligible"]}
    k_models = []
    if leader is not None:
        for other in models:
            if other == leader or other not in global_eligible:
                continue
            tested = [usage_pairs[usage].get((leader, other)) for usage in usages]
            wins = bonferroni_wins(
                [math.nan if p is None else p.p for p in tested],
                [math.nan if p is None else p.diff for p in tested],
                ALPHA,
            )
            k_models.append({"model": other, "wins": wins, "tests": len(usages)})
    k_bonferroni = {
        "leader": leader,
        "usages": len(usages),
        "alpha_per_test": number(ALPHA / len(usages)) if usages else None,
        "models": k_models,
    }
    return {
        "track": track,
        "scopes": scopes,
        "k_bonferroni": k_bonferroni,
        "spearman": _spearman(inputs, track, global_block),
    }


def build_summary(
    inputs: CampaignInputs, *, min_coverage: float = COMMON_MIN_COVERAGE
) -> dict[str, Any]:
    """Résumé ``qb.report/1`` de la campagne (agrégats seuls)."""
    tracks = [
        block
        for track in TRACKS
        if (block := track_stats(inputs, track, min_coverage=min_coverage)) is not None
    ]
    aa = inputs.aa_reference
    return {
        "schema": "qb.report/1",
        "campaign": inputs.campaign,
        "partial": inputs.partial,
        "set": {"id": inputs.set_id, "hash": inputs.set_hash},
        "generation_manifest": inputs.generation_hash,
        "judgment_manifest": inputs.judgment_hash,
        "k": inputs.k,
        "method": {
            "alpha": ALPHA,
            "bootstrap_resamples": DEFAULT_RESAMPLES,
            "bootstrap_seed": DEFAULT_SEED,
            "common_min_coverage": min_coverage,
        },
        "completeness": inputs.completeness.as_record(),
        "models": [
            {
                "tag": model["tag"],
                "digest": model["digest"],
                "family": model["family"],
                "tracks": [track for track in TRACKS if track in model["tracks"]],
            }
            for model in inputs.models
        ],
        "tracks": tracks,
        "aa_reference": (
            None if aa is None else {"path": aa.path, "sha256": aa.sha256, "date": aa.date}
        ),
    }
