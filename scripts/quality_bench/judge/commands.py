"""Sous-commande ``judge --campaign <c> --judge <id> [--max-cost-usd X]`` (CAP-5, AD-2, AD-8,
AD-12, AD-13, AD-15, AD-16) : seule à écrire ``campaigns/<c>/judgment-<id>/``.

Étapes : juge lu dans ``judges.yaml`` ; entrées (manifeste de génération, ``generation.jsonl``,
jeu) ; unités = critères des réponses de rédaction au statut ``ok`` ; juge cloud : refus de
toute question privée avant tout envoi ; ``machine.lock`` ; juge local : ``/api/ps`` d'Ollama
(un modèle chargé autre que le juge refuse le lancement, Ollama injoignable n'est qu'un
avertissement) ; ``judgment.lock`` ; manifeste ``phase = judgment`` écrit ou comparé ;
``keep_awake()`` ; ``StopFlag(judgment-<id>/STOP)`` lu entre deux unités ; boucle du juge ;
à toute sortie d'un juge local, ``keep_alive: 0`` sur Ollama (``unload_after``, au mieux).

Codes de sortie :
- 0 : jugement complet, ou arrêt propre (Ctrl+C, ``STOP``) ;
- 1 : entrées incohérentes, verrou occupé, modèle de génération chargé, manifeste différent à
  la reprise, question privée pour un juge cloud, service en panne après ``max_attempts``
  essais, lot refusé par l'API ;
- 2 : configuration invalide (``judges.yaml``, juge inconnu, ``endpoint`` nul, URL locale non
  locale, clé d'API absente de l'environnement, ``--max-cost-usd`` manquant pour un juge
  cloud) : rien n'est écrit ;
- 3 : plafond ``--max-cost-usd`` atteint avant un envoi (reprenable).

Journal ``campaigns/<c>/log-judge.log`` (après la prise des verrous ; console seule avant) :
identifiants, statuts, comptes et coûts, jamais de texte de question ni de réponse.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import time
from collections import Counter
from collections.abc import Callable
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
from ..ollama.client import OllamaClient, OllamaError, check_local_base_url
from .base import (
    CostCapError,
    Judge,
    JudgeError,
    JudgeInputError,
    JudgeLaunchError,
    PrivateQuestionError,
    Session,
)
from .pricing import Budget
from .prompt import prompt_template_hash
from .units import Unit, load_inputs

logger = logging.getLogger(__name__)

COMMAND = "judge"

# Points d'injection des tests (faux serveurs, faux clients, attente sans horloge réelle).
SLEEP: Callable[[float], None] = time.sleep


def make_transport() -> Any:
    """Transport ``httpx2`` du juge ``/v1/systemone`` et d'Ollama (``None`` : réseau réel)."""
    return None


def make_ollama_client(base_url: str) -> OllamaClient:
    return OllamaClient(base_url, transport=make_transport(), connect_timeout_s=5.0)


def make_anthropic_client(judge: config.JudgeConfig, api_key: str) -> Any:
    from .haiku import make_client

    return make_client(judge, api_key)


def make_openai_client(judge: config.JudgeConfig, api_key: str) -> Any:
    from .mimo import make_client

    return make_client(judge, api_key)


class JudgeConfigError(JudgeError):
    """Lancement refusé par la configuration ou l'environnement : code 2, rien n'est écrit."""


def resolve_judge(judge_id: str) -> config.JudgeConfig:
    judges = config.load_judges(paths.judges_config_path())
    if judge_id not in judges:
        raise JudgeConfigError(f"juge inconnu {judge_id!r} (connus : {sorted(judges)})")
    judge = judges[judge_id]
    if judge.endpoint is None:
        raise JudgeConfigError(
            f"juge {judge_id} : endpoint nul dans judges.yaml (point d'accès à renseigner)"
        )
    if judge.local:
        try:
            check_local_base_url(judge.endpoint)
            check_local_base_url(judge.options["ollama_url"])
        except ValueError as exc:
            raise JudgeConfigError(f"juge {judge_id} : {exc}") from None
    elif not judge.endpoint.startswith("https://"):
        raise JudgeConfigError(f"juge {judge_id} : point d'accès hébergé en https attendu")
    return judge


def api_key(judge: config.JudgeConfig) -> str | None:
    """Clé d'API lue dans ``os.environ`` (nom donné par ``api_key_env``), jamais écrite."""
    name = judge.options.get("api_key_env")
    if judge.local or name is None:
        return None
    value = os.environ.get(name, "").strip()
    if not value:
        raise JudgeConfigError(f"juge {judge.id} : variable d'environnement {name} absente ou vide")
    return value


