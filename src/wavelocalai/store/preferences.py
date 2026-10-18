"""Préférences choisies par l'UI (table `preferences`, migration `0003_preferences.sql`, AD-15).

`PreferenceStore` est l'interface que les services consomment. `SqlitePreferenceStore` écrit par
l'écrivain unique du store (lecture courte) ; `InMemoryPreferenceStore` sert aux tests. Les valeurs
sont des documents JSON (dict, liste, nombre, texte).
"""

from __future__ import annotations

import copy
import json
import logging
import sqlite3
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any, Protocol

from wavelocalai.store.db import Store, utc_now_iso

logger = logging.getLogger("wavelocalai.store")
_DELETED = object()


class PreferenceStore(Protocol):
    def get(self, key: str) -> Any | None:
        """Valeur enregistrée pour cette clé, `None` si elle n'existe pas."""
        ...

    def put(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> None: ...


class InMemoryPreferenceStore:
    def __init__(self) -> None:
        self._rows: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        value = self._rows.get(key)
        return None if value is None else copy.deepcopy(value)

    def put(self, key: str, value: Any) -> None:
        self._rows[key] = copy.deepcopy(value)

    def delete(self, key: str) -> None:
        self._rows.pop(key, None)


class SqlitePreferenceStore:
    """Table `preferences` du store. Les écritures partent en file chez l'écrivain unique ; les
    valeurs écrites depuis le démarrage restent en mémoire pour que la lecture suivante les voie.
    Sans store (avant le démarrage du serveur), les préférences vivent en mémoire seulement."""

    def __init__(self, get_store: Callable[[], Store | None]) -> None:
        self._get_store = get_store
        self._recent: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        if key in self._recent:
            value = self._recent[key]
            return None if value is _DELETED else copy.deepcopy(value)
        store = self._get_store()
        if store is None:
            return None
        try:
            rows = store.read("SELECT value FROM preferences WHERE key = ?", (key,))
            return json.loads(rows[0]["value"]) if rows else None
        except (sqlite3.Error, ValueError):
            logger.warning("Lecture de la préférence %s impossible", key, exc_info=True)
            return None

    def put(self, key: str, value: Any) -> None:
        document = json.dumps(value, ensure_ascii=False)  # refuse ce qui n'est pas du JSON
        self._recent[key] = copy.deepcopy(value)
        now = utc_now_iso()

        def write(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO preferences (key, value, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value,"
                " updated_at = excluded.updated_at",
                (key, document, now),
            )

        self._submit(write, key)

    def delete(self, key: str) -> None:
        self._recent[key] = _DELETED

        def write(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM preferences WHERE key = ?", (key,))

        self._submit(write, key)

    def _submit(self, write: Callable[[sqlite3.Connection], None], key: str) -> None:
        store = self._get_store()
        if store is None:
            return
        try:
            store.write(write).add_done_callback(_log_failure)
        except RuntimeError:  # store fermé à l'arrêt
            logger.debug("Store fermé : préférence %s non écrite", key)


def _log_failure(future: Future) -> None:
    if (error := future.exception()) is not None:
        logger.warning("Écriture d'une préférence échouée : %s", error)
