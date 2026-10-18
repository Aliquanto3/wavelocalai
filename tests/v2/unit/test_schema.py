"""Schéma du hub : instantané versionné des migrations et contraintes de `0001_hub.sql` (AD-12).

Pour chaque `snapshots/schema_vN.sql`, on applique les migrations jusqu'à N sur une base vide et on
compare le schéma à l'instantané : une migration fusionnée ne change jamais, et une nouvelle
migration arrive avec son instantané. Pour en écrire un : `python -m tests.v2.unit.test_schema N`.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from wavelocalai.runs.models import (
    CO2_ALLOCATIONS,
    CO2_METHODS,
    CONVERSATION_KINDS,
    LEAF_KINDS,
    ORIGINS,
    ROOT_KINDS,
    RUN_KINDS,
    STATUSES,
    TPS_SOURCES,
)
from wavelocalai.store.migrate import discover, migrate

SNAPSHOTS = Path(__file__).parent / "snapshots"
NOW = "2026-10-18T12:00:00.000Z"


def dump_schema(path: Path) -> str:
    """Schéma lisible et stable : version, puis chaque objet par type et nom."""
    conn = sqlite3.connect(path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        rows = conn.execute(
            "SELECT type, name, sql FROM sqlite_master"
            " WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type, name"
        ).fetchall()
    finally:
        conn.close()
    body = "\n\n".join(f"{sql.strip()};" for _, _, sql in rows).replace("\r\n", "\n")
    return f"-- user_version: {version}\n\n{body}\n"


def _snapshot(version: int) -> Path:
    return SNAPSHOTS / f"schema_v{version}.sql"


def test_every_migration_has_its_snapshot():
    versions = [m.version for m in discover()]
    on_disk = sorted(int(p.stem.removeprefix("schema_v")) for p in SNAPSHOTS.glob("schema_v*.sql"))
    assert on_disk == versions


@pytest.mark.parametrize("version", [m.version for m in discover()])
def test_schema_matches_the_versioned_snapshot(tmp_path, version):
    db = tmp_path / "wavelocalai.db"
    assert migrate(db, target=version) == version
    expected = _snapshot(version).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert dump_schema(db) == expected


# --- contraintes de 0001_hub.sql ---------------------------------------------------------------


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "wavelocalai.db"
    migrate(db)
    connection = sqlite3.connect(db)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("INSERT INTO app_sessions VALUES ('s', ?, 'startup')", (NOW,))
    yield connection
    connection.close()


def _run(conn, run_id="r1", kind="chat", status="running", **columns):
    values = {"id": run_id, "kind": kind, "app_session": "s", "status": status, "started_at": NOW}
    values.update(columns)
    names = ", ".join(values)
    conn.execute(
        f"INSERT INTO runs ({names}) VALUES ({', '.join('?' * len(values))})",  # noqa: S608
        tuple(values.values()),
    )


def test_code_vocabulary_equals_the_schema_vocabulary(conn):
    """Chaque valeur du code est admise, une valeur inconnue est refusée (listes closes d'AD-5)."""
    assert set(RUN_KINDS) == set(ROOT_KINDS) | set(LEAF_KINDS)
    assert set(STATUSES) == {
        "running", "awaiting_approval", "ok", "error", "cancelled", "interrupted"
    }  # fmt: skip
    assert set(RUN_KINDS) == {
        "chat", "arena", "rag", "agent", "ingest", "pull", "eval", "bench",
        "generation", "judge", "embedding",
    }  # fmt: skip
    for index, kind in enumerate(RUN_KINDS):
        _run(conn, f"k{index}", kind=kind)
    for index, status in enumerate(STATUSES):
        _run(conn, f"s{index}", status=status)
    for index, origin in enumerate(ORIGINS):
        _run(conn, f"o{index}", origin=origin)
    for index, source in enumerate(TPS_SOURCES):
        _run(conn, f"t{index}", tps_source=source)
    for index, method in enumerate(CO2_METHODS):
        _run(conn, f"m{index}", co2_method=method, co2_estimated=0, co2_reason="raison")
    for index, allocation in enumerate(CO2_ALLOCATIONS):
        _run(conn, f"a{index}", co2_allocation=allocation)
    for index, kind in enumerate(CONVERSATION_KINDS):
        conn.execute("INSERT INTO conversations VALUES (?, ?, NULL, ?)", (f"c{index}", kind, NOW))
    for column, bad in [
        ("kind", "inconnu"), ("status", "done"), ("origin", "mars"), ("tps_source", "x"),
        ("co2_method", "local"), ("co2_allocation", "partage"),
    ]:  # fmt: skip
        with pytest.raises(sqlite3.IntegrityError):
            _run(conn, "bad", **{column: bad})
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO conversations VALUES ('c9', 'arena', NULL, ?)", (NOW,))


def test_co2_needs_a_reason_when_the_value_is_unknown(conn):
    _run(conn, "ok", co2_mg=1.2, co2_method="codecarbon", co2_estimated=0)
    with pytest.raises(sqlite3.IntegrityError):
        _run(conn, "nu", co2_method="unmeasurable", co2_estimated=1)  # mg nul sans raison


def test_run_requires_an_existing_session_and_parent(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _run(conn, "x", app_session="inconnue")
    with pytest.raises(sqlite3.IntegrityError):
        _run(conn, "x", kind="generation", parent_run_id="absent")


def test_params_and_events_must_be_json(conn):
    with pytest.raises(sqlite3.IntegrityError):
        _run(conn, "x", params="pas du json")
    _run(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO run_events VALUES ('r1', 0, 'x', ?, '{}')", (NOW,))  # seq >= 1
    conn.execute("INSERT INTO run_events VALUES ('r1', 1, 'run_started', ?, '{}')", (NOW,))
    with pytest.raises(sqlite3.IntegrityError):  # (run_id, seq) unique
        conn.execute("INSERT INTO run_events VALUES ('r1', 1, 'run_started', ?, '{}')", (NOW,))


def test_erasing_a_conversation_keeps_the_runs_without_text(conn):
    """Prépare AD-13 : messages supprimés, `runs` gardés avec `conversation_id` à NULL."""
    conn.execute("INSERT INTO conversations VALUES ('c', 'chat', NULL, ?)", (NOW,))
    _run(conn, "r1", conversation_id="c")
    conn.execute(
        "INSERT INTO messages VALUES ('m', 'c', 'r1', 'user', 'texte', NULL, NULL, ?)", (NOW,)
    )
    conn.execute("DELETE FROM conversations WHERE id = 'c'")
    assert conn.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
    assert conn.execute("SELECT conversation_id FROM runs").fetchall() == [(None,)]


if __name__ == "__main__":  # écrit l'instantané de la version donnée
    import tempfile

    target = int(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        database = Path(tmp) / "wavelocalai.db"
        migrate(database, target=target)
        _snapshot(target).write_text(dump_schema(database), encoding="utf-8", newline="\n")
    print(f"instantané écrit : {_snapshot(target)}")
