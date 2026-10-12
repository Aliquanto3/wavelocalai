"""Sous-commande ``grade --campaign <c>`` (AD-3, AD-10, AD-16) : seule à écrire
``campaigns/<c>/grading.jsonl``.

Sans verrou machine ni réseau. Elle lit ``campaigns/<c>.yaml``, le manifeste et
``generation.jsonl`` de la campagne, le jeu ``sets/<set>/`` et, pour la rédaction, le seul
dossier ``judgment-<grading.judge>/``, puis réécrit ``grading.jsonl`` en entier : une ligne
``qb.grading/1`` canonique par ligne de génération, triée par ``key``, sans date. Deux passes
sur les mêmes entrées donnent des octets identiques.

Codes de sortie : 0 ; 1 si les entrées sont incohérentes (manifeste absent ou d'un autre jeu,
empreinte du jeu différente, question absente, ``prompt_hash`` différent, ligne de génération
ou de jugement d'un autre manifeste ou hors schéma, données NLTK absentes alors qu'une question
de consignes est à corriger) : rien n'est écrit ; 2 si
``campaigns/<c>.yaml`` est absent ou invalide. Journal ``campaigns/<c>/log-grade.log`` :
identifiants, statuts, comptes et raisons rédigées par le banc, jamais de contenu de question
ni de réponse.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..common import config, paths
from ..common.jsonl import JsonlReadError, read_jsonl, rewrite_jsonl
from ..common.logs import setup_logging
from ..common.manifest import blocking_hash
from ..common.schemas import SchemaValidationError, UnknownSchemaError, validate
from ..questions.schema import set_hash
from .base import WRITING_GRADER

logger = logging.getLogger(__name__)

COMMAND = "grade"
# Correcteurs qui lisent les données NLTK du banc (vérificateurs de consignes empruntés).
NLTK_GRADERS = ("ifbench", "mifeval_fr")


class GradeError(RuntimeError):
    """Entrées de correction incohérentes : rien n'est écrit (code 1)."""


@dataclass(frozen=True)
class Judgments:
    """Verdicts du juge retenu : empreinte de son manifeste et verdicts par clé de génération."""

    manifest_hash: str
    by_generation_key: dict[str, dict[str, dict[str, Any]]]


def _validated(record: Any, expected: str, where: str) -> None:
    # Message sans valeur : le chemin et le mot-clé en défaut seulement (une ligne de génération
    # porte la sortie du modèle, une question privée peut y figurer).
    try:
        name = validate(record)
    except UnknownSchemaError:
        raise GradeError(f"{where} : champ « schema » absent ou inconnu") from None
    except SchemaValidationError as exc:
        raise GradeError(f"{where} : hors schéma (champ {exc.path}, {exc.kind})") from None
    if name != expected:
        raise GradeError(f"{where} : schéma {name} au lieu de {expected}")


