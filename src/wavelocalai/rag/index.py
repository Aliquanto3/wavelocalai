"""Port `VectorIndex` : où vivent les vecteurs des extraits (AD-16).

Deux implémentations : `SqliteVecIndex` (tables vec0 `chunks_vec_<dim>` du fichier SQLite, `rowid`
= `chunks.id`) et `NumpyIndex` (en mémoire, repli des tests qui n'ont pas besoin de l'extension).
Les deux comparent par distance cosinus (0 = même direction).

Les méthodes sont synchrones et prennent la connexion SQLite du contexte : celle de l'écrivain pour
`add` et `remove` (dans sa transaction, donc la suppression d'un document et de ses vecteurs est
atomique, AD-13), une connexion de lecture pour `search`. `NumpyIndex` ignore la connexion. `numpy`
n'est importé que dans les méthodes de `NumpyIndex`.
"""

from __future__ import annotations

import logging
import sqlite3
import struct
import threading
from collections.abc import Sequence
from typing import Protocol

from wavelocalai.store.vec import ensure_vec_table, vec_table, vec_tables

logger = logging.getLogger("wavelocalai.rag")

BATCH = 500  # identifiants par requête (limite de variables de SQLite)


class VectorIndex(Protocol):
    persistent: bool  # les vecteurs survivent à un redémarrage (vrai pour sqlite-vec)

    def add(
        self, conn: sqlite3.Connection, ids: Sequence[int], vectors: Sequence[Sequence[float]]
    ) -> None:
        """Indexe `vectors[i]` sous l'identifiant d'extrait `ids[i]`. La dimension est celle des
        vecteurs ; la table qui lui correspond est créée au besoin (premier embedding)."""
        ...

    def remove(self, conn: sqlite3.Connection, ids: Sequence[int]) -> None:
        """Retire les vecteurs de ces extraits, quelle que soit leur dimension."""
        ...

    def search(
        self,
        conn: sqlite3.Connection,
        vector: Sequence[float],
        k: int,
        *,
        among: str | None = None,
    ) -> list[tuple[int, float]]:
        """Les `k` extraits les plus proches : `(chunk_id, distance cosinus)`, du plus proche.
        `among` : requête SQL (sans paramètre) qui rend les identifiants admis ; le filtre est
        appliqué avant de prendre les `k` plus proches, jamais après."""
        ...

    def count(self, conn: sqlite3.Connection, dim: int | None = None) -> int:
        """Nombre de vecteurs (de cette dimension, ou de toutes)."""
        ...

    def clear(self, conn: sqlite3.Connection) -> None:
        """Vide l'index (« Vider la base », AD-13) : la table vec0 est supprimée puis recréée, pas
        vidée ligne à ligne, pour qu'aucun vecteur ne reste dans ses pages."""
        ...


