"""Téléchargement des fichiers bruts des sources, à révision épinglée et empreinte vérifiée.

Seule porte réseau des importeurs (AD-15) : un fichier d'un dépôt de données Hugging Face
(``huggingface_hub``) ou d'un dépôt GitHub à un commit donné (``urllib``). Chaque fichier
porte son empreinte ``sha256`` attendue, versionnée dans l'importeur. Un fichier déjà présent
avec la bonne empreinte n'est pas retéléchargé. Une empreinte différente, après téléchargement
ou sur un fichier local modifié, supprime le fichier et lève ``SourceIntegrityError`` : aucun
candidat n'est alors écrit, et un nouveau ``fetch`` retélécharge le fichier. Les télémétries sont coupées avant l'import de
``huggingface_hub`` (``tests/unit/test_telemetry.py``).
"""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from src.core.telemetry import disable_telemetry

disable_telemetry()

from huggingface_hub import hf_hub_download  # noqa: E402

from ...common.canonical import sha256_bytes  # noqa: E402

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_S = 120


class SourceIntegrityError(RuntimeError):
    """Fichier téléchargé d'empreinte inattendue (source modifiée ou téléchargement corrompu)."""


@dataclass(frozen=True)
class RemoteFile:
    """Fichier brut d'une source : dépôt, révision complète, chemin dans le dépôt, empreinte."""

    host: str  # "hf" (dépôt de données Hugging Face) ou "github"
    repo: str
    revision: str
    path: str
    sha256: str

    def __post_init__(self) -> None:
        if self.host not in ("hf", "github"):
            raise ValueError(f"hôte inconnu : {self.host!r}")
        if not re.fullmatch(r"[0-9a-f]{40}", self.revision):
            raise ValueError(f"révision non épinglée (SHA complet attendu) : {self.revision!r}")
        posix = PurePosixPath(self.path)
        if posix.is_absolute() or ".." in posix.parts:
            raise ValueError(f"chemin hors du dépôt : {self.path!r}")

    @property
    def url(self) -> str:
        if self.host == "github":
            return f"https://raw.githubusercontent.com/{self.repo}/{self.revision}/{self.path}"
        return f"https://huggingface.co/datasets/{self.repo}/resolve/{self.revision}/{self.path}"

    def local_path(self, raw_dir: Path) -> Path:
        """Emplacement local : ``raw/<hôte>/<dépôt>/<révision>/<chemin>``. La révision fait
        partie du chemin : changer de révision dans l'importeur ne heurte pas l'ancien fichier."""
        return raw_dir.joinpath(
            self.host, *self.repo.split("/"), self.revision, *PurePosixPath(self.path).parts
        )


Downloader = Callable[[RemoteFile, Path], None]


def _download_github(remote: RemoteFile, target: Path) -> None:
    with (
        urllib.request.urlopen(remote.url, timeout=_HTTP_TIMEOUT_S) as response,  # noqa: S310
        open(target, "wb") as handle,
    ):
        shutil.copyfileobj(response, handle)


def _download_hf(remote: RemoteFile, target: Path) -> None:
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        downloaded = hf_hub_download(
            remote.repo,
            remote.path,
            repo_type="dataset",
            revision=remote.revision,
            cache_dir=Path(tmp) / "cache",
            local_dir=Path(tmp) / "files",
        )
        shutil.copyfile(downloaded, target)


def default_downloader(remote: RemoteFile, target: Path) -> None:
    """Télécharge ``remote`` dans ``target`` (réseau)."""
    if remote.host == "github":
        _download_github(remote, target)
    else:
        _download_hf(remote, target)


def file_sha256(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.is_file() else None


def fetch_files(
    files: Iterable[RemoteFile], raw_dir: Path, downloader: Downloader = default_downloader
) -> dict[RemoteFile, Path]:
    """Rend chaque fichier présent sous ``raw_dir`` avec son empreinte attendue.

    Fichier absent : téléchargé (``downloader``, injectable pour les tests) dans un temporaire
    voisin ``.part``, vérifié, puis mis en place. Empreinte inattendue, après téléchargement ou
    sur un fichier local : fichier supprimé, ``SourceIntegrityError``.
    """
    result: dict[RemoteFile, Path] = {}
    for remote in files:
        path = remote.local_path(raw_dir)
        actual = file_sha256(path)
        if actual == remote.sha256:
            logger.info("%s déjà présent, empreinte vérifiée", remote.url)
            result[remote] = path
            continue
        if actual is not None:
            path.unlink()
            raise SourceIntegrityError(
                f"Empreinte inattendue pour le fichier local {path} : {actual} au lieu de "
                f"{remote.sha256} (fichier modifié, supprimé ; relancer fetch pour le "
                "retélécharger)"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.part")
        logger.info("Téléchargement de %s", remote.url)
        try:
            downloader(remote, tmp)
            actual = file_sha256(tmp)
            if actual != remote.sha256:
                raise SourceIntegrityError(
                    f"Empreinte inattendue pour {remote.url} : {actual} au lieu de "
                    f"{remote.sha256} (fichier supprimé)"
                )
            tmp.replace(path)
        finally:
            if tmp.exists():
                tmp.unlink()
        result[remote] = path
    return result
