"""Sous-commandes ``calibrate`` et ``calibrate-sample`` (CAP-6, AD-3, AD-16) : calibration du
juge, en lecture seule, sans réseau ni verrou.

Seul module du banc qui lit ``judgment-<id>/judgment.jsonl``, ``batches.jsonl`` et
``calibration/labels.jsonl`` (AD-3). Entrées : ``report.inputs.load_inputs(c, partial=True)``
(configuration, manifeste, jeu, familles par ``models_resolved[].family``), puis
``generation.jsonl`` relu (lignes au manifeste concordant) : une unité jugeable par critère d'une
ligne ``usage = writing`` et ``status = ok`` (même règle que ``judge/units.py``).

- ``calibrate --campaign <c> [--min-agreement x] [--max-qwen-bias y] [--cascade-margins …]
  [--projected-judgments n]`` écrit ``campaigns/<c>/calibration-report.{md,json}`` (temporaires
  puis ``os.replace``) : accord, biais Qwen, coût, cascade Winnow → Haiku par marge, stabilité
  au rejeu, et une proposition seulement si les deux seuils sont fournis.
- ``calibrate-sample --campaign <c> [--size 100] [--seed 0]`` écrit
  ``calibration/labels-todo-<c>.jsonl`` (lignes ``qb.label/1`` à étiqueter) et
  ``labels-todo-<c>.md`` (consigne, réponse et critère de chaque item : seul fichier qui en
  contient, sous ``data/``).

Jamais d'écriture de ``labels.jsonl``, ``judgment.jsonl``, ``grading.jsonl`` ni sous
``benchmarks/`` ; aucun juge, ni Ollama, ni réseau, ni ``machine.lock``.

Codes de sortie : 0 ; 1 si les entrées sont incohérentes (ligne hors schéma, de jugement d'un
autre manifeste ou d'un autre juge, clé inconnue ou en double, étiquette invalide, BOM ou
dernière ligne sans fin de ligne ou date impossible dans ``labels.jsonl``, ``judgment.jsonl``
sans ``manifest.json``, ``labels-todo-<c>.jsonl`` déjà en partie rempli, échantillon sans unité
jugeable) : rien n'est écrit ; 2 si ``campaigns/<c>.yaml`` est absent ou invalide, ou si un
réglage est hors bornes. Journaux ``log-calibrate.log`` et ``log-calibrate-sample.log`` : identifiants, comptes
et chemins, jamais de texte de question ni de réponse.
"""

from __future__ import annotations

import argparse
import codecs
import datetime
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..common import config, paths
from ..common.canonical import canonical_bytes, pretty_bytes
from ..common.logs import setup_logging
from ..common.manifest import blocking_hash
from .calibration_markdown import render_calibration, render_labels_todo
from .calibration_measures import (
    DEFAULT_MARGINS,
    DEFAULT_PROJECTED_JUDGMENTS,
    REPLAY_SUFFIX,
    JudgeData,
    Labels,
    Unit,
    Verdict,
    build_report,
    draw_sample,
    is_counting,
)
from .inputs import CampaignInputs, ReportError, _read_manifest, load_inputs
from .pilot_commands import _lines, _validated, _write_atomic

logger = logging.getLogger(__name__)

COMMAND = "calibrate"
SAMPLE_COMMAND = "calibrate-sample"
JUDGMENT_PREFIX = "judgment-"
DEFAULT_SAMPLE_SIZE = 100
DEFAULT_SEED = 0
_TODO_FIELDS = ("label", "author", "labeled_at", "note")


# -- Consigne et réponse vues par le juge (reprises de judge/prompt.py, test d'égalité) -----


def render_instruction(messages: Sequence[Mapping[str, Any]]) -> str:
    """Consigne : messages de la question rendus ``rôle : contenu``."""
    return "\n\n".join(f"{message['role']} : {message['content']}" for message in messages)


def final_answer(output: Sequence[Mapping[str, Any]]) -> str:
    """Contenu verbatim du dernier message ``assistant`` (chaîne vide s'il n'y en a aucun)."""
    for message in reversed(output):
        if message.get("role") == "assistant":
            return str(message.get("content") or "")
    return ""


# -- Lecture --------------------------------------------------------------------------------


