"""Unités à juger (AD-16) : entrées validées de la phase de jugement.

Entrées, sans aucun YAML de campagne :
- manifeste de génération (``phase = generation``, même campagne) ;
- ``generation.jsonl`` : chaque ligne validée, ``manifest`` = empreinte du ``blocking``,
  campagne égale, clé unique, question présente dans le jeu avec le même ``prompt_hash`` ;
- jeu ``sets/<blocking.set.id>/`` dont l'empreinte égale ``blocking.set.hash``.

Unités : lignes ``usage = writing`` et ``status = ok`` seulement, une par critère de
``question.criteria`` sans ``check`` (un critère de comptage est vérifié par le code), clé ``"{generation_key}|{criterion}"``. Aucun message d'erreur ne cite de
texte de question ni de réponse.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..common import paths
from ..common.jsonl import JsonlReadError, read_jsonl
from ..common.manifest import blocking_hash
from ..common.schemas import SchemaValidationError, UnknownSchemaError, validate
from ..questions.schema import set_hash
from .base import JudgeInputError
from .prompt import final_answer, render_instruction


@dataclass(frozen=True)
class Unit:
    """Un critère d'une réponse de rédaction à juger."""

    key: str
    generation_key: str
    criterion: str
    criterion_question: str
    question_id: str
    private: bool
    instruction: str
    answer: str


@dataclass(frozen=True)
class Inputs:
    """Manifeste de génération lu, son empreinte et les unités à juger (ordre des clés)."""

    manifest: dict[str, Any]
    manifest_hash: str
    units: list[Unit]
    writing_lines: int


def _validated(record: Any, expected: str, where: str) -> None:
    try:
        name = validate(record)
    except UnknownSchemaError:
        raise JudgeInputError(f"{where} : champ « schema » absent ou inconnu") from None
    except SchemaValidationError as exc:
        raise JudgeInputError(f"{where} : hors schéma (champ {exc.path}, {exc.kind})") from None
    if name != expected:
        raise JudgeInputError(f"{where} : schéma {name} au lieu de {expected}")


def _read_lines(path: Any, where: str) -> list[dict[str, Any]]:
    try:
        return read_jsonl(path)
    except JsonlReadError as exc:
        raise JudgeInputError(f"{where} : {exc}") from None


def read_generation_manifest(campaign: str) -> dict[str, Any]:
    path = paths.generation_manifest_path(campaign)
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except FileNotFoundError:
        raise JudgeInputError(f"manifeste de génération absent : {path}") from None
    except (OSError, ValueError) as exc:
        raise JudgeInputError(f"manifeste de génération illisible ({type(exc).__name__})") from None
    _validated(manifest, "qb.manifest/1", "manifeste de génération")
    if manifest["phase"] != "generation":
        raise JudgeInputError(f"manifeste de génération : phase {manifest['phase']}")
    if manifest["campaign"] != campaign:
        raise JudgeInputError(
            f"manifeste de la campagne {manifest['campaign']} au lieu de {campaign}"
        )
    return manifest


def _load_set(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    blocking_set = manifest["blocking"]["set"]
    set_id = blocking_set["id"]
    try:
        questions_path = paths.set_questions_path(set_id)
        tracks_path = paths.set_tracks_path(set_id)
    except ValueError as exc:
        raise JudgeInputError(str(exc)) from None
    if not questions_path.exists() or not tracks_path.exists():
        raise JudgeInputError(f"jeu {set_id} absent : {questions_path.parent}")
    questions = _read_lines(questions_path, f"jeu {set_id}")
    try:
        with open(tracks_path, encoding="utf-8") as handle:
            tracks = json.load(handle)
        computed = set_hash(questions, tracks)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise JudgeInputError(f"jeu {set_id} illisible ({type(exc).__name__})") from None
    if computed != blocking_set["hash"]:
        raise JudgeInputError(f"empreinte du jeu {set_id} différente de celle du manifeste")
    return {question["id"]: question for question in questions}


def load_inputs(campaign: str) -> Inputs:
    """Lit et vérifie les entrées ; ``JudgeInputError`` (code 1) à la première incohérence."""
    manifest = read_generation_manifest(campaign)
    manifest_hash = blocking_hash(manifest)
    questions = _load_set(manifest)
    generation_path = paths.generation_path(campaign)
    if not generation_path.exists():
        raise JudgeInputError(f"generation.jsonl absent : {generation_path}")
    units: list[Unit] = []
    seen: set[str] = set()
    writing_lines = 0
    for line_no, line in enumerate(_read_lines(generation_path, "generation.jsonl"), start=1):
        where = f"generation.jsonl ligne {line_no}"
        _validated(line, "qb.generation/1", where)
        if line["manifest"] != manifest_hash:
            raise JudgeInputError(f"{where} : produite par un autre manifeste")
        if line["campaign"] != campaign:
            raise JudgeInputError(f"{where} : campagne {line['campaign']} au lieu de {campaign}")
        if line["key"] in seen:
            raise JudgeInputError(f"{where} : clé en double {line['key']}")
        seen.add(line["key"])
        question = questions.get(line["question_id"])
        if question is None:
            raise JudgeInputError(f"{where} : question {line['question_id']} absente du jeu")
        if line["prompt_hash"] != question["prompt_hash"]:
            raise JudgeInputError(f"{where} : prompt_hash différent de la question")
        if line["usage"] != question["usage"]:
            raise JudgeInputError(f"{where} : usage différent de la question")
        if line["usage"] != "writing" or line["status"] != "ok":
            continue
        writing_lines += 1
        criteria = question.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise JudgeInputError(f"{where} : question de rédaction sans critères")
        instruction = render_instruction(question["messages"])
        answer = final_answer(line["output"])
        for criterion in criteria:
            if "check" in criterion:
                continue  # vérifié par le code (grading/counting.py) : jamais soumis au juge
            units.append(
                Unit(
                    key=f"{line['key']}|{criterion['id']}",
                    generation_key=line["key"],
                    criterion=criterion["id"],
                    criterion_question=criterion["question"],
                    question_id=question["id"],
                    private=bool(question.get("private")),
                    instruction=instruction,
                    answer=answer,
                )
            )
    units.sort(key=lambda unit: unit.key)
    return Inputs(manifest, manifest_hash, units, writing_lines)
