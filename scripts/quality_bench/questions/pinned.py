"""Fichiers bruts épinglés (révision et empreinte), sans réseau.

``RemoteFile`` décrit un fichier d'un dépôt à une révision complète, avec son empreinte
``sha256`` attendue ; ``file_sha256`` la calcule sur disque. ``verify_local_files`` vérifie des
fichiers déjà téléchargés par ``fetch`` et ne télécharge jamais : c'est la porte des fichiers
bruts pour ``build-set``, qui n'a aucun accès réseau (AD-12, AD-15). Le téléchargement vit dans
``importers/remote.py``, qui réexporte ce module.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..common.canonical import sha256_bytes


class SourceIntegrityError(RuntimeError):
    """Fichier brut absent ou d'empreinte inattendue (source modifiée, fichier corrompu)."""


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


def file_sha256(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.is_file() else None


def verify_local_files(
    files: Iterable[RemoteFile], raw_dir: Path, fetch_hint: str = "fetch"
) -> dict[RemoteFile, Path]:
    """Rend le chemin local de chaque fichier, après vérification de son empreinte.

    Ne télécharge jamais et ne modifie rien : un fichier absent ou d'empreinte inattendue
    lève ``SourceIntegrityError``, dont le message nomme le fichier et la commande ``fetch`` à
    lancer (``fetch_hint``).
    """
    result: dict[RemoteFile, Path] = {}
    for remote in files:
        path = remote.local_path(raw_dir)
        actual = file_sha256(path)
        if actual is None:
            raise SourceIntegrityError(
                f"Fichier brut absent : {path} ({remote.url}) ; lancer "
                f"`python -m scripts.quality_bench {fetch_hint}`"
            )
        if actual != remote.sha256:
            raise SourceIntegrityError(
                f"Empreinte inattendue pour le fichier local {path} : {actual} au lieu de "
                f"{remote.sha256} ; relancer `python -m scripts.quality_bench {fetch_hint}`"
            )
        result[remote] = path
    return result
