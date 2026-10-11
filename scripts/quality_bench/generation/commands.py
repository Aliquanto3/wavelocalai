"""Sous-commande ``generate --campaign <c> [--ollama-url <url>]`` (AD-7, AD-8, AD-12 à AD-14) :
seule à écrire ``campaigns/<c>/manifest.json``, ``generation.jsonl`` et ``warmups.jsonl``.

Étapes : configuration ``campaigns/<c>.yaml`` ; jeu ``sets/<set>/`` et son empreinte ; plan
(sélection, paliers) ; ``machine.lock`` ; version d'Ollama et préflight de chaque modèle
(``/api/tags``, ``/api/show``) ; ``generation.lock`` ; manifeste écrit ou comparé (liste de
contrôle d'AD-13 consignée dans ``informative.checklist`` et affichée) ; ``keep_awake()`` ;
``StopFlag`` ; boucle du runner.

Codes de sortie : 0 (campagne complète, ou arrêt propre par Ctrl+C ou ``STOP``) ; 1 (jeu absent
ou incohérent, verrou occupé, Ollama injoignable au lancement, manifeste différent à la reprise,
service toujours absent ou revenu dans une autre version, trop d'erreurs de suite) ; 2
(configuration invalide, sélection ou palier hors jeu, préflight refusé, URL non locale).

Jusqu'à l'acceptation du préflight, le journal ne va qu'à la console : un lancement refusé
n'écrit aucun fichier de campagne. Ensuite ``campaigns/<c>/log-generate.log`` : identifiants,
statuts et comptes, jamais de contenu de question ni de réponse.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..common import config, paths
from ..common.jsonl import JsonlReadError, open_for_append, read_jsonl
from ..common.keepawake import keep_awake
from ..common.locks import FileLock, LockBusyError
from ..common.logs import setup_logging
from ..common.manifest import (
    ManifestMismatchError,
    blocking_hash,
    build_manifest,
    collect_informative,
    ensure_manifest,
)
from ..common.stop import StopFlag
from ..ollama.client import DEFAULT_BASE_URL, OllamaClient, OllamaError, check_local_base_url
from ..questions.schema import set_hash
from .preflight import LaunchError, check_launch, find_tag, resolve_model
from .runner import GenerationAbortedError, Runner, SetError, build_plan

logger = logging.getLogger(__name__)

COMMAND = "generate"
# Liste de contrôle d'avant campagne (AD-13), consignée dans informative.checklist.
CHECKLIST_REMINDERS = (
    "Mises à jour automatiques d'Ollama coupées",
    "Windows Update en pause pour la durée de la campagne",
    "OLLAMA_NUM_PARALLEL absent ou à 1 pour le service Ollama",
    "Aucun autre usage du GPU",
    "Données NLTK et dépendances installées",
)
NUM_PARALLEL_ENV = "OLLAMA_NUM_PARALLEL"

# Points d'injection des tests (Ollama simulé, attente sans horloge réelle) : lus à l'appel.
SLEEP: Callable[[float], None] = time.sleep
CLOCK: Callable[[], float] = time.monotonic


def make_client(base_url: str) -> OllamaClient:
    """Client Ollama de la campagne (remplacé par les tests pour simuler le service)."""
    return OllamaClient(base_url)


class GenerateError(RuntimeError):
    """Lancement impossible ou campagne interrompue : code 1."""


def checklist() -> dict[str, Any]:
    """Rappels d'AD-13 et valeur de ``OLLAMA_NUM_PARALLEL`` vue par ce processus."""
    return {
        "reminders": list(CHECKLIST_REMINDERS),
        "ollama_num_parallel": os.environ.get(NUM_PARALLEL_ENV),
    }


def _log_checklist(items: Mapping[str, Any]) -> None:
    logger.info("Liste de contrôle d'avant campagne (AD-13) :")
    for reminder in items["reminders"]:
        logger.info("  - %s", reminder)
    value = items["ollama_num_parallel"]
    if value not in (None, "", "1"):
        logger.warning(
            "%s=%s dans l'environnement de ce processus (celui du service Ollama peut "
            "différer) : la campagne exige une seule file (absent ou 1) côté service",
            NUM_PARALLEL_ENV,
            value,
        )


def load_set(set_id: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any], str]:
    """Questions par ``id``, ``tracks.json`` et empreinte du jeu ; ``GenerateError`` s'il manque
    ou s'il est illisible."""
    questions_path = paths.set_questions_path(set_id)
    tracks_path = paths.set_tracks_path(set_id)
    if not questions_path.exists() or not tracks_path.exists():
        raise GenerateError(f"jeu {set_id} absent : {questions_path.parent} (lancer build-set)")
    try:
        questions = read_jsonl(questions_path)
        with open(tracks_path, encoding="utf-8") as handle:
            tracks = json.load(handle)
        digest = set_hash(questions, tracks)
    except (JsonlReadError, OSError, ValueError, KeyError, TypeError) as exc:
        raise GenerateError(f"jeu {set_id} illisible ({type(exc).__name__})") from None
    if not isinstance(tracks, dict):
        raise GenerateError(f"jeu {set_id} : tracks.json n'est pas un objet")
    return {question["id"]: question for question in questions}, tracks, digest


