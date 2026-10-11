"""Téléchargement des fichiers bruts des sources, à révision épinglée et empreinte vérifiée.

Seule porte réseau des importeurs (AD-15) : un fichier d'un dépôt de données Hugging Face
(``huggingface_hub``) ou d'un dépôt GitHub à un commit donné (``urllib``). ``RemoteFile``,
``file_sha256`` et ``verify_local_files`` (sans réseau) vivent dans ``questions/pinned.py`` et
sont réexportés ici. Chaque fichier porte son empreinte ``sha256`` attendue, versionnée dans
l'importeur. Un fichier déjà présent avec la bonne empreinte n'est pas retéléchargé. Une
empreinte différente, après téléchargement ou sur un fichier local modifié, supprime le fichier
et lève ``SourceIntegrityError`` : aucun candidat n'est alors écrit, et un nouveau ``fetch``
retélécharge le fichier. Les télémétries sont coupées avant l'import de ``huggingface_hub``
(``tests/unit/test_telemetry.py``).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path

from src.core.telemetry import disable_telemetry

disable_telemetry()

from huggingface_hub import hf_hub_download  # noqa: E402

from ..pinned import (  # noqa: E402 (réexportés : API de la story 2)
    RemoteFile,
    SourceIntegrityError,
    file_sha256,
    verify_local_files,
)

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_S = 120

__all__ = [
    "Downloader",
    "RemoteFile",
    "SourceIntegrityError",
    "default_downloader",
    "fetch_files",
    "file_sha256",
    "verify_local_files",
]

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
