"""Store SQLite : un écrivain sur un fil, des lectures sur connexions courtes (AD-12).

La base est un seul fichier (`wavelocalai.db` dans le dossier de données), en WAL, avec
`foreign_keys` et `secure_delete`. Toute écriture passe par `Store.write` / `Store.awrite` : une
connexion dédiée, ouverte et utilisée par un seul fil, exécute les écritures l'une après l'autre,
chacune dans une transaction. Les lectures ouvrent une connexion courte, en lecture seule.
"""

from __future__ import annotations

import asyncio
import queue
import sqlite3
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

from wavelocalai.store.migrate import MIGRATIONS_DIR, migrate
from wavelocalai.store.vec import ensure_vec_table, load_vec

DB_NAME = "wavelocalai.db"
BUSY_TIMEOUT_MS = 5000
T = TypeVar("T")

_Job = tuple[Callable[[sqlite3.Connection], Any], "Future[Any]"]


def utc_now_iso() -> str:
    """Date courante en ISO 8601 UTC avec `Z`, à la milliseconde (convention de la v2)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def db_path(data_dir: Path) -> Path:
    return data_dir / DB_NAME


def _pragmas(conn: sqlite3.Connection) -> None:
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA secure_delete=ON")


class Store:
    """Accès à la base : écrivain unique (`write`) et lectures courtes (`read`)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._jobs: queue.Queue[_Job | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._lock = threading.Lock()
        self.vec_available = False  # sqlite-vec chargé par l'écrivain (AD-12)

    @classmethod
    def open(cls, path: Path, migrations_dir: Path = MIGRATIONS_DIR) -> Store:
        """Migre la base (la crée si elle manque) puis démarre l'écrivain.

        Lève `DatabaseTooNewError` ou `MigrationError` : le serveur ne démarre pas.
        """
        migrate(path, migrations_dir)
        store = cls(path)
        store._start()
        return store

    # --- écrivain ------------------------------------------------------------------------------

    def _start(self) -> None:
        ready: Future[None] = Future()
        self._thread = threading.Thread(
            target=self._run, args=(ready,), name="wavelocalai-db-writer", daemon=True
        )
        self._thread.start()
        ready.result()  # remonte une erreur d'ouverture

    def _run(self, ready: Future[None]) -> None:
        try:
            conn = sqlite3.connect(self.path, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            _pragmas(conn)
            self.vec_available = load_vec(conn)
        except Exception as exc:  # noqa: BLE001 - rendu à l'appelant de `_start`
            ready.set_exception(exc)
            return
        ready.set_result(None)
        try:
            while (job := self._jobs.get()) is not None:
                func, future = job
                if not future.set_running_or_notify_cancel():
                    continue
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    result = func(conn)
                    conn.execute("COMMIT")
                except BaseException as exc:  # noqa: BLE001 - rendu à l'appelant du futur
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    future.set_exception(exc)
                else:
                    future.set_result(result)
        finally:
            conn.close()

    def write(self, func: Callable[[sqlite3.Connection], T]) -> Future[T]:
        """Met `func(conn)` dans la file de l'écrivain, dans une transaction (`COMMIT` si elle
        rend, `ROLLBACK` si elle lève). Rend un futur ; `func` tourne sur le fil de l'écrivain."""
        future: Future[T] = Future()
        with self._lock:
            if self._closed:
                raise RuntimeError("Le store est fermé.")
            self._jobs.put((func, future))
        return future

    async def awrite(self, func: Callable[[sqlite3.Connection], T]) -> T:
        return await asyncio.wrap_future(self.write(func))

    async def ensure_vec_table(self, dim: int) -> str:
        """Crée `chunks_vec_<dim>` si elle manque (idempotent, AD-12) ; rend son nom."""
        return await self.awrite(lambda conn: ensure_vec_table(conn, dim))

    def close(self) -> None:
        """Termine les écritures en file, puis ferme l'écrivain."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._jobs.put(None)
        if self._thread is not None:
            self._thread.join()

    # --- lectures ------------------------------------------------------------------------------

    def read(self, sql: str, params: Sequence[Any] = (), *, vec: bool = False) -> list[sqlite3.Row]:
        """Lecture sur une connexion courte (ouverte et fermée par l'appel). `vec` : charge
        sqlite-vec pour interroger une table `chunks_vec_<dim>`."""
        conn = sqlite3.connect(self.path)
        try:
            conn.row_factory = sqlite3.Row
            _pragmas(conn)
            if vec:
                load_vec(conn)
            conn.execute("PRAGMA query_only=ON")
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    async def aread(
        self, sql: str, params: Sequence[Any] = (), *, vec: bool = False
    ) -> list[sqlite3.Row]:
        return await asyncio.to_thread(partial(self.read, sql, params, vec=vec))
