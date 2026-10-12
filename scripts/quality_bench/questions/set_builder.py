"""Construction d'un jeu de questions figé : ``build-set --set <s>`` (AD-2, AD-4, AD-5, AD-6).

**Cœur pur** : ``assemble(config, candidates_by_source) -> (questions, tracks)``.

- Sources dans l'ordre du YAML. Les identifiants de ``exclude`` (liste facultative par source
  du YAML) sont retirés des candidats de la source avant tout tirage ; un identifiant absent des
  candidats est une ``SetBuildError``. Un groupe déjà pris par une source précédente est exclu
  des suivantes (une traduction garde le groupe de son origine : pas de doublon).
- Échantillon ``think_off`` d'une source par groupes entiers (``per_group`` plafonne le nombre
  de questions gardées par groupe) : groupes triés, mélangés par
  ``Random(sha256([seed, "sample", source]))``, ajoutés tant que le total reste ≤ effectif ;
  un groupe qui dépasse est sauté. Total ≠ effectif : ``SetBuildError``.
- Tirage ``think_on`` par usage, même algorithme, graine ``[seed, "think_on", usage]``.
- Contrôles : effectifs exacts, identifiants uniques, une ``unit`` dans un seul ``group``, un
  ``group`` dans un seul usage, palier d'AD-5, ``validate_question`` sur chaque question.

**Coquille** : ``build_set(set_id)`` charge les candidats des importeurs (story 2), appelle les
générateurs en mémoire, lit les fichiers maison, vérifie les fichiers bruts sans réseau
(``verify_local_files``), écrit ``sets/<s>/questions.jsonl``, ``tracks.json`` et
``benchmarks/quality/sets/<s>/index.jsonl`` dans des dossiers temporaires voisins puis les
renomme ; rien n'est écrit en cas d'échec. Journal : identifiants, comptes et empreintes
seulement, jamais de contenu de question privée.
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import shutil
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common import paths
from ..common.canonical import pretty_bytes, sha256_bytes, sha256_hex
from ..common.config import DEFAULT_GENERATION, ConfigError, SetConfig, load_set, read_yaml
from ..common.jsonl import read_jsonl, rewrite_jsonl
from ..common.locks import FileLock, LockBusyError
from ..common.logs import setup_logging
from ..common.schemas import USAGES, validate
from .build import required_num_ctx
from .generators import oneruler_fr, var_math
from .generators.var_math import GeneratorError
from .house import PRODUCER as HOUSE_PRODUCER
from .house import house_path, load_house
from .pinned import SourceIntegrityError, verify_local_files
from .schema import REFUSED_SOURCES, SOURCES, QuestionError, set_hash, validate_question

logger = logging.getLogger(__name__)

SET_INDEX_SCHEMA = "qb.set_index/1"
_INDEX_FIELDS = ("id", "usage", "group", "unit", "source", "license", "private", "question_hash")
_PUBLIC_INDEX_FIELDS = ("prompt_hash", "target_hash")
# Réglages permis par générateur (generator_params du YAML de jeu).
_GENERATOR_PARAMS = {
    "var-math-fr": {"variants"},
    "oneruler-fr-niah": set(),
    "oneruler-fr-cwe": set(),
    "oneruler-fr-none": set(),
}


class SetBuildError(RuntimeError):
    """Jeu impossible à construire (effectif, groupe, palier, source absente, jeu existant)."""


# Refus attendus : journalisés sans pile (leurs messages ne citent aucune valeur privée).
EXPECTED_ERRORS = (SetBuildError, SourceIntegrityError, QuestionError, GeneratorError)


@dataclass(frozen=True)
class BuiltSet:
    """Jeu assemblé en mémoire, avant écriture."""

    config: SetConfig
    questions: list[dict[str, Any]]
    tracks: dict[str, list[str]]
    private_files: dict[str, str]  # source → empreinte du fichier privé lu

    @property
    def hash(self) -> str:
        return set_hash(self.questions, self.tracks)


# --- Cœur pur ------------------------------------------------------------------------------


def derived_rng(*parts: Any) -> random.Random:
    """Générateur dérivé d'une étape : ``Random(int(sha256_hex([...]), 16))`` (AD-4)."""
    return random.Random(int(sha256_hex(list(parts)), 16))


