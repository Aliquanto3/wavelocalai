"""Dossier de données : création, alerte OneDrive et verrou d'instance unique (AD-23)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO

LOCK_NAME = ".wavelocalai.lock"


class DataDirLockedError(Exception):
    """Un autre serveur utilise déjà ce dossier de données."""


def ensure_data_dir(path: Path) -> Path:
    """Crée le dossier de données (et son sous-dossier de journaux) s'il manque."""
    (path / "logs").mkdir(parents=True, exist_ok=True)
    return path


def is_under_onedrive(path: Path) -> bool:
    """Vrai si un composant du chemin est un dossier OneDrive : la synchronisation peut corrompre
    la base SQLite en mode WAL."""
    return any(part.lower().startswith("onedrive") for part in path.resolve().parts)


class DataDirLock:
    """Verrou exclusif sur un fichier du dossier de données, tenu tant que le serveur vit.

    Le système le libère aussi si le processus meurt : pas de verrou périmé à nettoyer.
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / LOCK_NAME
        self._handle: IO[bytes] | None = None

    def acquire(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        handle = self.path.open("r+b")
        try:
            _lock(handle)
        except OSError as exc:
            handle.close()
            raise DataDirLockedError(
                f"Un autre wavelocalai-v2 utilise déjà le dossier de données {self.data_dir}. "
                "Arrêtez-le, ou choisissez un autre dossier (--data-dir)."
            ) from exc
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            _unlock(self._handle)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> DataDirLock:
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


if sys.platform == "win32":  # pragma: no cover - une seule branche par plateforme
    import msvcrt

    def _lock(handle: IO[bytes]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle: IO[bytes]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:  # pragma: no cover
    import fcntl

    def _lock(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
