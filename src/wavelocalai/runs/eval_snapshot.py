"""Ce que l'instantané d'une évaluation (`GET /api/runs/{id}`, kind `eval`) ajoute au run (story 7.1).

Lecture seule sur la base : les notes vivent dans `evaluations` (une ligne par modèle évalué, question
et métrique), la configuration dans les événements `eval_questions` et `judge` du flux. Tout se
calcule ici, le front n'en refait rien (AD-20) : la moyenne par modèle et métrique avec son
« sur 8 questions (1 non évaluée) », et, pour une évaluation arrêtée, les notes manquantes avec leur
raison. Un inconnu n'est jamais un 0.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from wavelocalai.store.db import Store

METRICS = ("faithfulness", "relevance", "context_precision")
NOT_EVALUATED_STOPPED = "non évalué : évaluation arrêtée"
PARTIAL_STATUSES = ("cancelled", "interrupted", "error")  # terminé sans avoir tout noté


def aggregate(scores: Iterable[int | None], total: int, *, settled: bool = True) -> dict[str, Any]:
    """Moyenne des notes présentes (entier de 0 à 100, `None` sans note) sur `total` questions :
    `{score, evaluated, not_evaluated, pending, total}`. `scores` : une valeur par question déjà
    traitée (`None` = non évaluée). Pendant l'évaluation (`settled=False`), une question pas encore
    traitée est `pending`, pas « non évaluée » ; une fois le run terminé, elle ne sera plus notée
    (évaluation arrêtée) et compte dans `not_evaluated`. `score` est `None` sans aucune note."""
    seen = list(scores)
    present = [s for s in seen if s is not None]
    mean = None if not present else int(sum(present) / len(present) + 0.5)
    unseen = max(total - len(seen), 0)
    return {
        "score": mean,
        "evaluated": len(present),
        "not_evaluated": len(seen) - len(present) + (unseen if settled else 0),
        "pending": 0 if settled else unseen,
        "total": total,
    }


def measure_totals(events: Iterable[Mapping[str, Any]], total: int) -> dict[str, Any]:
    """Mesures d'un modèle sur un jeu de questions (revue 7.3, AD-20 : le front n'en calcule rien),
    lues dans ses événements `metrics` (une réponse obtenue chacun) : `tps` = débit moyen des
    réponses dont le débit est mesuré (`tps_measured` d'entre elles), `co2.mg` = somme des CO2
    mesurés ou estimés (`co2.measured` d'entre elles, `estimated` si l'un l'est, `unmeasurable` si
    des réponses ont un CO2 mais aucun chiffré), `answered` réponses mesurables sur `total`
    questions. Un inconnu est `None`, jamais 0."""
    seen = list(events)
    rates = [e["tps"] for e in seen if isinstance(e.get("tps"), (int, float))]
    co2 = [e["co2"] for e in seen if isinstance(e.get("co2"), Mapping)]
    grams = [c["mg"] for c in co2 if isinstance(c.get("mg"), (int, float))]
    return {
        "tps": sum(rates) / len(rates) if rates else None,
        "tps_measured": len(rates),
        "co2": {
            "mg": sum(grams) if grams else None,
            "measured": len(grams),
            "estimated": any(c.get("estimated") is True for c in co2),
            "unmeasurable": bool(co2) and not grams,
        },
        "answered": len(seen),
        "total": total,
    }


async def measures_by_lane(
    store: Store, run_id: str, lanes: Sequence[str], question_count: int
) -> dict[str, dict[str, Any]]:
    """`{lane: measure_totals}` d'après les `metrics` enregistrés (vides une fois effacée)."""
    rows = await store.aread(
        "SELECT data FROM run_events WHERE run_id = ? AND type = 'metrics' ORDER BY seq",
        (run_id,),
    )
    by_lane: dict[str, dict[int, dict[str, Any]]] = {lane: {} for lane in lanes}
    for row in rows:
        data = json.loads(row["data"])
        if data.get("lane") in by_lane:  # une relance : la dernière mesure de la question
            by_lane[data["lane"]][int(data.get("question_index") or 0)] = data
    return {
        lane: measure_totals(events.values(), question_count) for lane, events in by_lane.items()
    }


def _row_view(row: Any) -> dict[str, Any]:
    detail = json.loads(row["detail"]) if row["detail"] else {}
    return {
        "lane": row["lane"],
        "question_index": row["question_index"],
        "metric": row["metric"],
        "score": row["score"],
        "reason": row["reason"],
        "verdicts": detail.get("verdicts"),
        "questions": detail.get("questions"),
        "useful": detail.get("useful"),
    }


async def eval_record(store: Store, run_id: str) -> dict[str, Any]:
    """`questions` et `judge` du flux (vides une fois l'évaluation effacée, AD-13)."""
    rows = await store.aread(
        "SELECT type, data FROM run_events WHERE run_id = ? AND type IN ('eval_questions', 'judge')"
        " ORDER BY seq",
        (run_id,),
    )
    record: dict[str, Any] = {"questions": None, "judge": None}
    for row in rows:
        data = json.loads(row["data"])
        if row["type"] == "eval_questions":
            record["questions"] = data.get("questions")
        else:
            record["judge"] = data
    return record


def summarize(
    rows: Sequence[dict[str, Any]],
    lanes: Sequence[str],
    question_count: int,
    *,
    settled: bool = True,
) -> dict[str, dict[str, dict[str, Any]]]:
    """`{lane: {metric: aggregate}}` pour chaque modèle évalué et chaque métrique."""
    return {
        lane: {
            metric: aggregate(
                (r["score"] for r in rows if r["lane"] == lane and r["metric"] == metric),
                question_count,
                settled=settled,
            )
            for metric in METRICS
        }
        for lane in lanes
    }


def missing_rows(
    rows: Sequence[dict[str, Any]], lanes: Sequence[str], question_count: int
) -> list[dict[str, Any]]:
    """Les notes qu'une évaluation arrêtée n'a pas eu le temps de produire, chacune « non évalué :
    évaluation arrêtée » (jamais 0)."""
    done = {(r["lane"], r["question_index"], r["metric"]) for r in rows}
    return [
        {
            "lane": lane,
            "question_index": index,
            "metric": metric,
            "score": None,
            "reason": NOT_EVALUATED_STOPPED,
        }
        for lane in lanes
        for index in range(question_count)
        for metric in METRICS
        if (lane, index, metric) not in done
    ]


async def eval_snapshot_fields(store: Store, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Champs d'un instantané `eval` : `config`, `erased`, `partial`, `evaluations` (les notes lues
    en base, de quoi tout reconstruire sans relancer un modèle), `summary`, `measures` (débit moyen
    et CO2 total par modèle) et, si l'évaluation est
    partielle, `missing`. `config` et les listes sont vides une fois l'évaluation effacée."""
    run_id = snapshot["run_id"]
    record = await eval_record(store, run_id)
    settled = snapshot["status"] not in ("running", "awaiting_approval")
    erased = settled and not (
        await store.aread("SELECT 1 FROM run_events WHERE run_id = ? LIMIT 1", (run_id,))
    )
    rows = [
        _row_view(row)
        for row in await store.aread(
            "SELECT lane, question_index, metric, score, reason, detail FROM evaluations"
            " WHERE run_id = ? ORDER BY question_index, lane, metric",
            (run_id,),
        )
    ]
    questions = record["questions"]
    lanes = [c["model"] for c in snapshot["children"] if c["kind"] == "generation"]
    lanes = list(dict.fromkeys(lanes))  # une feuille par modèle et question : l'ordre de départ
    config = (
        None
        if questions is None
        else {
            "questions": list(questions),
            "models": lanes,
            "judge": snapshot["params"].get("judge"),
            "allow_cloud": bool(snapshot["params"].get("allow_cloud")),
        }
    )
    count = len(questions or []) or (max((r["question_index"] for r in rows), default=-1) + 1)
    partial = snapshot["status"] in PARTIAL_STATUSES
    fields: dict[str, Any] = {
        "erased": erased,
        "config": config,
        "partial": partial,
        "evaluations": rows,
        "summary": summarize(rows, lanes, count, settled=settled),
        "measures": await measures_by_lane(store, run_id, lanes, count),
        "judge": record["judge"],
    }
    if partial:
        fields["missing"] = missing_rows(rows, lanes, count) if config is not None else []
    return fields


async def list_eval_runs(store: Store, limit: int = 20, excerpt: int = 200) -> list[dict[str, Any]]:
    """Les évaluations les plus récentes d'abord, pour les rouvrir (décision n° 14, story 7.3) :
    identifiant, statut, dates, modèles évalués (ordre de départ), nombre de questions et début de
    la première. Une évaluation effacée n'y figure plus (rien à rouvrir), comme pour l'Arène."""
    rows = await store.aread(
        "SELECT r.id, r.status, r.started_at, r.ended_at,"
        " (SELECT data FROM run_events e WHERE e.run_id = r.id AND e.type = 'eval_questions'"
        "  LIMIT 1) AS questions"
        " FROM runs r WHERE r.kind = 'eval' AND r.parent_run_id IS NULL"
        " AND (r.status IN ('running', 'awaiting_approval')"
        "  OR EXISTS (SELECT 1 FROM run_events e WHERE e.run_id = r.id))"
        " ORDER BY r.started_at DESC, r.rowid DESC LIMIT ?",
        (limit,),
    )
    if not rows:
        return []
    marks = ",".join("?" * len(rows))
    leaves = await store.aread(
        f"SELECT parent_run_id, model FROM runs WHERE kind = 'generation'"  # noqa: S608
        f" AND parent_run_id IN ({marks}) ORDER BY started_at, rowid",
        tuple(row["id"] for row in rows),
    )
    models: dict[str, dict[str, None]] = {}  # une feuille par modèle et question : sans doublon
    for leaf in leaves:
        models.setdefault(leaf["parent_run_id"], {})[leaf["model"]] = None
    runs = []
    for row in rows:
        questions = (
            (json.loads(row["questions"]).get("questions") or []) if row["questions"] else []
        )
        runs.append(
            {
                "run_id": row["id"],
                "status": row["status"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "models": list(models.get(row["id"], {})),
                "question_count": len(questions),
                "question": (questions[0] if questions else "")[:excerpt],
            }
        )
    return runs