def read_units(inputs: CampaignInputs) -> tuple[list[Unit], dict[str, dict[str, Any]]]:
    """Unités jugeables (ordre des clés) et lignes de génération de rédaction ``ok`` retenues,
    par clé de génération."""
    campaign = inputs.campaign
    expected = {item.key for item in inputs.expected}
    families = {model["tag"]: model["family"] for model in inputs.models}
    units: list[Unit] = []
    records: dict[str, dict[str, Any]] = {}
    path = paths.generation_path(campaign)
    for line_no, record in enumerate(_lines(path, f"{campaign} generation.jsonl"), start=1):
        if record["manifest"] != inputs.generation_hash or record["key"] not in expected:
            continue  # écartée et comptée par load_inputs
        if record["usage"] != "writing" or record["status"] != "ok":
            continue
        question = inputs.questions[record["question_id"]]
        criteria = question.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise ReportError(
                f"generation.jsonl ligne {line_no} : question de rédaction sans critères"
            )
        records[record["key"]] = record
        for criterion in criteria:
            if "check" in criterion:
                continue  # vérifié par le code : ni jugé, ni étiqueté, ni calibré
            units.append(
                Unit(
                    key=f"{record['key']}|{criterion['id']}",
                    generation_key=record["key"],
                    model=record["model"],
                    qwen=families.get(record["model"]) == "qwen",
                    question_id=record["question_id"],
                    track=record["track"],
                    criterion=criterion["id"],
                    counting=is_counting(criterion["question"]),
                    private=bool(question.get("private")),
                )
            )
    units.sort(key=lambda unit: unit.key)
    return units, records


def judgment_ids(campaign: str) -> list[str]:
    """Identifiants des dossiers ``judgment-<id>/`` de la campagne (ordre alphabétique)."""
    directory = paths.campaign_dir(campaign)
    if not directory.is_dir():
        return []
    ids = []
    for entry in sorted(directory.iterdir()):
        if not entry.is_dir() or not entry.name.startswith(JUDGMENT_PREFIX):
            continue
        judge_id = entry.name[len(JUDGMENT_PREFIX) :]
        try:
            paths.check_id(judge_id, "juge")
        except ValueError:
            logger.warning("Dossier %s ignoré : identifiant de juge invalide", entry.name)
            continue
        ids.append(judge_id)
    return ids


def read_judge(
    campaign: str, judge_id: str, generation_hash: str, unit_keys: frozenset[str]
) -> JudgeData:
    """Dossier ``judgment-<id>/`` contrôlé comme dans ``grading/commands._load_judgments`` :
    sans manifeste, « absent » ; manifeste d'une autre génération, « discordant » (exclu, sans
    échec) ; toute autre incohérence lève ``ReportError``."""
    manifest_path = paths.judgment_manifest_path(campaign, judge_id)
    if not manifest_path.exists():
        if paths.judgment_path(campaign, judge_id).exists():
            raise ReportError(f"judgment-{judge_id} : judgment.jsonl sans manifest.json")
        return JudgeData(judge_id, "absent")
    manifest = _read_manifest(manifest_path, "judgment", f"manifeste de jugement {judge_id}")
    judge = manifest["blocking"]["judge"]
    if judge["id"] != judge_id:
        raise ReportError(f"judgment-{judge_id} : manifeste d'un autre juge ({judge['id']})")
    manifest_hash = blocking_hash(manifest)
    generation_manifest = manifest["blocking"]["generation_manifest"]
    if generation_manifest != generation_hash:
        logger.warning(
            "judgment-%s : jugement d'un autre manifeste de génération, juge exclu", judge_id
        )
        return JudgeData(
            judge_id,
            "discordant",
            manifest_hash=manifest_hash,
            judge=judge,
            generation_manifest=generation_manifest,
        )
    verdicts: dict[str, Verdict] = {}
    path = paths.judgment_path(campaign, judge_id)
    for line_no, line in enumerate(_lines(path, f"judgment-{judge_id}"), start=1):
        where = f"judgment-{judge_id}/judgment.jsonl ligne {line_no}"
        _validated(line, "qb.judgment/1", where)
        if line["manifest"] != manifest_hash:
            raise ReportError(f"{where} : produite par un autre manifeste")
        if line["judge"] != judge_id:
            raise ReportError(f"{where} : juge {line['judge']} au lieu de {judge_id}")
        if line["key"] != f"{line['generation_key']}|{line['criterion']}":
            raise ReportError(f"{where} : clé incohérente avec generation_key et criterion")
        if line["key"] not in unit_keys:
            raise ReportError(f"{where} : clé {line['key']} inconnue des unités jugeables")
        if line["key"] in verdicts:
            raise ReportError(f"{where} : clé en double {line['key']}")
        probability = line["probability"]
        verdicts[line["key"]] = Verdict(
            verdict=line["verdict"],
            probability=None if probability is None else float(probability),
            cost_usd=float(line["cost_usd"]),
        )
    batch_costs: list[float] = []
    seen: set[str] = set()
    path = paths.batches_path(campaign, judge_id)
    for line_no, line in enumerate(_lines(path, f"judgment-{judge_id} batches"), start=1):
        where = f"judgment-{judge_id}/batches.jsonl ligne {line_no}"
        _validated(line, "qb.batch/1", where)
        if line["manifest"] != manifest_hash:
            raise ReportError(f"{where} : produite par un autre manifeste")
        if line["judge"] != judge_id:
            raise ReportError(f"{where} : juge {line['judge']} au lieu de {judge_id}")
        if line["key"] in seen:
            raise ReportError(f"{where} : clé en double {line['key']}")
        seen.add(line["key"])
        if line["status"] == "collected":
            batch_costs.append(float(line["cost_usd"]))
    return JudgeData(
        judge_id,
        "present",
        manifest_hash=manifest_hash,
        judge=judge,
        generation_manifest=generation_manifest,
        verdicts=verdicts,
        batch_costs=tuple(batch_costs),
    )


