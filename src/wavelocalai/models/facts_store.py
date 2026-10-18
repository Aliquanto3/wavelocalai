"""`model_facts` sur le store SQLite : cache de `/api/show` par `(tag, digest)` (AD-12, AD-15).

Écritures par l'écrivain unique du store (migration `0002_model_facts.sql`), lectures courtes. Les
écritures ne bloquent pas la boucle : elles partent en file, et les faits écrits depuis le
démarrage restent aussi en mémoire pour que la lecture suivante les voie. Sans store (avant le
démarrage du serveur), les faits vivent en mémoire seulement.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from concurrent.futures import Future

from wavelocalai.models.facts import InMemoryFactsStore, ModelFacts
from wavelocalai.store.db import Store

logger = logging.getLogger("wavelocalai.models")

_COLUMNS = (
    "tag, digest, size_bytes, family, parameter_size, quantization, context_length, capabilities,"
    " params_total_b, expert_count, expert_used_count, fetched_at"
)


def _from_row(row: sqlite3.Row) -> ModelFacts:
    try:
        capabilities = tuple(str(c) for c in json.loads(row["capabilities"]))
    except (TypeError, ValueError):
        capabilities = ()
    return ModelFacts(
        tag=row["tag"],
        digest=row["digest"],
        size_bytes=row["size_bytes"],
        family=row["family"],
        parameter_size=row["parameter_size"],
        quantization=row["quantization"],
        context_length=row["context_length"],
        capabilities=capabilities,
        params_total_b=row["params_total_b"],
        expert_count=row["expert_count"],
        expert_used_count=row["expert_used_count"],
        fetched_at=row["fetched_at"],
    )


class SqliteFactsStore:
    def __init__(self, get_store: Callable[[], Store | None]) -> None:
        self._get_store = get_store
        self._recent = InMemoryFactsStore()  # écritures en file, et repli sans store

    def get(self, tag: str, digest: str) -> ModelFacts | None:
        recent = self._recent.get(tag, digest)
        store = self._get_store()
        if recent is not None or store is None:
            return recent
        rows = self._read(
            store, f"SELECT {_COLUMNS} FROM model_facts WHERE tag = ? AND digest = ?", (tag, digest)
        )
        return _from_row(rows[0]) if rows else None

    def put(self, facts: ModelFacts) -> None:
        self._recent.put(facts)
        store = self._get_store()
        if store is None:
            return
        row = (
            facts.tag, facts.digest, facts.size_bytes, facts.family, facts.parameter_size,
            facts.quantization, facts.context_length, json.dumps(list(facts.capabilities)),
            facts.params_total_b, facts.expert_count, facts.expert_used_count, facts.fetched_at,
        )  # fmt: skip

        def write(conn: sqlite3.Connection) -> None:
            conn.execute(
                f"INSERT OR REPLACE INTO model_facts ({_COLUMNS})"  # noqa: S608
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )

        try:
            store.write(write).add_done_callback(_log_failure)
        except RuntimeError:  # store fermé à l'arrêt : les faits se relisent au prochain démarrage
            logger.debug("Store fermé : faits de %s non écrits", facts.tag)

    def latest_per_tag(self) -> list[ModelFacts]:
        latest: dict[str, ModelFacts] = {f.tag: f for f in self._recent.latest_per_tag()}
        store = self._get_store()
        if store is not None:
            for row in self._read(store, f"SELECT {_COLUMNS} FROM model_facts", ()):
                facts = _from_row(row)
                current = latest.get(facts.tag)
                if current is None or facts.fetched_at > current.fetched_at:
                    latest[facts.tag] = facts
        return list(latest.values())

    @staticmethod
    def _read(store: Store, sql: str, params: tuple) -> list[sqlite3.Row]:
        try:
            return store.read(sql, params)
        except sqlite3.Error:
            logger.warning("Lecture de model_facts impossible", exc_info=True)
            return []


def _log_failure(future: Future) -> None:
    if (error := future.exception()) is not None:
        logger.warning("Écriture de model_facts échouée : %s", error)
