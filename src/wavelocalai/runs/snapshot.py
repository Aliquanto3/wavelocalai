"""Instantané d'un run (`GET /api/runs/{id}`, AD-5) : statut, métriques des feuilles, erreur.

Lecture seule sur la base : le hub y écrit le statut à la clôture, et les métriques n'existent que
sur les feuilles. Un run composite rend ses feuilles dans `children`. Ce qui se calcule sur un run
terminé y figure aussi, pas dans le flux : le `verdict` local/cloud d'une Arène (story 3.5), sa
`config` (de quoi la relancer ou la modifier) et `erased` (story 3.6). Une évaluation (story 7.1)
porte ses notes, leur résumé et `partial` (`runs/eval_snapshot.py`) ; un banc d'essai (story 7.4)
son entrée, sa sortie et son `format_verdict` (`runs/bench_snapshot.py`). Un run `agent` porte
`totals` (story 6.4 : tours, étapes, durée et CO2 de la tâche, additionnés ici et non à l'écran,
AD-20) et `mission` (story 6.5). La liste des Arènes (`GET /api/arena/runs`) est lue ici aussi.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from wavelocalai.config import PriceTable
from wavelocalai.runs.agent_totals import agent_totals
from wavelocalai.runs.bench_snapshot import bench_snapshot_fields
from wavelocalai.runs.eval_snapshot import eval_snapshot_fields
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


ACTIVE = ("running", "awaiting_approval")
EXCERPT_CHARS = 200


async def arena_record(store: Store, run_id: str) -> dict[str, Any]:
    """Ce que le flux d'une Arène dit de sa configuration et de ses notes : `question`, `judge`
    (événements), `scores` (`judge_score` par lane) et `lanes` (dernier `lane_status` de chaque
    lane) : le dernier événement d'une lane l'emporte. Vide après l'effacement de l'Arène (AD-13) :
    la question, les raisons et les notes vivaient dans `run_events`."""
    rows = await store.aread(
        "SELECT type, data FROM run_events WHERE run_id = ?"
        " AND type IN ('question', 'judge', 'judge_score', 'lane_status') ORDER BY seq",
        (run_id,),
    )
    record: dict[str, Any] = {"question": None, "judge": None, "scores": {}, "lanes": {}}
    for row in rows:
        data = json.loads(row["data"])
        if row["type"] == "judge_score":
            record["scores"][data.get("lane")] = data
        elif row["type"] == "lane_status":
            record["lanes"][data.get("lane")] = data
        else:
            record[row["type"]] = data
    return record


def _scores(record: dict[str, Any]) -> dict[str, float]:
    """Note /100 de chaque lane ; une note nulle (« non évalué ») n'en fait pas partie."""
    return {
        lane: data["score"]
        for lane, data in record["scores"].items()
        if isinstance(data.get("score"), int | float)
    }


async def _has_events(store: Store, run_id: str) -> bool:
    rows = await store.aread("SELECT 1 FROM run_events WHERE run_id = ? LIMIT 1", (run_id,))
    return bool(rows)


def _config(snapshot: dict[str, Any], record: dict[str, Any]) -> dict[str, Any] | None:
    """La configuration d'une Arène : de quoi la relancer (« Relancer ») ou la reprendre dans le
    formulaire (« Modifier la question »). `None` sans question dans le flux (Arène effacée)."""
    question = record["question"]
    if question is None:
        return None
    return {
        "models": [c["model"] for c in snapshot["children"] if c["kind"] == "generation"],
        "prompt": question.get("text") or "",
        "criteria": list(question.get("criteria") or []),
        "judge": snapshot["params"].get("judge"),
    }


async def run_snapshot(
    store: Store, run_id: str, prices: PriceTable | None = None
) -> dict[str, Any] | None:
    """Instantané du run, ou `None` s'il n'existe pas.

    Une Arène terminée `ok` porte `verdict` (local/cloud, table de prix `prices`) ; `null` quand
    elle n'a pas de modèle local et de modèle cloud notés, ou n'est pas terminée normalement. Toute
    Arène porte `config` (`null` une fois effacée) et `erased` : vrai pour une Arène terminée dont
    les événements ont été supprimés (AD-13) ; ses lignes `runs` restent, sans texte."""
    rows = await store.aread(
        "SELECT * FROM runs WHERE id = ? OR parent_run_id = ? ORDER BY started_at, rowid",
        (run_id, run_id),
    )
    snapshot = next((run_snapshot_row(row) for row in rows if row["id"] == run_id), None)
    if snapshot is None:
        return None
    snapshot["children"] = [run_snapshot_row(row) for row in rows if row["parent_run_id"] == run_id]
    if snapshot["kind"] == "arena":
        record = await arena_record(store, run_id)
        settled = snapshot["status"] not in ACTIVE
        snapshot["erased"] = settled and not await _has_events(store, run_id)
        snapshot["config"] = _config(snapshot, record)
        snapshot["verdict"] = (
            build_verdict(snapshot["children"], _scores(record), prices or PriceTable())
            if snapshot["status"] == "ok"
            else None
        )
    elif snapshot["kind"] == "agent":
        rows = await store.aread(
            "SELECT count(*) AS n FROM run_events WHERE run_id = ? AND type = 'step'", (run_id,)
        )
        snapshot["totals"] = agent_totals(snapshot, rows[0]["n"])
        snapshot["mission"] = await mission_totals(store, run_id)
    elif snapshot["kind"] == "eval":  # notes, résumé et partiel d'une évaluation (story 7.1)
        snapshot.update(await eval_snapshot_fields(store, snapshot))
    elif snapshot["kind"] == "bench":  # entrée, sortie et verdict de format (story 7.4)
        snapshot.update(await bench_snapshot_fields(store, snapshot))
    return snapshot


async def mission_totals(store: Store, run_id: str) -> dict[str, Any] | None:
    """Totaux d'une mission d'équipe (story 6.5) : durée et pic de mémoire du poste, lus dans son
    événement `mission_totals` ; `None` pour un agent seul ou une mission encore en cours."""
    rows = await store.aread(
        "SELECT data FROM run_events WHERE run_id = ? AND type = 'mission_totals'"
        " ORDER BY seq DESC LIMIT 1",
        (run_id,),
    )
    if not rows:
        return None
    data = json.loads(rows[0]["data"])
    return {
        "duration_s": data.get("duration_s"),
        "peak_memory_gb": data.get("peak_memory_gb"),
        "agents_done": data.get("agents_done"),
    }


async def list_arena_runs(store: Store, limit: int = 20) -> list[dict[str, Any]]:
    """Les Arènes les plus récentes d'abord, pour les rouvrir : identifiant, statut, dates, modèles
    comparés et début de la question. Une Arène effacée n'y figure plus (rien à rouvrir)."""
    rows = await store.aread(
        "SELECT r.id, r.status, r.started_at, r.ended_at,"
        " (SELECT data FROM run_events e WHERE e.run_id = r.id AND e.type = 'question'"
        "  LIMIT 1) AS question"
        " FROM runs r WHERE r.kind = 'arena' AND r.parent_run_id IS NULL"
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
    models: dict[str, list[str]] = {}
    for leaf in leaves:
        models.setdefault(leaf["parent_run_id"], []).append(leaf["model"])
    runs = []
    for row in rows:
        text = (json.loads(row["question"]).get("text") or "") if row["question"] else ""
        runs.append(
            {
                "run_id": row["id"],
                "status": row["status"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "models": models.get(row["id"], []),
                "question": text[:EXCERPT_CHARS],
            }
        )
    return runs


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