def read_judges(
    campaign: str, generation_hash: str, unit_keys: frozenset[str]
) -> dict[str, JudgeData]:
    return {
        judge_id: read_judge(campaign, judge_id, generation_hash, unit_keys)
        for judge_id in judgment_ids(campaign)
    }


def _check_labeled_at(value: str | None, where: str) -> None:
    """Date réelle : le schéma ne vérifie que la forme (``2026-13-45`` y passe)."""
    if value is None:
        return
    # strptime plutôt que fromisoformat : celui-ci accepte ``24:00:00`` depuis Python 3.11.
    layout = "%Y-%m-%dT%H:%M:%SZ" if "T" in value else "%Y-%m-%d"
    try:
        datetime.datetime.strptime(value, layout)
    except ValueError:
        raise ReportError(f"{where} : labeled_at {value} n'est pas une date réelle") from None


def _check_hand_edited(path: Path) -> None:
    """Fichier rempli à la main : BOM UTF-8 en tête ou dernière ligne sans fin de ligne refusés
    (``read_jsonl`` ignorerait la dernière ligne)."""
    name = path.name
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ReportError(f"{name} illisible : {path} ({type(exc).__name__})") from None
    if data.startswith(codecs.BOM_UTF8):
        raise ReportError(f"{name} : BOM UTF-8 en tête ({path}) ; l'enregistrer en UTF-8 sans BOM")
    if data and not data.endswith(b"\n"):
        raise ReportError(
            f"{name} : dernière ligne sans fin de ligne ({path}) ; read_jsonl ignorerait "
            "la dernière ligne : ajouter un retour à la ligne final"
        )


def read_labels(campaign: str, unit_keys: frozenset[str]) -> Labels:
    """Étiquettes ``qb.label/1`` de ``calibration/labels.jsonl`` ; fichier absent : aucune.

    BOM UTF-8 en tête ou dernière ligne sans fin de ligne : refusés (``read_jsonl`` ignorerait
    la dernière étiquette). Ligne hors schéma, clé en double, clé de la campagne qui n'est pas
    une unité jugeable : ``ReportError`` avec le numéro de ligne. Lignes d'autres campagnes,
    ``null`` et ``undecidable`` : comptées, hors de l'accord."""
    path = paths.labels_path()
    if not path.exists():
        return Labels(False, 0, {}, 0, 0, 0)
    _check_hand_edited(path)
    prefix = f"{campaign}|"
    values: dict[str, bool] = {}
    seen: set[str] = set()
    keys: set[str] = set()
    to_label = undecidable = other = 0
    records = _lines(path, "labels.jsonl")
    for line_no, record in enumerate(records, start=1):
        where = f"labels.jsonl ligne {line_no}"
        _validated(record, "qb.label/1", where)
        _check_labeled_at(record["labeled_at"], where)
        key = record["key"]
        if key in seen:
            raise ReportError(f"{where} : clé en double {key}")
        seen.add(key)
        if not key.startswith(prefix):
            other += 1
            continue
        if key not in unit_keys:
            raise ReportError(
                f"{where} : clé {key} de la campagne {campaign} qui n'est pas une unité jugeable"
            )
        keys.add(key)
        label = record["label"]
        if label is None:
            to_label += 1
        elif label == "undecidable":
            undecidable += 1
        else:
            values[key] = bool(label)
    return Labels(
        True, len(records), values, to_label, undecidable, other, campaign_keys=frozenset(keys)
    )


