"""Verrous de fichier du système, non bloquants (AD-12).

``msvcrt.locking`` sous Windows, ``fcntl.flock`` ailleurs : le système libère le verrou à la
mort du processus, il n'y a donc jamais de verrou orphelin. Le PID et l'heure de début écrits
dans le fichier ne servent qu'à l'information de l'opérateur, jamais à décider.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import TracebackType

from .canonical import utc_now

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

# Sous Windows, le verrou porte sur un octet loin après le texte d'information : un second
# processus peut ainsi lire le PID du détenteur (les verrous Windows sont impératifs).
_WINDOWS_LOCK_OFFSET = 0x7FFFFFFE


class LockBusyError(RuntimeError):
    """Le verrou est déjà détenu par un autre processus (ou un autre descripteur)."""

    def __init__(self, path: Path, holder: str) -> None:
        self.path = path
        self.holder = holder
        detail = f" ; détenteur (à titre indicatif) : {holder}" if holder else ""
        super().__init__(f"Verrou occupé : {path}{detail}")


class FileLock:
    """Verrou exclusif sur ``path``, pris sans attendre (``LockBusyError`` s'il est occupé).

    S'utilise en contexte : ``with FileLock(path) as lock: ...``.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> FileLock:
        if self._fd is not None:
            raise RuntimeError(f"Verrou déjà détenu par cet objet : {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
        fd = os.open(self.path, flags, 0o644)
        try:
            _lock(fd)
        except OSError:
            os.close(fd)
            raise LockBusyError(self.path, self._read_holder()) from None
        self._fd = fd
        info = f"pid={os.getpid()} started_at={utc_now()}\n".encode()
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, info)
        return self

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            os.ftruncate(fd, 0)
            _unlock(fd)
        finally:
            os.close(fd)

    def _read_holder(self) -> str:
        try:
            with open(self.path, encoding="utf-8", errors="replace") as handle:
                return handle.read(200).strip()
        except OSError:
            return ""

    def __enter__(self) -> FileLock:
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


if sys.platform == "win32":

    def _lock(fd: int) -> None:
        os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