def _blob(vector: Sequence[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _check_batch(ids: Sequence[int], vectors: Sequence[Sequence[float]]) -> int:
    if len(ids) != len(vectors) or not ids:
        raise ValueError("Autant d'identifiants que de vecteurs, et au moins un.")
    dims = {len(v) for v in vectors}
    if len(dims) != 1:
        raise ValueError(f"Les vecteurs d'un lot ont des dimensions différentes : {sorted(dims)}.")
    return dims.pop()


class SqliteVecIndex:
    """Tables vec0 du fichier SQLite (extension sqlite-vec chargée dans la connexion)."""

    persistent = True

    def add(
        self, conn: sqlite3.Connection, ids: Sequence[int], vectors: Sequence[Sequence[float]]
    ) -> None:
        dim = _check_batch(ids, vectors)
        table = ensure_vec_table(conn, dim)  # idempotent (AD-12)
        conn.executemany(
            f"INSERT INTO {table}(rowid, embedding) VALUES (?, ?)",
            [(int(i), _blob(v)) for i, v in zip(ids, vectors, strict=True)],
        )

    def remove(self, conn: sqlite3.Connection, ids: Sequence[int]) -> None:
        # Pas de cascade sur une table virtuelle : on supprime par `rowid` (AD-13).
        for table in vec_tables(conn).values():
            for start in range(0, len(ids), BATCH):
                part = [int(i) for i in ids[start : start + BATCH]]
                marks = ",".join("?" * len(part))
                conn.execute(f"DELETE FROM {table} WHERE rowid IN ({marks})", part)

    def search(
        self,
        conn: sqlite3.Connection,
        vector: Sequence[float],
        k: int,
        *,
        among: str | None = None,
    ) -> list[tuple[int, float]]:
        table = vec_table(len(vector))
        if len(vector) not in vec_tables(conn):
            return []
        # vec0 applique `rowid IN (...)` avant la sélection des `k` plus proches.
        allowed = "" if among is None else f" AND rowid IN ({among})"
        rows = conn.execute(
            f"SELECT rowid, distance FROM {table} WHERE embedding MATCH ? AND k = ?{allowed} "
            "ORDER BY distance",
            (_blob(vector), int(k)),
        ).fetchall()
        return [(int(rowid), float(distance)) for rowid, distance in rows]

    def count(self, conn: sqlite3.Connection, dim: int | None = None) -> int:
        tables = vec_tables(conn)
        names = list(tables.values()) if dim is None else [tables[dim]] if dim in tables else []
        return sum(conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in names)

    def clear(self, conn: sqlite3.Connection) -> None:
        # Supprimer puis recréer (AD-13) : `DROP TABLE` libère les pages de la table et de ses
        # tables d'ombre, le `VACUUM` qui suit les réécrit sans les vecteurs.
        for dim, table in vec_tables(conn).items():
            conn.execute(f"DROP TABLE {table}")
            ensure_vec_table(conn, dim)


class NumpyIndex:
    """Repli en mémoire (tests) : produit scalaire de vecteurs normalisés, sans extension."""

    persistent = False

    def __init__(self) -> None:
        self._vectors: dict[int, tuple[int, object]] = {}  # id -> (dim, tableau normalisé)
        self._lock = threading.Lock()

    @staticmethod
    def _unit(vector: Sequence[float]):  # type: ignore[no-untyped-def]
        import numpy as np

        array = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(array))
        return array / norm if norm else array

    def add(
        self, conn: sqlite3.Connection, ids: Sequence[int], vectors: Sequence[Sequence[float]]
    ) -> None:
        dim = _check_batch(ids, vectors)
        with self._lock:
            for chunk_id, vector in zip(ids, vectors, strict=True):
                self._vectors[int(chunk_id)] = (dim, self._unit(vector))

    def remove(self, conn: sqlite3.Connection, ids: Sequence[int]) -> None:
        with self._lock:
            for chunk_id in ids:
                self._vectors.pop(int(chunk_id), None)

    def search(
        self,
        conn: sqlite3.Connection,
        vector: Sequence[float],
        k: int,
        *,
        among: str | None = None,
    ) -> list[tuple[int, float]]:
        query = self._unit(vector)
        allowed = None if among is None else {int(row[0]) for row in conn.execute(among)}
        with self._lock:
            scored = [
                (chunk_id, 1.0 - float(query @ stored))  # type: ignore[operator]
                for chunk_id, (dim, stored) in self._vectors.items()
                if dim == len(vector) and (allowed is None or chunk_id in allowed)
            ]
        return sorted(scored, key=lambda item: (item[1], item[0]))[: int(k)]

    def count(self, conn: sqlite3.Connection, dim: int | None = None) -> int:
        with self._lock:
            return sum(1 for d, _ in self._vectors.values() if dim is None or d == dim)

    def clear(self, conn: sqlite3.Connection) -> None:
        with self._lock:
            self._vectors.clear()


def select_index(vec_available: bool) -> VectorIndex:
    """L'index d'une base : `SqliteVecIndex` si l'écrivain a chargé sqlite-vec, sinon `NumpyIndex`
    (CPython sans chargement d'extensions, par exemple celui de `setup-python` sur macOS). Le repli
    ne lance jamais de requête `vec0`, mais ses vecteurs vivent en mémoire : ils ne survivent pas
    à un redémarrage."""
    if vec_available:
        return SqliteVecIndex()
    logger.warning(
        "sqlite-vec indisponible : index vectoriel en mémoire (numpy), perdu à l'arrêt du serveur"
    )
    return NumpyIndex()
