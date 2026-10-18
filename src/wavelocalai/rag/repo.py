"""Requêtes SQL des tables `documents` et `chunks` (migration 0004).

Chaque fonction prend la connexion de l'écrivain et tourne dans sa transaction (`Store.write`) :
l'écriture d'un document, de ses extraits et de ses vecteurs reste cohérente (AD-12, AD-13).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from typing import Any

from wavelocalai.rag.index import VectorIndex
from wavelocalai.rag.split import ChunkDraft


def insert_document(
    conn: sqlite3.Connection,
    *,
    doc_id: str,
    source: str,
    fingerprint: str,
    size_bytes: int,
    embedding_model: str,
    run_id: str,
    now: str,
) -> None:
    """Nouveau document `indexing`. Un essai raté du même contenu (`failed`) est remplacé.
    `sqlite3.IntegrityError` si le contenu est déjà présent (course entre deux imports)."""
    conn.execute(
        "DELETE FROM documents WHERE fingerprint = ? AND status = 'failed'", (fingerprint,)
    )
    conn.execute(
        "INSERT INTO documents (id, source, fingerprint, size_bytes, embedding_model, status,"
        " run_id, created_at) VALUES (?, ?, ?, ?, ?, 'indexing', ?, ?)",
        (doc_id, source, fingerprint, size_bytes, embedding_model, run_id, now),
    )


def insert_chunks(conn: sqlite3.Connection, doc_id: str, drafts: Sequence[ChunkDraft]) -> list[int]:
    """Extraits du document, dans l'ordre ; rend leurs identifiants (= `rowid` des vecteurs)."""
    conn.executemany(
        "INSERT INTO chunks (document_id, position, page, text) VALUES (?, ?, ?, ?)",
        [(doc_id, d.position, d.page, d.text) for d in drafts],
    )
    rows = conn.execute(
        "SELECT id FROM chunks WHERE document_id = ? ORDER BY position", (doc_id,)
    ).fetchall()
    return [int(row[0]) for row in rows]


def delete_chunks(conn: sqlite3.Connection, index: VectorIndex, doc_id: str) -> int:
    """Retire les vecteurs puis les extraits du document (même transaction) ; rend leur nombre."""
    ids = [
        int(row[0])
        for row in conn.execute("SELECT id FROM chunks WHERE document_id = ?", (doc_id,))
    ]
    if ids:
        index.remove(conn, ids)
        conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
    return len(ids)


def delete_document(conn: sqlite3.Connection, index: VectorIndex, doc_id: str) -> None:
    """Retire le document, ses extraits et leurs vecteurs (annulation d'un import)."""
    delete_chunks(conn, index, doc_id)
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


def mark_ready(
    conn: sqlite3.Connection,
    doc_id: str,
    *,
    dim: int,
    chunk_count: int,
    page_count: int | None,
    now: str,
) -> None:
    conn.execute(
        "UPDATE documents SET status = 'ready', embedding_dim = ?, chunk_count = ?,"
        " page_count = ?, ready_at = ?, error = NULL WHERE id = ?",
        (dim, chunk_count, page_count, now, doc_id),
    )


def mark_failed(
    conn: sqlite3.Connection, index: VectorIndex, doc_id: str, error: dict[str, Any]
) -> None:
    """`failed` avec l'enveloppe d'erreur ; les extraits partiels et leurs vecteurs sont retirés
    (un document qui n'est pas `ready` n'est jamais interrogeable, et ne garde pas de texte)."""
    delete_chunks(conn, index, doc_id)
    conn.execute(
        "UPDATE documents SET status = 'failed', chunk_count = 0, embedding_dim = NULL,"
        " ready_at = NULL, error = ? WHERE id = ?",
        (json.dumps(error, ensure_ascii=False), doc_id),
    )


# Lectures (`Store.aread`).
PRESENT_SQL = (
    "SELECT id, source, status, chunk_count FROM documents"
    " WHERE fingerprint = ? AND status <> 'failed'"
)  # même contenu déjà présent, en cours ou terminé
BASE_MODEL_SQL = (
    "SELECT embedding_model, embedding_dim FROM documents"
    " WHERE status IN ('indexing', 'ready') ORDER BY created_at DESC LIMIT 1"
)  # modèle de la base (AD-16) ; la dimension n'est connue que d'un document `ready`
BASE_DIM_SQL = (
    "SELECT embedding_dim FROM documents WHERE status = 'ready' AND embedding_dim IS NOT NULL"
    " LIMIT 1"
)
INTERRUPTED_SQL = "SELECT id, source FROM documents WHERE status = 'indexing'"
LIST_SQL = (
    "SELECT id, source, status, chunk_count, page_count, size_bytes, embedding_model, created_at,"
    " ready_at, run_id, error FROM documents ORDER BY created_at DESC, id"
)  # tous les statuts : l'écran présente `indexing` et `failed` comme tels
TOTALS_SQL = (
    "SELECT COUNT(*) AS documents, COALESCE(SUM(chunk_count), 0) AS chunks FROM documents"
    " WHERE status = 'ready'"
)  # ce que la base peut interroger (story 4.4) : les documents `ready` seulement
