"""Mesures de la calibration du juge (CAP-6) : fonctions pures, sans I/O.

- **Unités jugeables** : un critère d'une réponse de rédaction ``ok`` (clé de jugement
  ``<generation_key>|<critère>``), avec le modèle, sa famille (biais Qwen = ``family == "qwen"``)
  et l'heuristique de comptage du critère.
- **Accord** avec les étiquettes humaines ``true``/``false`` sur les unités qu'un juge a notées
  d'un verdict booléen : part d'accord, intervalle de Wilson à 95 %, indulgence (juge vrai,
  humain faux), sévérité (juge faux, humain vrai), unités étiquetées sans ligne ou en ``error``.
- **Biais Qwen** = accord(Qwen) − accord(non-Qwen) ; accord à part des critères de comptage.
- **Coût** : Σ ``cost_usd`` des lots ``collected`` de ``batches.jsonl`` s'il y en a, sinon de
  ``judgment.jsonl`` ; par jugement, et projeté sur ``projected_judgments`` jugements.
- **Cascade** Winnow → Haiku par marge ``m`` : ``p ≥ 0,5 + m`` → vrai, ``p ≤ 0,5 − m`` → faux,
  sinon (ou ligne ``error``, ou ``p`` nulle) verdict de Haiku de la même clé.
- **Stabilité** d'une paire ``<id>`` / ``<id>-replay`` comparable.
- **Admissibilité et proposition** : seulement si les deux seuils sont fournis ; jamais un choix
  appliqué.
- **Échantillon à étiqueter** : tirage déterministe par graine.

Aucun texte de question ni de réponse n'entre dans le résultat ; les flottants sont finis ou
``None``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..common.canonical import sha256_hex

WINNOW = "winnow"
HAIKU = "haiku"
MIMO = "mimo"
CASCADE = "winnow-cascade-haiku"
REPLAY_SUFFIX = "-replay"
DEFAULT_MARGINS = tuple(step / 100 for step in range(0, 51, 5))
# Volume de la campagne complète (juge-et-calibration.md : (80 × 20 + 40 × 15) réponses × ~5).
DEFAULT_PROJECTED_JUDGMENTS = 11_000
# Champs du bloc ``judge`` d'un manifeste de jugement comparés entre un juge et son rejeu.
COMPARED_JUDGE_FIELDS = (
    "endpoint",
    "model",
    "settings",
    "prompt_template_hash",
    "weights_sha256",
    "server_version",
)
# Tolérance des comparaisons aux seuils (arrondis binaires de 0,8, 0,1…).
EPSILON = 1e-12

# -- Heuristique des critères de comptage ---------------------------------------------------

_NUMBER_WORDS = (
    "deux",
    "trois",
    "quatre",
    "cinq",
    "six",
    "sept",
    "huit",
    "neuf",
    "dix",
    "onze",
    "douze",
    "treize",
    "quatorze",
    "quinze",
    "seize",
    "vingt",
    "trente",
    "quarante",
    "cinquante",
    "soixante",
    "cent",
)
_COUNT_UNITS = (
    "mot",
    "phrase",
    "paragraphe",
    "réplique",
    "ligne",
    "puce",
    "élément",
    "étape",
    "conseil",
    "question",
)
_WORD_NUMBER = "(?:{w})s?(?:-(?:et-)?(?:un|une|{w})s?)*".format(w="|".join(_NUMBER_WORDS))
COUNTING_RE = re.compile(
    r"\b(?:\d+|une?\s+seule?|" + _WORD_NUMBER + r")\s+(?:[\w'’-]+\s+)?"
    r"(?:" + "|".join(_COUNT_UNITS) + r")s?\b",
    re.IGNORECASE,
)


def is_counting(criterion: str) -> bool:
    """Critère qui demande de compter : nombre (chiffres, deux… cent, « un seul »), au plus un
    mot, puis une unité (mots, phrases, paragraphes, répliques, lignes, puces, éléments, étapes,
    conseils, questions)."""
    return COUNTING_RE.search(criterion) is not None


# -- Données d'entrée -----------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    """Unité jugeable : un critère d'une réponse de rédaction ``ok`` (sans aucun texte)."""

    key: str
    generation_key: str
    model: str
    qwen: bool
    question_id: str
    track: str
    criterion: str
    counting: bool
    private: bool


