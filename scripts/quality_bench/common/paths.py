"""Chemins des données du banc (AD-2).

Racine : ``$QUALITY_BENCH_DATA``, par défaut ``<racine du dépôt>/data/quality_bench`` (ignoré
par git). La variable est relue à chaque appel : les tests la redirigent vers ``tmp_path``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

DATA_ENV = "QUALITY_BENCH_DATA"
PACKAGE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_DIR.parents[1]

# Identifiants de campagne et de juge : pas de séparateur de chemin, pas de « | » (clés AD-4).
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]*")


def check_id(value: str, what: str = "identifiant") -> str:
    """Refuse un identifiant qui sortirait de son dossier ou casserait une clé."""
    if not isinstance(value, str) or not _ID_RE.fullmatch(value) or ".." in value:
        raise ValueError(f"{what} invalide : {value!r} (lettres, chiffres, « . _ @ - »)")
    return value


def data_root() -> Path:
    """Racine des données : ``$QUALITY_BENCH_DATA`` ou ``data/quality_bench`` du dépôt."""
    override = os.environ.get(DATA_ENV)
    return Path(override) if override else REPO_ROOT / "data" / "quality_bench"


def machine_lock_path() -> Path:
    """Verrou machine exclusif : génération, jugement et ``build-set`` (AD-12)."""
    return data_root() / "machine.lock"


def campaign_dir(campaign: str) -> Path:
    return data_root() / "campaigns" / check_id(campaign, "campagne")


def campaign_config_path(campaign: str) -> Path:
    """YAML versionné de la campagne : ``scripts/quality_bench/campaigns/<c>.yaml``."""
    return PACKAGE_DIR / "campaigns" / f"{check_id(campaign, 'campagne')}.yaml"


def generation_manifest_path(campaign: str) -> Path:
    return campaign_dir(campaign) / "manifest.json"


def generation_path(campaign: str) -> Path:
    return campaign_dir(campaign) / "generation.jsonl"


def warmups_path(campaign: str) -> Path:
    return campaign_dir(campaign) / "warmups.jsonl"


def generation_lock_path(campaign: str) -> Path:
    return campaign_dir(campaign) / "generation.lock"


def generation_stop_path(campaign: str) -> Path:
    return campaign_dir(campaign) / "STOP"


def grading_path(campaign: str) -> Path:
    return campaign_dir(campaign) / "grading.jsonl"


def log_path(campaign: str, command: str) -> Path:
    """Journal d'une commande : ``campaigns/<c>/log-<commande>.log``."""
    return campaign_dir(campaign) / f"log-{check_id(command, 'commande')}.log"


def judges_config_path() -> Path:
    """YAML versionné des juges : ``scripts/quality_bench/judges.yaml`` (AD-8)."""
    return PACKAGE_DIR / "judges.yaml"


def judgment_dir(campaign: str, judge: str) -> Path:
    return campaign_dir(campaign) / f"judgment-{check_id(judge, 'juge')}"


def judgment_manifest_path(campaign: str, judge: str) -> Path:
    return judgment_dir(campaign, judge) / "manifest.json"


def judgment_path(campaign: str, judge: str) -> Path:
    return judgment_dir(campaign, judge) / "judgment.jsonl"


def batches_path(campaign: str, judge: str) -> Path:
    return judgment_dir(campaign, judge) / "batches.jsonl"


def judgment_lock_path(campaign: str, judge: str) -> Path:
    return judgment_dir(campaign, judge) / "judgment.lock"


def judgment_stop_path(campaign: str, judge: str) -> Path:
    return judgment_dir(campaign, judge) / "STOP"


# Sources du jeu de questions et données d'avant campagne (AD-2, AD-15).
def sources_dir() -> Path:
    """Racine des sources : ``sources/<slug>/`` par importeur ou générateur."""
    return data_root() / "sources"


def source_dir(slug: str) -> Path:
    return sources_dir() / check_id(slug, "source")


def source_raw_dir(slug: str) -> Path:
    """Fichiers bruts téléchargés d'une source, à la révision épinglée."""
    return source_dir(slug) / "raw"


