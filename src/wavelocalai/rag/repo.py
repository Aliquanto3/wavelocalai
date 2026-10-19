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


# Question (story 4.4). Base interrogeable : un document `ready` au moins ; son modèle d'embedding
# (une base = un modèle, AD-16 ; le plus récent si plusieurs, ce qui ne devrait pas arriver).
READY_BASE_SQL = (
    "SELECT embedding_model, count(*) AS documents, sum(chunk_count) AS chunks FROM documents"
    " WHERE status = 'ready' GROUP BY embedding_model ORDER BY max(ready_at) DESC LIMIT 1"
)
CHUNK_SQL = (
    "SELECT c.id, c.document_id, d.source, c.page, c.position, c.text FROM chunks c"
    " JOIN documents d ON d.id = c.document_id WHERE c.id = ? AND d.status = 'ready'"
)  # un extrait n'est lisible que si son document est `ready` (AD-16)
READY_CHUNK_IDS_SQL = (
    "SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.status = 'ready'"
)


def search_chunks(
    conn: sqlite3.Connection, index: VectorIndex, vector: Sequence[float], top_k: int
) -> list[dict[str, Any]]:
    """Les `top_k` extraits de documents `ready` les plus proches de `vector`, du plus proche, avec
    leur distance cosinus. Les extraits d'un document encore `indexing` sont déjà dans l'index :
    la recherche les écarte **avant** de prendre les plus proches (AD-16, jamais de document à
    moitié indexé), quel que soit leur nombre."""
    hits = index.search(conn, vector, top_k, among=READY_CHUNK_IDS_SQL)
    if not hits:
        return []
    marks = ",".join("?" * len(hits))
    rows = {
        int(row["id"]): row
        for row in conn.execute(
            "SELECT c.id, c.document_id, d.source, c.page, c.text FROM chunks c"
            " JOIN documents d ON d.id = c.document_id"
            f" WHERE d.status = 'ready' AND c.id IN ({marks})",
            [chunk_id for chunk_id, _ in hits],
        )
    }
    found: list[dict[str, Any]] = []
    for chunk_id, distance in hits:
        row = rows.get(chunk_id)
        if row is None:  # extrait d'un document non prêt, ou supprimé depuis l'index
            continue
        found.append(
            {
                "chunk_id": chunk_id,
                "doc_id": row["document_id"],
                "document": row["source"],
                "page": row["page"],
                "text": row["text"],
                "distance": distance,
            }
        )
        if len(found) == top_k:
            break
    return found
