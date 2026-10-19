"""Recherche d'une question (story 4.4) : seuls les extraits de documents `ready` comptent, filtrés
avant la sélection des plus proches, quel que soit le nombre d'extraits en cours d'indexation."""

from __future__ import annotations

from pathlib import Path

import pytest

from wavelocalai.rag.index import NumpyIndex, SqliteVecIndex, VectorIndex
from wavelocalai.rag.repo import search_chunks
from wavelocalai.store.db import Store, db_path

from ..conftest import needs_vec

DIM = 8
PENDING = 4200  # au-delà du plafond KNN de sqlite-vec (4096)


@pytest.fixture
def store(tmp_path: Path):
    opened = Store.open(db_path(tmp_path / "data"))
    yield opened
    opened.close()


@pytest.fixture(params=[pytest.param("sqlite-vec", marks=needs_vec), "numpy"])
def index(request) -> VectorIndex:
    return SqliteVecIndex() if request.param == "sqlite-vec" else NumpyIndex()


def _axis(i: int, wobble: float = 0.0) -> list[float]:
    vector = [0.0] * DIM
    vector[i] = 1.0
    vector[(i + 1) % DIM] = wobble
    return vector


def _fill(store: Store, index: VectorIndex) -> None:
    """Un document `ready` de deux extraits loin de la question, un document `indexing` de
    `PENDING` extraits tout près d'elle (déjà dans l'index, comme pendant un import)."""

    def write(conn):
        now = "2026-10-19T00:00:00Z"
        conn.execute(
            "INSERT INTO documents (id, source, fingerprint, size_bytes, embedding_model,"
            " embedding_dim, status, chunk_count, created_at, ready_at)"
            " VALUES ('ready', 'pret.txt', 'a', 1, 'm', ?, 'ready', 2, ?, ?)",
            (DIM, now, now),
        )
        conn.execute(
            "INSERT INTO documents (id, source, fingerprint, size_bytes, embedding_model,"
            " embedding_dim, status, created_at) VALUES ('busy', 'gros.txt', 'b', 1, 'm', ?,"
            " 'indexing', ?)",
            (DIM, now),
        )
        conn.executemany(
            "INSERT INTO chunks (id, document_id, position, text) VALUES (?, 'ready', ?, ?)",
            [(1, 0, "le moins loin des prêts"), (2, 1, "le plus loin")],
        )
        busy = list(range(10, 10 + PENDING))
        conn.executemany(
            "INSERT INTO chunks (id, document_id, position, text) VALUES (?, 'busy', ?, 'x')",
            [(chunk_id, n) for n, chunk_id in enumerate(busy)],
        )
        index.add(conn, [1, 2], [_axis(1, 0.5), _axis(2)])
        index.add(conn, busy, [_axis(0, 0.001 * (n % 50)) for n in range(PENDING)])

    store.write(write).result()


def test_ready_chunks_are_found_behind_thousands_of_closer_chunks_still_indexing(store, index):
    _fill(store, index)
    question = _axis(0, 0.9)  # tout près du document en cours, assez près du premier prêt
    found = store.read_with(
        lambda conn: search_chunks(conn, index, question, 2),
        vec=isinstance(index, SqliteVecIndex),
    )
    assert [item["chunk_id"] for item in found] == [1, 2]
    assert {item["doc_id"] for item in found} == {"ready"}
    assert found[0]["distance"] < found[1]["distance"]