def _read_manifest(path: Any, phase: str, where: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except FileNotFoundError:
        raise GradeError(f"{where} absent : {path}") from None
    except (OSError, ValueError) as exc:
        raise GradeError(f"{where} illisible : {path} ({type(exc).__name__})") from None
    _validated(manifest, "qb.manifest/1", where)
    if manifest["phase"] != phase:
        raise GradeError(f"{where} : phase {manifest['phase']} au lieu de {phase}")
    return manifest


def _read_lines(path: Any, where: str) -> list[dict[str, Any]]:
    try:
        return read_jsonl(path)
    except JsonlReadError as exc:
        raise GradeError(f"{where} : {exc}") from None


def _load_set(set_id: str, manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    blocking_set = manifest["blocking"]["set"]
    if blocking_set["id"] != set_id:
        raise GradeError(
            f"jeu {set_id} de la configuration différent du jeu {blocking_set['id']} du manifeste"
        )
    questions_path = paths.set_questions_path(set_id)
    tracks_path = paths.set_tracks_path(set_id)
    if not questions_path.exists() or not tracks_path.exists():
        raise GradeError(f"jeu {set_id} absent : {questions_path.parent}")
    questions = _read_lines(questions_path, f"jeu {set_id}")
    try:
        with open(tracks_path, encoding="utf-8") as handle:
            tracks = json.load(handle)
    except (OSError, ValueError) as exc:
        raise GradeError(f"tracks.json du jeu {set_id} illisible ({type(exc).__name__})") from None
    try:
        computed = set_hash(questions, tracks)
    except (KeyError, TypeError, ValueError) as exc:
        raise GradeError(f"jeu {set_id} illisible ({type(exc).__name__})") from None
    if computed != blocking_set["hash"]:
        raise GradeError(f"empreinte du jeu {set_id} différente de celle du manifeste")
    by_id: dict[str, dict[str, Any]] = {}
    for question in questions:
        by_id[question["id"]] = question
    return by_id


def _check_generation(
    lines: list[dict[str, Any]],
    campaign: str,
    manifest_hash: str,
    questions: Mapping[str, Mapping[str, Any]],
) -> None:
    seen: set[str] = set()
    for line_no, line in enumerate(lines, start=1):
        where = f"generation.jsonl ligne {line_no}"
        _validated(line, "qb.generation/1", where)
        if line["manifest"] != manifest_hash:
            raise GradeError(f"{where} : produite par un autre manifeste")
        if line["campaign"] != campaign:
            raise GradeError(f"{where} : campagne {line['campaign']} au lieu de {campaign}")
        if line["key"] in seen:
            raise GradeError(f"{where} : clé en double {line['key']}")
        seen.add(line["key"])
        question = questions.get(line["question_id"])
        if question is None:
            raise GradeError(f"{where} : question {line['question_id']} absente du jeu")
        if line["prompt_hash"] != question["prompt_hash"]:
            raise GradeError(f"{where} : prompt_hash différent de la question {question['id']}")
        if line["usage"] != question["usage"]:
            raise GradeError(f"{where} : usage différent de la question {question['id']}")


def _load_judgments(
    campaign: str,
    judge: str | None,
    generation_hash: str,
    generations: Mapping[str, Mapping[str, Any]],
    questions: Mapping[str, Mapping[str, Any]],
) -> Judgments | None:
    """Verdicts du seul juge retenu, ou ``None`` sans juge désigné ou sans dossier."""
    if judge is None:
        logger.info("Aucun juge désigné (grading.judge) : rédaction en attente de jugement")
        return None
    manifest_path = paths.judgment_manifest_path(campaign, judge)
    lines_path = paths.judgment_path(campaign, judge)
    if not manifest_path.exists():
        if lines_path.exists():
            raise GradeError(f"judgment-{judge} : judgment.jsonl sans manifest.json")
        logger.info("Dossier judgment-%s absent : rédaction en attente de jugement", judge)
        return None
    manifest = _read_manifest(manifest_path, "judgment", f"manifeste de jugement {judge}")
    if manifest["blocking"]["generation_manifest"] != generation_hash:
        raise GradeError(f"judgment-{judge} : jugement d'un autre manifeste de génération")
    if manifest["blocking"]["judge"]["id"] != judge:
        raise GradeError(f"judgment-{judge} : manifeste d'un autre juge")
    manifest_hash = blocking_hash(manifest)
    by_key: dict[str, dict[str, dict[str, Any]]] = {}
    for line_no, line in enumerate(_read_lines(lines_path, f"judgment-{judge}"), start=1):
        where = f"judgment-{judge}/judgment.jsonl ligne {line_no}"
        _validated(line, "qb.judgment/1", where)
        if line["manifest"] != manifest_hash:
            raise GradeError(f"{where} : produite par un autre manifeste")
        if line["judge"] != judge:
            raise GradeError(f"{where} : juge {line['judge']} au lieu de {judge}")
        if line["key"] != f"{line['generation_key']}|{line['criterion']}":
            raise GradeError(f"{where} : clé incohérente avec generation_key et criterion")
        generation = generations.get(line["generation_key"])
        if generation is None:
            raise GradeError(f"{where} : clé de génération absente de generation.jsonl")
        question = questions[generation["question_id"]]
        if question["grader"]["name"] != WRITING_GRADER:
            raise GradeError(f"{where} : jugement d'une question hors rédaction")
        if line["criterion"] not in {item["id"] for item in question["criteria"]}:
            raise GradeError(f"{where} : critère inconnu de la question {question['id']}")
        criteria = by_key.setdefault(line["generation_key"], {})
        if line["criterion"] in criteria:
            raise GradeError(f"{where} : clé en double {line['key']}")
        criteria[line["criterion"]] = {"verdict": line["verdict"], "error": line["error"]}
    return Judgments(manifest_hash, by_key)


def grade_campaign(campaign: str) -> int:
    """Corrige la campagne ``campaign`` et réécrit ``grading.jsonl`` ; rend le nombre de lignes.

    ``config.ConfigError`` si la configuration est absente ou invalide ; ``GradeError`` si les
    entrées sont incohérentes (rien n'est écrit dans les deux cas)."""
    # Import tardif : les correcteurs chargent nltk et le code emprunté, que les autres
    # sous-commandes n'ont pas à charger.
    from .nlp import FETCH_COMMAND, missing_resources
    from .registry import grade_line

    config_path = paths.campaign_config_path(campaign)
    if not config_path.exists():
        raise config.ConfigError(f"configuration de campagne absente : {config_path}")
    campaign_config = config.load_campaign(config_path)
    manifest = _read_manifest(
        paths.generation_manifest_path(campaign), "generation", "manifeste de génération"
    )
    if manifest["campaign"] != campaign:
        raise GradeError(f"manifeste de la campagne {manifest['campaign']} au lieu de {campaign}")
    generation_hash = blocking_hash(manifest)
    questions = _load_set(campaign_config.set_id, manifest)
    generation_path = paths.generation_path(campaign)
    if not generation_path.exists():
        raise GradeError(f"generation.jsonl absent : {generation_path}")
    lines = _read_lines(generation_path, "generation.jsonl")
    _check_generation(lines, campaign, generation_hash, questions)
    generations = {line["key"]: line for line in lines}
    judgments = _load_judgments(
        campaign, campaign_config.grading["judge"], generation_hash, generations, questions
    )
    uses_nltk = any(
        questions[line["question_id"]]["grader"]["name"] in NLTK_GRADERS for line in lines
    )
    if uses_nltk:
        missing = missing_resources()
        if missing:
            raise GradeError(
                f"données NLTK absentes de {paths.nltk_data_dir()} : {', '.join(missing)} "
                f"(lancer {FETCH_COMMAND})"
            )

    records = []
    statuses: Counter[str] = Counter()
    for key in sorted(generations):
        generation = generations[key]
        question = questions[generation["question_id"]]
        writing = question["grader"]["name"] == WRITING_GRADER
        verdicts = None
        judgment_manifest = None
        if writing and judgments is not None and generation["status"] == "ok":
            verdicts = judgments.by_generation_key.get(key, {})
            judgment_manifest = judgments.manifest_hash
        graded = grade_line(question, generation, verdicts)
        if graded.record["status"] == "awaiting_judgment":
            judgment_manifest = None  # aucun verdict complet : la ligne n'a pas été jugée
        record = {
            **graded.record,
            "generation_manifest": generation_hash,
            "judgment_manifest": judgment_manifest,
        }
        validate(record)
        statuses[record["status"]] += 1
        if record["status"] in ("error", "non_compliant") and graded.reason:
            logger.info("%s : %s (%s)", key, record["status"], graded.reason)
        records.append(record)
    count = rewrite_jsonl(paths.grading_path(campaign), records)
    logger.info(
        "%d lignes corrigées : %s",
        count,
        ", ".join(f"{status} {statuses[status]}" for status in sorted(statuses)) or "aucune",
    )
    return count


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign", required=True, help="identifiant de la campagne")


def _run(args: argparse.Namespace) -> int:
    try:
        log_file = paths.log_path(args.campaign, COMMAND)
    except ValueError as exc:
        setup_logging(COMMAND, None)
        logger.error("%s", exc)
        return 2
    setup_logging(COMMAND, log_file)
    try:
        grade_campaign(args.campaign)
    except config.ConfigError as exc:
        logger.error("Configuration invalide : %s", exc)
        return 2
    except GradeError as exc:
        logger.error("Correction refusée, rien n'est écrit : %s", exc)
        return 1
    return 0


GRADE = (
    COMMAND,
    "Corriger une campagne : réécrit campaigns/<c>/grading.jsonl (sans réseau ni verrou)",
    _configure,
    _run,
)