def draw_whole_groups(
    groups: Mapping[str, list[dict[str, Any]]], target: int, rng: random.Random, what: str
) -> list[str]:
    """Groupes tirés (triés, mélangés, ajoutés tant que le total reste ≤ ``target``) ; leur
    total vaut exactement ``target``, sinon ``SetBuildError`` qui nomme ``what``."""
    order = sorted(groups)
    rng.shuffle(order)
    taken, total = [], 0
    for group in order:
        size = len(groups[group])
        if total + size <= target:
            taken.append(group)
            total += size
    if total != target:
        available = sum(len(members) for members in groups.values())
        raise SetBuildError(
            f"{what} : le tirage glouton à graine par groupes entiers n'atteint pas l'effectif "
            f"exact {target} ({total} tirées ; {len(groups)} groupes, {available} questions "
            "disponibles)"
        )
    return sorted(taken)


def _group_by(questions: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        groups[question["group"]].append(dict(question))
    return {group: sorted(members, key=lambda q: q["id"]) for group, members in groups.items()}


def sample_source(
    candidates: list[dict[str, Any]],
    count: int,
    seed: int,
    source: str,
    per_group: int | None = None,
) -> list[dict[str, Any]]:
    """Échantillon ``think_off`` d'une source, par groupes entiers (après ``per_group``)."""
    rng = derived_rng(seed, "sample", source)
    groups = _group_by(candidates)
    if per_group is not None:
        for group in sorted(groups):
            members = groups[group]
            if len(members) > per_group:
                groups[group] = sorted(rng.sample(members, per_group), key=lambda q: q["id"])
    taken = draw_whole_groups(groups, count, rng, f"source {source}")
    return [question for group in taken for question in groups[group]]


def check_tier(question: Mapping[str, Any]) -> None:
    """Contrôle de palier d'AD-5 avec les paliers et plafonds par défaut de la configuration."""
    tiers = DEFAULT_GENERATION["num_ctx_tiers"]
    needed = required_num_ctx(question["est_prompt_tokens"], question["usage"])
    if question["num_ctx"] not in tiers or question["num_ctx"] < needed:
        raise SetBuildError(
            f"{question['id']} : palier num_ctx {question['num_ctx']} insuffisant ou hors des "
            f"paliers {tiers} (minimum {needed:.0f})"
        )


def check_questions(questions: list[dict[str, Any]]) -> None:
    """Contrôles du jeu : schéma, identifiants uniques, ``unit`` ⊂ ``group``, ``group`` dans un
    seul usage, palier."""
    seen: set[str] = set()
    unit_groups: dict[str, set[str]] = defaultdict(set)
    group_usages: dict[str, set[str]] = defaultdict(set)
    for question in questions:
        try:
            validate_question(question)
        except QuestionError as error:
            detail = error.redacted() if question.get("private", True) else str(error)
            raise SetBuildError(f"{question.get('id')!r} : {detail}") from None
        if question["id"] in seen:
            raise SetBuildError(f"identifiant en double : {question['id']}")
        seen.add(question["id"])
        unit_groups[question["unit"]].add(question["group"])
        group_usages[question["group"]].add(question["usage"])
        check_tier(question)
    for unit, groups in sorted(unit_groups.items()):
        if len(groups) > 1:
            raise SetBuildError(f"unit {unit} à cheval sur {len(groups)} groupes")
    for group, usages in sorted(group_usages.items()):
        if len(usages) > 1:
            raise SetBuildError(f"groupe {group} à cheval sur les usages {sorted(usages)}")


def draw_think_on(questions: list[dict[str, Any]], config: SetConfig) -> list[str]:
    """Identifiants ``think_on`` : par usage, groupes entiers, graine ``[seed, "think_on", u]``."""
    selected: list[str] = []
    for usage in USAGES:
        target = config.think_on.get(usage, 0)
        groups = _group_by(q for q in questions if q["usage"] == usage)
        if not groups and not target:
            continue
        rng = derived_rng(config.seed, "think_on", usage)
        taken = draw_whole_groups(groups, target, rng, f"think_on de l'usage {usage}")
        selected.extend(question["id"] for group in taken for question in groups[group])
    return sorted(selected)


def exclude_candidates(
    candidates: list[dict[str, Any]], exclude: Iterable[str], source: str
) -> list[dict[str, Any]]:
    """Candidats de ``source`` privés des identifiants ``exclude`` (liste du YAML de jeu) ; un
    identifiant absent des candidats est une ``SetBuildError`` qui nomme la source et l'id."""
    excluded = set(exclude)
    if not excluded:
        return candidates
    present = {candidate["id"] for candidate in candidates}
    missing = sorted(excluded - present)
    if missing:
        raise SetBuildError(
            f"source {source} : identifiants exclus absents des candidats {missing} (faute de "
            "frappe, ou renumérotation après un changement de révision)"
        )
    return [candidate for candidate in candidates if candidate["id"] not in excluded]


def assemble(
    config: SetConfig, candidates_by_source: Mapping[str, list[dict[str, Any]]]
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Assemble le jeu : questions triées par ``id`` et ``{"think_off", "think_on"}``."""
    taken_groups: set[str] = set()
    questions: list[dict[str, Any]] = []
    for entry in config.sources:
        candidates = candidates_by_source.get(entry.source)
        if candidates is None:
            raise SetBuildError(f"source {entry.source} : aucun candidat chargé")
        for candidate in candidates:
            if candidate.get("source") != entry.source:
                raise SetBuildError(
                    f"source {entry.source} : candidat d'une autre source ({candidate.get('id')})"
                )
        candidates = exclude_candidates(candidates, entry.exclude, entry.source)
        available = [c for c in candidates if c["group"] not in taken_groups]
        sample = sample_source(available, entry.count, config.seed, entry.source, entry.per_group)
        taken_groups.update(question["group"] for question in sample)
        questions.extend(sample)
    questions.sort(key=lambda question: question["id"])
    check_questions(questions)
    for usage, count in config.think_off.items():
        actual = sum(1 for question in questions if question["usage"] == usage)
        if actual != count:
            raise SetBuildError(f"usage {usage} : {actual} questions au lieu de {count}")
    think_off = [question["id"] for question in questions]
    tracks = {"think_off": think_off, "think_on": draw_think_on(questions, config)}
    if not set(tracks["think_on"]) <= set(think_off):
        raise SetBuildError("think_on n'est pas inclus dans think_off")
    return questions, tracks


def index_rows(questions: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Lignes ``qb.set_index/1`` (liste blanche d'AD-6), validées une à une."""
    rows = []
    for question in questions:
        row = {"schema": SET_INDEX_SCHEMA, **{field: question[field] for field in _INDEX_FIELDS}}
        if not question["private"]:
            row.update({field: question[field] for field in _PUBLIC_INDEX_FIELDS})
        validate(row)
        rows.append(row)
    return rows


# --- Coquille : chargement des sources -----------------------------------------------------


def check_generator_params(config: SetConfig) -> None:
    """Réglages de générateur permis (``ConfigError`` : YAML de jeu invalide)."""
    for entry in config.sources:
        allowed = _GENERATOR_PARAMS.get(entry.source, set())
        unknown = sorted(set(entry.generator_params) - allowed)
        if unknown:
            raise ConfigError(
                f"{entry.source}.generator_params : clés inconnues {unknown} "
                f"(permises : {sorted(allowed)})"
            )
        variants = entry.generator_params.get("variants", 1)
        if not isinstance(variants, int) or isinstance(variants, bool) or variants < 1:
            raise ConfigError(
                f"{entry.source}.generator_params.variants : entier ≥ 1 attendu, reçu {variants!r}"
            )


def read_set_config(set_id: str) -> SetConfig:
    path = paths.set_config_path(set_id)
    if not path.is_file():
        raise ConfigError(f"YAML de jeu absent : {path}")
    config = load_set(path, SOURCES, REFUSED_SOURCES)
    check_generator_params(config)
    return config


def _private_file(source: str, private_files: dict[str, str]) -> Path:
    path = house_path(source) if SOURCES[source].producer == HOUSE_PRODUCER else None
    if path is None:
        path = paths.private_source_path(source)
    if not path.is_file():
        hint = (
            "questions privées hors dépôt, à restaurer depuis leur sauvegarde"
            if SOURCES[source].private
            else "fichier versionné du dépôt, à restaurer par git"
        )
        raise SetBuildError(f"fichier de la source {source} absent : {path} ({hint})")
    if SOURCES[source].private:
        digest = sha256_bytes(path.read_bytes())
        private_files[source] = digest
        logger.info("%s : fichier privé lu, sha256 %s", source, digest)
    return path


def _read_source_yaml(path: Path, source: str) -> Any:
    """YAML d'une source (privée ou versionnée) : un défaut est une ``SetBuildError`` qui nomme
    le fichier, pas une erreur du YAML de jeu."""
    try:
        return read_yaml(path)
    except ConfigError as error:
        raise SetBuildError(f"fichier de la source {source} ({path}) : {error}") from None


def _oneruler_texts() -> oneruler_fr.OneRulerTexts:
    local = verify_local_files(
        oneruler_fr.RAW_FILES,
        paths.source_raw_dir(oneruler_fr.BUNDLE),
        fetch_hint=f"fetch --source {oneruler_fr.BUNDLE}",
    )
    by_path = {remote.path: path for remote, path in local.items()}

    def read(name: str) -> str:
        with open(by_path[name], encoding="utf-8") as handle:
            return handle.read()

    return oneruler_fr.parse_texts(
        read(oneruler_fr.BOOK_PATH),
        read(oneruler_fr.NIAH_TEMPLATE_PATH),
        read(oneruler_fr.CWE_TEMPLATE_PATH),
    )


def load_candidates(config: SetConfig) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Candidats de chaque source du jeu, et empreintes des fichiers privés lus."""
    candidates: dict[str, list[dict[str, Any]]] = {}
    private_files: dict[str, str] = {}
    oneruler_texts = None
    for entry in config.sources:
        spec = SOURCES[entry.source]
        if entry.source in oneruler_fr.GENERATORS:
            if oneruler_texts is None:
                oneruler_texts = _oneruler_texts()
            generate = oneruler_fr.GENERATORS[entry.source]
            candidates[entry.source] = generate(oneruler_texts, entry.generator_seed, entry.count)
        elif entry.source == var_math.SOURCE:

            path = _private_file(entry.source, private_files)
            problems = var_math.parse_problems(_read_source_yaml(path, entry.source))
            candidates[entry.source] = var_math.generate(
                problems,
                entry.generator_seed,
                entry.generator_params.get("variants", var_math.DEFAULT_VARIANTS),
            )
        elif spec.producer == HOUSE_PRODUCER:
            path = _private_file(entry.source, private_files)
            try:
                candidates[entry.source] = load_house(path, entry.source)
            except ConfigError as error:  # YAML illisible ou clé en double : pas le YAML de jeu
                raise SetBuildError(
                    f"fichier de la source {entry.source} ({path}) : {error}"
                ) from None
        else:
            path = paths.candidates_path(entry.source)
            if not path.is_file():
                raise SetBuildError(
                    f"candidats absents pour {entry.source} : {path} ; lancer "
                    f"`python -m scripts.quality_bench fetch --source {entry.source}`"
                )
            candidates[entry.source] = read_jsonl(path)
        logger.info("%s : %d candidats", entry.source, len(candidates[entry.source]))
        if entry.exclude:
            logger.info(
                "%s : %d identifiants à exclure (YAML de jeu)", entry.source, len(entry.exclude)
            )
    return candidates, private_files


def prepare_set(set_id: str, config: SetConfig | None = None) -> BuiltSet:
    """Charge les sources et assemble le jeu en mémoire (aucune écriture)."""
    config = config or read_set_config(set_id)
    candidates, private_files = load_candidates(config)
    questions, tracks = assemble(config, candidates)
    return BuiltSet(config, questions, tracks, private_files)


# --- Coquille : écriture -------------------------------------------------------------------


def _refuse_existing(set_id: str) -> None:
    for directory in (paths.set_dir(set_id), paths.set_index_dir(set_id)):
        if directory.exists():
            raise SetBuildError(
                f"jeu {set_id} déjà construit : {directory} existe (un jeu s'écrit une fois)"
            )


def _tmp_dir(directory: Path) -> Path:
    return directory.with_name(f".{directory.name}.tmp")


def write_set(built: BuiltSet) -> dict[str, str]:
    """Écrit les trois fichiers du jeu (dossiers temporaires voisins, puis renommage) ; rend
    leurs empreintes ``sha256``."""
    set_id = built.config.set_id
    data_dir, index_dir = paths.set_dir(set_id), paths.set_index_dir(set_id)
    _refuse_existing(set_id)
    tmp_data, tmp_index = _tmp_dir(data_dir), _tmp_dir(index_dir)
    for tmp in (tmp_data, tmp_index):
        if tmp.exists():
            shutil.rmtree(tmp)
    try:
        rewrite_jsonl(tmp_data / "questions.jsonl", built.questions)
        with open(tmp_data / "tracks.json", "wb") as handle:
            handle.write(pretty_bytes(built.tracks))
            handle.flush()
            os.fsync(handle.fileno())
        rewrite_jsonl(tmp_index / "index.jsonl", index_rows(built.questions))
        digests = {
            "questions.jsonl": sha256_bytes((tmp_data / "questions.jsonl").read_bytes()),
            "tracks.json": sha256_bytes((tmp_data / "tracks.json").read_bytes()),
            "index.jsonl": sha256_bytes((tmp_index / "index.jsonl").read_bytes()),
        }
        _refuse_existing(set_id)
        os.rename(tmp_data, data_dir)
        try:
            os.rename(tmp_index, index_dir)
        except BaseException:
            shutil.rmtree(data_dir)
            raise
    finally:
        for tmp in (tmp_data, tmp_index):
            if tmp.exists():
                shutil.rmtree(tmp)
    return digests


def build_set(set_id: str, config: SetConfig | None = None) -> BuiltSet:
    """Construit et écrit le jeu ``set_id`` (sans verrou : voir la commande ``build-set``)."""
    config = config or read_set_config(set_id)
    _refuse_existing(set_id)
    built = prepare_set(set_id, config)
    digests = write_set(built)
    n_on = len(built.tracks["think_on"])
    logger.info(
        "Jeu %s écrit : %d questions think_off, %d think_on ; empreinte du jeu %s",
        set_id,
        len(built.questions),
        n_on,
        built.hash,
    )
    for name, digest in digests.items():
        logger.info("%s : sha256 %s", name, digest)
    return built


# --- Commande build-set --------------------------------------------------------------------


def _configure_build_set(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--set", required=True, metavar="<set>", dest="set_id", help="jeu")


def _run_build_set(args: argparse.Namespace) -> int:
    setup_logging("build-set", paths.sets_log_path("build-set"))
    try:
        config = read_set_config(args.set_id)
    except (ConfigError, ValueError) as error:
        logger.error("YAML de jeu invalide : %s", error)
        return 2
    try:
        with FileLock(paths.machine_lock_path()):
            build_set(args.set_id, config)
            return 0
    except LockBusyError as error:
        logger.error("%s : machine occupée (génération, jugement ou téléchargement)", error)
        return 1
    except ConfigError as error:
        logger.error("YAML de jeu invalide : %s", error)
        return 2
    except EXPECTED_ERRORS as error:
        # Refus attendus (jeu existant, source absente, empreinte, effectif, palier) : sans pile.
        logger.error(
            "build-set %s refusé, rien n'est écrit : %s : %s",
            args.set_id,
            type(error).__name__,
            error,
        )
        return 1
    except Exception:  # erreur inattendue : journalisée avec sa pile, code 1
        logger.exception("build-set %s interrompu, rien n'est écrit", args.set_id)
        return 1


BUILD_SET = (
    "build-set",
    "Construit le jeu --set <s> (sets/<s>.yaml) : questions.jsonl et tracks.json sous "
    "$QUALITY_BENCH_DATA/sets/<s>/, index versionné benchmarks/quality/sets/<s>/index.jsonl ; "
    "écrit une fois, sans réseau, sous machine.lock.",
    _configure_build_set,
    _run_build_set,
)

__all__ = [
    "BUILD_SET",
    "BuiltSet",
    "EXPECTED_ERRORS",
    "SetBuildError",
    "assemble",
    "build_set",
    "draw_whole_groups",
    "exclude_candidates",
    "index_rows",
    "prepare_set",
    "read_set_config",
]
