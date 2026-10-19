"""Ce que l'instantané d'une évaluation (`GET /api/runs/{id}`, kind `eval`) ajoute au run (story 7.1).

Lecture seule sur la base : les notes vivent dans `evaluations` (une ligne par modèle évalué, question
et métrique), la configuration dans les événements `eval_questions` et `judge` du flux. Tout se
calcule ici, le front n'en refait rien (AD-20) : la moyenne par modèle et métrique avec son
« sur 8 questions (1 non évaluée) », et, pour une évaluation arrêtée, les notes manquantes avec leur
raison. Un inconnu n'est jamais un 0.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

from wavelocalai.store.db import Store

METRICS = ("faithfulness", "relevance", "context_precision")
NOT_EVALUATED_STOPPED = "non évalué : évaluation arrêtée"
PARTIAL_STATUSES = ("cancelled", "interrupted", "error")  # terminé sans avoir tout noté


def aggregate(scores: Iterable[int | None], total: int) -> dict[str, Any]:
    """Moyenne des notes présentes (entier de 0 à 100, `None` sans note) sur `total` questions :
    `{score, evaluated, not_evaluated, total}`. `not_evaluated` compte les questions sans note,
    celles qui n'ont pas encore de ligne comprises ; `score` est `None` sans aucune note."""
    present = [s for s in scores if s is not None]
    mean = None if not present else int(sum(present) / len(present) + 0.5)
    return {
        "score": mean,
        "evaluated": len(present),
        "not_evaluated": max(total - len(present), 0),
        "total": total,
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
    rows: Sequence[dict[str, Any]], lanes: Sequence[str], question_count: int
) -> dict[str, dict[str, dict[str, Any]]]:
    """`{lane: {metric: aggregate}}` pour chaque modèle évalué et chaque métrique."""
    return {
        lane: {
            metric: aggregate(
                (r["score"] for r in rows if r["lane"] == lane and r["metric"] == metric),
                question_count,
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
    en base, de quoi tout reconstruire sans relancer un modèle), `summary` et, si l'évaluation est
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
        "summary": summarize(rows, lanes, count),
        "judge": record["judge"],
    }
    if partial:
        fields["missing"] = missing_rows(rows, lanes, count) if config is not None else []
    return fields
