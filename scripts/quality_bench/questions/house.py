"""Questions maison (format ``qb.house/1``) : rédaction versionnée et questions privées.

- ``writing-fr`` : versionnée en entier dans ``questions/writing/writing-fr.yaml`` (non privée :
  le juge cloud doit la lire), avec des critères fermés.
- ``instructions-fr``, ``tools-fr``, ``extraction-fr``, ``abstention-fr`` : privées, sous
  ``$QUALITY_BENCH_DATA/private/<source>.yaml`` seulement (hors dépôt).

```yaml
schema: qb.house/1
source: extraction-fr
questions:
  - number: 1
    group: extraction-fr/0001          # facultatif ; opaque pour une source privée
    messages: [{role: user, content: "…"}]
    turns: null                         # facultatifs : turns, tools, format
    grader_params: {schema: {…}, subset: extraction-fr}
    target: {…}
    criteria: [{id: c1, question: "… ?"}]   # rédaction seulement ; check: facultatif, voir checks.py
  - number: 2
    derived_from: tools/bfcl-live/0042  # tools-fr seulement : ne remplace que messages
    messages: [{role: user, content: "…"}]
```

Une question dérivée (``derived_from``) copie ``tools``, ``format``, ``env``, ``grader.params``,
``target`` et ``group`` du candidat d'origine (AD-5 : une traduction garde le groupe de son
origine). Le chargement est pur (``build_house``) ; ``load_house`` lit le YAML par
``common/config.read_yaml`` et, au besoin, les candidats d'origine.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..common import paths
from ..common.canonical import pretty_bytes
from ..common.config import read_yaml
from ..common.jsonl import read_jsonl
from ..common.schemas import check_schema, instance_errors
from .build import build_question
from .checks import CheckError, validate_checks
from .schema import SOURCES, QuestionError

SCHEMA_ID = "qb.house/1"
PRODUCER = "questions/house.py"
WRITING_DIR = paths.PACKAGE_DIR / "questions" / "writing"
DERIVABLE_SOURCES = {"tools-fr"}
MIN_CRITERIA, MAX_CRITERIA = 4, 6

_QUESTION_KEYS = {
    "number",
    "group",
    "messages",
    "turns",
    "tools",
    "format",
    "grader_params",
    "target",
    "criteria",
    "derived_from",
}
_DERIVED_KEYS = {"number", "messages", "derived_from"}
# Paramètres de correcteur exigés (clés exactes) par correcteur des sources maison.
_GRADER_PARAMS = {
    "mifeval_fr": {"instruction_id_list", "key", "kwargs"},
    "json_schema": {"schema", "subset"},
    "abstention_marker": {"marker"},
    "judge_criteria": set(),
}


def house_sources() -> list[str]:
    """Sources produites par ce module, triées."""
    return sorted(slug for slug, spec in SOURCES.items() if spec.producer == PRODUCER)


def house_path(source: str, file: str | None = None) -> Path:
    """Fichier d'une source maison : privé (hors dépôt) ou versionné (rédaction).

    ``file`` (clé ``file`` du YAML de jeu) : autre fichier versionné de la source, sous
    ``questions/writing/`` ; refusé pour une source privée."""
    spec = SOURCES.get(source)
    if spec is None or spec.producer != PRODUCER:
        raise QuestionError(f"source maison inconnue : {source!r}")
    if spec.private:
        if file is not None:
            raise QuestionError(f"{source} : fichier choisi interdit pour une source privée")
        return paths.private_source_path(source)
    return WRITING_DIR / (file or f"{source}.yaml")


def _fail(where: str, message: str) -> QuestionError:
    return QuestionError(f"{where} : {message}")


def _messages(value: Any, where: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise _fail(where, "messages : liste non vide attendue")
    for message in value:
        if (
            not isinstance(message, Mapping)
            or set(message) != {"role", "content"}
            or message["role"] not in ("system", "user")
            or not isinstance(message["content"], str)
            or not message["content"].strip()
        ):
            raise _fail(where, "messages : {role: system|user, content: texte} attendus")
    return [dict(message) for message in value]


def _check_grader_params(spec, params: Any, target: Any, messages, where: str) -> None:
    expected = _GRADER_PARAMS.get(spec.grader)
    if expected is None:
        raise _fail(where, f"correcteur {spec.grader} : seulement par derived_from")
    if not isinstance(params, Mapping) or set(params) != expected:
        raise _fail(where, f"grader_params : clés exactes {sorted(expected)} attendues")
    contents = "\n".join(message["content"] for message in messages)
    if spec.grader == "mifeval_fr":
        ids, kwargs = params["instruction_id_list"], params["kwargs"]
        if (
            not isinstance(ids, list)
            or not ids
            or len(set(ids)) != len(ids)
            or not all(isinstance(item, str) and item.startswith("fr:") for item in ids)
            or not isinstance(kwargs, list)
            or len(kwargs) != len(ids)
            or not all(isinstance(item, Mapping) for item in kwargs)
            or not isinstance(params["key"], str)
        ):
            raise _fail(where, "grader_params M-IFEval FR mal formés (ids fr:…, kwargs alignés)")
    elif spec.grader == "json_schema":
        try:
            check_schema(params["schema"])
        except Exception as error:  # schéma JSON invalide ; jamais son texte (question privée)
            path = "".join(f"/{part}" for part in getattr(error, "path", ())) or "/"
            raise _fail(where, f"schéma JSON invalide (chemin {path})") from None
        schema_text = pretty_bytes(params["schema"]).decode("utf-8").rstrip("\n")
        if schema_text not in contents:
            raise _fail(where, "le schéma de grader_params doit figurer tel quel dans le prompt")
        if target is None:
            raise _fail(where, "target : valeurs attendues obligatoires en extraction")
        problem = instance_errors(params["schema"], target)
        if problem is not None:
            raise _fail(where, f"target non conforme au schéma : champ {problem}")
    elif spec.grader == "abstention_marker":
        marker = params["marker"]
        if not isinstance(marker, str) or not marker.strip() or marker not in contents:
            raise _fail(where, "marker : chaîne imposée dans la consigne attendue")
    if spec.grader in ("mifeval_fr", "abstention_marker", "judge_criteria") and target is not None:
        raise _fail(where, f"target : nulle attendue pour {spec.grader}")


def _has_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_has_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_float(item) for item in value)
    return False


def _criteria(value: Any, writing: bool, where: str) -> list[dict[str, Any]] | None:
    if not writing:
        if value is not None:
            raise _fail(where, "criteria : réservés à la rédaction")
        return None
    if not isinstance(value, list) or not MIN_CRITERIA <= len(value) <= MAX_CRITERIA:
        raise _fail(where, f"criteria : {MIN_CRITERIA} à {MAX_CRITERIA} critères attendus")
    for index, criterion in enumerate(value, start=1):
        if (
            not isinstance(criterion, Mapping)
            or not {"id", "question"} <= set(criterion) <= {"id", "question", "check"}
            or criterion["id"] != f"c{index}"
            or not isinstance(criterion["question"], str)
            or not criterion["question"].strip().endswith("?")
        ):
            raise _fail(
                where,
                f"critère {index} : {{id: c{index}, question: « … ? », check: (facultatif)}} attendu",
            )
        if "check" in criterion:
            try:
                validate_checks(criterion["check"])
            except CheckError as error:
                raise _fail(where, f"critère {index} : {error}") from None
    return [dict(criterion) for criterion in value]


def _derived(source: str, raw: Mapping[str, Any], origins, where: str) -> dict[str, Any]:
    if source not in DERIVABLE_SOURCES:
        raise _fail(where, f"derived_from : réservé à {sorted(DERIVABLE_SOURCES)}")
    if set(raw) != _DERIVED_KEYS:
        raise _fail(where, f"question dérivée : clés exactes {sorted(_DERIVED_KEYS)}")
    origin_id = raw["derived_from"]
    origin = origins.get(origin_id) if isinstance(origin_id, str) else None
    if origin is None:
        raise _fail(where, f"derived_from introuvable : {origin_id!r}")
    if origin["usage"] != SOURCES[source].usage or origin["private"]:
        raise _fail(where, f"derived_from : origine publique d'usage {SOURCES[source].usage}")
    if origin["grader"]["name"] != SOURCES[source].grader:
        raise _fail(where, "derived_from : correcteur de l'origine différent de la source")
    messages = _messages(raw["messages"], where)
    if [message["role"] for message in messages] != [
        message["role"] for message in origin["messages"]
    ]:
        raise _fail(where, "derived_from : mêmes rôles de messages que l'origine attendus")
    return {
        "group": origin["group"],
        "messages": messages,
        "tools": origin["tools"],
        "format": origin["format"],
        "env": origin["env"],
        "turns": origin["turns"],
        "grader_params": origin["grader"]["params"],
        "target": origin["target"],
    }


def build_house(
    document: Any, source: str, origins: Mapping[str, Mapping[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Questions d'un document ``qb.house/1`` déjà lu ; ``QuestionError`` au premier défaut.

    ``origins`` : candidats publics indexés par identifiant, pour ``derived_from``.
    """
    spec = SOURCES.get(source)
    if spec is None or spec.producer != PRODUCER:
        raise QuestionError(f"source maison inconnue : {source!r}")
    if not isinstance(document, Mapping) or set(document) != {"schema", "source", "questions"}:
        raise QuestionError(f"{source} : clés {{schema, source, questions}} exactement attendues")
    if document["schema"] != SCHEMA_ID or document["source"] != source:
        raise QuestionError(f"{source} : schéma {SCHEMA_ID} et source {source!r} attendus")
    raw_questions = document["questions"]
    if not isinstance(raw_questions, list) or not raw_questions:
        raise QuestionError(f"{source} : liste de questions non vide attendue")
    questions = []
    numbers: set[int] = set()
    group_re = re.compile(rf"{re.escape(source)}/[0-9]+")
    for index, raw in enumerate(raw_questions):
        where = f"{source}, questions[{index}]"
        if not isinstance(raw, Mapping):
            raise _fail(where, "objet attendu")
        unknown = sorted(str(key) for key in raw if key not in _QUESTION_KEYS)
        if unknown:
            raise _fail(where, f"clés inconnues {unknown}")
        number = raw.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise _fail(where, "number : entier ≥ 1 attendu")
        if number in numbers:
            raise _fail(where, f"numéro en double {number}")
        numbers.add(number)
        where = f"{source} n° {number}"
        if "derived_from" in raw:
            fields = _derived(source, raw, origins or {}, where)
            env = fields.pop("env")
            criteria = None
        else:
            for key in ("messages", "grader_params", "target"):
                if key not in raw:
                    raise _fail(where, f"clé {key} obligatoire")
            messages = _messages(raw["messages"], where)
            if _has_float(raw["target"]):
                raise _fail(where, "flottant interdit dans la cible (entier ou chaîne, AD-4)")
            _check_grader_params(spec, raw["grader_params"], raw["target"], messages, where)
            group = raw.get("group", f"{source}/{number:04d}")
            if (
                not isinstance(group, str)
                or not group
                or (spec.private and not group_re.fullmatch(group))
            ):
                raise _fail(where, f"group : opaque « {source}/<numéro> » attendu")
            fields = {
                "group": group,
                "messages": messages,
                "turns": raw.get("turns"),
                "tools": raw.get("tools"),
                "format": raw.get("format"),
                "grader_params": raw["grader_params"],
                "target": raw["target"],
            }
            env = None
            criteria = _criteria(raw.get("criteria"), spec.usage == "writing", where)
        try:
            questions.append(
                build_question(source=source, number=number, env=env, criteria=criteria, **fields)
            )
        except QuestionError as error:
            # Question privée : chemin et nature du défaut, jamais de valeur.
            raise _fail(where, error.redacted() if spec.private else str(error)) from None
        except ValueError as error:  # palier introuvable (taille estimée seulement)
            raise _fail(where, str(error)) from None
    return sorted(questions, key=lambda question: question["id"])


def _origins_for(document: Any) -> dict[str, dict[str, Any]]:
    """Candidats publics cités par ``derived_from``, lus dans ``sources/<slug>/``."""
    wanted = {
        raw["derived_from"]
        for raw in (document.get("questions") or [] if isinstance(document, Mapping) else [])
        if isinstance(raw, Mapping) and isinstance(raw.get("derived_from"), str)
    }
    origins: dict[str, dict[str, Any]] = {}
    for slug in sorted({origin.split("/")[1] for origin in wanted if origin.count("/") == 2}):
        if slug not in SOURCES or SOURCES[slug].private:
            continue
        path = paths.candidates_path(slug)
        if not path.exists():
            raise QuestionError(
                f"candidats d'origine absents : {path} ; lancer "
                f"`python -m scripts.quality_bench fetch --source {slug}`"
            )
        origins.update({row["id"]: row for row in read_jsonl(path) if row["id"] in wanted})
    return origins


def load_house(
    path: str | Path, source: str, origins: Mapping[str, Mapping[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Lit un fichier ``qb.house/1`` et rend ses questions validées, triées par ``id``."""
    document = read_yaml(path)
    if origins is None:
        origins = _origins_for(document)
    return build_house(document, source, origins)