@dataclass(frozen=True)
class Verdict:
    """Ligne de jugement : verdict booléen, ou ``None`` pour une ligne ``error``."""

    verdict: bool | None
    probability: float | None
    cost_usd: float


@dataclass(frozen=True)
class JudgeData:
    """Dossier ``judgment-<id>/`` lu : ``present``, ``absent`` (sans manifeste) ou
    ``discordant`` (manifeste d'une autre génération : exclu, lignes non lues)."""

    id: str
    status: str
    manifest_hash: str | None = None
    judge: Mapping[str, Any] | None = None
    generation_manifest: str | None = None
    verdicts: Mapping[str, Verdict] | None = None
    batch_costs: tuple[float, ...] = ()

    @property
    def present(self) -> bool:
        return self.status == "present"


@dataclass(frozen=True)
class Labels:
    """Étiquettes lues : ``values`` = étiquettes ``true``/``false`` de la campagne ;
    ``campaign_keys`` = toutes ses clés présentes, quelle que soit l'étiquette."""

    file_present: bool
    lines: int
    values: Mapping[str, bool]
    to_label: int
    undecidable: int
    other_campaigns: int
    campaign_keys: frozenset[str] = frozenset()  # toutes les clés de la campagne, nulles comprises


def _finite(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def _ratio(part: float, whole: float) -> float | None:
    return None if not whole else part / whole


def _wilson(successes: int, n: int) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    # Import tardif : scipy (stats/), comme pilot.
    from ..stats.wilson import wilson_interval

    low, high = wilson_interval(successes, n)
    return _finite(low), _finite(high)


# -- Accord, biais, comptage ----------------------------------------------------------------


def agreement(
    units: Iterable[Unit], labels: Mapping[str, bool], decisions: Mapping[str, bool | None]
) -> dict[str, Any]:
    """Accord sur les unités étiquetées ``true``/``false`` à verdict booléen ; ``decisions`` :
    clé → verdict (``None`` = ligne ``error``), clé absente = aucune ligne."""
    labeled = n = agree = lenient = severe = without_line = errors = 0
    for unit in units:
        human = labels.get(unit.key)
        if human is None:
            continue
        labeled += 1
        if unit.key not in decisions:
            without_line += 1
            continue
        judged = decisions[unit.key]
        if judged is None:
            errors += 1
            continue
        n += 1
        if judged == human:
            agree += 1
        elif judged:
            lenient += 1
        else:
            severe += 1
    low, high = _wilson(agree, n)
    return {
        "labeled": labeled,
        "n": n,
        "agree": agree,
        "rate": _ratio(agree, n),
        "ci_low": low,
        "ci_high": high,
        "lenient": lenient,
        "lenient_rate": _ratio(lenient, n),
        "severe": severe,
        "severe_rate": _ratio(severe, n),
        "labeled_without_line": without_line,
        "labeled_error": errors,
    }


def qwen_bias(
    units: Sequence[Unit], labels: Mapping[str, bool], decisions: Mapping[str, bool | None]
) -> dict[str, Any]:
    """Accord(Qwen) − accord(non-Qwen), indéfini si un groupe n'a aucune unité mesurée."""
    qwen = agreement((u for u in units if u.qwen), labels, decisions)
    other = agreement((u for u in units if not u.qwen), labels, decisions)
    bias = None
    if qwen["rate"] is not None and other["rate"] is not None:
        bias = qwen["rate"] - other["rate"]
    return {"bias": bias, "qwen": qwen, "non_qwen": other}


def measures(
    units: Sequence[Unit], labels: Mapping[str, bool], decisions: Mapping[str, bool | None]
) -> dict[str, Any]:
    """Accord, biais Qwen et accord à part des critères de comptage d'une configuration."""
    return {
        "agreement": agreement(units, labels, decisions),
        "qwen_bias": qwen_bias(units, labels, decisions),
        "counting": {
            "counting": agreement((u for u in units if u.counting), labels, decisions),
            "other": agreement((u for u in units if not u.counting), labels, decisions),
        },
    }


# -- Coût et couverture ---------------------------------------------------------------------


def judge_cost(data: JudgeData, projected_judgments: int) -> dict[str, Any]:
    """Total facturé (lots ``collected`` s'il y en a, sinon lignes), par jugement et projeté."""
    verdicts = data.verdicts or {}
    if data.batch_costs:
        source, total = "batches", math.fsum(data.batch_costs)
    else:
        source, total = "judgments", math.fsum(v.cost_usd for v in verdicts.values())
    per_judgment = _ratio(total, len(verdicts))
    return {
        "source": source,
        "total_usd": total,
        "lines": len(verdicts),
        "per_judgment_usd": per_judgment,
        "projected_usd": None if per_judgment is None else per_judgment * projected_judgments,
    }


def coverage(units: Sequence[Unit], data: JudgeData) -> dict[str, Any]:
    verdicts = data.verdicts or {}
    errors = sum(1 for v in verdicts.values() if v.verdict is None)
    return {
        "units": len(units),
        "lines": len(verdicts),
        "verdicts": len(verdicts) - errors,
        "errors": errors,
        "missing": len(units) - len(verdicts),
        "share": _ratio(len(verdicts), len(units)),
    }


def decisions_of(data: JudgeData) -> dict[str, bool | None]:
    return {key: v.verdict for key, v in (data.verdicts or {}).items()}


# -- Cascade --------------------------------------------------------------------------------


def cascade_bounds(margin: float) -> tuple[float, float]:
    return round(0.5 - margin, 2), round(0.5 + margin, 2)


def cascade_id(margin: float) -> str:
    low, high = cascade_bounds(margin)
    return f"{CASCADE}@{low:.2f}-{high:.2f}"


def cascade_decisions(
    winnow: Mapping[str, Verdict], haiku: Mapping[str, Verdict], margin: float
) -> tuple[dict[str, bool | None], int, int]:
    """Verdicts de la cascade sur les unités notées par Winnow, nombre d'escalades et
    d'escalades sans ligne de Haiku (unité alors sans verdict de la cascade)."""
    low, high = cascade_bounds(margin)
    decisions: dict[str, bool | None] = {}
    escalated = without_haiku = 0
    for key in sorted(winnow):
        line = winnow[key]
        p = line.probability
        if line.verdict is not None and p is not None and p >= high:
            decisions[key] = True
        elif line.verdict is not None and p is not None and p <= low:
            decisions[key] = False
        else:
            escalated += 1
            fallback = haiku.get(key)
            if fallback is None:
                without_haiku += 1
            else:
                decisions[key] = fallback.verdict
    return decisions, escalated, without_haiku


def cascade(
    units: Sequence[Unit],
    labels: Mapping[str, bool],
    winnow: JudgeData,
    haiku: JudgeData,
    margins: Sequence[float],
    projected_judgments: int,
) -> list[dict[str, Any]]:
    """Une entrée par marge : bornes, identifiant, part escaladée, coût, accord et biais."""
    haiku_cost = judge_cost(haiku, projected_judgments)["per_judgment_usd"]
    winnow_lines = winnow.verdicts or {}
    entries = []
    for margin in margins:
        decisions, escalated, without_haiku = cascade_decisions(
            winnow_lines, haiku.verdicts or {}, margin
        )
        low, high = cascade_bounds(margin)
        if escalated == 0:
            cost: float | None = 0.0
        else:
            cost = None if haiku_cost is None else haiku_cost * escalated
        per_judgment = None if cost is None else _ratio(cost, len(winnow_lines))
        entries.append(
            {
                "id": cascade_id(margin),
                "margin": margin,
                "low": low,
                "high": high,
                "winnow_lines": len(winnow_lines),
                "escalated": escalated,
                "escalated_share": _ratio(escalated, len(winnow_lines)),
                "escalated_without_haiku": without_haiku,
                "cost": {
                    "total_usd": cost,
                    "per_judgment_usd": per_judgment,
                    "projected_usd": (
                        None if per_judgment is None else per_judgment * projected_judgments
                    ),
                },
                **measures(units, labels, decisions),
            }
        )
    return entries


# -- Stabilité ------------------------------------------------------------------------------


def first_difference(a: Any, b: Any, where: str) -> str | None:
    """Chemin du premier champ différent entre deux valeurs JSON (clés triées), ou ``None``."""
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return f"{where}.{key}"
            found = first_difference(a[key], b[key], f"{where}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return where
        for index, (x, y) in enumerate(zip(a, b, strict=True)):
            found = first_difference(x, y, f"{where}[{index}]")
            if found is not None:
                return found
        return None
    return None if a == b and type(a) is type(b) else where


def stability(base: JudgeData, replay: JudgeData | None) -> dict[str, Any]:
    """Part de verdicts identiques entre un juge et son rejeu ``<id>-replay``."""
    entry: dict[str, Any] = {
        "judge": base.id,
        "replay": base.id + REPLAY_SUFFIX,
        "status": "computed",
        "field": None,
        "n": 0,
        "identical": 0,
        "rate": None,
        "ci_low": None,
        "ci_high": None,
        "changed": 0,
        "true_to_false": 0,
        "false_to_true": 0,
        "judge_only": 0,
        "replay_only": 0,
    }
    if replay is None or replay.status == "absent":
        entry["status"] = "replay_absent"
        return entry
    if base.status != "present":
        entry["status"] = f"judge_{base.status}"
        return entry
    assert base.judge is not None and replay.judge is not None  # noqa: S101 (manifestes lus)
    for name in COMPARED_JUDGE_FIELDS:
        found = first_difference(base.judge.get(name), replay.judge.get(name), name)
        if found is not None:
            entry.update(status="not_comparable", field=found)
            return entry
    if base.generation_manifest != replay.generation_manifest or not replay.present:
        entry.update(status="not_comparable", field="generation_manifest")
        return entry
    first, second = base.verdicts or {}, replay.verdicts or {}
    for key in sorted(set(first) | set(second)):
        if key not in second:
            entry["judge_only"] += 1
            continue
        if key not in first:
            entry["replay_only"] += 1
            continue
        a, b = first[key].verdict, second[key].verdict
        if a is None or b is None:
            continue
        entry["n"] += 1
        if a == b:
            entry["identical"] += 1
        elif a:
            entry["true_to_false"] += 1
        else:
            entry["false_to_true"] += 1
    entry["changed"] = entry["n"] - entry["identical"]
    entry["rate"] = _ratio(entry["identical"], entry["n"])
    entry["ci_low"], entry["ci_high"] = _wilson(entry["identical"], entry["n"])
    return entry


# -- Admissibilité et proposition -----------------------------------------------------------


def admissibility(
    block: Mapping[str, Any], min_agreement: float | None, max_qwen_bias: float | None
) -> dict[str, bool | None]:
    """Chaque critère : ``None`` = seuil non fixé ; biais indéfini = non admissible."""
    rate = block["agreement"]["rate"]
    bias = block["qwen_bias"]["bias"]
    agreement_ok = None
    if min_agreement is not None:
        agreement_ok = rate is not None and rate >= min_agreement - EPSILON
    bias_ok = None
    if max_qwen_bias is not None:
        bias_ok = bias is not None and abs(bias) <= max_qwen_bias + EPSILON
    admissible = None
    if agreement_ok is not None and bias_ok is not None:
        admissible = agreement_ok and bias_ok
    return {"agreement": agreement_ok, "qwen_bias": bias_ok, "admissible": admissible}


def proposal(
    candidates: Sequence[Mapping[str, Any]],
    min_agreement: float | None,
    max_qwen_bias: float | None,
) -> dict[str, Any] | None:
    """Proposition (jamais appliquée) : accord maximal, puis coût projeté minimal, puis ordre
    des configurations ; ``None`` sans les deux seuils."""
    if min_agreement is None or max_qwen_bias is None:
        return None
    admissible = [c for c in candidates if c["admissibility"]["admissible"]]
    result: dict[str, Any] = {
        "status": "none_admissible",
        "id": None,
        "agreement": None,
        "qwen_bias": None,
        "projected_usd": None,
        "candidates": len(candidates),
        "admissible": [c["id"] for c in admissible],
    }
    if not admissible:
        return result

    def rank(item: tuple[int, Mapping[str, Any]]) -> tuple[float, float, int]:
        index, candidate = item
        cost = candidate["projected_usd"]
        return (-candidate["agreement"], math.inf if cost is None else cost, index)

    _, best = min(enumerate(admissible), key=rank)
    result.update(
        status="proposed",
        id=best["id"],
        agreement=best["agreement"],
        qwen_bias=best["qwen_bias"],
        projected_usd=best["projected_usd"],
    )
    return result


# -- Rapport --------------------------------------------------------------------------------


def configuration_order(judge_ids: Iterable[str]) -> list[str]:
    """``winnow``, la cascade, ``mimo``, ``haiku``, puis les autres juges (ordre alphabétique),
    hors ``*-replay``."""
    others = sorted({j for j in judge_ids if not j.endswith(REPLAY_SUFFIX)} - {WINNOW, MIMO, HAIKU})
    return [WINNOW, CASCADE, MIMO, HAIKU, *others]


def _units_summary(units: Sequence[Unit]) -> dict[str, int]:
    return {
        "total": len(units),
        "qwen": sum(1 for u in units if u.qwen),
        "non_qwen": sum(1 for u in units if not u.qwen),
        "counting": sum(1 for u in units if u.counting),
        "private": sum(1 for u in units if u.private),
        "models": len({u.model for u in units}),
        "responses": len({u.generation_key for u in units}),
    }


def _judge_entry(data: JudgeData) -> dict[str, Any]:
    return {
        "id": data.id,
        "status": data.status,
        "manifest": data.manifest_hash,
        "lines": len(data.verdicts or {}),
        "collected_batches": len(data.batch_costs),
    }


def build_report(
    *,
    campaign: str,
    generation_manifest: str,
    units: Sequence[Unit],
    judges: Mapping[str, JudgeData],
    labels: Labels,
    min_agreement: float | None,
    max_qwen_bias: float | None,
    margins: Sequence[float],
    projected_judgments: int,
) -> dict[str, Any]:
    """Rapport de calibration (JSON) : aucune date, aucun texte, ordre fixe."""
    order = configuration_order(judges)
    configurations: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    def candidate(entry_id: str, block: Mapping[str, Any], cost: Mapping[str, Any]) -> dict:
        verdict = admissibility(block, min_agreement, max_qwen_bias)
        if block["agreement"]["rate"] is not None:
            candidates.append(
                {
                    "id": entry_id,
                    "agreement": block["agreement"]["rate"],
                    "qwen_bias": block["qwen_bias"]["bias"],
                    "projected_usd": cost["projected_usd"],
                    "admissibility": verdict,
                }
            )
        return verdict

    cascade_section: dict[str, Any] = {"status": "computed", "missing": [], "margins": []}
    for config_id in order:
        if config_id == CASCADE:
            missing = [j for j in (WINNOW, HAIKU) if j not in judges or not judges[j].present]
            entry: dict[str, Any] = {"id": CASCADE, "kind": "cascade"}
            if missing:
                cascade_section.update(status="not_simulable", missing=missing)
                entry["status"] = "not_simulable"
            else:
                cascade_section["margins"] = cascade(
                    units,
                    labels.values,
                    judges[WINNOW],
                    judges[HAIKU],
                    margins,
                    projected_judgments,
                )
                for margin_entry in cascade_section["margins"]:
                    margin_entry["admissibility"] = candidate(
                        margin_entry["id"], margin_entry, margin_entry["cost"]
                    )
                entry["status"] = "computed"
            configurations.append(entry)
            continue
        data = judges.get(config_id, JudgeData(config_id, "absent"))
        entry = {"id": config_id, "kind": "judge", "status": data.status}
        if data.present:
            entry["coverage"] = coverage(units, data)
            entry["cost"] = judge_cost(data, projected_judgments)
            entry.update(measures(units, labels.values, decisions_of(data)))
            entry["admissibility"] = candidate(config_id, entry, entry["cost"])
        configurations.append(entry)

    stability_entries = []
    for config_id in order:
        if config_id == CASCADE:
            continue
        base = judges.get(config_id, JudgeData(config_id, "absent"))
        replay = judges.get(config_id + REPLAY_SUFFIX)
        if base.status == "absent" and (replay is None or replay.status == "absent"):
            continue
        stability_entries.append(stability(base, replay))

    return {
        "campaign": campaign,
        "generation_manifest": generation_manifest,
        "units": _units_summary(units),
        "labels": {
            "file_present": labels.file_present,
            "lines": labels.lines,
            "used": len(labels.values),
            "true": sum(1 for v in labels.values.values() if v),
            "false": sum(1 for v in labels.values.values() if not v),
            "undecidable": labels.undecidable,
            "to_label": labels.to_label,
            "other_campaigns": labels.other_campaigns,
        },
        "settings": {
            "min_agreement": min_agreement,
            "max_qwen_bias": max_qwen_bias,
            "cascade_margins": list(margins),
            "projected_judgments": projected_judgments,
        },
        "judges": [_judge_entry(judges[j]) for j in sorted(judges)],
        "configurations": configurations,
        "cascade": cascade_section,
        "stability": stability_entries,
        "proposal": proposal(candidates, min_agreement, max_qwen_bias),
    }


# -- Échantillon à étiqueter ----------------------------------------------------------------


def _hash_key(seed: int, salt: str) -> Callable[[str], tuple[str, str]]:
    return lambda key: (sha256_hex([seed, salt, key]), key)


def _model_items(units: Sequence[Unit], quota: int, seed: int) -> list[Unit]:
    """Réponses triées par empreinte, un critère par réponse et par tour jusqu'au quota."""
    by_response: dict[str, list[Unit]] = {}
    for unit in units:
        by_response.setdefault(unit.generation_key, []).append(unit)
    order = _hash_key(seed, "calibration")
    responses = [
        sorted(by_response[gk], key=lambda u: order(u.key)) for gk in sorted(by_response, key=order)
    ]
    chosen: list[Unit] = []
    depth = 0
    while len(chosen) < quota and any(depth < len(r) for r in responses):
        for criteria in responses:
            if depth < len(criteria) and len(chosen) < quota:
                chosen.append(criteria[depth])
        depth += 1
    return chosen


@dataclass(frozen=True)
class Sample:
    items: list[Unit]
    quotas: dict[str, int]  # modèle → quota
    drawn: dict[str, int]  # modèle → critères tirés
    groups: dict[str, int]  # « qwen » / « non_qwen » → quota du groupe


def draw_sample(units: Sequence[Unit], size: int, seed: int) -> Sample:
    """Moitié Qwen, moitié non-Qwen (tout à un groupe si l'autre est vide ; un éventuel reste
    au groupe Qwen), partagé à parts égales entre les modèles du groupe (reste aux premiers
    tags) ; ordre final par empreinte ``[seed, "calibration-order", key]``."""
    groups = {
        "qwen": [u for u in units if u.qwen],
        "non_qwen": [u for u in units if not u.qwen],
    }
    if groups["qwen"] and groups["non_qwen"]:
        group_quotas = {"qwen": size - size // 2, "non_qwen": size // 2}
    else:
        group_quotas = {name: (size if members else 0) for name, members in groups.items()}
    quotas: dict[str, int] = {}
    drawn: dict[str, int] = {}
    items: list[Unit] = []
    for name in ("qwen", "non_qwen"):
        models = sorted({u.model for u in groups[name]})
        if not models:
            continue
        share, rest = divmod(group_quotas[name], len(models))
        for index, model in enumerate(models):
            quota = share + (1 if index < rest else 0)
            chosen = _model_items([u for u in groups[name] if u.model == model], quota, seed)
            quotas[model], drawn[model] = quota, len(chosen)
            items.extend(chosen)
    order = _hash_key(seed, "calibration-order")
    items.sort(key=lambda u: order(u.key))
    return Sample(items=items, quotas=quotas, drawn=drawn, groups=group_quotas)
