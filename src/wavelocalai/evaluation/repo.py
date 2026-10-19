"""Écriture des notes de l'évaluation (table `evaluations`, migration 0006, story 7.1).

Fonction qui prend la connexion de l'écrivain unique (AD-12) : elle s'exécute dans une transaction
ouverte par `Store.awrite`. L'effacement (AD-13) est dans `runs/repo.py::erase_eval`.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from wavelocalai.runs.repo import dumps


def insert_evaluation(
    conn: sqlite3.Connection,
    run_id: str,
    lane: str,
    question_index: int,
    metric: str,
    score: int | None,
    reason: str,
    detail: dict[str, Any] | None,
    created_at: str,
) -> None:
    """Une note (ou son absence, `score` nul avec sa raison). Remplace la ligne du même
    (run, modèle, question, métrique) : une note n'est écrite qu'une fois, mais jamais en double."""
    conn.execute(
        "INSERT OR REPLACE INTO evaluations (run_id, lane, question_index, metric, score, reason,"
        " detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            lane,
            question_index,
            metric,
            score,
            reason,
            None if detail is None else dumps(detail),
            created_at,
        ),
    )
