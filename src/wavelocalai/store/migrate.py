"""Migrations du store : `migrations/NNNN_nom.sql`, avant seulement (AD-12).

Au démarrage, chaque migration en attente est appliquée dans sa propre transaction, après une copie
`wavelocalai.db.bak-<user_version>` de la base existante. La version vit dans `PRAGMA user_version`.
Une seule copie est gardée : celle de la dernière migration ; les précédentes sont supprimées une
fois la suivante réussie. Un effacement (AD-13) supprime aussi la copie (`remove_backups`), qui
contient l'état d'avant la migration, texte effacé compris.
Une base dont la version dépasse celle du code est refusée : un code trop ancien n'ouvre pas une
base plus récente.
"""

from __future__ import annotations

import glob
import logging
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
logger = logging.getLogger(__name__)
_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


class MigrationError(Exception):
    """Une migration a échoué ou le dossier des migrations est incohérent (message en français)."""


class DatabaseTooNewError(MigrationError):
    """La base a été écrite par une version plus récente de l'application."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Migrations du dossier, triées ; leurs numéros doivent se suivre à partir de 1."""
    found: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _NAME.match(path.name)
        if match is None:
            raise MigrationError(f"Nom de migration invalide : {path.name} (attendu NNNN_nom.sql).")
        found.append(Migration(int(match.group(1)), match.group(2), path))
    if [m.version for m in found] != list(range(1, len(found) + 1)):
        raise MigrationError(
            f"Les migrations de {directory} doivent être numérotées 0001, 0002… sans trou."
        )
    return found


def statements(script: str) -> Iterator[str]:
    """Découpe un script SQL en instructions complètes (triggers et commentaires compris)."""
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            yield buffer.strip()
            buffer = ""
    if buffer.strip():
        yield buffer.strip()


def backup_path(db_path: Path, version: int) -> Path:
    return db_path.with_name(f"{db_path.name}.bak-{version}")


def backup_files(db_path: Path) -> list[Path]:
    """Les copies `<base>.bak-<version>` présentes à côté de la base."""
    return sorted(db_path.parent.glob(f"{glob.escape(db_path.name)}.bak-*"))


def remove_backups(db_path: Path, keep: Path | None = None) -> bool:
    """Supprime les copies de la base, sauf `keep`. Rend faux si l'une n'a pas pu l'être (fichier
    tenu par un autre programme) : l'appelant le sait et réessaie plus tard."""
    removed = True
    for copy in backup_files(db_path):
        if copy == keep:
            continue
        try:
            copy.unlink(missing_ok=True)
        except OSError:
            logger.warning("La copie %s de la base n'a pas pu être supprimée.", copy, exc_info=True)
            removed = False
    return removed


def migrate(db_path: Path, directory: Path = MIGRATIONS_DIR, *, target: int | None = None) -> int:
    """Amène la base à `target` (la dernière migration par défaut) ; rend sa version.

    Crée la base si elle manque. `DatabaseTooNewError` si `user_version` dépasse `target`.
    """
    migrations = discover(directory)
    latest = migrations[-1].version if migrations else 0
    goal = latest if target is None else target
    existed = db_path.is_file() and db_path.stat().st_size > 0
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if current > goal:
            raise DatabaseTooNewError(
                f"La base {db_path} est à la version {current}, plus récente que celle de "
                f"cette application ({goal}). Mettez l'application à jour : elle ne modifie "
                "pas une base plus récente que son code."
            )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        pending = [m for m in migrations if current < m.version <= goal]
        if not pending:
            return current
        has_schema = existed and conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
        copy = backup_path(db_path, current) if has_schema else None
        if copy is not None:
            _backup(conn, copy)
        for migration in pending:
            _apply(conn, migration, db_path, current)
            current = migration.version
        # Migration réussie : la nouvelle copie est la seule gardée (les anciennes ne servent plus).
        remove_backups(db_path, keep=copy)
        return current
    finally:
        conn.close()


def _backup(conn: sqlite3.Connection, target: Path) -> None:
    target.unlink(missing_ok=True)
    copy = sqlite3.connect(target)
    try:
        conn.backup(copy)  # copie cohérente, y compris ce qui est encore dans le journal WAL
    finally:
        copy.close()


def _apply(conn: sqlite3.Connection, migration: Migration, db_path: Path, before: int) -> None:
    script = migration.path.read_text(encoding="utf-8")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for statement in statements(script):
            conn.execute(statement)
        conn.execute(f"PRAGMA user_version = {migration.version}")
        conn.execute("COMMIT")
    except sqlite3.Error as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        saved = f" ; sa copie est dans {backup_path(db_path, before)}." if before else "."
        raise MigrationError(
            f"La migration {migration.path.name} a échoué ({exc}). "
            f"La base reste à la version {before}{saved}"
        ) from exc