# -- Réglages -------------------------------------------------------------------------------


def _check_threshold(value: float | None, option: str) -> None:
    if value is not None and not 0 <= value <= 1:
        raise config.ConfigError(f"{option} hors de [0, 1] : {value}")


_MARGINS_FORMAT = " (point décimal, marges séparées par des virgules : 0,0.05,0.1)"


def parse_margins(text: str | None) -> tuple[float, ...]:
    """Marges de la cascade (``0,0.05,0.1`` : virgules entre les marges, point décimal) ;
    chacune dans [0, 0,5], deux décimales au plus (identifiant de la cascade)."""
    if text is None:
        return DEFAULT_MARGINS
    margins = set()
    for part in text.split(","):
        if not part.strip():
            continue
        try:
            value = float(part)
        except ValueError:
            raise config.ConfigError(
                f"--cascade-margins : nombre attendu, pas {part!r}{_MARGINS_FORMAT}"
            ) from None
        if not 0 <= value <= 0.5:
            raise config.ConfigError(
                f"--cascade-margins : marge hors de [0, 0.5] : {part.strip()}{_MARGINS_FORMAT}"
            )
        if abs(value * 100 - round(value * 100)) > 1e-9:
            raise config.ConfigError(
                f"--cascade-margins : deux décimales au plus (identifiant de la cascade) : "
                f"{part.strip()}{_MARGINS_FORMAT}"
            )
        margins.add(round(value, 2))
    if not margins:
        raise config.ConfigError(
            f"--cascade-margins : au moins une marge attendue{_MARGINS_FORMAT}"
        )
    return tuple(sorted(margins))


# -- calibrate ------------------------------------------------------------------------------


def calibrate_campaign(
    campaign: str,
    *,
    min_agreement: float | None = None,
    max_qwen_bias: float | None = None,
    margins: str | None = None,
    projected_judgments: int = DEFAULT_PROJECTED_JUDGMENTS,
) -> Path:
    """Calcule et écrit le rapport de calibration ; rend le chemin de ``calibration-report.md``.

    ``config.ConfigError`` (code 2) ; ``ReportError`` (code 1) : rien n'est écrit."""
    _check_threshold(min_agreement, "--min-agreement")
    _check_threshold(max_qwen_bias, "--max-qwen-bias")
    margin_values = parse_margins(margins)
    if projected_judgments < 1:
        raise config.ConfigError(
            f"--projected-judgments : entier ≥ 1 attendu ({projected_judgments})"
        )
    inputs = load_inputs(campaign, partial=True)
    units, _ = read_units(inputs)
    unit_keys = frozenset(unit.key for unit in units)
    judges = read_judges(campaign, inputs.generation_hash, unit_keys)
    labels = read_labels(campaign, unit_keys)
    report = build_report(
        campaign=campaign,
        generation_manifest=inputs.generation_hash,
        units=units,
        judges=judges,
        labels=labels,
        min_agreement=min_agreement,
        max_qwen_bias=max_qwen_bias,
        margins=margin_values,
        projected_judgments=projected_judgments,
    )
    target = paths.calibration_report_path(campaign, ".md")
    _write_atomic(
        {
            paths.calibration_report_path(campaign, ".json"): pretty_bytes(report),
            target: render_calibration(report).encode("utf-8"),
        }
    )
    _log_report(report, target)
    return target


def _log_report(report: Mapping[str, Any], target: Path) -> None:
    units, labels = report["units"], report["labels"]
    logger.info(
        "Unités jugeables : %d (Qwen %d, non-Qwen %d, comptage %d, privées %d)",
        units["total"],
        units["qwen"],
        units["non_qwen"],
        units["counting"],
        units["private"],
    )
    for judge in report["judges"]:
        logger.info(
            "Juge %s : %s, %d lignes, %d lots relevés",
            judge["id"],
            judge["status"],
            judge["lines"],
            judge["collected_batches"],
        )
    logger.info(
        "Étiquettes : %s, %d lignes, %d retenues, %d à étiqueter, %d indécidables, %d d'autres "
        "campagnes",
        "présentes" if labels["file_present"] else "absentes",
        labels["lines"],
        labels["used"],
        labels["to_label"],
        labels["undecidable"],
        labels["other_campaigns"],
    )
    logger.info("Cascade : %s", report["cascade"]["status"])
    proposal = report["proposal"]
    logger.info(
        "Proposition : %s",
        (
            "aucune (seuil non fixé)"
            if proposal is None
            else (proposal["id"] or "aucune configuration admissible")
        ),
    )
    logger.info("Rapport de calibration écrit dans %s", target.parent)


