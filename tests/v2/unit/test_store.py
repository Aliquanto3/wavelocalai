"""Store SQLite : pragmas, écrivain unique sur un fil, lectures courtes, migrations (AD-12)."""

from __future__ import annotations

import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from wavelocalai.store.db import DB_NAME, Store, db_path, utc_now_iso
from wavelocalai.store.migrate import (
    MIGRATIONS_DIR,
    DatabaseTooNewError,
    MigrationError,
    backup_path,
    discover,
    migrate,
    statements,
)

HUB_TABLES = {"app_sessions", "conversations", "messages", "run_events", "runs"}


@pytest.fixture
def store(tmp_path: Path):
    opened = Store.open(db_path(tmp_path / "data"))
    yield opened
    opened.close()


def _tables(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        return {name for (name,) in rows}
    finally:
        conn.close()


def _migrations_dir(tmp_path: Path, **extra: str) -> Path:
    """Copie de `0001_hub.sql` plus des migrations de test (`{"0002_x.sql": "…"}`)."""
    directory = tmp_path / "migrations"
    directory.mkdir()
    shutil.copy(MIGRATIONS_DIR / "0001_hub.sql", directory)
    for name, sql in extra.items():
        (directory / name).write_text(sql, encoding="utf-8")
    return directory


def test_absent_database_is_created_with_the_hub_schema(tmp_path):
    path = db_path(tmp_path / "data")
    assert not path.exists()
    store = Store.open(path)
    try:
        assert path.name == DB_NAME == "wavelocalai.db"
        assert _tables(path) >= HUB_TABLES
        assert store.read("PRAGMA user_version")[0][0] == len(discover())
        assert not list(path.parent.glob("*.bak-*"))  # rien à sauvegarder sur une base neuve
    finally:
        store.close()


def test_pragmas_wal_foreign_keys_secure_delete(store):
    assert store.read("PRAGMA journal_mode")[0][0] == "wal"
    writer = store.write(
        lambda conn: [
            conn.execute(f"PRAGMA {name}").fetchone()[0]
            for name in ("foreign_keys", "secure_delete", "journal_mode")
        ]
    ).result()
    assert writer == [1, 1, "wal"]
    assert store.read("PRAGMA foreign_keys")[0][0] == 1
    assert store.read("PRAGMA secure_delete")[0][0] == 1


def test_all_writes_run_on_one_dedicated_thread(store):
    store.write(lambda conn: conn.execute("CREATE TABLE t (n INTEGER, thread INTEGER)")).result()

    def insert(n: int):
        return store.write(
            lambda conn: conn.execute("INSERT INTO t VALUES (?, ?)", (n, threading.get_ident()))
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = list(pool.map(insert, range(200)))
    for future in futures:
        future.result()
    rows = store.read("SELECT count(*) AS n, count(DISTINCT thread) AS threads FROM t")[0]
    assert (rows["n"], rows["threads"]) == (200, 1)
    assert store.read("SELECT thread FROM t LIMIT 1")[0][0] != threading.get_ident()


def test_a_failing_write_rolls_back_and_the_writer_survives(store):
    def broken(conn):
        conn.execute("INSERT INTO app_sessions VALUES ('s1', ?, 'startup')", (utc_now_iso(),))
        raise RuntimeError("boum")

    with pytest.raises(RuntimeError, match="boum"):
        store.write(broken).result()
    assert store.read("SELECT count(*) FROM app_sessions")[0][0] == 0
    store.write(
        lambda conn: conn.execute(
            "INSERT INTO app_sessions VALUES ('s2', ?, 'startup')", (utc_now_iso(),)
        )
    ).result()
    assert store.read("SELECT id FROM app_sessions")[0][0] == "s2"


async def test_awrite_and_aread(store):
    await store.awrite(
        lambda conn: conn.execute(
            "INSERT INTO app_sessions VALUES ('s1', ?, 'reset')", (utc_now_iso(),)
        )
    )
    rows = await store.aread("SELECT reason FROM app_sessions")
    assert [r["reason"] for r in rows] == ["reset"]


def test_reads_are_short_and_read_only(store):
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        store.read("INSERT INTO app_sessions VALUES ('x', 'now', 'startup')")


def test_write_after_close_is_refused(tmp_path):
    store = Store.open(db_path(tmp_path))
    store.close()
    store.close()  # idempotent
    with pytest.raises(RuntimeError, match="fermé"):
        store.write(lambda conn: None)


def test_utc_now_iso_is_iso8601_with_z():
    assert utc_now_iso().endswith("Z") and len(utc_now_iso()) == len("2026-10-18T12:00:00.000Z")


# --- migrations -------------------------------------------------------------------------------


def test_existing_database_is_backed_up_then_migrated(tmp_path):
    path = tmp_path / "wavelocalai.db"
    directory = _migrations_dir(tmp_path)
    assert migrate(path, directory) == 1
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO app_sessions VALUES ('s1', 'now', 'startup')")
    conn.commit()
    conn.close()

    (directory / "0002_extra.sql").write_text("CREATE TABLE extra (n INTEGER);\n", encoding="utf-8")
    assert migrate(path, directory) == 2

    bak = backup_path(path, 1)
    assert bak.name == "wavelocalai.db.bak-1"
    saved = sqlite3.connect(bak)
    try:
        assert saved.execute("PRAGMA user_version").fetchone()[0] == 1
        assert saved.execute("SELECT id FROM app_sessions").fetchall() == [("s1",)]
        assert "extra" not in _tables(bak)
    finally:
        saved.close()
    assert "extra" in _tables(path)
    assert migrate(path, directory) == 2  # idempotent
    assert not backup_path(path, 2).exists()


def test_failing_migration_is_rolled_back(tmp_path):
    path = tmp_path / "wavelocalai.db"
    directory = _migrations_dir(tmp_path)
    migrate(path, directory)
    (directory / "0002_bad.sql").write_text(
        "CREATE TABLE good (n INTEGER);\nINSERT INTO absent VALUES (1);\n", encoding="utf-8"
    )
    with pytest.raises(MigrationError, match="0002_bad.sql") as info:
        migrate(path, directory)
    assert "wavelocalai.db.bak-1" in str(info.value)
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        conn.close()
    assert "good" not in _tables(path)


def test_newer_database_refuses_to_start(tmp_path):
    path = db_path(tmp_path / "data")
    migrate(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    with pytest.raises(DatabaseTooNewError, match="version 99"):
        Store.open(path)
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 99  # intacte
    finally:
        conn.close()
    assert not list(path.parent.glob("*.bak-*"))


def test_discover_requires_contiguous_numbered_files(tmp_path):
    (tmp_path / "0002_x.sql").write_text("", encoding="utf-8")
    with pytest.raises(MigrationError, match="sans trou"):
        discover(tmp_path)
    (tmp_path / "x.sql").write_text("", encoding="utf-8")
    with pytest.raises(MigrationError, match="invalide"):
        discover(tmp_path)


def test_real_migrations_are_numbered_from_0001():
    assert [m.path.name for m in discover()][0] == "0001_hub.sql"


def test_statement_splitter_keeps_triggers_and_comments_whole():
    script = (
        "-- commentaire ; avec point-virgule\nCREATE TABLE a (n INTEGER);\n"
        "CREATE TRIGGER t AFTER INSERT ON a BEGIN\n  UPDATE a SET n = 1;\nEND;\n-- fin\n"
    )
    parts = list(statements(script))
    assert len(parts) == 3 and parts[1].startswith("CREATE TRIGGER") and parts[1].endswith("END;")


def test_purge_is_checkpoint_vacuum_checkpoint_and_follows_the_commit_in_the_writer_queue(store):
    # AD-13 : après la transaction de `DELETE`, `wal_checkpoint(TRUNCATE)`, `VACUUM`, puis de
    # nouveau `wal_checkpoint(TRUNCATE)`, dans la même tâche de l'écrivain.
    from wavelocalai.store.db import purge_free_space

    assert store.write(lambda conn: conn.in_transaction, purge=True).result() is True
    assert store.write(lambda conn: conn.in_transaction).result() is True  # transaction ouverte
    assert store.read("PRAGMA journal_mode")[0][0] == "wal"

    statements_run: list[str] = []

    class Recorder:
        def execute(self, sql):
            statements_run.append(sql)
            return self

        def fetchall(self):
            return []

    purge_free_space(Recorder())  # type: ignore[arg-type]
    assert statements_run == [
        "PRAGMA wal_checkpoint(TRUNCATE)",
        "VACUUM",
        "PRAGMA wal_checkpoint(TRUNCATE)",
    ]


def test_a_failing_purge_job_still_rolls_back_the_transaction(store):
    def failing(conn):
        conn.execute("INSERT INTO app_sessions VALUES ('s', 'x', 'startup')")
        raise ValueError("échec")

    with pytest.raises(ValueError):
        store.write(failing, purge=True).result()
    assert store.read("SELECT count(*) AS n FROM app_sessions")[0]["n"] == 0


def test_a_purge_blocked_by_a_reader_is_reported_then_replayed(store):
    # AD-13 : un lecteur qui tient le journal empêche `wal_checkpoint(TRUNCATE)` (`busy`) ; le
    # texte resterait dans le `-wal`. L'effacement est validé, la purge reste due et se rejoue.
    store.write(lambda conn: conn.execute("PRAGMA busy_timeout=50"))
    store.write(
        lambda conn: conn.execute(
            "INSERT INTO app_sessions VALUES ('s', 'Aiguille-Unique-5521', 'startup')"
        )
    ).result()
    wal = Path(f"{store.path}-wal")
    reader = sqlite3.connect(store.path, isolation_level=None)
    try:
        reader.execute("BEGIN")
        reader.execute("SELECT count(*) FROM app_sessions").fetchall()
        store.write(lambda conn: conn.execute("DELETE FROM app_sessions"), purge=True).result()
        assert store.purge_pending is True
        assert b"Aiguille-Unique-5521" in wal.read_bytes()
    finally:
        reader.close()
    store.write(lambda conn: None).result()  # écriture suivante : la purge est rejouée
    assert store.purge_pending is False
    assert wal.stat().st_size == 0
    assert b"Aiguille-Unique-5521" not in Path(store.path).read_bytes()


def test_a_failing_purge_does_not_undo_or_fail_the_committed_erase(store, monkeypatch):
    import wavelocalai.store.db as db

    def broken(conn):
        raise sqlite3.OperationalError("disque plein")

    store.write(
        lambda conn: conn.execute("INSERT INTO app_sessions VALUES ('s', 'x', 'startup')")
    ).result()
    monkeypatch.setattr(db, "purge_free_space", broken)
    assert (
        store.write(
            lambda conn: conn.execute("DELETE FROM app_sessions").rowcount, purge=True
        ).result()
        == 1
    )
    assert store.read("SELECT count(*) AS n FROM app_sessions")[0]["n"] == 0
    assert store.purge_pending is True
    monkeypatch.undo()
    store.write(lambda conn: None).result()
    assert store.purge_pending is False


# --- copies d'avant migration : une seule, supprimée à l'effacement (AD-13) --------------------


def _copies(path: Path) -> list[str]:
    return sorted(p.name for p in path.parent.glob("*.bak-*"))


def test_only_the_last_copy_is_kept_and_the_previous_one_goes_after_the_next_migration(tmp_path):
    path = tmp_path / "wavelocalai.db"
    directory = _migrations_dir(tmp_path)
    migrate(path, directory)
    assert _copies(path) == []  # base neuve : rien à copier
    (directory / "0002_a.sql").write_text("CREATE TABLE a (n INTEGER);\n", encoding="utf-8")
    migrate(path, directory)
    assert _copies(path) == ["wavelocalai.db.bak-1"]
    (directory / "0003_b.sql").write_text("CREATE TABLE b (n INTEGER);\n", encoding="utf-8")
    migrate(path, directory)
    assert _copies(path) == ["wavelocalai.db.bak-2"]  # celle de la migration 3 : une seule
    migrate(path, directory)  # rien à migrer : la copie reste, rien n'est supprimé
    assert _copies(path) == ["wavelocalai.db.bak-2"]


def test_a_failed_migration_keeps_its_own_copy_for_the_recovery(tmp_path):
    path = tmp_path / "wavelocalai.db"
    directory = _migrations_dir(tmp_path, **{"0002_a.sql": "CREATE TABLE a (n INTEGER);\n"})
    migrate(path, directory)
    (directory / "0003_bad.sql").write_text("INSERT INTO absent VALUES (1);\n", encoding="utf-8")
    with pytest.raises(MigrationError):
        migrate(path, directory)
    assert "wavelocalai.db.bak-2" in _copies(path)  # sa copie reste pour la reprise


def _database_with_a_copy_holding(tmp_path: Path, text: str) -> Path:
    """Base migrée de 1 à 2 qui contient `text` : sa copie `.bak-1` le contient aussi."""
    path = db_path(tmp_path / "data")
    directory = _migrations_dir(tmp_path)
    migrate(path, directory)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO app_sessions VALUES ('s', ?, 'startup')", (text,))
    conn.commit()
    conn.close()
    (directory / "0002_extra.sql").write_text("CREATE TABLE extra (n INTEGER);\n", encoding="utf-8")
    return path


def test_an_erase_removes_the_copy_that_still_holds_the_erased_text(tmp_path):
    path = _database_with_a_copy_holding(tmp_path, "Aiguille-Unique-7788")
    store = Store.open(path, tmp_path / "migrations")
    try:
        copy = backup_path(path, 1)
        assert b"Aiguille-Unique-7788" in copy.read_bytes()  # l'état d'avant, texte compris
        store.write(lambda conn: conn.execute("DELETE FROM app_sessions"), purge=True).result()
        assert not copy.exists() and _copies(path) == []
        assert store.purge_pending is False
    finally:
        store.close()
    assert b"Aiguille-Unique-7788" not in path.read_bytes()


def test_a_copy_that_cannot_be_removed_keeps_the_purge_due_then_is_removed(tmp_path, monkeypatch):
    path = _database_with_a_copy_holding(tmp_path, "Aiguille-Unique-9911")
    store = Store.open(path, tmp_path / "migrations")
    copy = backup_path(path, 1)
    real_unlink = Path.unlink

    def locked(self, missing_ok=False):
        if self.name.endswith(".bak-1"):
            raise PermissionError("fichier tenu par un autre programme")
        return real_unlink(self, missing_ok=missing_ok)

    try:
        monkeypatch.setattr(Path, "unlink", locked)
        store.write(lambda conn: conn.execute("DELETE FROM app_sessions"), purge=True).result()
        assert copy.exists() and store.purge_pending is True  # l'effacement est validé, pas fini
        monkeypatch.undo()
        store.write(lambda conn: None).result()  # écriture suivante : la suppression est rejouée
        assert not copy.exists() and store.purge_pending is False
    finally:
        store.close()
