"""Contraintes de `0004_documents.sql` (documents et extraits, AD-12, AD-16)."""

from __future__ import annotations

import sqlite3

import pytest

from wavelocalai.store.migrate import migrate

NOW = "2026-10-18T12:00:00.000Z"
ERROR = '{"code": "ingest_failed"}'


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "wavelocalai.db"
    migrate(db)
    connection = sqlite3.connect(db)
    connection.execute("PRAGMA foreign_keys=ON")
    yield connection
    connection.close()


def _doc(conn, doc_id="d1", fingerprint="f1", status="indexing", **columns):
    values = {
        "id": doc_id,
        "source": "a.pdf",
        "fingerprint": fingerprint,
        "size_bytes": 10,
        "embedding_model": "nomic-embed-text:latest",
        "status": status,
        "created_at": NOW,
        **columns,
    }
    names = ", ".join(values)
    marks = ", ".join("?" * len(values))
    conn.execute(f"INSERT INTO documents ({names}) VALUES ({marks})", list(values.values()))


def test_the_columns_of_a_document(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    assert {"source", "fingerprint", "embedding_model", "status"} <= columns
    chunk_columns = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}
    assert {"id", "document_id", "position", "page", "text"} <= chunk_columns


def test_status_is_a_closed_list(conn):
    for status in ("indexing",):
        _doc(conn, f"ok-{status}", f"f-{status}", status)
    with pytest.raises(sqlite3.IntegrityError):
        _doc(conn, "x", "fx", "queued")


def test_a_failed_document_needs_its_error_and_a_ready_one_its_dimension(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _doc(conn, "f", "ff", "failed")
    _doc(conn, "f", "ff", "failed", error=ERROR)
    with pytest.raises(sqlite3.IntegrityError):
        _doc(conn, "r", "fr", "ready")
    _doc(conn, "r", "fr", "ready", embedding_dim=768, ready_at=NOW)
    with pytest.raises(sqlite3.IntegrityError):
        _doc(conn, "e", "fe", "failed", error="pas du json")


def test_the_same_content_is_not_present_twice_unless_the_first_failed(conn):
    _doc(conn, "a", "same", "indexing")
    with pytest.raises(sqlite3.IntegrityError):
        _doc(conn, "b", "same", "indexing")
    conn.execute("UPDATE documents SET status = 'failed', error = ? WHERE id = 'a'", (ERROR,))
    _doc(conn, "b", "same", "indexing")  # l'échec ne bloque pas un nouvel essai
    _doc(conn, "c", "same", "failed", error=ERROR)  # ni plusieurs échecs


def test_chunks_follow_their_document_and_keep_a_unique_position(conn):
    _doc(conn)
    conn.execute("INSERT INTO chunks (document_id, position, page, text) VALUES ('d1', 0, 1, 'a')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO chunks (document_id, position, text) VALUES ('d1', 0, 'b')")
    with pytest.raises(sqlite3.IntegrityError):  # page 0 n'existe pas
        conn.execute(
            "INSERT INTO chunks (document_id, position, page, text) VALUES ('d1', 1, 0, 'b')"
        )
    with pytest.raises(sqlite3.IntegrityError):  # document inconnu
        conn.execute("INSERT INTO chunks (document_id, position, text) VALUES ('nope', 0, 'b')")
    conn.execute("DELETE FROM documents WHERE id = 'd1'")
    assert conn.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0


def test_a_chunk_id_is_never_reused(conn):
    """Un vecteur oublié ne doit jamais désigner un autre extrait : AUTOINCREMENT."""
    _doc(conn)
    first = conn.execute(
        "INSERT INTO chunks (document_id, position, text) VALUES ('d1', 0, 'a')"
    ).lastrowid
    conn.execute("DELETE FROM chunks WHERE id = ?", (first,))
    second = conn.execute(
        "INSERT INTO chunks (document_id, position, text) VALUES ('d1', 0, 'b')"
    ).lastrowid
    assert second > first
