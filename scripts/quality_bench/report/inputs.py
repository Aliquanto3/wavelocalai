"""Entrées du rapport (AD-3, AD-8, AD-17) : lecture, contrôles, clés attendues et complétude.

Lit ``campaigns/<c>.yaml``, le manifeste de génération, le jeu ``sets/<set>/``,
``generation.jsonl``, ``grading.jsonl``, le seul manifeste ``judgment-<grading.judge>/manifest.json``
(jamais ``judgment.jsonl`` ni ``labels.jsonl``) et un fichier de référence AA local.

- **Incohérence** (``ReportError``, code 1, jamais levée par ``--partial``) : manifeste absent ou
  d'un autre jeu, empreinte du jeu différente, ligne hors schéma, clé en double, question absente
  du jeu ou ``prompt_hash`` différent, clé de correction inconnue de la génération, référence AA
  hors schéma.
- **Complétude** : clés attendues = ``models_resolved`` × pistes du modèle × questions de la
  piste restreintes à ``selection`` × seeds (``seed_base + epoch``, ``epoch < k``), depuis le
  ``blocking`` du manifeste et le jeu. Clé manquante, ``awaiting_judgment`` ou empreinte
  discordante (ligne de génération, ``generation_manifest`` ou ``judgment_manifest`` de
  correction, empreinte de configuration) : ``IncompleteError`` (code 1), sauf avec
  ``--partial``, qui écarte et compte ces lignes et marque le rapport partiel.

Les messages ne portent que des chemins, des clés, des comptes et des noms de champ : jamais de
contenu de question ni de réponse.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..common import config, paths
from ..common.canonical import sha256_bytes
from ..common.jsonl import JsonlReadError, read_jsonl
from ..common.manifest import blocking_hash
from ..common.schemas import TRACKS, SchemaValidationError, UnknownSchemaError, validate
from ..common.selection import SelectionError, selected_ids
from ..questions.schema import set_hash

logger = logging.getLogger(__name__)

AA_FILE_RE = re.compile(r"aa-(\d{4}-\d{2}-\d{2})\.json")
MAX_ISSUES = 20


class ReportError(RuntimeError):
    """Entrées incohérentes : rien n'est écrit (code 1), même avec ``--partial``."""


class IncompleteError(RuntimeError):
    """Campagne incomplète ou discordante sans ``--partial`` : rien n'est écrit (code 1)."""


@dataclass(frozen=True)
class Expected:
    """Clé attendue : (modèle, piste, question, seed)."""

    key: str
    model: str
    track: str
    question_id: str
    seed: int


@dataclass(frozen=True)
class Row:
    """Ligne retenue : génération et correction concordantes d'une clé attendue."""

    key: str
    model: str
    digest: str
    track: str
    question_id: str
    seed: int
    status: str
    score: float | None
    success: bool | None
    metrics: dict[str, float]


@dataclass
class Completeness:
    expected: int = 0
    retained: int = 0
    generation_missing: int = 0
    generation_discordant: int = 0
    grading_missing: int = 0
    grading_discordant: int = 0
    awaiting_judgment: int = 0
    config_discordant: bool = False
    has_issues: bool = False
    issues: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        self.has_issues = True
        if len(self.issues) < MAX_ISSUES:  # le premier écart est nommé ; les autres comptés
            self.issues.append(message)

    def as_record(self) -> dict[str, Any]:
        return {
            "expected": self.expected,
            "retained": self.retained,
            "generation_missing": self.generation_missing,
            "generation_discordant": self.generation_discordant,
            "grading_missing": self.grading_missing,
            "grading_discordant": self.grading_discordant,
            "awaiting_judgment": self.awaiting_judgment,
            "config_discordant": self.config_discordant,
        }

    def summary_text(self) -> str:
        return (
            f"{self.expected} clés attendues, {self.retained} retenues ; génération : "
            f"{self.generation_missing} manquantes, {self.generation_discordant} discordantes ; "
            f"correction : {self.grading_missing} manquantes, {self.grading_discordant} "
            f"discordantes, {self.awaiting_judgment} en attente du juge ; configuration "
            f"{'discordante' if self.config_discordant else 'concordante'}"
        )