def preflight(client: OllamaClient, models: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """``models_resolved`` de chaque modèle, dans l'ordre de la configuration ; ``LaunchError``
    au premier refus."""
    tags = client.tags()
    resolved = []
    for model in models:
        if find_tag(tags, model["tag"]) is None:
            resolve_model(model, {}, tags)  # lève LaunchError (modèle absent de /api/tags)
        resolved.append(resolve_model(model, client.show(model["tag"]), tags))
        logger.info(
            "Préflight %s : capacités %s, pistes %s, num_ctx_max effectif %d",
            model["tag"],
            ",".join(resolved[-1]["capabilities"]),
            ",".join(resolved[-1]["tracks"]),
            resolved[-1]["num_ctx_max"],
        )
    return resolved


def generate_campaign(campaign: str, base_url: str = DEFAULT_BASE_URL) -> bool:
    """Lance ou reprend la campagne ; rend ``False`` après un arrêt propre (code 0 aussi)."""
    config_path = paths.campaign_config_path(campaign)
    if not config_path.exists():
        raise config.ConfigError(f"configuration de campagne absente : {config_path}")
    campaign_config = config.load_campaign(config_path)
    generation = campaign_config.generation
    questions, tracks, digest = load_set(campaign_config.set_id)
    plan = build_plan(generation, questions, tracks)
    logger.info(
        "Campagne %s, jeu %s : %d question(s) think_off, %d think_on sélectionnée(s)",
        campaign,
        campaign_config.set_id,
        len(plan["think_off"]),
        len(plan["think_on"]),
    )

    with FileLock(paths.machine_lock_path()):
        client = make_client(base_url)
        try:
            ollama_version = client.version()
            models_resolved = preflight(client, generation["models"])
            check_launch(models_resolved, plan)
            with FileLock(paths.generation_lock_path(campaign)) as generation_lock:
                setup_logging(COMMAND, paths.log_path(campaign, COMMAND))
                logger.info(
                    "Lancement de generate : campagne %s, jeu %s, Ollama %s, %d modèle(s)",
                    campaign,
                    campaign_config.set_id,
                    ollama_version,
                    len(models_resolved),
                )
                items = checklist()
                _log_checklist(items)
                manifest = build_manifest(
                    phase="generation",
                    campaign=campaign,
                    set_info={
                        "id": campaign_config.set_id,
                        "hash": digest,
                        "n": {track: len(tracks[track]) for track in ("think_off", "think_on")},
                    },
                    generation={
                        "hash": campaign_config.generation_hash,
                        "resolved": generation,
                    },
                    models_resolved=models_resolved,
                    ollama_version=ollama_version,
                    informative=collect_informative(checklist=items),
                )
                existing = ensure_manifest(paths.generation_manifest_path(campaign), manifest)
                manifest_hash = blocking_hash(existing)
                with (
                    keep_awake(),
                    StopFlag(paths.generation_stop_path(campaign)) as stop,
                    open_for_append(paths.generation_path(campaign), generation_lock) as lines,
                    open_for_append(paths.warmups_path(campaign), generation_lock) as warmups,
                ):
                    runner = Runner(
                        client=client,
                        campaign=campaign,
                        generation=generation,
                        models=models_resolved,
                        plan=plan,
                        manifest_hash=manifest_hash,
                        ollama_version=ollama_version,
                        generations=lines,
                        warmups=warmups,
                        stop=stop,
                        sleep=SLEEP,
                        clock=CLOCK,
                    )
                    completed = runner.run()
        finally:
            client.close()
    if completed:
        logger.info("Campagne %s : génération complète", campaign)
    else:
        logger.info("Campagne %s : arrêt propre, reprise par la même commande", campaign)
    return completed


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign", required=True, help="identifiant de la campagne")
    parser.add_argument(
        "--ollama-url",
        default=DEFAULT_BASE_URL,
        help=f"URL locale d'Ollama (défaut : {DEFAULT_BASE_URL})",
    )


def _run(args: argparse.Namespace) -> int:
    setup_logging(COMMAND, None)  # console seule jusqu'à l'acceptation du préflight
    try:
        paths.check_id(args.campaign, "campagne")
        base_url = check_local_base_url(args.ollama_url)
    except ValueError as exc:
        logger.error("Lancement refusé : %s", exc)
        return 2
    try:
        generate_campaign(args.campaign, base_url)
    except (config.ConfigError, LaunchError) as exc:
        logger.error("Lancement refusé, rien n'est écrit : %s", exc)
        return 2
    except (GenerateError, SetError, LockBusyError) as exc:
        logger.error("Lancement impossible : %s", exc)
        return 1
    except (ManifestMismatchError, GenerationAbortedError) as exc:
        logger.error("%s", exc)
        return 1
    except OllamaError as exc:
        logger.error(
            "Ollama : %s ; arrêt, aucune ligne n'est écrite pour la question en cours, "
            "s'il y en a une",
            exc,
        )
        return 1
    except JsonlReadError as exc:
        logger.error("Fichier de campagne illisible : %s", exc)
        return 1
    return 0


GENERATE = (
    COMMAND,
    "Générer une campagne sur Ollama (deux pistes, reprenable) : écrit campaigns/<c>/",
    _configure,
    _run,
)
