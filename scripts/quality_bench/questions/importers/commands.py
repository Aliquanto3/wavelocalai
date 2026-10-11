"""Sous-commandes d'avant campagne : ``fetch`` (jeux publics) et ``fetch-nltk`` (données NLTK).

``fetch`` télécharge aussi les lots bruts des générateurs (``RAW_BUNDLES`` : ``oneruler-fr``),
sous ``sources/<lot>/raw/``, sans écrire de candidats : ``build-set`` appelle les générateurs en
mémoire et se contente de vérifier ces fichiers. Toutes deux prennent ``machine.lock`` en
exclusif (AD-12) : aucun téléchargement pendant une génération ou un jugement. Les modules
d'importeurs (qui chargent ``huggingface_hub``) ne sont importés qu'à l'exécution, jamais au
chargement de la CLI.
"""

from __future__ import annotations

import argparse
import importlib
import logging

from ...common import paths
from ...common.jsonl import rewrite_jsonl
from ...common.locks import FileLock, LockBusyError
from ...common.logs import setup_logging
from ..generators import oneruler_fr
from ..schema import REFUSED_SOURCES, SOURCES

logger = logging.getLogger(__name__)

_IMPORTERS_PREFIX = "questions/importers/"

# Lots de fichiers bruts des générateurs : nom du lot → fichiers épinglés. Téléchargés par
# ``fetch`` sous ``sources/<lot>/raw/``, vérifiés (jamais téléchargés) par ``build-set``.
RAW_BUNDLES = {"oneruler-fr": oneruler_fr.RAW_FILES}


class UnknownSourceError(ValueError):
    """Source refusée ou hors de la liste fermée."""


def importable_slugs() -> list[str]:
    """Sources produites par un importeur de jeu public (les autres ont un générateur)."""
    return sorted(
        slug for slug, spec in SOURCES.items() if spec.producer.startswith(_IMPORTERS_PREFIX)
    )


def load_importer(slug: str):
    """Importeur d'une source : ``IMPORTERS[slug]`` du module producteur déclaré dans ``SOURCES``."""
    if slug in REFUSED_SOURCES:
        raise UnknownSourceError(f"Source refusée « {slug} » : {REFUSED_SOURCES[slug]}")
    if slug not in importable_slugs():
        raise UnknownSourceError(
            f"Source inconnue ou sans importeur : {slug!r} (sources importables : "
            f"{', '.join(importable_slugs())} ; lots bruts des générateurs : "
            f"{', '.join(sorted(RAW_BUNDLES))})"
        )
    module_path = SOURCES[slug].producer.removesuffix(".py").replace("/", ".")
    module = importlib.import_module(f"scripts.quality_bench.{module_path}")
    return module.IMPORTERS[slug]


def fetch_source(slug: str, downloader=None) -> int:
    """Télécharge les fichiers bruts de ``slug`` puis réécrit ses candidats ; rend leur nombre.

    Les anciens candidats sont supprimés d'abord : après un échec (empreinte, réseau,
    conversion), la source n'a plus de candidats plutôt que des candidats périmés.
    """
    from .remote import default_downloader, fetch_files

    importer = load_importer(slug)
    paths.candidates_path(slug).unlink(missing_ok=True)
    local = fetch_files(
        importer.files, paths.source_raw_dir(slug), downloader or default_downloader
    )
    questions = importer.convert({remote.path: path for remote, path in local.items()})
    count = rewrite_jsonl(paths.candidates_path(slug), questions)
    logger.info(
        "%s : %d questions candidates écrites dans %s", slug, count, paths.candidates_path(slug)
    )
    return count


def fetch_bundle(name: str, downloader=None) -> int:
    """Télécharge et vérifie les fichiers bruts du lot ``name`` ; rend leur nombre."""
    from .remote import default_downloader, fetch_files

    local = fetch_files(
        RAW_BUNDLES[name], paths.source_raw_dir(name), downloader or default_downloader
    )
    logger.info(
        "%s : %d fichiers bruts vérifiés sous %s", name, len(local), paths.source_raw_dir(name)
    )
    return len(local)


def fetchable_names() -> list[str]:
    """Sources importables puis lots bruts des générateurs (ordre de ``fetch --all``)."""
    return importable_slugs() + sorted(RAW_BUNDLES)


def _check_fetchable(name: str) -> None:
    if name not in RAW_BUNDLES:
        load_importer(name)


def _configure_fetch(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--source",
        action="append",
        metavar="<slug>",
        help="source à importer, ou lot brut d'un générateur (oneruler-fr) ; répétable",
    )
    group.add_argument(
        "--all", action="store_true", help="toutes les sources importables et les lots bruts"
    )


def _with_machine_lock(command: str, action) -> int:
    setup_logging(command, paths.sources_log_path(command))
    try:
        with FileLock(paths.machine_lock_path()):
            return action()
    except LockBusyError as error:
        logger.error(
            "%s : machine occupée (génération, jugement ou téléchargement en cours)", error
        )
        return 1
    except Exception:  # empreinte inattendue, réseau, source mal formée : journalisé, code 1
        logger.exception("%s interrompu ; les candidats déjà écrits restent valides", command)
        return 1


def _run_fetch(args: argparse.Namespace) -> int:
    slugs = fetchable_names() if args.all else list(dict.fromkeys(args.source))
    for slug in slugs:
        try:
            _check_fetchable(slug)
        except UnknownSourceError as error:
            setup_logging("fetch", paths.sources_log_path("fetch"))
            logger.error("%s", error)
            return 2

    def action() -> int:
        failed = []
        for slug in slugs:
            try:
                if slug in RAW_BUNDLES:
                    fetch_bundle(slug)
                else:
                    fetch_source(slug)
            except Exception:  # empreinte, réseau, conversion : journalisé, sources suivantes
                logger.exception("%s : import échoué, aucun candidat écrit", slug)
                failed.append(slug)
        if failed:
            logger.error(
                "Sources en échec (%d/%d) : %s", len(failed), len(slugs), ", ".join(failed)
            )
            return 1
        return 0

    return _with_machine_lock("fetch", action)


def _configure_fetch_nltk(parser: argparse.ArgumentParser) -> None:
    del parser  # aucune option


def _run_fetch_nltk(args: argparse.Namespace) -> int:
    del args
    from .nltk_data import fetch_nltk_data

    def action() -> int:
        root = paths.nltk_data_dir()
        for package, digest in fetch_nltk_data(root).items():
            logger.info("NLTK %s : sha256 %s", package, digest)
        logger.info("Données NLTK prêtes sous %s (variable NLTK_DATA)", root)
        return 0

    return _with_machine_lock("fetch-nltk", action)


FETCH = (
    "fetch",
    "Télécharge les jeux publics (révision et empreintes épinglées) et écrit leurs questions "
    "candidates sous $QUALITY_BENCH_DATA/sources/, ainsi que les fichiers bruts des "
    "générateurs (oneruler-fr) ; prend machine.lock.",
    _configure_fetch,
    _run_fetch,
)
FETCH_NLTK = (
    "fetch-nltk",
    "Télécharge les données NLTK (punkt, punkt_tab, stopwords, averaged_perceptron_tagger_eng) "
    "sous $QUALITY_BENCH_DATA/nltk_data ; prend machine.lock.",
    _configure_fetch_nltk,
    _run_fetch_nltk,
)

__all__ = [
    "FETCH",
    "FETCH_NLTK",
    "RAW_BUNDLES",
    "fetch_bundle",
    "fetch_source",
    "fetchable_names",
    "importable_slugs",
    "load_importer",
]