@dataclass(frozen=True)
class AAReference:
    """Indices AA datés lus hors ligne : chemin relatif à ``benchmarks/quality/``."""

    path: str
    sha256: str
    date: str
    entries: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CampaignInputs:
    campaign: str
    partial: bool
    set_id: str
    set_hash: str
    manifest: dict[str, Any]
    generation_hash: str
    judgment_hash: str | None
    k: int
    models: tuple[dict[str, Any], ...]
    questions: dict[str, dict[str, Any]]
    expected: tuple[Expected, ...]
    rows: dict[str, Row]
    completeness: Completeness
    aa_reference: AAReference | None


# -- Lecture --------------------------------------------------------------------------------


def _validated(record: Any, expected: str, where: str) -> None:
    # Message sans valeur : le chemin et le mot-clé en défaut seulement.
    try:
        name = validate(record)
    except UnknownSchemaError:
        raise ReportError(f"{where} : champ « schema » absent ou inconnu") from None
    except SchemaValidationError as exc:
        raise ReportError(f"{where} : hors schéma (champ {exc.path}, {exc.kind})") from None
    if name != expected:
        raise ReportError(f"{where} : schéma {name} au lieu de {expected}")


def _read_json(path: Path, where: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise ReportError(f"{where} absent : {path}") from None
    except (OSError, ValueError) as exc:
        raise ReportError(f"{where} illisible : {path} ({type(exc).__name__})") from None


def _read_manifest(path: Path, phase: str, where: str) -> dict[str, Any]:
    manifest = _read_json(path, where)
    _validated(manifest, "qb.manifest/1", where)
    if manifest["phase"] != phase:
        raise ReportError(f"{where} : phase {manifest['phase']} au lieu de {phase}")
    return manifest


def _read_lines(path: Path, where: str) -> list[dict[str, Any]]:
    """Lignes d'un JSONL ; fichier absent : aucune ligne (clés manquantes)."""
    if not path.exists():
        logger.info("%s absent : %s", where, path)
        return []
    try:
        return read_jsonl(path)
    except JsonlReadError as exc:
        raise ReportError(f"{where} : {exc}") from None


def _load_set(set_id: str, manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    blocking_set = manifest["blocking"]["set"]
    if blocking_set["id"] != set_id:
        raise ReportError(
            f"jeu {set_id} de la configuration différent du jeu {blocking_set['id']} du manifeste"
        )
    questions_path = paths.set_questions_path(set_id)
    tracks_path = paths.set_tracks_path(set_id)
    if not questions_path.exists() or not tracks_path.exists():
        raise ReportError(f"jeu {set_id} absent : {questions_path.parent}")
    try:
        questions = read_jsonl(questions_path)
    except JsonlReadError as exc:
        raise ReportError(f"jeu {set_id} : {exc}") from None
    tracks = _read_json(tracks_path, f"tracks.json du jeu {set_id}")
    try:
        computed = set_hash(questions, tracks)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ReportError(f"jeu {set_id} illisible ({type(exc).__name__})") from None
    if computed != blocking_set["hash"]:
        raise ReportError(f"empreinte du jeu {set_id} différente de celle du manifeste")
    by_id = {question["id"]: question for question in questions}
    for track in TRACKS:
        listed = tracks.get(track)
        if not isinstance(listed, list) or any(qid not in by_id for qid in listed):
            raise ReportError(f"tracks.json du jeu {set_id} : piste {track} illisible")
    _check_units(by_id)
    return by_id, tracks


def _check_units(questions: Mapping[str, Mapping[str, Any]]) -> None:
    """Une ``unit`` ne franchit ni un ``group`` ni un usage (AD-5)."""
    seen: dict[str, tuple[str, str]] = {}
    for qid in sorted(questions):
        question = questions[qid]
        info = (question["usage"], question["group"])
        if seen.setdefault(question["unit"], info) != info:
            raise ReportError(f"unité {question['unit']} : plusieurs groupes ou usages")


# -- Clés attendues -------------------------------------------------------------------------


def expected_keys(
    campaign: str,
    manifest: Mapping[str, Any],
    questions: Mapping[str, Mapping[str, Any]],
    tracks: Mapping[str, list[str]],
) -> tuple[list[Expected], int]:
    """Clés attendues, dans l'ordre du runner (modèle, piste, question, seed), et ``k``."""
    try:
        resolved = manifest["blocking"]["generation"]["resolved"]
        request = resolved["request"]
        k, seed_base = request["k"], request["seed_base"]
        selection = resolved["selection"]
    except (KeyError, TypeError):
        raise ReportError("manifeste : section generation.resolved illisible") from None
    if not (isinstance(k, int) and k >= 1 and isinstance(seed_base, int) and seed_base >= 0):
        raise ReportError("manifeste : generation.resolved.request.k ou seed_base invalide")
    try:
        selected = selected_ids(selection, questions, tracks["think_off"], tracks["think_on"])
    except SelectionError as exc:
        raise ReportError(f"manifeste : {exc}") from None
    except (KeyError, TypeError):
        raise ReportError("manifeste : generation.resolved.selection illisible") from None
    expected: list[Expected] = []
    for model in manifest["blocking"]["models_resolved"]:
        for track in TRACKS:
            if track not in model["tracks"]:
                continue
            ids = sorted(
                dict.fromkeys(qid for qid in tracks[track] if selected is None or qid in selected)
            )
            for qid in ids:
                for epoch in range(k):
                    seed = seed_base + epoch
                    key = f"{campaign}|{model['tag']}|{track}|{qid}|{seed}"
                    expected.append(Expected(key, model["tag"], track, qid, seed))
    return expected, k


# -- Références AA --------------------------------------------------------------------------


def _reject_constant(name: str) -> Any:
    """``NaN``, ``Infinity`` et ``-Infinity`` : aucune forme JSON, refusés (index non fini)."""
    raise ValueError(f"constante non finie {name}")


def _finite_float(text: str) -> float:
    """Nombre JSON décimal ; un littéral qui déborde (``1e999`` → ``inf``) est refusé."""
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"nombre non fini {text}")
    return value


def load_aa_reference(date: str | None) -> AAReference | None:
    """Fichier ``references/aa-<date>.json`` (le plus récent sans ``date``) ; ``None`` si aucun
    fichier. ``ReportError`` si la date demandée est absente ou si le fichier est hors schéma."""
    directory = paths.references_dir()
    if date is not None:
        try:
            path = paths.aa_reference_path(date)
        except ValueError as exc:
            raise ReportError(str(exc)) from None
        if not path.exists():
            raise ReportError(f"référence AA du {date} absente : {path}")
    else:
        candidates = (
            sorted(p for p in directory.iterdir() if p.is_file() and AA_FILE_RE.fullmatch(p.name))
            if directory.is_dir()
            else []
        )
        if not candidates:
            logger.info("Aucune référence AA sous %s : section Spearman sans indice", directory)
            return None
        path = candidates[-1]
    match = AA_FILE_RE.fullmatch(path.name)
    assert match is not None  # noqa: S101 (nom construit ou filtré ci-dessus)
    try:
        data = path.read_bytes()
        document = json.loads(
            data.decode("utf-8"), parse_constant=_reject_constant, parse_float=_finite_float
        )
    except (OSError, ValueError) as exc:
        raise ReportError(f"référence AA illisible : {path} ({type(exc).__name__})") from None
    where = f"référence AA {path.name}"
    _validated(document, "qb.aa_reference/1", where)
    if document["date"] != match.group(1):
        raise ReportError(f"{where} : date {document['date']} différente du nom du fichier")
    seen: set[tuple[str, str]] = set()
    for entry in document["entries"]:
        pair = (entry["tag"], entry["variant"])
        if pair in seen:
            raise ReportError(f"{where} : entrée en double ({entry['tag']}, {entry['variant']})")
        seen.add(pair)
    return AAReference(
        path=path.relative_to(paths.exports_root()).as_posix(),
        sha256=sha256_bytes(data),
        date=document["date"],
        entries=tuple(document["entries"]),
    )


# -- Contrôles ------------------------------------------------------------------------------


def _judgment_hash(
    campaign: str, judge: str | None, generation_hash: str, completeness: Completeness
) -> str | None:
    """Empreinte du manifeste du juge retenu, ou ``None`` (aucun juge, aucun dossier, ou
    jugement d'un autre manifeste de génération : écart consigné)."""
    if judge is None:
        return None
    path = paths.judgment_manifest_path(campaign, judge)
    if not path.exists():
        return None
    manifest = _read_manifest(path, "judgment", f"manifeste de jugement {judge}")
    if manifest["blocking"]["judge"]["id"] != judge:
        raise ReportError(f"judgment-{judge} : manifeste d'un autre juge")
    if manifest["blocking"]["generation_manifest"] != generation_hash:
        completeness.note(f"judgment-{judge} : jugement d'un autre manifeste de génération")
        return None
    return blocking_hash(manifest)


def _check_generation_line(
    line: Mapping[str, Any],
    where: str,
    campaign: str,
    questions: Mapping[str, Mapping[str, Any]],
) -> None:
    _validated(line, "qb.generation/1", where)
    if line["campaign"] != campaign:
        raise ReportError(f"{where} : campagne {line['campaign']} au lieu de {campaign}")
    question = questions.get(line["question_id"])
    if question is None:
        raise ReportError(f"{where} : question {line['question_id']} absente du jeu")
    if line["prompt_hash"] != question["prompt_hash"]:
        raise ReportError(f"{where} : prompt_hash différent de la question {question['id']}")
    for name in ("usage", "group", "unit"):
        if line[name] != question[name]:
            raise ReportError(f"{where} : {name} différent de la question {question['id']}")
    expected_key = (
        f"{campaign}|{line['model']}|{line['track']}|{line['question_id']}|{line['seed']}"
    )
    if line["key"] != expected_key:
        raise ReportError(f"{where} : clé incohérente avec ses champs")


def load_inputs(
    campaign: str, *, partial: bool = False, aa_date: str | None = None
) -> CampaignInputs:
    """Lit et contrôle les entrées de la campagne ``campaign``.

    ``config.ConfigError`` (code 2) si ``campaigns/<c>.yaml`` est absent ou invalide ;
    ``ReportError`` si les entrées sont incohérentes ; ``IncompleteError`` si la campagne est
    incomplète ou discordante sans ``partial``."""
    config_path = paths.campaign_config_path(campaign)
    if not config_path.exists():
        raise config.ConfigError(f"configuration de campagne absente : {config_path}")
    campaign_config = config.load_campaign(config_path)
    manifest = _read_manifest(
        paths.generation_manifest_path(campaign), "generation", "manifeste de génération"
    )
    if manifest["campaign"] != campaign:
        raise ReportError(f"manifeste de la campagne {manifest['campaign']} au lieu de {campaign}")
    generation_hash = blocking_hash(manifest)
    questions, tracks = _load_set(campaign_config.set_id, manifest)
    completeness = Completeness()
    if manifest["blocking"]["generation"]["hash"] != campaign_config.generation_hash:
        completeness.config_discordant = True
        completeness.note(
            "configuration modifiée : empreinte de la section generation différente de celle "
            "du manifeste (blocking.generation.hash)"
        )
    expected, k = expected_keys(campaign, manifest, questions, tracks)
    expected_by_key = {item.key: item for item in expected}
    completeness.expected = len(expected)
    models = tuple(manifest["blocking"]["models_resolved"])
    digests = {model["tag"]: model["digest"] for model in models}
    aa_reference = load_aa_reference(aa_date)

    # Génération : toute ligne lue, retenue si son manifeste concorde.
    generation_lines: dict[str, dict[str, Any]] = {}
    kept_generation: set[str] = set()
    path = paths.generation_path(campaign)
    for line_no, line in enumerate(_read_lines(path, "generation.jsonl"), start=1):
        where = f"generation.jsonl ligne {line_no}"
        _check_generation_line(line, where, campaign, questions)
        if line["key"] in generation_lines:
            raise ReportError(f"{where} : clé en double {line['key']}")
        generation_lines[line["key"]] = line
        if line["manifest"] != generation_hash:
            completeness.generation_discordant += 1
            completeness.note(f"{where} : produite par un autre manifeste")
            continue
        if line["key"] not in expected_by_key or line["digest"] != digests.get(line["model"]):
            raise ReportError(f"{where} : clé {line['key']} hors des clés attendues du manifeste")
        kept_generation.add(line["key"])

    judgment_hash = _judgment_hash(
        campaign, campaign_config.grading["judge"], generation_hash, completeness
    )

    # Correction : lignes retenues si leur génération l'est et si leurs empreintes concordent.
    grading_lines: dict[str, dict[str, Any]] = {}
    path = paths.grading_path(campaign)
    for line_no, line in enumerate(_read_lines(path, "grading.jsonl"), start=1):
        where = f"grading.jsonl ligne {line_no}"
        _validated(line, "qb.grading/1", where)
        if line["key"] in grading_lines:
            raise ReportError(f"{where} : clé en double {line['key']}")
        if line["key"] not in generation_lines:
            raise ReportError(f"{where} : clé {line['key']} inconnue de generation.jsonl")
        grading_lines[line["key"]] = line
        if line["key"] not in kept_generation:
            continue  # génération déjà écartée et comptée
        if line["generation_manifest"] != generation_hash:
            completeness.grading_discordant += 1
            completeness.note(f"{where} : generation_manifest d'un autre manifeste")
            continue
        if line["judgment_manifest"] is not None and line["judgment_manifest"] != judgment_hash:
            completeness.grading_discordant += 1
            completeness.note(f"{where} : judgment_manifest différent du juge retenu")
            continue

    rows: dict[str, Row] = {}
    for item in expected:
        if item.key not in generation_lines:
            completeness.generation_missing += 1
            completeness.note(f"clé absente de generation.jsonl : {item.key}")
            continue
        if item.key not in kept_generation:
            continue
        grading = grading_lines.get(item.key)
        if grading is None:
            completeness.grading_missing += 1
            completeness.note(f"clé absente de grading.jsonl : {item.key}")
            continue
        if grading["generation_manifest"] != generation_hash or (
            grading["judgment_manifest"] is not None
            and grading["judgment_manifest"] != judgment_hash
        ):
            continue
        if grading["status"] == "awaiting_judgment":
            completeness.awaiting_judgment += 1
            completeness.note(f"{item.key} : en attente du juge (awaiting_judgment)")
            continue  # écartée et comptée, comme une ligne manquante (unité nulle)
        rows[item.key] = Row(
            key=item.key,
            model=item.model,
            digest=digests[item.model],
            track=item.track,
            question_id=item.question_id,
            seed=item.seed,
            status=grading["status"],
            score=None if grading["score"] is None else float(grading["score"]),
            success=grading["success"],
            metrics={name: float(value) for name, value in grading["metrics"].items()},
        )
    completeness.retained = len(rows)

    if completeness.has_issues:
        logger.warning("Campagne incomplète ou discordante : %s", completeness.summary_text())
        logger.warning("Premier écart : %s", completeness.issues[0])
        if not partial:
            raise IncompleteError(
                f"{completeness.issues[0]} ({completeness.summary_text()}) ; relancer avec "
                "--partial pour publier un rapport partiel"
            )
    return CampaignInputs(
        campaign=campaign,
        partial=partial,
        set_id=campaign_config.set_id,
        set_hash=manifest["blocking"]["set"]["hash"],
        manifest=manifest,
        generation_hash=generation_hash,
        judgment_hash=judgment_hash,
        k=k,
        models=models,
        questions=questions,
        expected=tuple(expected),
        rows=rows,
        completeness=completeness,
        aa_reference=aa_reference,
    )
