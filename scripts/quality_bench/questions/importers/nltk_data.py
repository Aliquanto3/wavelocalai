"""Téléchargement des données NLTK d'avant campagne (AD-15) : ``fetch-nltk``.

Les vérificateurs IFBench et M-IFEval (story 4) lisent ``punkt``, ``punkt_tab``,
``stopwords`` et ``averaged_perceptron_tagger_eng`` sous ``$QUALITY_BENCH_DATA/nltk_data``
(variable ``NLTK_DATA``), sans jamais rien télécharger pendant une campagne. Seul ce module
appelle ``nltk.download`` ; chaque archive est vérifiée contre l'empreinte ``sha256`` épinglée
ci-dessous, et un paquet déjà présent avec la bonne empreinte n'est pas retéléchargé. Une
empreinte inattendue après téléchargement supprime l'archive et son dossier extrait, puis lève
``NltkDataError``. Le dossier extrait de chaque archive vérifiée est supprimé puis réextrait
du zip, à chaque exécution.
"""

from __future__ import annotations

import logging
import shutil
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...common.canonical import sha256_bytes

logger = logging.getLogger(__name__)

# Paquet → (sous-dossier, empreinte sha256 de l'archive, licence déclarée par l'index NLTK).
# Empreintes relevées au téléchargement du 2026-10-11 (nltk 3.10.3) ; un changement en amont
# fait échouer la commande au lieu d'installer en silence d'autres données. Les archives ne
# sont jamais versionnées : seules ces empreintes et ces licences le sont.
PACKAGES: dict[str, tuple[str, str, str]] = {
    "averaged_perceptron_tagger_eng": (
        "taggers",
        "6025f530624335c67d6547d44757b357b4e79bae030a0383e9887a92c1718f0b",
        "MIT License",
    ),
    "punkt": (
        "tokenizers",
        "51c3078994aeaf650bfc8e028be4fb42b4a0d177d41c012b6a983979653660ec",
        "Unknown",
    ),
    "punkt_tab": (
        "tokenizers",
        "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106",
        "Unknown",
    ),
    "stopwords": (
        "corpora",
        "48c0e52d8b52546e827f53761fb30300c0ab94f70660d28bd65ba0a86270946b",
        "Unknown",
    ),
}


class NltkDataError(RuntimeError):
    """Archive NLTK absente ou d'empreinte inattendue après téléchargement."""


def archive_path(root: Path, package: str) -> Path:
    subdir = PACKAGES[package][0]
    return root / subdir / f"{package}.zip"


def _archive_sha256(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.is_file() else None


def _nltk_download(package: str, download_dir: Path) -> bool:
    import nltk  # import local : seule la commande d'avant campagne en a besoin

    return bool(
        nltk.download(package, download_dir=str(download_dir), quiet=True, raise_on_error=True)
    )


def _remove_package(root: Path, package: str) -> None:
    """Supprime l'archive et le dossier extrait d'un paquet non conforme : NLTK ne doit jamais
    lire de données dont l'empreinte n'a pas été vérifiée."""
    path = archive_path(root, package)
    path.unlink(missing_ok=True)
    extracted = path.with_suffix("")
    if extracted.is_dir():
        shutil.rmtree(extracted)


def _extract(path: Path) -> None:
    """Réextrait une archive vérifiée : ``nltk.data.find`` lit le dossier extrait avant le
    zip, et seul le zip porte une empreinte ; le dossier n'est donc jamais réutilisé tel quel."""
    extracted = path.with_suffix("")
    if extracted.is_dir():
        shutil.rmtree(extracted)
    with zipfile.ZipFile(path) as archive:
        archive.extractall(path.parent)


def fetch_nltk_data(
    root: Path, download: Callable[[str, Path], Any] = _nltk_download
) -> dict[str, str]:
    """Télécharge et vérifie les paquets de ``PACKAGES`` sous ``root`` ; rend ``{paquet: sha256}``.

    ``download`` est injectable pour les tests (aucun réseau).
    """
    root.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}
    for package, (_subdir, expected, _license) in sorted(PACKAGES.items()):
        path = archive_path(root, package)
        actual = _archive_sha256(path)
        if actual == expected:
            logger.info("NLTK %s déjà présent, empreinte vérifiée", package)
        else:
            logger.info("Téléchargement NLTK de %s vers %s", package, root)
            download(package, root)
            actual = _archive_sha256(path)
        if actual is None:
            raise NltkDataError(f"Archive NLTK absente après téléchargement : {path}")
        if actual != expected:
            _remove_package(root, package)
            raise NltkDataError(
                f"Empreinte inattendue pour {path} : {actual} au lieu de {expected} ; archive et "
                "dossier extrait supprimés (données NLTK modifiées en amont : vérifier puis "
                "mettre à jour PACKAGES)"
            )
        _extract(path)
        result[package] = actual
    return result
