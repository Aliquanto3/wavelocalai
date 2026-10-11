"""Schéma de question ``qb.question/1`` (AD-5), liste fermée des sources et sources refusées.

Noyau pur : aucune I/O. Une question est valide si elle respecte le schéma JSON fermé, si sa
``source`` figure dans ``SOURCES`` (jamais dans ``REFUSED_SOURCES``) avec l'usage, la licence et
le caractère privé déclarés pour cette source, et si ses trois empreintes se recalculent à
l'identique (AD-4). La validation JSON Schema passe par ``common/schemas.py``, seul module qui
importe ``jsonschema``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ..common.canonical import sha256_hex
from ..common.schemas import USAGES, SchemaValidationError, validate_with

QUESTION_SCHEMA_ID = "qb.question/1"

# Licences admises d'une question (AD-5) ; « private » pour les seules questions privées.
LICENSES = ("Apache-2.0", "MIT", "CC-BY-4.0", "ODC-BY-1.0", "public-domain", "private")

# Correcteurs nommés sans version (la version vit dans le registre de la story 4, AD-10).
GRADERS = (
    "exact_answer",  # réponse exacte normalisée ou numérique (raisonnement)
    "ifbench",  # vérificateurs IFBench (consignes)
    "mifeval_fr",  # vérificateurs M-IFEval FR (consignes)
    "bfcl_ast",  # AST des appels de fonction, simple, multiple ou parallèle (outils)
    "bfcl_state",  # état final après exécution multi-tours dans envs/ (outils)
    "bfcl_irrelevance",  # aucun appel de fonction attendu (abstention)
    "json_schema",  # instance JSON valide contre le schéma (extraction)
    "squad_f1",  # correspondance exacte normalisée et F1, plusieurs réponses admises (RAG)
    "oneruler_niah",  # valeurs de l'aiguille retrouvées, ou réponse « aucune » (RAG, abstention)
    "oneruler_cwe",  # mots les plus fréquents de la liste, ensemble attendu (RAG)
    "abstention_marker",  # marqueur d'abstention imposé par la consigne, et rien d'autre
    "judge_criteria",  # verdicts du juge retenu sur les critères fermés (rédaction)
)

HASH_FIELDS = ("question_hash", "prompt_hash", "target_hash")


@dataclass(frozen=True)
class SourceSpec:
    """Source admise : un seul producteur (module du paquet), usage, licence, caractère privé."""

    slug: str
    usage: str
    license: str
    producer: str
    grader: str
    private: bool = False

    @property
    def generated(self) -> bool:
        """Source produite par un générateur à graine (``generator_seed`` obligatoire)."""
        return self.producer.startswith("questions/generators/")


# Liste fermée des sources (slugs) ; chacune n'a qu'un producteur : un importeur de jeu public
# (questions/importers/), un générateur à graine (questions/generators/) ou le chargeur des
# questions maison (questions/house.py), versionnées (rédaction) ou privées (hors dépôt).
SOURCES: dict[str, SourceSpec] = {
    spec.slug: spec
    for spec in (
        SourceSpec(
            "bbeh-mini", "reasoning", "CC-BY-4.0", "questions/importers/bbeh.py", "exact_answer"
        ),
        SourceSpec(
            "ifbench", "instructions", "ODC-BY-1.0", "questions/importers/ifbench.py", "ifbench"
        ),
        SourceSpec(
            "mifeval-fr",
            "instructions",
            "Apache-2.0",
            "questions/importers/mifeval.py",
            "mifeval_fr",
        ),
        SourceSpec("bfcl-live", "tools", "Apache-2.0", "questions/importers/bfcl.py", "bfcl_ast"),
        SourceSpec(
            "bfcl-parallel", "tools", "Apache-2.0", "questions/importers/bfcl.py", "bfcl_ast"
        ),
        SourceSpec(
            "bfcl-multi", "tools", "Apache-2.0", "questions/importers/bfcl.py", "bfcl_state"
        ),
        SourceSpec(
            "bfcl-irrelevance",
            "abstention",
            "Apache-2.0",
            "questions/importers/bfcl.py",
            "bfcl_irrelevance",
        ),
        SourceSpec(
            "jsonschemabench",
            "extraction",
            "MIT",
            "questions/importers/jsonschemabench.py",
            "json_schema",
        ),
        SourceSpec("piaf", "rag", "MIT", "questions/importers/piaf.py", "squad_f1"),
        # Générateurs à graine.
        SourceSpec(
            "var-math-fr",
            "reasoning",
            "private",
            "questions/generators/var_math.py",
            "exact_answer",
            private=True,
        ),
        SourceSpec(
            "oneruler-fr-niah", "rag", "MIT", "questions/generators/oneruler_fr.py", "oneruler_niah"
        ),
        SourceSpec(
            "oneruler-fr-cwe", "rag", "MIT", "questions/generators/oneruler_fr.py", "oneruler_cwe"
        ),
        SourceSpec(
            "oneruler-fr-none",
            "abstention",
            "MIT",
            "questions/generators/oneruler_fr.py",
            "oneruler_niah",
        ),
        # Questions maison : privées (hors dépôt) ou versionnées (rédaction).
        SourceSpec(
            "instructions-fr",
            "instructions",
            "private",
            "questions/house.py",
            "mifeval_fr",
            private=True,
        ),
        SourceSpec("tools-fr", "tools", "private", "questions/house.py", "bfcl_ast", private=True),
        SourceSpec(
            "extraction-fr",
            "extraction",
            "private",
            "questions/house.py",
            "json_schema",
            private=True,
        ),
        SourceSpec(
            "abstention-fr",
            "abstention",
            "private",
            "questions/house.py",
            "abstention_marker",
            private=True,
        ),
        SourceSpec("writing-fr", "writing", "MIT", "questions/house.py", "judge_criteria"),
    )
}

# Sources refusées (exclusions de pistes-et-questions.md) : slug → raison.
REFUSED_SOURCES: dict[str, str] = {
    "ifeval": "IFEval (EN) : saturé chez les SLM récents (≥ 80 % dès 2B)",
    "ifeval-fr": "IFEval-fr (le-leadboard) : aucune licence déclarée",
    "fquad": "FQuAD : non commercial, redistribution interdite",
    "gsm-symbolic": "GSM-Symbolic : CC-BY-NC-ND, pas d'adaptation FR distribuable",
    "math-500": "MATH-500 tel quel : contamination de Qwen2.5 (reproduction mot pour mot)",
    "musr": "MuSR : ne discrimine pas (0,33 à 0,41 de 1B à 14B)",
    "bfcl-non-live-ast": "BFCL non-live AST : au plafond (~88 % dès 4B)",
    "bfcl-web-search": "BFCL web search : exige SerpAPI, donc le réseau",
}

_ID_RE = re.compile(r"^(?P<usage>[a-z]+)/(?P<source>[a-z0-9-]+)/(?P<number>[0-9]{4,})$")
_NULLABLE_OBJECT = {"type": ["object", "null"]}
_NON_EMPTY = {"type": "string", "minLength": 1}
_HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_CHAT_MESSAGE = {
    "type": "object",
    "properties": {
        "role": {"enum": ["system", "user", "assistant", "tool"]},
        "content": {"type": "string"},
    },
    "required": ["role", "content"],
    "additionalProperties": False,
}

QUESTION_V1: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema": {"const": QUESTION_SCHEMA_ID},
        "id": _NON_EMPTY,
        "usage": {"enum": list(USAGES)},
        "group": _NON_EMPTY,
        "unit": _NON_EMPTY,
        "source": _NON_EMPTY,
        "license": {"enum": list(LICENSES)},
        "private": {"type": "boolean"},
        "generator": {"type": ["string", "null"], "minLength": 1},
        "generator_seed": {"type": ["integer", "null"], "minimum": 0},
        "num_ctx": {"type": "integer", "minimum": 1},
        "est_prompt_tokens": {"type": "integer", "minimum": 1},
        "messages": {"type": "array", "minItems": 1, "items": _CHAT_MESSAGE},
        "turns": {
            "type": ["array", "null"],
            "minItems": 1,
            "items": {"type": "array", "minItems": 1, "items": _CHAT_MESSAGE},
        },
        "tools": {"type": ["array", "null"], "minItems": 1, "items": {"type": "object"}},
        "format": _NULLABLE_OBJECT,
        "env": {
            "type": ["object", "null"],
            "properties": {"name": _NON_EMPTY, "initial_state": {"type": "object"}},
            "required": ["name", "initial_state"],
            "additionalProperties": False,
        },
        "grader": {
            "type": "object",
            "properties": {"name": {"enum": list(GRADERS)}, "params": {"type": "object"}},
            "required": ["name", "params"],
            "additionalProperties": False,
        },
        "target": {},
        "criteria": {
            "type": ["array", "null"],
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {"id": _NON_EMPTY, "question": _NON_EMPTY},
                "required": ["id", "question"],
                "additionalProperties": False,
            },
        },
        "question_hash": _HASH,
        "prompt_hash": _HASH,
        "target_hash": _HASH,
    },
    "additionalProperties": False,
}
QUESTION_V1["required"] = list(QUESTION_V1["properties"])


class QuestionError(ValueError):
    """Question non conforme à ``qb.question/1`` ou aux règles de sa source.

    Un défaut de schéma JSON porte ``path`` et ``kind`` : ``redacted()`` rend alors un message
    sans aucune valeur (questions privées). Les autres messages du banc ne citent que des
    identifiants, des chemins et des noms de champ.
    """

    def __init__(self, message: str, *, path: str | None = None, kind: str | None = None):
        super().__init__(message)
        self.path = path
        self.kind = kind

    def redacted(self) -> str:
        """Message sûr pour une question privée : chemin et nature du défaut seulement."""
        if self.path is None:
            return str(self)
        return f"champ {self.path} non conforme ({self.kind})"


def prompt_hash(question: Mapping[str, Any]) -> str:
    """Empreinte de ``{messages, turns, tools, format, env, num_ctx}`` (AD-4)."""
    keys = ("messages", "turns", "tools", "format", "env", "num_ctx")
    return sha256_hex({key: question[key] for key in keys})


def target_hash(question: Mapping[str, Any]) -> str:
    """Empreinte de ``{target, criteria}`` (AD-4)."""
    return sha256_hex({"target": question["target"], "criteria": question["criteria"]})


def question_hash(question: Mapping[str, Any]) -> str:
    """Empreinte de la ligne entière, champs d'empreinte exclus (AD-4)."""
    return sha256_hex({k: v for k, v in question.items() if k not in HASH_FIELDS})