# -- calibrate-sample -----------------------------------------------------------------------


def calibrate_sample(
    campaign: str, *, size: int = DEFAULT_SAMPLE_SIZE, seed: int = DEFAULT_SEED
) -> Path:
    """Tire l'échantillon à étiqueter et écrit ``labels-todo-<c>.{jsonl,md}`` ; rend le chemin
    du ``.md``. ``config.ConfigError`` (code 2) ; ``ReportError`` (code 1) : rien n'est écrit."""
    if size < 1:
        raise config.ConfigError(f"--size : entier ≥ 1 attendu ({size})")
    jsonl_path = paths.labels_todo_path(campaign, ".jsonl")
    target = paths.labels_todo_path(campaign, ".md")
    if jsonl_path.exists():
        _check_hand_edited(jsonl_path)
    # Toute saisie compte : label, mais aussi author, labeled_at ou note posés avant le label.
    filled = [
        line_no
        for line_no, record in enumerate(_lines(jsonl_path, jsonl_path.name), start=1)
        if any(record.get(field) is not None for field in _TODO_FIELDS)
    ]
    if filled:
        raise ReportError(
            f"{jsonl_path.name} contient déjà des étiquettes (ligne {filled[0]}, "
            f"{len(filled)} au total) : l'ajouter à labels.jsonl ou le déplacer avant un "
            "nouveau tirage"
        )
    inputs = load_inputs(campaign, partial=True)
    units, records = read_units(inputs)
    unit_keys = frozenset(unit.key for unit in units)
    judges = read_judges(campaign, inputs.generation_hash, unit_keys)
    public = [unit for unit in units if not unit.private]
    public_keys = {unit.key for unit in public}
    # Seul un juge concordant hors rejeu qui a une ligne pour chaque unité publique restreint le
    # réservoir, aux clés où il rend un verdict booléen ; un juge partiel (plafond de coût,
    # arrêt) la ramènerait à quelques modèles : ignoré, avec sa couverture.
    restricting = []
    for judge_id, data in sorted(judges.items()):
        if not data.present or judge_id.endswith(REPLAY_SUFFIX):
            continue
        verdicts = data.verdicts or {}
        covered = sum(1 for key in public_keys if key in verdicts)
        if covered < len(public_keys):
            logger.info(
                "judgment-%s partiel (%d unités publiques sur %d) : ignoré pour réduire le "
                "réservoir",
                judge_id,
                covered,
                len(public_keys),
            )
            continue
        restricting.append(data)
    if not restricting:
        logger.warning(
            "Aucun juge complet : réservoir non réduit aux unités notées (toutes les unités "
            "publiques)"
        )
    reservoir = [
        unit
        for unit in public
        if all((data.verdicts or {})[unit.key].verdict is not None for data in restricting)
    ]
    labels = read_labels(campaign, unit_keys)
    already = [unit for unit in reservoir if unit.key in labels.campaign_keys]
    if already:
        reservoir = [unit for unit in reservoir if unit.key not in labels.campaign_keys]
        logger.info("%d unités déjà présentes dans labels.jsonl : écartées", len(already))
    logger.info(
        "Réservoir : %d unités jugeables publiques sur %d%s",
        len(reservoir),
        len(units),
        (
            " (verdicts booléens de " + ", ".join(data.id for data in restricting) + ")"
            if restricting
            else ""
        ),
    )
    if not reservoir:
        raise ReportError(
            f"aucune unité jugeable à échantillonner dans la campagne {campaign}"
            + (" (toutes déjà présentes dans labels.jsonl)" if already else "")
        )
    sample = draw_sample(reservoir, size, seed)
    for model in sorted(sample.quotas):
        if sample.drawn[model] < sample.quotas[model]:
            logger.warning(
                "Modèle %s : quota de %d non atteint, %d critères tirés (tout le modèle)",
                model,
                sample.quotas[model],
                sample.drawn[model],
            )
    label_lines = []
    items = []
    for number, unit in enumerate(sample.items, start=1):
        label_lines.append(
            {
                "schema": "qb.label/1",
                "key": unit.key,
                "label": None,
                "author": None,
                "labeled_at": None,
                "note": None,
            }
        )
        question = inputs.questions[unit.question_id]
        criterion = next(c for c in question["criteria"] if c["id"] == unit.criterion)
        items.append(
            {
                "number": number,
                "question_id": unit.question_id,
                "track": unit.track,
                "criterion": unit.criterion,
                "criterion_question": criterion["question"],
                "instruction": render_instruction(question["messages"]),
                "answer": final_answer(records[unit.generation_key]["output"]),
            }
        )
    markdown = render_labels_todo(campaign, items).encode("utf-8")
    jsonl_bytes = b"".join(canonical_bytes(line) + b"\n" for line in label_lines)
    # Un seul _write_atomic : le .jsonl et le .md (rang = numéro d'item) restent accordés.
    _write_atomic({jsonl_path: jsonl_bytes, target: markdown})
    logger.info(
        "Échantillon de %d critères (taille demandée %d, graine %d) : Qwen %d, non-Qwen %d ; "
        "par modèle : %s",
        len(sample.items),
        size,
        seed,
        sum(1 for unit in sample.items if unit.qwen),
        sum(1 for unit in sample.items if not unit.qwen),
        ", ".join(
            f"{model} {sample.drawn[model]}/{sample.quotas[model]}"
            for model in sorted(sample.quotas)
        ),
    )
    logger.info("Échantillon écrit dans %s et %s", jsonl_path, target)
    return target


