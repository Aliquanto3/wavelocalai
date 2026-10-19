"""Réception des fichiers d'un import : copie sur disque dans un dossier temporaire, empreinte.

La route lit les fichiers déposés avant de répondre (la requête ne les garde pas), les copie ici
sous un nom neutre (`0001.pdf`, jamais le nom de l'utilisateur : pas de traversée de chemin), puis
confie le dossier au service d'ingestion qui le supprime à la fin du run, annulation comprise.
Un fichier trop gros n'est pas écrit : il est lu pour son empreinte et refusé avec sa raison.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

CHUNK_BYTES = 1024 * 1024
MAX_NAME_CHARS = 255
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class Upload(Protocol):
    """Ce que la route passe : un `starlette.datastructures.UploadFile`, ou tout objet pareil."""

    filename: str | None

    async def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True)
class StagedFile:
    name: str  # nom affiché, sans dossier (la `source` du document)
    path: Path
    fingerprint: str  # SHA-256 du contenu
    size: int
    rejected: str | None = None  # raison d'un refus décidé à la réception (taille)


def new_staging_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="wavelocalai-ingest-"))


def discard_staging(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)


def clean_name(filename: str | None) -> str:
    """Nom de fichier sans dossier ni caractère de contrôle, borné à 255 caractères."""
    name = _CONTROL.sub("", (filename or "").replace("\\", "/").rsplit("/", 1)[-1]).strip()
    return name[:MAX_NAME_CHARS] or "document"


async def stage_upload(upload: Upload, directory: Path, index: int, max_bytes: int) -> StagedFile:
    """Copie `upload` dans `directory` sous `<index>.<extension>` en calculant son empreinte."""
    name = clean_name(upload.filename)
    suffix = Path(name).suffix.lower()
    suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) else ""
    path = directory / f"{index:04d}{suffix}"
    digest = hashlib.sha256()
    size = 0
    rejected: str | None = None
    with path.open("wb") as handle:
        while chunk := await upload.read(CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
            if size <= max_bytes:
                handle.write(chunk)
            elif rejected is None:
                rejected = f"le fichier dépasse {max_bytes // (1024 * 1024)} Mo"
    if rejected is not None:
        path.unlink(missing_ok=True)
    return StagedFile(name, path, digest.hexdigest(), size, rejected)