def with_hashes(question: Mapping[str, Any]) -> dict[str, Any]:
    """Copie de ``question`` complétée de ses trois empreintes."""
    record = {k: v for k, v in question.items() if k not in HASH_FIELDS}
    record["prompt_hash"] = prompt_hash(record)
    record["target_hash"] = target_hash(record)
    record["question_hash"] = question_hash(record)
    return record


def set_hash(questions: Iterable[Mapping[str, Any]], tracks: Mapping[str, Any]) -> str:
    """Empreinte du jeu (AD-4) : ``{questions: [[id, question_hash] triés par id], tracks}``."""
    pairs = sorted([question["id"], question["question_hash"]] for question in questions)
    return sha256_hex({"questions": pairs, "tracks": dict(tracks)})


def _check_nfc(value: Any, where: str) -> None:
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise QuestionError(f"chaîne non normalisée en NFC : {where}")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _check_nfc(key, f"{where}.{key}")
            _check_nfc(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_nfc(item, f"{where}[{index}]")


def _check_no_float(value: Any, where: str) -> None:
    """Une cible numérique est un entier ou une chaîne, jamais un flottant (AD-4)."""
    if isinstance(value, float):
        raise QuestionError(f"flottant interdit dans la cible : {where}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _check_no_float(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_no_float(item, f"{where}[{index}]")


def validate_question(question: Mapping[str, Any]) -> dict[str, Any]:
    """Valide une question ``qb.question/1`` et rend sa copie ; ``QuestionError`` sinon."""
    record = dict(question)
    try:
        validate_with(QUESTION_SCHEMA_ID, QUESTION_V1, record)
    except SchemaValidationError as error:
        raise QuestionError(str(error), path=error.path, kind=error.kind) from None

    source = record["source"]
    if source in REFUSED_SOURCES:
        raise QuestionError(f"source refusée « {source} » : {REFUSED_SOURCES[source]}")
    spec = SOURCES.get(source)
    if spec is None:
        raise QuestionError(f"source hors de la liste fermée : {source!r}")
    if record["usage"] != spec.usage:
        raise QuestionError(f"usage {record['usage']!r} non déclaré pour la source {source}")
    if record["license"] != spec.license:
        raise QuestionError(f"licence {record['license']!r} différente de celle de {source}")
    if record["private"] != spec.private or (record["license"] == "private") != spec.private:
        raise QuestionError(f"caractère privé incohérent avec la source {source}")
    if record["grader"]["name"] != spec.grader:
        raise QuestionError(f"correcteur {record['grader']['name']!r} non déclaré pour {source}")

    match = _ID_RE.match(record["id"])
    if match is None or match["usage"] != record["usage"] or match["source"] != source:
        raise QuestionError(f"identifiant hors forme <usage>/<source>/<numéro> : {record['id']!r}")
    for field in ("id", "group", "unit"):
        if "|" in record[field]:
            raise QuestionError(f"« | » interdit dans {field} (clés AD-4)")
    if (record["generator"] is None) != (record["generator_seed"] is None):
        raise QuestionError("generator et generator_seed vont ensemble (tous deux nuls ou non)")
    if (record["criteria"] is None) != (record["usage"] != "writing"):
        raise QuestionError("criteria : obligatoire en rédaction, nul ailleurs")

    _check_nfc(record, "question")
    _check_no_float(record["target"], "target")

    for field, compute in (
        ("prompt_hash", prompt_hash),
        ("target_hash", target_hash),
        ("question_hash", question_hash),
    ):
        if record[field] != compute(record):
            raise QuestionError(f"{field} ne se recalcule pas à l'identique")
    return record
