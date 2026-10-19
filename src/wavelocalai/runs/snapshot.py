"""Instantané d'un run (`GET /api/runs/{id}`, AD-5) : statut, métriques des feuilles, erreur.

Lecture seule sur la base : le hub y écrit le statut à la clôture, et les métriques n'existent que
sur les feuilles. Un run composite rend ses feuilles dans `children`. Ce qui se calcule sur un run
terminé y figure aussi, pas dans le flux : le `verdict` local/cloud d'une Arène (story 3.5).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from wavelocalai.config import PriceTable
from wavelocalai.runs.verdict import build_verdict
from wavelocalai.store.db import Store

METRIC_COLUMNS = (
    "origin",
    "input_tokens",
    "output_tokens",
    "ttft_s",
    "load_s",
    "eval_s",
    "total_s",
    "tps",
    "tps_source",
    "energy_wh",
)


def _co2(row: sqlite3.Row) -> dict[str, Any] | None:
    if row["co2_method"] is None:
        return None
    low, high = row["co2_range_low_mg"], row["co2_range_high_mg"]
    return {
        "mg": row["co2_mg"],
        "method": row["co2_method"],
        "estimated": bool(row["co2_estimated"]),
        "range_mg": None if low is None or high is None else {"low": low, "high": high},
        "allocation": row["co2_allocation"],
        "reason": row["co2_reason"],
    }


def run_snapshot_row(row: sqlite3.Row) -> dict[str, Any]:
    has_metrics = any(row[column] is not None for column in METRIC_COLUMNS)
    return {
        "run_id": row["id"],
        "kind": row["kind"],
        "parent_run_id": row["parent_run_id"],
        "conversation_id": row["conversation_id"],
        "status": row["status"],
        "model": row["model"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "params": json.loads(row["params"]),
        "error": None if row["error"] is None else json.loads(row["error"]),
        "metrics": (
            {**{column: row[column] for column in METRIC_COLUMNS}, "co2": _co2(row)}
            if has_metrics or row["co2_method"] is not None
            else None
        ),
    }


async def _scores(store: Store, run_id: str) -> dict[str, float]:
    """Note /100 de chaque lane, lue dans les `judge_score` du flux ; une note nulle (« non
    évalué ») n'en fait pas partie."""
    rows = await store.aread(
        "SELECT data FROM run_events WHERE run_id = ? AND type = 'judge_score' ORDER BY seq",
        (run_id,),
    )
    scores: dict[str, float] = {}
    for row in rows:
        data = json.loads(row["data"])
        if isinstance(data.get("score"), int | float):
            scores[data["lane"]] = data["score"]
        else:
            scores.pop(data.get("lane"), None)
    return scores


async def run_snapshot(
    store: Store, run_id: str, prices: PriceTable | None = None
) -> dict[str, Any] | None:
    """Instantané du run, ou `None` s'il n'existe pas.

    Une Arène terminée `ok` porte `verdict` (local/cloud, table de prix `prices`) ; `null` quand
    elle n'a pas de modèle local et de modèle cloud notés, ou n'est pas terminée normalement."""
    rows = await store.aread(
        "SELECT * FROM runs WHERE id = ? OR parent_run_id = ? ORDER BY started_at, rowid",
        (run_id, run_id),
    )
    snapshot = next((run_snapshot_row(row) for row in rows if row["id"] == run_id), None)
    if snapshot is None:
        return None
    snapshot["children"] = [run_snapshot_row(row) for row in rows if row["parent_run_id"] == run_id]
    if snapshot["kind"] == "arena":
        snapshot["verdict"] = (
            build_verdict(
                snapshot["children"], await _scores(store, run_id), prices or PriceTable()
            )
            if snapshot["status"] == "ok"
            else None
        )
    return snapshot


async def stream_state(store: Store, run_id: str) -> tuple[str, str | None, int] | None:
    """(statut, parent, dernier `seq` écrit) d'un run, ou `None` s'il n'existe pas."""
    rows = await store.aread(
        "SELECT r.status, r.parent_run_id, coalesce(max(e.seq), 0) AS last FROM runs r"
        " LEFT JOIN run_events e ON e.run_id = r.id WHERE r.id = ? GROUP BY r.id",
        (run_id,),
    )
    if not rows:
        return None
    return rows[0]["status"], rows[0]["parent_run_id"], rows[0]["last"]
