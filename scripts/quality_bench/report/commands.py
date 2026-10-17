"""Sous-commande ``report --campaign <c> [--partial] [--aa-date AAAA-MM-JJ]`` (AD-6, AD-17) :
seule à écrire ``benchmarks/quality/<c>/`` (``$QUALITY_BENCH_EXPORTS``).

Sans verrou machine ni réseau. Elle lit la configuration, le manifeste, le jeu,
``generation.jsonl``, ``grading.jsonl`` et un fichier de référence AA local
(``benchmarks/quality/references/aa-<AAAA-MM-JJ>.json``, le plus récent par défaut), vérifie la
complétude, agrège par unité statistique et réécrit le dossier d'export en entier : scores
``qb.score/1``, résumé ``qb.report/1``, copie du manifeste, rapport Markdown et graphiques SVG.

Codes de sortie : 0 ; 1 si les entrées sont incohérentes, ou si la campagne est incomplète ou
discordante sans ``--partial`` (rien n'est écrit) ; 2 si ``campaigns/<c>.yaml`` est absent ou
invalide. Journal ``campaigns/<c>/log-report.log`` : identifiants, comptes et écarts, jamais de
contenu de question ni de réponse.
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from ..common import config, paths
from ..common.logs import setup_logging
from ..common.schemas import LegacyCampaignError
from .inputs import IncompleteError, ReportError, load_inputs

logger = logging.getLogger(__name__)

COMMAND = "report"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def report_campaign(
    campaign: str,
    *,
    partial: bool = False,
    aa_date: str | None = None,
    common_min_coverage: float | None = None,
) -> Path:
    """Produit et écrit les exports de ``campaign`` ; rend le dossier écrit.

    ``config.ConfigError`` (code 2) ; ``ReportError`` ou ``IncompleteError`` (code 1) : rien
    n'est écrit."""
    # Import tardif : numpy, scipy et statsmodels (stats/), que les autres sous-commandes n'ont
    # pas à charger.
    from .campaign import COMMON_MIN_COVERAGE, build_summary
    from .charts import charts
    from .export import export_files, write_export_dir
    from .markdown import render

    try:
        target = paths.campaign_exports_dir(campaign)
    except ValueError as exc:
        raise ReportError(str(exc)) from None
    inputs = load_inputs(campaign, partial=partial, aa_date=aa_date)
    summary = build_summary(
        inputs,
        min_coverage=COMMON_MIN_COVERAGE if common_min_coverage is None else common_min_coverage,
    )
    files = export_files(inputs, summary, render(summary), charts(summary))
    write_export_dir(campaign, files)
    completeness = inputs.completeness
    logger.info(
        "Rapport%s écrit dans %s : %d fichiers, %d lignes retenues sur %d attendues",
        " partiel" if partial else "",
        target,
        len(files),
        completeness.retained,
        completeness.expected,
    )
    return target


def aa_date_argument(value: str) -> str:
    """Type argparse de ``--aa-date`` (``report`` et ``pilot``) : date ``AAAA-MM-JJ``."""
    if not _DATE_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(f"date AAAA-MM-JJ attendue, reçu {value!r}")
    return value


def coverage_argument(value: str) -> float:
    """Type argparse de ``--common-min-coverage`` : fraction dans ]0, 1]."""
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"fraction attendue, reçu {value!r}") from None
    if not 0 < number <= 1:
        raise argparse.ArgumentTypeError(f"fraction dans ]0, 1] attendue, reçu {value!r}")
    return number


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign", required=True, help="identifiant de la campagne")
    parser.add_argument(
        "--partial",
        action="store_true",
        help="publier malgré des lignes manquantes ou discordantes (écartées, comptées, rapport "
        "marqué partiel)",
    )
    parser.add_argument(
        "--aa-date",
        type=aa_date_argument,
        default=None,
        metavar="AAAA-MM-JJ",
        help="date du fichier benchmarks/quality/references/aa-<date>.json (le plus récent par "
        "défaut)",
    )
    parser.add_argument(
        "--common-min-coverage",
        type=coverage_argument,
        default=None,
        metavar="FRACTION",
        help="couverture minimale (unités définies / unités du périmètre) d'un modèle classé ; "
        "0,9 par défaut (AD-17)",
    )


def _run(args: argparse.Namespace) -> int:
    try:
        log_file = paths.log_path(args.campaign, COMMAND)
    except ValueError as exc:
        setup_logging(COMMAND, None)
        logger.error("%s", exc)
        return 2
    setup_logging(COMMAND, log_file)
    try:
        report_campaign(
            args.campaign,
            partial=args.partial,
            aa_date=args.aa_date,
            common_min_coverage=args.common_min_coverage,
        )
    except config.ConfigError as exc:
        logger.error("Configuration invalide : %s", exc)
        return 2
    except LegacyCampaignError as exc:
        logger.error("Rapport refusé, rien n'est écrit : %s", exc)
        return 2
    except IncompleteError as exc:
        logger.error("Rapport refusé (campagne incomplète), rien n'est écrit : %s", exc)
        return 1
    except ReportError as exc:
        logger.error("Rapport refusé, rien n'est écrit : %s", exc)
        return 1
    return 0


REPORT = (
    COMMAND,
    "Statistiques et rapport d'une campagne : réécrit benchmarks/quality/<c>/ (sans réseau ni "
    "verrou)",
    _configure,
    _run,
)
