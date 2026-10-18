"""Lecture d'une conversation (AD-5, AD-13) : messages, raisonnement, mesures et CO2 de chaque
réponse tels que l'écran les a montrés, et liste des conversations.

Lecture seule sur la base : le hub écrit les messages à la création du run et à sa clôture (AD-5).
Les mesures et le `co2` viennent de la ligne `runs` de la réponse (AD-10), pas du flux, qui s'efface
avec la conversation. Le modèle de la conversation est celui de son dernier run : il n'y a donc pas
de champ de plus à tenir à jour.
"""

from __future__ import annotations

import json
from typing import Any

from wavelocalai.runs.snapshot import run_snapshot_row
from wavelocalai.store.db import Store

ACTIVE_STATUSES = ("running", "awaiting_approval")
MAX_LIST = 100


def _run_view(row: Any) -> dict[str, Any]:
    view = run_snapshot_row(row)
    del view["error"]  # l'enveloppe d'erreur n'est pas du contenu de conversation
    return view


async def conversation_view(store: Store, conversation_id: str) -> dict[str, Any] | None:
    """La conversation et ses messages dans l'ordre d'écriture, ou `None` si elle n'existe pas.

    Chaque message porte le `run` qui l'a écrit (statut, modèle, mesures, `co2`). Le champ
    `active_run_id` est le run en cours de la conversation, que l'écran suit par son flux."""
    conversation = await store.aread(
        "SELECT id, kind, title, created_at FROM conversations WHERE id = ?", (conversation_id,)
    )
    if not conversation:
        return None
    messages = await store.aread(
        "SELECT id, run_id, role, content, reasoning, tool_calls, created_at FROM messages"
        " WHERE conversation_id = ? ORDER BY rowid",
        (conversation_id,),
    )
    runs = await store.aread(
        "SELECT * FROM runs WHERE conversation_id = ? AND parent_run_id IS NULL"
        " ORDER BY started_at, rowid",
        (conversation_id,),
    )
    by_id = {row["id"]: _run_view(row) for row in runs}
    last = runs[-1] if runs else None
    active = next((r["id"] for r in reversed(runs) if r["status"] in ACTIVE_STATUSES), None)
    head = conversation[0]
    return {
        "id": head["id"],
        "kind": head["kind"],
        "title": head["title"],
        "created_at": head["created_at"],
        # Le modèle et la créativité gardés par conversation : ceux du dernier run.
        "model": None if last is None else last["model"],
        "temperature": None if last is None else json.loads(last["params"]).get("temperature"),
        "active_run_id": active,
        "messages": [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "reasoning": row["reasoning"],
                "tool_calls": None if row["tool_calls"] is None else json.loads(row["tool_calls"]),
                "created_at": row["created_at"],
                "run": by_id.get(row["run_id"]),
            }
            for row in messages
        ],
    }


async def list_conversations(
    store: Store, kind: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Les conversations les plus récentes d'abord (dernière activité), avec leur dernier modèle."""
    limit = max(1, min(limit, MAX_LIST))
    rows = await store.aread(
        "SELECT c.id, c.kind, c.title, c.created_at,"
        " (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count,"
        " (SELECT r.model FROM runs r WHERE r.conversation_id = c.id AND r.parent_run_id IS NULL"
        "  ORDER BY r.started_at DESC, r.rowid DESC LIMIT 1) AS model,"
        " coalesce((SELECT max(m.created_at) FROM messages m WHERE m.conversation_id = c.id),"
        "  c.created_at) AS updated_at"
        " FROM conversations c WHERE (? IS NULL OR c.kind = ?)"
        " ORDER BY updated_at DESC, c.rowid DESC LIMIT ?",
        (kind, kind, limit),
    )
    return [{key: row[key] for key in row.keys()} for row in rows]  # noqa: SIM118 - sqlite3.Row
