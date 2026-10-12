"""Sous-commande ``pilot --campaign <c> [--replay <c>-replay] [--aa-date AAAA-MM-JJ]`` (CAP-8) :
mesures du pilote, en lecture seule.

Elle lit ``campaigns/<c>.yaml``, les manifestes, ``generation.jsonl``, ``grading.jsonl`` (tel
quel), ``warmups.jsonl`` et ``log-generate.log`` du pilote et du rejeu (``<c>-replay`` par
défaut), le jeu, ``scripts/quality_bench/pilot.yaml``, l'ancien banc et le catalogue (chemins de
``pilot.yaml``, jamais modifiés) et un éventuel ``benchmarks/quality/references/aa-<date>.json``.
Elle n'écrit que ``campaigns/<c>/pilot-report.md``, ``pilot-report.json`` (temporaires puis
``os.replace``) et ``log-pilot.log``. Ni verrou machine, ni réseau, ni Ollama.

Codes de sortie : 0 (complétude publiée, jamais bloquante ; rejeu absent : section « rejeu
absent ») ; 1 si les entrées sont incohérentes (ligne hors schéma, jeu ou section ``generation``
hors ``selection`` différents entre pilote et rejeu, ancien banc ou catalogue illisible…) : rien
n'est écrit ; 2 si ``campaigns/<c>.yaml`` ou ``pilot.yaml`` est absent ou invalide, ou si le
rejeu désigne la campagne pilote elle-même. Journal : identifiants, comptes et chemins, jamais de
contenu de question ni de réponse.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..common import config, paths
from ..common.canonical import pretty_bytes, sha256_bytes, sha256_hex
from ..common.jsonl import JsonlReadError, read_jsonl
from ..common.logs import setup_logging
from ..common.schemas import SchemaValidationError, UnknownSchemaError, validate
from .commands import aa_date_argument
from .inputs import CampaignInputs, ReportError, load_inputs

if TYPE_CHECKING:  # import tardif à l'exécution : numpy, scipy et statsmodels (stats/)
    from .pilot import CampaignData

logger = logging.getLogger(__name__)

COMMAND = "pilot"
RETRY_MESSAGE = "Ollama ne répond plus"


# -- Lecture --------------------------------------------------------------------------------


def _validated(record: Any, expected: str, where: str) -> None:
    try:
        name = validate(record)
    except UnknownSchemaError:
        raise ReportError(f"{where} : champ « schema » absent ou inconnu") from None
    except SchemaValidationError as exc:
        raise ReportError(f"{where} : hors schéma (champ {exc.path}, {exc.kind})") from None
    if name != expected:
        raise ReportError(f"{where} : schéma {name} au lieu de {expected}")


def _lines(path: Path, where: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return read_jsonl(path)
    except JsonlReadError as exc:
        raise ReportError(f"{where} : {exc}") from None


def _reference(path: Path, label: str, where: str) -> tuple[Any, dict[str, str]]:
    """Fichier JSON de référence (lecture seule) et sa trace ``{path, sha256}``."""
    try:
        data = path.read_bytes()
        document = json.loads(data.decode("utf-8"))
    except FileNotFoundError:
        raise ReportError(f"{where} absent : {path}") from None
    except (OSError, ValueError) as exc:
        raise ReportError(f"{where} illisible : {path} ({type(exc).__name__})") from None
    if not isinstance(document, dict) or not isinstance(document.get("models"), dict):
        raise ReportError(f"{where} illisible : {path} (objet « models » attendu)")
    return document, {"path": label, "sha256": sha256_bytes(data)}


def _retries_in_log(campaign: str) -> int | None:
    path = paths.log_path(campaign, "generate")
    if not path.exists():
        return None
    with open(path, encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if RETRY_MESSAGE in line)


def campaign_data(inputs: CampaignInputs) -> CampaignData:
    """Faits des lignes concordantes, statuts de correction bruts, chauffes et journal."""
    from .pilot import CampaignData
    from .projection import Line, Warmup

    campaign = inputs.campaign
    expected = {item.key for item in inputs.expected}
    lines: dict[str, Line] = {}
    for record in _lines(paths.generation_path(campaign), f"{campaign} generation.jsonl"):
        if record["manifest"] != inputs.generation_hash or record["key"] not in expected:
            continue  # écartée et comptée par load_inputs
        question = inputs.questions[record["question_id"]]
        tokens, durations = record["tokens"], record["durations_ns"]
        lines[record["key"]] = Line(
            key=record["key"],
            model=record["model"],
            digest=record["digest"],
            track=record["track"],
            question_id=record["question_id"],
            usage=record["usage"],
            source=question["source"],
            num_ctx=record["num_ctx"],
            seed=record["seed"],
            status=record["status"],
            calls=record["calls"],
            attempts=record["attempts"],
            prompt=tokens["prompt"],
            prompt_cached=tokens["prompt_cached"],
            completion=tokens["completion"],
            thinking_est=tokens["thinking_est"],
            wall_s=float(record["wall_s"]),
            prompt_eval_ns=durations["prompt_eval"],
            eval_ns=durations["eval"],
            prompt_hash=record["prompt_hash"],
            output_hash=sha256_hex(record["output"]),
        )
    grading_status = {
        record["key"]: record["status"]
        for record in _lines(paths.grading_path(campaign), f"{campaign} grading.jsonl")
        if record.get("key") in lines
        and record.get("generation_manifest") == inputs.generation_hash
    }
    warmups = []
    path = paths.warmups_path(campaign)
    for line_no, record in enumerate(_lines(path, f"{campaign} warmups.jsonl"), start=1):
        _validated(record, "qb.warmup/1", f"{campaign} warmups.jsonl ligne {line_no}")
        if record["manifest"] != inputs.generation_hash or record["campaign"] != campaign:
            continue
        warmups.append(
            Warmup(
                model=record["model"],
                num_ctx=record["num_ctx"],
                prompt_tokens=record["prompt_tokens"],
                prefill_tok_s=record["prefill_tok_s"],
            )
        )
    return CampaignData(
        inputs=inputs,
        lines=lines,
        grading_status=grading_status,
        warmups=tuple(warmups),
        log_retries=_retries_in_log(campaign),
    )


def _full_tracks(set_id: str) -> dict[str, list[str]]:
    path = paths.set_tracks_path(set_id)
    try:
        tracks = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReportError(f"tracks.json du jeu {set_id} illisible ({type(exc).__name__})") from None
    return tracks


def _first_difference(a: Any, b: Any, where: str) -> str | None:
    """Chemin du premier champ différent entre deux valeurs JSON (clés triées), ou ``None``."""
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return f"{where}.{key}"
            found = _first_difference(a[key], b[key], f"{where}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return where
        for index, (x, y) in enumerate(zip(a, b, strict=True)):
            found = _first_difference(x, y, f"{where}[{index}]")
            if found is not None:
                return found
        return None
    return None if a == b and type(a) is type(b) else where


def _check_replay_generation(pilot: CampaignInputs, replay: CampaignInputs) -> None:
    """Le rejeu doit reprendre la section ``generation`` résolue du pilote, ``selection``
    exceptée (AD-4) : sinon ``ReportError`` qui nomme le premier champ différent."""

    def resolved(inputs: CampaignInputs) -> dict[str, Any]:
        section = dict(inputs.manifest["blocking"]["generation"]["resolved"])
        section.pop("selection", None)
        return section

    found = _first_difference(resolved(pilot), resolved(replay), "generation.resolved")
    if found is not None:
        raise ReportError(
            f"rejeu {replay.campaign} : section generation différente de celle du pilote "
            f"{pilot.campaign} (premier écart : {found})"
        )


def _load_replay(replay: str, pilot: CampaignInputs, aa_date: str | None) -> CampaignInputs | None:
    if not (
        paths.campaign_config_path(replay).exists()
        and paths.generation_manifest_path(replay).exists()
    ):
        logger.info(
            "Rejeu %s absent (configuration ou manifeste) : section « rejeu absent »", replay
        )
        return None
    inputs = load_inputs(replay, partial=True, aa_date=aa_date)
    if inputs.set_id != pilot.set_id or inputs.set_hash != pilot.set_hash:
        raise ReportError(f"jeu différent entre le pilote {pilot.campaign} et le rejeu {replay}")
    _check_replay_generation(pilot, inputs)
    return inputs


def _settings_trace(path: Path) -> dict[str, str]:
    """Chemin de ``pilot.yaml`` (relatif à la racine du dépôt s'il y est) et son ``sha256``."""
    try:
        label = path.resolve().relative_to(paths.REPO_ROOT).as_posix()
    except ValueError:
        label = path.as_posix()
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise config.ConfigError(f"réglage du pilote illisible : {path} ({exc})") from None
    return {"path": label, "sha256": sha256_bytes(data)}


# -- Écriture -------------------------------------------------------------------------------


def _write_atomic(files: Mapping[Path, bytes]) -> None:
    """Chaque fichier est écrit dans un temporaire voisin, puis tous sont mis en place par
    ``os.replace`` ; un échec avant le renommage laisse les anciens fichiers intacts."""
    temporaries = []
    try:
        for path, data in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.tmp")
            with open(tmp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            temporaries.append((tmp, path))
        for tmp, path in temporaries:
            os.replace(tmp, path)
    finally:
        for tmp, _ in temporaries:
            if tmp.exists():
                tmp.unlink()


def pilot_campaign(campaign: str, *, replay: str | None = None, aa_date: str | None = None) -> Path:
    """Calcule et écrit le rapport du pilote ; rend le chemin de ``pilot-report.md``.

    ``config.ConfigError`` (code 2) ; ``ReportError`` (code 1) : rien n'est écrit."""
    # Import tardif : numpy, scipy et statsmodels (stats/).
    from .pilot import build_pilot_report, old_bench_by_tag
    from .pilot_markdown import render_pilot

    settings = config.load_pilot_settings(paths.pilot_settings_path())
    replay_id = replay or f"{campaign}-replay"
    try:
        paths.check_id(replay_id, "campagne de rejeu")
    except ValueError as exc:
        raise config.ConfigError(str(exc)) from None
    if replay_id == campaign:
        raise config.ConfigError(f"campagne de rejeu identique à la campagne pilote : {campaign}")
    settings_trace = _settings_trace(settings.path)
    pilot_inputs = load_inputs(campaign, partial=True, aa_date=aa_date)
    replay_inputs = _load_replay(replay_id, pilot_inputs, aa_date)
    old_bench, old_trace = _reference(settings.old_bench_path, settings.old_bench, "ancien banc")
    catalog, catalog_trace = _reference(settings.catalog_path, settings.catalog, "catalogue")
    pilot_tags = [model["tag"] for model in pilot_inputs.models]
    tags = list(dict.fromkeys([*settings.full_models, *pilot_tags]))
    old = old_bench_by_tag(old_bench, catalog, tags)
    pilot = campaign_data(pilot_inputs)
    replay_data = None if replay_inputs is None else campaign_data(replay_inputs)
    report = build_pilot_report(
        pilot=pilot,
        replay=replay_data,
        replay_campaign=replay_id,
        full_tracks=_full_tracks(pilot_inputs.set_id),
        old=old,
        full_models=settings.full_models,
        settings=settings,
        references={"old_bench": old_trace, "catalog": catalog_trace, "settings": settings_trace},
    )
    markdown = render_pilot(report).encode("utf-8")
    target = paths.pilot_report_path(campaign, ".md")
    _write_atomic(
        {paths.pilot_report_path(campaign, ".json"): pretty_bytes(report), target: markdown}
    )
    for data in (pilot, replay_data):
        if data is not None:
            logger.info(
                "Complétude de %s : %s",
                data.inputs.campaign,
                data.inputs.completeness.summary_text(),
            )
    projection = report["projection"]
    logger.info(
        "Rapport du pilote écrit dans %s : projection %s h (budget %s h)%s, rejeu %s",
        target.parent,
        projection["total_hours"],
        projection["budget_hours"],
        "" if projection["complete"] else ", débit inconnu pour au moins un modèle",
        "absent" if replay_data is None else f"{report['stability']['joined']} paires jointes",
    )
    return target


# -- CLI ------------------------------------------------------------------------------------


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign", required=True, help="identifiant de la campagne pilote")
    parser.add_argument(
        "--replay",
        default=None,
        metavar="<c>-replay",
        help="campagne de rejeu (défaut : <campagne>-replay ; absente : section « rejeu absent »)",
    )
    parser.add_argument(
        "--aa-date",
        type=aa_date_argument,
        default=None,
        metavar="AAAA-MM-JJ",
        help="date du fichier benchmarks/quality/references/aa-<date>.json (le plus récent par "
        "défaut)",
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
        pilot_campaign(args.campaign, replay=args.replay, aa_date=args.aa_date)
    except config.ConfigError as exc:
        logger.error("Configuration invalide : %s", exc)
        return 2
    except ReportError as exc:
        logger.error("Rapport du pilote refusé, rien n'est écrit : %s", exc)
        return 1
    return 0


PILOT = (
    COMMAND,
    "Mesures du pilote (discordance, stabilité au rejeu, tokens, projection de durée) : écrit "
    "campaigns/<c>/pilot-report.{md,json} (lecture seule, sans réseau ni verrou)",
    _configure,
    _run,
)