def build_judge(judge: config.JudgeConfig, key: str | None) -> Judge:
    if judge.kind == "systemone":
        if judge.local:
            from .systemone import SystemOneJudge

            return SystemOneJudge(judge, SLEEP, transport=make_transport())
        from .decider import DeciderJudge

        return DeciderJudge(judge, SLEEP, api_key=key, transport=make_transport())
    if judge.kind == "anthropic_batch":
        from .haiku import HaikuJudge

        return HaikuJudge(judge, SLEEP, make_anthropic_client(judge, key or ""))
    from .mimo import MimoJudge

    return MimoJudge(judge, SLEEP, make_openai_client(judge, key or ""))


def check_private(judge: config.JudgeConfig, units: list[Unit]) -> None:
    """Juge cloud : ``PrivateQuestionError`` avant tout envoi si une unité est privée."""
    if not judge.cloud:
        return
    private = sorted({unit.question_id for unit in units if unit.private})
    if private:
        raise PrivateQuestionError(
            f"juge cloud {judge.id} : {len(private)} question(s) privée(s) parmi les unités "
            f"(première : {private[0]}) ; rien n'est envoyé (AD-15)"
        )


def _same_model(loaded: str, model: str) -> bool:
    def normalized(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    return normalized(loaded) == normalized(model)


def check_loaded_models(judge: config.JudgeConfig, client: OllamaClient) -> None:
    """Juge local : refuse le lancement si ``/api/ps`` liste un modèle autre que le juge."""
    try:
        loaded = client.ps()
    except OllamaError as exc:
        logger.warning(
            "Ollama injoignable sur %s (%s) : contrôle des modèles chargés impossible, "
            "lancement permis",
            judge.options["ollama_url"],
            exc,
        )
        return
    names = [str(entry.get("name") or entry.get("model") or "") for entry in loaded]
    names = [name for name in names if name]
    others = sorted(name for name in names if not _same_model(name, judge.model))
    if others:
        raise JudgeLaunchError(
            f"modèle(s) chargé(s) dans Ollama autre(s) que le juge {judge.model} : "
            f"{', '.join(others)} (VRAM de 8 Go) ; les décharger avant le jugement"
        )


def unload_local_judge(judge: config.JudgeConfig, client: OllamaClient) -> None:
    """``keep_alive: 0`` sur le modèle du juge local, au mieux (jamais une erreur)."""
    try:
        client.unload(judge.model)
    except OllamaError as exc:
        logger.warning("Déchargement de %s impossible (%s)", judge.model, exc)
    else:
        logger.info("Modèle du juge %s déchargé (keep_alive: 0)", judge.model)


def manifest_judge(judge: config.JudgeConfig) -> dict[str, Any]:
    """``blocking.judge`` du manifeste (AD-8)."""
    return {
        "id": judge.id,
        "config_hash": judge.config_hash,
        "endpoint": judge.endpoint,
        "model": judge.model,
        "settings": dict(judge.settings),
        "prompt_template_hash": prompt_template_hash(judge.kind),
        "weights_sha256": judge.weights_sha256,
        "server_version": judge.server_version,
    }


def judge_campaign(campaign: str, judge_id: str, max_cost_usd: float | None = None) -> bool:
    """Lance ou reprend le jugement ; ``False`` après un arrêt propre (code 0 aussi)."""
    judge = resolve_judge(judge_id)
    if judge.cloud and max_cost_usd is None:
        raise JudgeConfigError(f"juge cloud {judge_id} : --max-cost-usd obligatoire")
    key = api_key(judge)
    if judge.local and judge.weights_sha256 is None:
        logger.warning(
            "Juge local %s sans weights_sha256 dans judges.yaml : le manifeste du jugement ne "
            "portera pas l'empreinte des poids (à relever à l'import, comparée à SHA256SUMS)",
            judge_id,
        )
    inputs = load_inputs(campaign)
    check_private(judge, inputs.units)
    logger.info(
        "Campagne %s, juge %s : %d réponse(s) de rédaction au statut ok, %d critère(s) à juger",
        campaign,
        judge_id,
        inputs.writing_lines,
        len(inputs.units),
    )

    with FileLock(paths.machine_lock_path()):
        ollama = make_ollama_client(judge.options["ollama_url"]) if judge.local else None
        engine: Judge | None = None
        checked = False
        try:
            if ollama is not None:
                check_loaded_models(judge, ollama)
                checked = True
            with FileLock(paths.judgment_lock_path(campaign, judge_id)) as judgment_lock:
                setup_logging(COMMAND, paths.log_path(campaign, COMMAND))
                logger.info(
                    "Lancement de judge : campagne %s, juge %s (%s, %s), plafond %s",
                    campaign,
                    judge_id,
                    judge.kind,
                    judge.model,
                    "aucun (local)" if max_cost_usd is None else f"{max_cost_usd:g} $",
                )
                generation = inputs.manifest["blocking"]
                manifest = build_manifest(
                    phase="judgment",
                    campaign=campaign,
                    set_info=generation["set"],
                    generation=generation["generation"],
                    models_resolved=generation["models_resolved"],
                    ollama_version=generation["ollama_version"],
                    judge=manifest_judge(judge),
                    generation_manifest=inputs.manifest_hash,
                    informative=collect_informative(
                        prices=None if judge.prices is None else {"judge": judge_id, **judge.prices}
                    ),
                )
                existing = ensure_manifest(
                    paths.judgment_manifest_path(campaign, judge_id), manifest
                )
                manifest_hash = blocking_hash(existing)
                engine = build_judge(judge, key)
                budget = Budget(max_cost_usd if judge.cloud else None)
                with (
                    keep_awake(),
                    StopFlag(paths.judgment_stop_path(campaign, judge_id)) as stop,
                    open_for_append(
                        paths.judgment_path(campaign, judge_id), judgment_lock
                    ) as lines,
                ):
                    batches = (
                        open_for_append(paths.batches_path(campaign, judge_id), judgment_lock)
                        if judge.kind == "anthropic_batch"
                        else None
                    )
                    try:
                        session = Session(
                            judge_id=judge_id,
                            manifest_hash=manifest_hash,
                            writer=lines,
                            stop=stop,
                            budget=budget,
                            sleep=SLEEP,
                            batches=batches,
                        )
                        pending = [unit for unit in inputs.units if unit.key not in lines]
                        logger.info(
                            "%d critère(s) déjà jugé(s), %d à juger",
                            len(inputs.units) - len(pending),
                            len(pending),
                        )
                        try:
                            completed = engine.run(pending, session)
                        finally:
                            _log_summary(session, lines.path, budget)
                    finally:
                        if batches is not None:
                            batches.close()
        finally:
            if engine is not None:
                engine.close()
            if ollama is not None:
                if checked and judge.options["unload_after"]:
                    unload_local_judge(judge, ollama)
                ollama.close()
    if completed:
        logger.info("Campagne %s, juge %s : jugement complet", campaign, judge_id)
    else:
        logger.info(
            "Campagne %s, juge %s : arrêt propre, reprise par la même commande", campaign, judge_id
        )
    return completed


def _log_summary(session: Session, path: Any, budget: Budget) -> None:
    counts: Counter[str] = Counter()
    try:
        for line in read_jsonl(path):
            counts[
                "error" if line.get("error") is not None else str(line.get("verdict")).lower()
            ] += 1
    except JsonlReadError:
        return
    logger.info(
        "Ce lancement : %d ligne(s) écrite(s) dont %d en erreur, %.4f $ dépensés ; "
        "fichier : %d vrai(s), %d faux, %d erreur(s)",
        session.written,
        session.errors,
        budget.spent,
        counts["true"],
        counts["false"],
        counts["error"],
    )


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"nombre attendu : {text!r}") from None
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"nombre fini ≥ 0 attendu : {text!r}")
    return value


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign", required=True, help="identifiant de la campagne")
    parser.add_argument("--judge", required=True, help="identifiant du juge (judges.yaml)")
    parser.add_argument(
        "--max-cost-usd",
        type=_positive_float,
        default=None,
        help="plafond de dépense de ce lancement en USD (obligatoire pour un juge cloud)",
    )


def _run(args: argparse.Namespace) -> int:
    setup_logging(COMMAND, None)  # console seule jusqu'à la prise des verrous
    try:
        paths.check_id(args.campaign, "campagne")
        paths.check_id(args.judge, "juge")
    except ValueError as exc:
        logger.error("Lancement refusé : %s", exc)
        return 2
    try:
        judge_campaign(args.campaign, args.judge, args.max_cost_usd)
    except (config.ConfigError, JudgeConfigError) as exc:
        logger.error("Lancement refusé, rien n'est écrit : %s", exc)
        return 2
    except CostCapError as exc:
        logger.error("Arrêt sur plafond : %s", exc)
        return 3
    except (JudgeInputError, PrivateQuestionError, JudgeLaunchError, LockBusyError) as exc:
        logger.error("Lancement impossible : %s", exc)
        return 1
    except (ManifestMismatchError, JsonlReadError) as exc:
        logger.error("%s", exc)
        return 1
    except JudgeError as exc:
        logger.error("Jugement interrompu : %s", exc)
        return 1
    return 0


JUDGE = (
    COMMAND,
    "Juger la rédaction d'une campagne (un dossier judgment-<juge>/ par juge, reprenable)",
    _configure,
    _run,
)
