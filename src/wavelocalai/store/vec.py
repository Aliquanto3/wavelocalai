"""Extension sqlite-vec et tables vec0 `chunks_vec_<dim>` (AD-12, AD-16).

Les tables vectorielles sont la seule exception écrite aux migrations : leur dimension dépend du
modèle d'embedding, connue au premier embedding. `ensure_vec_table` les crée de façon idempotente,
sous un nom figé, avec `rowid = chunks.id`. `sqlite_vec` n'est importé que dans `load_vec`.
"""

from __future__ import annotations

import logging
import re
import sqlite3

logger = logging.getLogger("wavelocalai.store")

MAX_DIM = 8192
_VEC_TABLE = re.compile(r"^chunks_vec_(\d+)$")


def vec_table(dim: int) -> str:
    """Nom figé de la table vec0 pour cette dimension."""
    if not isinstance(dim, int) or isinstance(dim, bool) or not 1 <= dim <= MAX_DIM:
        raise ValueError(f"Dimension d'embedding invalide : {dim!r} (1 à {MAX_DIM}).")
    return f"chunks_vec_{dim}"


def load_vec(conn: sqlite3.Connection) -> bool:
    """Charge l'extension sqlite-vec dans la connexion ; `False` (journalisé) si elle manque ou si
    CPython est compilé sans chargement d'extensions."""
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)
    except (ImportError, AttributeError, sqlite3.Error) as exc:
        logger.warning("sqlite-vec n'a pas pu être chargé : %s", exc)
        return False
    return True


def ensure_vec_table(conn: sqlite3.Connection, dim: int) -> str:
    """Crée `chunks_vec_<dim>` (vec0, `rowid` = `chunks.id`) si elle manque ; rend son nom.
    Idempotent. À appeler sur la connexion de l'écrivain (dans sa transaction)."""
    name = vec_table(dim)
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {name} "
        f"USING vec0(embedding float[{dim}] distance_metric=cosine)"
    )
    return name


def vec_tables(conn: sqlite3.Connection) -> dict[int, str]:
    """Tables vec0 présentes : dimension -> nom (les tables d'ombre de vec0 sont écartées)."""
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    found: dict[int, str] = {}
    for (name,) in rows:
        match = _VEC_TABLE.match(name)
        if match:
            found[int(match.group(1))] = name
    return found
