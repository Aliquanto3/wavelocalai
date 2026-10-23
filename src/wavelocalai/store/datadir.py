"""Dossier de données : création, alerte OneDrive et verrou d'instance unique (AD-23)."""

from __future__ import annotations

import errno
import sys
from pathlib import Path
from typing import IO

LOCK_NAME = ".wavelocalai.lock"


class DataDirLockError(Exception):
    """Le verrou du dossier de données n'a pas pu être pris (la cause est dans le message)."""


class DataDirLockedError(DataDirLockError):
    """Un autre serveur utilise déjà ce dossier de données."""


# Codes d'un verrou déjà tenu (`msvcrt.locking` : EACCES ou EDEADLOCK ; `flock` : EAGAIN).
_HELD = {errno.EACCES, errno.EAGAIN, errno.EDEADLK, getattr(errno, "EWOULDBLOCK", errno.EAGAIN)}


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
        """Prend le verrou. `DataDirLockedError` si un serveur vivant le tient ; toute autre
        cause (droits, disque plein, dossier absent) est dite telle quelle (`DataDirLockError`)."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.path.touch(exist_ok=True)
            handle = self.path.open("r+b")
        except OSError as exc:
            raise DataDirLockError(
                f"Impossible de créer le verrou {self.path} : {exc.strerror or exc}. "
                "Vérifiez les droits et l'espace disque du dossier de données, ou choisissez un "
                "autre dossier (--data-dir)."
            ) from exc
        try:
            _lock(handle)
        except OSError as exc:
            handle.close()
            if exc.errno in _HELD or getattr(exc, "winerror", None) in {33, 32}:
                raise DataDirLockedError(
                    f"Un autre wavelocalai-v2 utilise déjà le dossier de données {self.data_dir}. "
                    "Arrêtez-le, ou choisissez un autre dossier (--data-dir)."
                ) from exc
            raise DataDirLockError(
                f"Impossible de prendre le verrou {self.path} : {exc.strerror or exc}."
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