def candidates_path(slug: str) -> Path:
    """Questions candidates ``qb.question/1`` d'une source (réécrit par son seul producteur)."""
    return source_dir(slug) / "candidates.jsonl"


def sources_log_path(command: str) -> Path:
    """Journal d'une commande de téléchargement : ``sources/log-<commande>.log``."""
    return sources_dir() / f"log-{check_id(command, 'commande')}.log"


def nltk_data_dir() -> Path:
    """Données NLTK du banc (``NLTK_DATA``) : ``$QUALITY_BENCH_DATA/nltk_data``."""
    return data_root() / "nltk_data"


# Jeux de questions (AD-2, AD-6) : données hors dépôt et index versionné.
EXPORTS_ENV = "QUALITY_BENCH_EXPORTS"


def set_config_path(set_id: str) -> Path:
    """YAML versionné du jeu : ``scripts/quality_bench/sets/<set>.yaml``."""
    return PACKAGE_DIR / "sets" / f"{check_id(set_id, 'jeu')}.yaml"


def sets_dir() -> Path:
    return data_root() / "sets"


def set_dir(set_id: str) -> Path:
    """Données du jeu (hors dépôt) : ``sets/<set>/``, écrit une fois par ``build-set``."""
    return sets_dir() / check_id(set_id, "jeu")


def set_questions_path(set_id: str) -> Path:
    return set_dir(set_id) / "questions.jsonl"


def set_tracks_path(set_id: str) -> Path:
    return set_dir(set_id) / "tracks.json"


def sets_log_path(command: str) -> Path:
    """Journal d'une commande sur les jeux : ``sets/log-<commande>.log``."""
    return sets_dir() / f"log-{check_id(command, 'commande')}.log"


def exports_root() -> Path:
    """Racine des exports versionnés : ``$QUALITY_BENCH_EXPORTS`` ou ``benchmarks/quality``."""
    override = os.environ.get(EXPORTS_ENV)
    return Path(override) if override else REPO_ROOT / "benchmarks" / "quality"


def set_index_dir(set_id: str) -> Path:
    return exports_root() / "sets" / check_id(set_id, "jeu")


def set_index_path(set_id: str) -> Path:
    """Index versionné du jeu (``qb.set_index/1``, liste blanche d'AD-6)."""
    return set_index_dir(set_id) / "index.jsonl"


# Exports d'une campagne et références hors ligne (AD-6, AD-17), écrits ou lus par report/.
# Dossiers réservés de benchmarks/quality/ : jamais un identifiant de campagne.
RESERVED_EXPORT_DIRS = ("sets", "references", "calibration")
_AA_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def campaign_exports_dir(campaign: str) -> Path:
    """Exports versionnés d'une campagne : ``benchmarks/quality/<c>/`` (réécrit par ``report``)."""
    check_id(campaign, "campagne")
    # Insensible à la casse : sous Windows, « References » désigne le dossier réservé.
    if campaign.casefold() in RESERVED_EXPORT_DIRS:
        raise ValueError(
            f"campagne invalide : {campaign!r} (dossier réservé de benchmarks/quality)"
        )
    return exports_root() / campaign


def references_dir() -> Path:
    """Références hors ligne versionnées : ``benchmarks/quality/references/``."""
    return exports_root() / "references"


def aa_reference_path(date: str) -> Path:
    """Indices Artificial Analysis datés : ``references/aa-<AAAA-MM-JJ>.json``."""
    if not isinstance(date, str) or not _AA_DATE_RE.fullmatch(date):
        raise ValueError(f"date invalide : {date!r} (AAAA-MM-JJ)")
    return references_dir() / f"aa-{date}.json"


def private_dir() -> Path:
    """Questions privées (hors dépôt) : ``$QUALITY_BENCH_DATA/private``."""
    return data_root() / "private"


def private_source_path(slug: str) -> Path:
    return private_dir() / f"{check_id(slug, 'source')}.yaml"


def review_dir() -> Path:
    """Échantillons de relecture (hors dépôt) : ``$QUALITY_BENCH_DATA/review``."""
    return data_root() / "review"
