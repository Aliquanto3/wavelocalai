"""Lecture et écriture des JSONL en ajout seul (AD-2, AD-12) : seul module à y toucher.

- ``read_jsonl`` / ``iter_jsonl`` : lecture seule. Un fragment final sans ``\\n`` (écriture
  interrompue) est ignoré ; toute autre ligne illisible lève ``JsonlReadError`` avec son numéro.
  Le fichier n'est jamais modifié.
- ``open_for_append`` : réservé au détenteur du verrou du fichier. Tronque physiquement le
  fragment final (journalisé), charge les clés présentes, puis écrit une ligne canonique + ``\\n``
  par enregistrement, avec ``flush`` et ``os.fsync``. Une clé déjà présente lève
  ``DuplicateKeyError`` sans rien écrire.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, BinaryIO

from .canonical import canonical_bytes
from .locks import FileLock

logger = logging.getLogger(__name__)

_CHUNK = 64 * 1024


class JsonlReadError(ValueError):
    """Ligne illisible (hors fragment final) : le fichier est corrompu, on s'arrête."""

    def __init__(self, path: Path, line_no: int, reason: str) -> None:
        self.path = path
        self.line_no = line_no
        super().__init__(f"{path} : ligne {line_no} illisible ({reason})")


class DuplicateKeyError(KeyError):
    """Écriture d'une clé déjà présente dans le fichier."""

    def __str__(self) -> str:
        return f"Clé déjà présente, rien n'est écrit : {self.args[0]!r}"


def iter_jsonl(path: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """Parcourt les enregistrements d'un JSONL, en lecture seule (fichier absent : vide)."""
    path = Path(path)
    if not path.exists():
        return
    with open(path, "rb") as handle:
        for line_no, raw in enumerate(handle, start=1):
            if not raw.endswith(b"\n"):
                return  # fragment final d'une écriture interrompue : ignoré
            yield _parse_line(path, line_no, raw)


def read_jsonl(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Liste des enregistrements d'un JSONL, en lecture seule (voir ``iter_jsonl``)."""
    return list(iter_jsonl(path))


def _parse_line(path: Path, line_no: int, raw: bytes) -> dict[str, Any]:
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JsonlReadError(path, line_no, str(exc)) from None
    if not isinstance(record, dict):
        raise JsonlReadError(path, line_no, "pas un objet JSON")
    return record


def _final_fragment_start(handle: BinaryIO, size: int) -> int:
    """Position qui suit le dernier ``\\n`` du fichier (0 s'il n'y en a aucun)."""
    end = size
    while end > 0:
        start = max(0, end - _CHUNK)
        handle.seek(start)
        block = handle.read(end - start)
        index = block.rfind(b"\n")
        if index >= 0:
            return start + index + 1
        end = start
    return 0


class JsonlAppender:
    """Écrivain en ajout seul, obtenu par ``open_for_append``."""

    def __init__(self, path: Path, keys: set[str], lock: FileLock) -> None:
        self.path = path
        self._keys = keys
        self._lock = lock
        self._broken = False
        self._handle = open(path, "ab")  # noqa: SIM115 (fermé par close / __exit__)

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(self._keys)

    def __contains__(self, key: object) -> bool:
        return key in self._keys

    def __len__(self) -> int:
        return len(self._keys)

    def append(self, record: Mapping[str, Any]) -> None:
        """Écrit ``record`` (qui porte une ``key`` chaîne) en une ligne, forcée sur disque."""
        key = record.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("Enregistrement sans clé « key » (chaîne non vide)")
        if self._broken:
            raise RuntimeError(
                f"Écriture refusée : une écriture précédente a échoué ({self.path}) ; "
                "rouvrir le fichier par open_for_append pour tronquer le fragment"
            )
        if not self._lock.held:
            raise RuntimeError(
                f"Écriture refusée : le verrou du fichier a été libéré ({self.path})"
            )
        if key in self._keys:
            raise DuplicateKeyError(key)
        line = canonical_bytes(record) + b"\n"
        try:
            self._handle.write(line)
            self._handle.flush()
            os.fsync(self._handle.fileno())
        except BaseException:
            # Ligne peut-être écrite en partie : plus aucune ligne ne doit s'y coller.
            self._broken = True
            self.close()
            raise
        self._keys.add(key)

    def close(self) -> None:
        if not self._handle.closed:
            try:
                self._handle.close()
            except OSError:
                # Le vidage final peut échouer après une erreur d'écriture : écrivain cassé.
                self._broken = True

    def __enter__(self) -> JsonlAppender:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def open_for_append(path: str | os.PathLike[str], lock: FileLock) -> JsonlAppender:
    """Ouvre ``path`` en ajout pour le détenteur de ``lock`` : tronque le fragment final,
    charge les clés présentes et renvoie l'écrivain."""
    if not isinstance(lock, FileLock) or not lock.held:
        raise RuntimeError(f"Écriture refusée : le verrou du fichier n'est pas détenu ({path})")
    path = Path(path)
    # Chaque JSONL a son verrou dans son dossier (generation.lock, judgment.lock), jamais
    # machine.lock ni le verrou d'une autre campagne.
    if lock.path.resolve().parent != path.resolve().parent:
        raise RuntimeError(
            f"Écriture refusée : le verrou {lock.path} n'est pas celui du dossier de {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with open(path, "r+b") as handle:
            size = handle.seek(0, os.SEEK_END)
            keep = _final_fragment_start(handle, size)
            if keep < size:
                handle.truncate(keep)
                handle.flush()
                os.fsync(handle.fileno())
                logger.warning(
                    "%s : fragment final de %d octets sans fin de ligne tronqué "
                    "(écriture interrompue, sa question sera rejouée)",
                    path,
                    size - keep,
                )
    keys: set[str] = set()
    for line_no, record in enumerate(iter_jsonl(path), start=1):
        key = record.get("key")
        if not isinstance(key, str) or not key:
            raise JsonlReadError(path, line_no, "clé « key » absente")
        if key in keys:
            raise JsonlReadError(path, line_no, f"clé en double {key!r}")
        keys.add(key)
    return JsonlAppender(path, keys, lock)


def rewrite_jsonl(path: str | os.PathLike[str], records: Iterable[Mapping[str, Any]]) -> int:
    """Réécrit ``path`` en entier (fichiers « réécrits » d'AD-2 : candidats d'une source,
    ``grading.jsonl``) : lignes canoniques + ``\n`` dans un fichier temporaire voisin, ``fsync``,
    puis ``os.replace``. Un arrêt en cours laisse l'ancien fichier intact. Rend le nombre de
    lignes écrites."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    count = 0
    try:
        with open(tmp, "wb") as handle:
            for record in records:
                handle.write(canonical_bytes(dict(record)) + b"\n")
                count += 1
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return count


def read_complete_jsonl(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Lit un JSONL tiers complet (fichier brut d'une source publique, jamais écrit par le
    banc) : la dernière ligne peut manquer de ``\n`` sans être un fragment, les lignes vides
    sont ignorées, toute ligne illisible lève ``JsonlReadError``."""
    path = Path(path)
    records = []
    with open(path, "rb") as handle:
        for line_no, raw in enumerate(handle, start=1):
            if raw.strip():
                records.append(_parse_line(path, line_no, raw.rstrip(b"\r\n") + b"\n"))
    return records