# -- CLI ------------------------------------------------------------------------------------


def _configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign", required=True, help="identifiant de la campagne")
    parser.add_argument(
        "--min-agreement",
        type=float,
        default=None,
        metavar="X",
        help="accord minimal dans [0, 1] (aucune valeur par défaut : « seuil non fixé »)",
    )
    parser.add_argument(
        "--max-qwen-bias",
        type=float,
        default=None,
        metavar="Y",
        help="biais Qwen maximal en valeur absolue dans [0, 1] (aucune valeur par défaut)",
    )
    parser.add_argument(
        "--cascade-margins",
        default=None,
        metavar="M1,M2,…",
        help="marges de la cascade Winnow → Haiku dans [0, 0.5], séparées par des virgules "
        "(défaut : 0,0.05,…,0.5)",
    )
    parser.add_argument(
        "--projected-judgments",
        type=int,
        default=DEFAULT_PROJECTED_JUDGMENTS,
        metavar="N",
        help=f"jugements de la projection du coût (défaut : {DEFAULT_PROJECTED_JUDGMENTS})",
    )


def _configure_sample(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign", required=True, help="identifiant de la campagne")
    parser.add_argument(
        "--size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        metavar="N",
        help=f"nombre de critères à étiqueter (défaut : {DEFAULT_SAMPLE_SIZE})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        metavar="S",
        help=f"graine du tirage (défaut : {DEFAULT_SEED})",
    )


def _execute(command: str, campaign: str, action: Any, refused: str) -> int:
    try:
        log_file = paths.log_path(campaign, command)
    except ValueError as exc:
        setup_logging(command, None)
        logger.error("%s", exc)
        return 2
    setup_logging(command, log_file)
    try:
        action()
    except config.ConfigError as exc:
        logger.error("Configuration invalide : %s", exc)
        return 2
    except ReportError as exc:
        logger.error("%s, rien n'est écrit : %s", refused, exc)
        return 1
    return 0


def _run(args: argparse.Namespace) -> int:
    return _execute(
        COMMAND,
        args.campaign,
        lambda: calibrate_campaign(
            args.campaign,
            min_agreement=args.min_agreement,
            max_qwen_bias=args.max_qwen_bias,
            margins=args.cascade_margins,
            projected_judgments=args.projected_judgments,
        ),
        "Calibration refusée",
    )


def _run_sample(args: argparse.Namespace) -> int:
    return _execute(
        SAMPLE_COMMAND,
        args.campaign,
        lambda: calibrate_sample(args.campaign, size=args.size, seed=args.seed),
        "Échantillon refusé",
    )


CALIBRATE = (
    COMMAND,
    "Calibration du juge (accord avec les étiquettes, biais Qwen, coût, cascade Winnow → Haiku, "
    "stabilité au rejeu) : écrit campaigns/<c>/calibration-report.{md,json} (lecture seule, "
    "sans réseau ni verrou)",
    _configure,
    _run,
)

CALIBRATE_SAMPLE = (
    SAMPLE_COMMAND,
    "Échantillon de critères à étiqueter : écrit calibration/labels-todo-<c>.{jsonl,md} "
    "(lecture seule, sans réseau ni verrou)",
    _configure_sample,
    _run_sample,
)
