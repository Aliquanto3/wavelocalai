"""Tables vec0 et port `VectorIndex` (AD-12, AD-16) : sqlite-vec réel et repli numpy, mêmes résultats."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wavelocalai.models.fake import fake_vector
from wavelocalai.rag.index import NumpyIndex, SqliteVecIndex, VectorIndex
from wavelocalai.store.db import Store, db_path
from wavelocalai.store.migrate import discover
from wavelocalai.store.vec import vec_table, vec_tables


@pytest.fixture
def store(tmp_path: Path):
    opened = Store.open(db_path(tmp_path / "data"))
    yield opened
    opened.close()


def _tables(store: Store) -> list[str]:
    rows = store.read("SELECT name FROM sqlite_master WHERE type = 'table'")
    return sorted(r["name"] for r in rows)


# --- store.ensure_vec_table ----------------------------------------------------------------------


def test_the_extension_is_loaded_by_the_writer(store):
    assert store.vec_available
    assert store.read("SELECT vec_version() AS v", vec=True)[0]["v"].startswith("v0.")


async def test_ensure_vec_table_creates_a_named_table_once(store):
    assert "chunks_vec_16" not in _tables(store)
    assert await store.ensure_vec_table(16) == "chunks_vec_16"
    assert await store.ensure_vec_table(16) == "chunks_vec_16"  # idempotent
    assert _tables(store).count("chunks_vec_16") == 1
    await store.ensure_vec_table(8)
    found = await store.awrite(lambda conn: vec_tables(conn))
    assert found == {8: "chunks_vec_8", 16: "chunks_vec_16"}  # sans les tables d'ombre de vec0


async def test_vec_tables_are_not_part_of_any_migration(store, tmp_path):
    """Seule exception écrite aux migrations (AD-12) : aucun `.sql` ne les crée."""
    creates = [
        m for m in discover() if "CREATE VIRTUAL TABLE" in m.path.read_text(encoding="utf-8")
    ]
    assert creates == []
    await store.ensure_vec_table(4)
    other = Store.open(db_path(tmp_path / "other"))
    try:
        assert "chunks_vec_4" not in _tables(other)
    finally:
        other.close()


@pytest.mark.parametrize("dim", [0, -3, 8193, True, 2.5])
def test_a_wrong_dimension_is_refused(dim):
    with pytest.raises(ValueError, match="Dimension"):
        vec_table(dim)


async def test_the_table_survives_a_reopen_and_ships_the_cosine_metric(tmp_path):
    path = db_path(tmp_path / "data")
    first = Store.open(path)
    await first.ensure_vec_table(3)
    await first.awrite(lambda c: SqliteVecIndex().add(c, [1, 2], [[1, 0, 0], [0, 1, 0]]))
    first.close()
    second = Store.open(path)
    try:
        found = second.read(
            "SELECT rowid, distance FROM chunks_vec_3 WHERE embedding MATCH ? AND k = 2",
            (b"\x00\x00\x80\x3f\x00\x00\x00\x00\x00\x00\x00\x00",),
            vec=True,
        )
        assert [(r["rowid"], round(r["distance"], 3)) for r in found] == [(1, 0.0), (2, 1.0)]
    finally:
        second.close()


# --- port VectorIndex : deux implémentations, mêmes réponses ---------------------------------------

TEXTS = {
    1: "le chat dort sur le canapé",
    2: "le chat mange des croquettes",
    3: "la voiture roule sur l'autoroute",
    4: "un train traverse la montagne",
}


@pytest.fixture(params=["sqlite-vec", "numpy"])
def index(request) -> VectorIndex:
    return SqliteVecIndex() if request.param == "sqlite-vec" else NumpyIndex()


def _fill(store: Store, index: VectorIndex, ids=tuple(TEXTS)):
    return store.write(
        lambda conn: index.add(conn, list(ids), [fake_vector(TEXTS[i]) for i in ids])
    ).result()


def _search(store, index, text, k=4):
    return index_search(store, index, fake_vector(text), k)


def index_search(store, index, vector, k):
    conn = sqlite3.connect(store.path)
    try:
        from wavelocalai.store.vec import load_vec

        load_vec(conn)
        return index.search(conn, vector, k)
    finally:
        conn.close()


def test_the_first_add_creates_the_table_of_its_dimension(store, index):
    _fill(store, index)
    if isinstance(index, SqliteVecIndex):
        assert "chunks_vec_16" in _tables(store)
    conn = sqlite3.connect(store.path)
    try:
        assert index.count(conn) == 4 if isinstance(index, NumpyIndex) else True
    finally:
        conn.close()


def test_search_returns_the_closest_chunks_first(store, index):
    _fill(store, index)
    found = _search(store, index, "le chat dort")
    assert [i for i, _ in found][:2] == [1, 2]  # les deux phrases sur le chat
    assert found == sorted(found, key=lambda item: item[1])
    assert _search(store, index, TEXTS[3], k=1)[0][0] == 3
    assert _search(store, index, TEXTS[3], k=1)[0][1] == pytest.approx(0.0, abs=1e-5)
    assert len(_search(store, index, "chat", k=2)) == 2


def test_both_implementations_agree(store, tmp_path):
    other = Store.open(db_path(tmp_path / "numpy"))
    try:
        sqlite_index, numpy_index = SqliteVecIndex(), NumpyIndex()
        _fill(store, sqlite_index)
        _fill(other, numpy_index)
        for query in ("chat", "voiture autoroute", "train montagne", "rien de commun"):
            a = _search(store, sqlite_index, query)
            b = _search(other, numpy_index, query)
            assert [d for _, d in a] == pytest.approx([d for _, d in b], abs=1e-4)
            # à distance égale l'ordre est libre : on compare les ex aequo en ensemble
            groups = lambda found: [  # noqa: E731
                {i for i, d2 in found if round(d2, 4) == round(d, 4)} for _, d in found
            ]
            assert groups(a) == groups(b)
    finally:
        other.close()


def test_remove_drops_the_vectors_of_those_chunks_only(store, index):
    _fill(store, index)
    store.write(lambda conn: index.remove(conn, [1, 3])).result()
    assert sorted(i for i, _ in _search(store, index, "chat voiture train", k=10)) == [2, 4]
    store.write(lambda conn: index.remove(conn, [99])).result()  # inconnu : sans effet


def test_vectors_of_other_dimensions_do_not_mix(store, index):
    _fill(store, index, ids=(1, 2))
    store.write(lambda conn: index.add(conn, [10], [[1.0, 0.0, 0.0]])).result()
    assert {i for i, _ in _search(store, index, "chat", k=10)} == {1, 2}
    assert index_search(store, index, [1.0, 0.0, 0.0], 10)[0][0] == 10
    assert index_search(store, index, [1.0, 0.0], 10) == []  # dimension sans table
    conn = sqlite3.connect(store.path)
    try:
        from wavelocalai.store.vec import load_vec

        load_vec(conn)
        assert index.count(conn) == 3 and index.count(conn, 16) == 2 and index.count(conn, 3) == 1
        assert index.count(conn, 5) == 0
    finally:
        conn.close()
    store.write(lambda conn: index.remove(conn, [10, 1])).result()  # toutes dimensions
    assert {i for i, _ in _search(store, index, "chat", k=10)} == {2}


def test_a_ragged_or_empty_batch_is_refused(store, index):
    with pytest.raises(ValueError):
        store.write(lambda conn: index.add(conn, [1, 2], [[1.0, 0.0], [1.0]])).result()
    with pytest.raises(ValueError):
        store.write(lambda conn: index.add(conn, [], [])).result()
    with pytest.raises(ValueError):
        store.write(lambda conn: index.add(conn, [1], [[1.0], [2.0]])).result()
