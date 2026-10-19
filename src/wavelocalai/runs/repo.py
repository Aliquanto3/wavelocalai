"""Écritures SQL du hub : fonctions qui prennent la connexion de l'écrivain unique (AD-12).

Elles s'exécutent toutes dans une transaction ouverte par `Store.write` ; seul le hub les appelle.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable
from typing import Any

from wavelocalai.errors import AppError
from wavelocalai.runs.models import AssistantMessage, Co2, LeafResult


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def insert_session(conn: sqlite3.Connection, session_id: str, started_at: str, reason: str) -> None:
    conn.execute(
        "INSERT INTO app_sessions (id, started_at, reason) VALUES (?, ?, ?)",
        (session_id, started_at, reason),
    )


def conversation_kind(conn: sqlite3.Connection, conversation_id: str) -> str | None:
    row = conn.execute("SELECT kind FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    return None if row is None else str(row[0])


def insert_conversation(conn: sqlite3.Connection, conv_id: str, kind: str, created_at: str) -> None:
    conn.execute(
        "INSERT INTO conversations (id, kind, created_at) VALUES (?, ?, ?)",
        (conv_id, kind, created_at),
    )


def insert_message(
    conn: sqlite3.Connection,
    conversation_id: str,
    run_id: str,
    role: str,
    created_at: str,
    message: AssistantMessage | str,
) -> None:
    if isinstance(message, str):
        message = AssistantMessage(content=message)
    conn.execute(
        "INSERT INTO messages (id, conversation_id, run_id, role, content, reasoning, tool_calls,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            uuid.uuid4().hex,
            conversation_id,
            run_id,
            role,
            message.content,
            message.reasoning,
            dumps(message.tool_calls) if message.tool_calls else None,
            created_at,
        ),
    )


def insert_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    kind: str,
    parent_run_id: str | None,
    app_session: str,
    conversation_id: str | None,
    model: str | None,
    started_at: str,
    params: dict[str, Any],
) -> None:
    conn.execute(
        "INSERT INTO runs (id, kind, parent_run_id, app_session, conversation_id, model, status,"
        " started_at, params) VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?)",
        (
            run_id,
            kind,
            parent_run_id,
            app_session,
            conversation_id,
            model,
            started_at,
            dumps(params),
        ),
    )


def erase_conversation(conn: sqlite3.Connection, conversation_id: str) -> None:
    """Efface une conversation (AD-13) : `messages` et `run_events` de ses runs sont supprimés, ses
    lignes `runs` restent sans texte avec `conversation_id` à `NULL` (registre carbone). Lève
    `not_found` si elle n'existe pas, `conversation_busy` si l'un de ses runs est actif : le
    contrôle se fait ici, dans la transaction de l'écrivain, donc après tout run en file.
    (Les `evaluations` des runs s'effaceront ici aussi quand leur table existera.)"""
    if conversation_kind(conn, conversation_id) is None:
        raise AppError("not_found", "Conversation introuvable.")
    active = conn.execute(
        "SELECT id FROM runs WHERE conversation_id = ? AND parent_run_id IS NULL"
        " AND status IN ('running', 'awaiting_approval') LIMIT 1",
        (conversation_id,),
    ).fetchone()
    if active is not None:
        raise AppError(
            "conversation_busy", "Un run de la conversation est actif.", run_id=active[0]
        )
    conn.execute(
        "DELETE FROM run_events WHERE run_id IN (SELECT id FROM runs WHERE conversation_id = ?)",
        (conversation_id,),
    )
    conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
    # `runs` gardés sans texte : l'enveloppe d'erreur garde son code, son message et son action
    # (textes fixes d'`errors.py`), mais pas `detail.technical`, texte d'exception ou de fournisseur
    # qui peut citer la question ou la réponse.
    conn.execute(
        "UPDATE runs SET conversation_id = NULL,"
        " error = CASE WHEN error IS NULL THEN NULL"
        " ELSE json_remove(error, '$.detail.technical') END"
        " WHERE conversation_id = ?",
        (conversation_id,),
    )
    conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


def erase_arena(conn: sqlite3.Connection, run_id: str) -> None:
    """Efface une Arène terminée (AD-13) : `run_events` et `messages` de la racine et de ses
    feuilles sont supprimés (la question, les réponses et les raisons du juge y vivent), les lignes
    `runs` restent sans texte comme registre carbone. Lève `run_not_found` si ce n'est pas une
    Arène, `arena_busy` si elle est active ; le contrôle se fait ici, dans la transaction de
    l'écrivain. Une Arène déjà effacée est effacée de nouveau sans erreur (idempotent)."""
    row = conn.execute(
        "SELECT status FROM runs WHERE id = ? AND kind = 'arena'", (run_id,)
    ).fetchone()
    if row is None:
        raise AppError("run_not_found", f"Arène {run_id} inconnue.", run_id=run_id)
    if row[0] in ("running", "awaiting_approval"):
        raise AppError("arena_busy", "L'Arène est active.", run_id=run_id)
    family = "SELECT id FROM runs WHERE id = ? OR parent_run_id = ?"
    conn.execute(
        f"DELETE FROM run_events WHERE run_id IN ({family})", (run_id, run_id)
    )  # noqa: S608
    conn.execute(f"DELETE FROM messages WHERE run_id IN ({family})", (run_id, run_id))  # noqa: S608
    # Enveloppe d'erreur gardée sans `detail.technical` (texte d'exception ou de fournisseur qui peut
    # citer la question ou la réponse), comme pour une conversation.
    conn.execute(
        "UPDATE runs SET error = CASE WHEN error IS NULL THEN NULL"
        " ELSE json_remove(error, '$.detail.technical') END"
        " WHERE id = ? OR parent_run_id = ?",
        (run_id, run_id),
    )


def insert_events(
    conn: sqlite3.Connection, run_id: str, events: Iterable[tuple[int, str, str, str]]
) -> None:
    """`events` : (seq, type, ts, data JSON déjà sérialisé et allégé du texte des sources)."""
    conn.executemany(
        "INSERT INTO run_events (run_id, seq, type, ts, data) VALUES (?, ?, ?, ?, ?)",
        [(run_id, seq, etype, ts, data) for seq, etype, ts, data in events],
    )


def finish_run_row(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    ended_at: str,
    error: dict[str, Any] | None,
    result: LeafResult | None = None,
    co2: Co2 | None = None,
) -> None:
    """Fixe le statut final ; les métriques et le `co2` ne s'écrivent que pour une feuille."""
    values: dict[str, Any] = {
        "status": status,
        "ended_at": ended_at,
        "error": None if error is None else dumps(error),
    }
    if result is not None:
        values.update(
            origin=result.origin,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            ttft_s=result.ttft_s,
            load_s=result.load_s,
            eval_s=result.eval_s,
            total_s=result.total_s,
            tps=result.tps,
            tps_source=result.tps_source,
            energy_wh=result.energy_wh,
        )
    if co2 is not None:
        values.update(_co2_columns(co2))
    assignments = ", ".join(f"{column} = ?" for column in values)
    conn.execute(
        f"UPDATE runs SET {assignments} WHERE id = ?", (*values.values(), run_id)
    )  # noqa: S608 - colonnes fixes


def _co2_columns(co2: Co2) -> dict[str, Any]:
    low = None if co2.range_mg is None else co2.range_mg["low"]
    high = None if co2.range_mg is None else co2.range_mg["high"]
    return {
        "co2_mg": co2.mg,
        "co2_method": co2.method,
        "co2_estimated": int(co2.estimated),
        "co2_range_low_mg": low,
        "co2_range_high_mg": high,
        "co2_allocation": co2.allocation,
        "co2_reason": co2.reason,
    }


def fill_cancelled_co2(conn: sqlite3.Connection, items: Iterable[tuple[str, Co2]]) -> None:
    """`co2` d'une feuille annulée qui n'en a pas (AD-10 : présent sur chaque feuille). Ne touche
    ni une feuille close avant l'annulation, ni un `co2` déjà écrit."""
    for run_id, co2 in items:
        values = _co2_columns(co2)
        assignments = ", ".join(f"{column} = ?" for column in values)
        conn.execute(
            f"UPDATE runs SET {assignments} WHERE id = ?"  # noqa: S608 - colonnes fixes
            " AND status = 'cancelled' AND co2_method IS NULL",
            (*values.values(), run_id),
        )


def amend_cancelled_co2(
    conn: sqlite3.Connection, run_id: str, co2: Co2, energy_wh: float | None
) -> bool:
    """Remplace le `co2` de remplacement (`unmeasurable`) d'une feuille annulée par la mesure faite
    jusqu'à l'annulation. Ne touche qu'une feuille `cancelled` dont le `co2` est sans valeur."""
    values = {**_co2_columns(co2), "energy_wh": energy_wh}
    assignments = ", ".join(f"{column} = ?" for column in values)
    cursor = conn.execute(
        f"UPDATE runs SET {assignments} WHERE id = ?"  # noqa: S608 - colonnes fixes
        " AND status = 'cancelled' AND co2_method = 'unmeasurable' AND co2_mg IS NULL",
        (*values.values(), run_id),
    )
    return cursor.rowcount > 0


def transition_status(conn: sqlite3.Connection, run_id: str, new: str, expected: str) -> bool:
    """Passe un run de `expected` à `new` (`running` <-> `awaiting_approval`) ; sans effet si son
    statut a déjà changé (clôture concurrente). Rend `True` si la ligne a bougé."""
    cursor = conn.execute(
        "UPDATE runs SET status = ? WHERE id = ? AND status = ?", (new, run_id, expected)
    )
    return cursor.rowcount > 0


def cancel_rows(conn: sqlite3.Connection, run_ids: Iterable[str], ended_at: str) -> None:
    conn.executemany(
        "UPDATE runs SET status = 'cancelled', ended_at = ? WHERE id = ?"
        " AND status IN ('running', 'awaiting_approval')",
        [(ended_at, run_id) for run_id in run_ids],
    )


def interrupt_orphans(conn: sqlite3.Connection, now: str) -> list[str]:
    """Runs restés `running` ou `awaiting_approval` : `interrupted`, plus un `run_ended` synthétique
    pour chaque racine (`seq` à la suite du dernier écrit), et le message assistant partiel déjà
    reçu. Rend les identifiants touchés."""
    rows = conn.execute(
        "SELECT id, parent_run_id, conversation_id FROM runs"
        " WHERE status IN ('running', 'awaiting_approval')"
    ).fetchall()
    for run_id, parent_id, conversation_id in rows:
        conn.execute(
            "UPDATE runs SET status = 'interrupted', ended_at = ? WHERE id = ?", (now, run_id)
        )
        if parent_id is not None:
            continue
        last = conn.execute(
            "SELECT max(seq) FROM run_events WHERE run_id = ?", (run_id,)
        ).fetchone()
        ended = {"status": "interrupted", "error": None}
        insert_events(conn, run_id, [((last[0] or 0) + 1, "run_ended", now, dumps(ended))])
        if conversation_id is not None:
            partial = _partial_message(conn, run_id)
            if not partial.is_empty():
                insert_message(conn, conversation_id, run_id, "assistant", now, partial)
    return [row[0] for row in rows]


def _partial_message(conn: sqlite3.Connection, run_id: str) -> AssistantMessage:
    answer: list[str] = []
    thought: list[str] = []
    for (raw,) in conn.execute(
        "SELECT data FROM run_events WHERE run_id = ? AND type = 'token' ORDER BY seq", (run_id,)
    ):
        data = json.loads(raw)
        (thought if data.get("channel") == "thought" else answer).append(data.get("text") or "")
    return AssistantMessage(content="".join(answer), reasoning="".join(thought) or None)
