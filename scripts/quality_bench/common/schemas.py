"""Schémas JSON des lignes, des manifestes et des exports (AD-6, AD-7, AD-8, AD-10, AD-14,
AD-16, AD-17) : seule définition du banc, et seul module qui importe ``jsonschema``.

Chaque ligne et chaque manifeste porte ``schema: "qb.<type>/<n>"``. ``validate(record)`` lit ce
champ, refuse un ``<n>`` inconnu (``UnknownSchemaError``) et vérifie l'enregistrement contre le
schéma correspondant (``additionalProperties: false`` partout). Un changement de champ
incrémente ``<n>`` : le schéma précédent reste lisible tant qu'il figure dans ``SCHEMAS``.

``conformity_error(schema, instance)`` vérifie une sortie de modèle contre le schéma JSON d'une
question d'extraction : validateur de la version déclarée par ``$schema``, entiers JSON
standard, aucune résolution distante.
"""

from __future__ import annotations

import ipaddress
import re
import uuid
from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, validators
from jsonschema.exceptions import best_match
from jsonschema_specifications import REGISTRY as _METASCHEMAS
from referencing import Registry
from referencing.exceptions import NoSuchResource

USAGES = ("reasoning", "instructions", "tools", "extraction", "rag", "abstention", "writing")
TRACKS = ("think_off", "think_on")
GENERATION_STATUSES = ("ok", "truncated", "context_exceeded", "error")
MANIFEST_PHASES = ("generation", "judgment")
GRADING_STATUSES = (
    "ok",
    "truncated",
    "non_compliant",
    "context_exceeded",
    "error",
    "awaiting_judgment",
)

_SCHEMA_ID_RE = re.compile(r"^qb\.([a-z_]+)/([1-9][0-9]*)$")

# Briques communes.
_HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_TIMESTAMP = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"}
_NON_EMPTY = {"type": "string", "minLength": 1}
_COUNT = {"type": "integer", "minimum": 0}
_THINK_VALUE = {"type": ["boolean", "string", "null"]}


def _closed(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    """Objet fermé : toutes les propriétés requises sauf mention contraire."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


def _turn_message(role: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "turn": _COUNT,
        "role": {"const": role},
        "content": {"type": "string"},
    }
    properties.update(extra or {})
    return _closed(properties)


GENERATION_V1: dict[str, Any] = _closed(
    {
        "schema": {"const": "qb.generation/1"},
        "key": _NON_EMPTY,
        "manifest": _HASH,
        "campaign": _NON_EMPTY,
        "model": _NON_EMPTY,
        "digest": _NON_EMPTY,
        "track": {"enum": list(TRACKS)},
        "question_id": _NON_EMPTY,
        "usage": {"enum": list(USAGES)},
        "group": _NON_EMPTY,
        "unit": _NON_EMPTY,
        "prompt_hash": _HASH,
        "seed": _COUNT,
        "epoch": _COUNT,
        "think": _THINK_VALUE,
        "backend": {"const": "ollama"},
        "ollama_version": _NON_EMPTY,
        "num_ctx": {"type": "integer", "minimum": 1},
        "num_predict": {"type": "integer", "minimum": 1},
        "status": {"enum": list(GENERATION_STATUSES)},
        "output": {
            "type": "array",
            "items": {
                "oneOf": [
                    _turn_message(
                        "assistant",
                        {
                            "thinking": {"type": ["string", "null"]},
                            "tool_calls": {"type": "array", "items": {"type": "object"}},
                        },
                    ),
                    _turn_message("tool"),
                    _turn_message("user"),
                ]
            },
        },
        "call_cap_reached": {"type": "boolean"},
        "tokens": _closed(
            {
                "prompt": _COUNT,
                "prompt_cached": _COUNT,
                "completion": _COUNT,
                "thinking_est": _COUNT,
                "answer_est": _COUNT,
            }
        ),
        "durations_ns": _closed(
            {"total": _COUNT, "load": _COUNT, "prompt_eval": _COUNT, "eval": _COUNT}
        ),
        "wall_s": {"type": "number", "minimum": 0},
        "calls": _COUNT,
        "attempts": _COUNT,
        "error": {"type": ["string", "null"]},
        "created_at": _TIMESTAMP,
    }
)

_MODEL_RESOLVED = _closed(
    {
        "tag": _NON_EMPTY,
        "digest": _NON_EMPTY,
        "family": _NON_EMPTY,
        "capabilities": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "tracks": {
            "type": "array",
            "items": {"enum": list(TRACKS)},
            "minItems": 1,
            "uniqueItems": True,
        },
        "think_off": _THINK_VALUE,
        "think_on": _THINK_VALUE,
        "num_ctx_max": {"type": "integer", "minimum": 1},
    }
)

_JUDGE = _closed(
    {
        "id": _NON_EMPTY,
        "config_hash": _HASH,
        "endpoint": _NON_EMPTY,
        "model": _NON_EMPTY,
        "settings": {"type": "object"},
        "prompt_template_hash": _HASH,
        "weights_sha256": {"oneOf": [_HASH, {"type": "null"}]},
        "server_version": {"type": ["string", "null"]},
    }
)

MANIFEST_V1: dict[str, Any] = {
    **_closed(
        {
            "schema": {"const": "qb.manifest/1"},
            "phase": {"enum": list(MANIFEST_PHASES)},
            "campaign": _NON_EMPTY,
            "created_at": _TIMESTAMP,
            "blocking": _closed(
                {
                    "set": _closed(
                        {
                            "id": _NON_EMPTY,
                            "hash": _HASH,
                            "n": _closed({"think_off": _COUNT, "think_on": _COUNT}),
                        }
                    ),
                    "generation": _closed({"hash": _HASH, "resolved": {"type": "object"}}),
                    "models_resolved": {"type": "array", "items": _MODEL_RESOLVED},
                    "ollama_version": {"type": ["string", "null"]},
                    "machine": _NON_EMPTY,
                    "harness_hash": _HASH,
                    "judge": {"oneOf": [_JUDGE, {"type": "null"}]},
                    "generation_manifest": {"oneOf": [_HASH, {"type": "null"}]},
                }
            ),
            "informative": _closed(
                {
                    "python": _NON_EMPTY,
                    "packages": {"type": "object", "additionalProperties": {"type": "string"}},
                    "code_commit": {"type": ["string", "null"]},
                    "nvidia_driver": {"type": ["string", "null"]},
                    "ollama_env": {"type": "object", "additionalProperties": {"type": "string"}},
                    "checklist": {"type": "object"},
                    "prices": {"type": ["object", "null"]},
                }
            ),
        }
    ),
    # Génération : ni juge ni manifeste amont ; jugement : les deux sont obligatoires.
    "if": {"properties": {"phase": {"const": "judgment"}}},
    "then": {
        "properties": {
            "blocking": {"properties": {"judge": {"type": "object"}, "generation_manifest": _HASH}}
        }
    },
    "else": {
        "properties": {
            "blocking": {
                "properties": {"judge": {"type": "null"}, "generation_manifest": {"type": "null"}}
            }
        }
    },
}

# Index versionné d'un jeu (AD-6) : liste blanche fermée ; empreintes de prompt et de cible
# pour les seules questions publiques, interdites pour une question privée.
_SET_INDEX_PUBLIC = ("prompt_hash", "target_hash")
SET_INDEX_V1: dict[str, Any] = {
    **_closed(
        {
            "schema": {"const": "qb.set_index/1"},
            "id": _NON_EMPTY,
            "usage": {"enum": list(USAGES)},
            "group": _NON_EMPTY,
            "unit": _NON_EMPTY,
            "source": _NON_EMPTY,
            "license": _NON_EMPTY,
            "private": {"type": "boolean"},
            "question_hash": _HASH,
            "prompt_hash": _HASH,
            "target_hash": _HASH,
        },
        required=[
            "schema",
            "id",
            "usage",
            "group",
            "unit",
            "source",
            "license",
            "private",
            "question_hash",
        ],
    ),
    "if": {"properties": {"private": {"const": False}}},
    "then": {"required": list(_SET_INDEX_PUBLIC)},
    "else": {"not": {"anyOf": [{"required": [field]} for field in _SET_INDEX_PUBLIC]}},
}

# Manifeste versionné d'un jeu (AD-6, amendement du 2026-10-17) : provenance publique seulement.
# Aucun texte de question, aucune empreinte de fichier privé : les entrées listées sont les
# fichiers publics (candidats des importeurs, fichiers bruts des générateurs, questions maison
# versionnées).
SET_INPUT_KINDS = ("candidates", "raw", "house")
SET_MANIFEST_V1: dict[str, Any] = _closed(
    {
        "schema": {"const": "qb.set_manifest/1"},
        "set": _NON_EMPTY,
        "set_hash": _HASH,
        "seed": _COUNT,
        "counts": _closed({"think_off": _COUNT, "think_on": _COUNT}),
        "generators": {"type": "array", "items": _NON_EMPTY, "uniqueItems": True},
        "inputs": {
            "type": "array",
            "items": _closed(
                {
                    "source": _NON_EMPTY,
                    "kind": {"enum": list(SET_INPUT_KINDS)},
                    "path": _NON_EMPTY,
                    "sha256": _HASH,
                }
            ),
        },
        "index_sha256": _HASH,
        "commit": {"type": ["string", "null"], "pattern": "^[0-9a-f]{40}$"},
        "dirty": {"type": ["boolean", "null"]},
    }
)

# Ligne de correction (AD-10) : seul porteur de score et de success (AD-3). Règles croisées :
# erreurs du banc et attente du juge sans score ; échecs du modèle à 0 ; rédaction
# (judge_criteria) sans success ; ailleurs, score = success.
_UNSCORED = ["context_exceeded", "error", "awaiting_judgment"]
_MODEL_FAILURES = ["truncated", "non_compliant"]
GRADING_V1: dict[str, Any] = {
    **_closed(
        {
            "schema": {"const": "qb.grading/1"},
            "key": _NON_EMPTY,
            "generation_manifest": _HASH,
            "judgment_manifest": {"oneOf": [_HASH, {"type": "null"}]},
            "grader": {"type": "string", "pattern": "^[a-z][a-z0-9_]*@[1-9][0-9]*$"},
            "status": {"enum": list(GRADING_STATUSES)},
            "score": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "success": {"type": ["boolean", "null"]},
            "metrics": {"type": "object", "additionalProperties": {"type": "number"}},
        }
    ),
    "allOf": [
        {
            "if": {"properties": {"status": {"enum": _UNSCORED}}},
            "then": {"properties": {"score": {"type": "null"}, "success": {"type": "null"}}},
        },
        {
            "if": {"properties": {"status": {"enum": _MODEL_FAILURES}}},
            "then": {"properties": {"score": {"const": 0}, "success": {"enum": [False, None]}}},
        },
        {
            "if": {"properties": {"status": {"const": "ok"}}},
            "then": {"properties": {"score": {"type": "number"}}},
        },
        {
            "if": {"properties": {"grader": {"pattern": "^judge_criteria@"}}},
            "then": {"properties": {"success": {"type": "null"}}},
            "else": {
                "if": {"properties": {"status": {"enum": ["ok", *_MODEL_FAILURES]}}},
                "then": {"properties": {"success": {"type": "boolean"}}},
            },
        },
        {
            "if": {"properties": {"success": {"const": True}}, "required": ["success"]},
            "then": {"properties": {"score": {"const": 1}}},
        },
        {
            "if": {"properties": {"success": {"const": False}}, "required": ["success"]},
            "then": {"properties": {"score": {"const": 0}}},
        },
    ],
}

# Ligne de jugement (AD-16), une par critère : verdict booléen, ou nul avec une erreur.
JUDGMENT_V1: dict[str, Any] = {
    **_closed(
        {
            "schema": {"const": "qb.judgment/1"},
            "key": _NON_EMPTY,
            "generation_key": _NON_EMPTY,
            "manifest": _HASH,
            "criterion": _NON_EMPTY,
            "judge": _NON_EMPTY,
            "verdict": {"type": ["boolean", "null"]},
            "probability": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
            "tokens": _closed({"input": _COUNT, "output": _COUNT}),
            "cost_usd": {"type": "number", "minimum": 0},
            "attempts": _COUNT,
            "error": {"type": ["string", "null"]},
            "created_at": _TIMESTAMP,
        }
    ),
    "if": {"properties": {"error": {"type": "null"}}},
    "then": {"properties": {"verdict": {"type": "boolean"}}},
    "else": {"properties": {"verdict": {"type": "null"}}},
}

# Lot cloud consigné (AD-16), dans ``judgment-<juge>/batches.jsonl`` : ligne ``submitted`` écrite
# avant toute attente (clés du lot dans l'ordre des ``custom_id``), puis ligne ``collected`` après
# lecture des résultats (comptes, tokens, coût réel, issue de chaque clé). Aucun texte.
BATCH_OUTCOMES = ("ok", "transient", "unit")
_BATCH_COMMON = {
    "schema": {"const": "qb.batch/1"},
    "key": _NON_EMPTY,
    "batch_id": _NON_EMPTY,
    "judge": _NON_EMPTY,
    "manifest": _HASH,
    "created_at": _TIMESTAMP,
}
BATCH_V1: dict[str, Any] = {
    "oneOf": [
        _closed(
            {
                **_BATCH_COMMON,
                "status": {"const": "submitted"},
                "keys": {
                    "type": "array",
                    "items": _NON_EMPTY,
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "estimate_usd": {"type": "number", "minimum": 0},
            }
        ),
        _closed(
            {
                **_BATCH_COMMON,
                "status": {"const": "collected"},
                "counts": _closed(
                    {"succeeded": _COUNT, "errored": _COUNT, "canceled": _COUNT, "expired": _COUNT}
                ),
                "tokens": _closed({"input": _COUNT, "output": _COUNT}),
                "cost_usd": {"type": "number", "minimum": 0},
                "outcomes": {
                    "type": "object",
                    "additionalProperties": {"enum": list(BATCH_OUTCOMES)},
                },
            }
        ),
    ]
}

# Chauffe consignée (AD-14) : une ligne par requête de chauffe, jamais par question. ``size``,
# ``size_vram`` (``/api/ps``) et ``prefill_tok_s`` sont nuls s'ils sont inconnus.
WARMUP_V1: dict[str, Any] = _closed(
    {
        "schema": {"const": "qb.warmup/1"},
        "key": _NON_EMPTY,
        "manifest": _HASH,
        "campaign": _NON_EMPTY,
        "model": _NON_EMPTY,
        "num_ctx": {"type": "integer", "minimum": 1},
        "prompt_tokens": _COUNT,
        "size": {"type": ["integer", "null"], "minimum": 0},
        "size_vram": {"type": ["integer", "null"], "minimum": 0},
        "prefill_tok_s": {"type": ["number", "null"], "minimum": 0},
        "load_ns": _COUNT,
        "created_at": _TIMESTAMP,
    }
)

# Exports d'une campagne (AD-6, AD-17), écrits par report/ sous benchmarks/quality/<c>/ :
# schémas fermés, flottants finis seulement, ``null`` pour une valeur indéfinie.
_NUMBER = {"type": "number"}
_MAYBE_NUMBER = {"type": ["number", "null"]}
_MAYBE_COUNT = {"type": ["integer", "null"], "minimum": 0}
_MAYBE_TAG = {"type": ["string", "null"], "minLength": 1}
_DATE = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
CONTINUOUS_METRICS = ("instructions_followed", "f1")
REPORT_METHODS = ("mcnemar", "paired_z")
P_METHODS = ("mcnemar", "z", "sign")
SPEARMAN_CONCLUSIONS = ("inconclusive", "investigate", "concordant", "not_significant")
AA_STATUSES = ("measured", "estimated")
AA_VARIANTS = ("reasoning", "non_reasoning")

# Score d'une question pour un modèle (AD-6) : ni identifiant ni texte de question.
SCORE_V1: dict[str, Any] = _closed(
    {
        "schema": {"const": "qb.score/1"},
        "question_hash": _HASH,
        "model": _NON_EMPTY,
        "digest": _NON_EMPTY,
        "track": {"enum": list(TRACKS)},
        "seed": _COUNT,
        "status": {"enum": list(GRADING_STATUSES)},
        "score": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        "success": {"type": ["boolean", "null"]},
        "metrics": {"type": "object", "additionalProperties": _NUMBER},
    }
)

_REPORT_MODEL_STATS = _closed(
    {
        "model": _NON_EMPTY,
        "mean": _MAYBE_NUMBER,
        "n": _COUNT,
        "excluded": _COUNT,
        "se": _MAYBE_NUMBER,
        "ci_low": _MAYBE_NUMBER,
        "ci_high": _MAYBE_NUMBER,
        "sim_ci_low": _MAYBE_NUMBER,
        "sim_ci_high": _MAYBE_NUMBER,
        "rank": {"type": ["integer", "null"], "minimum": 1},
        "group": {"type": ["integer", "null"], "minimum": 1},
        "graded": _COUNT,
        "truncated": _COUNT,
        "truncation_rate": _MAYBE_NUMBER,
    }
)
_REPORT_COMPARISON = _closed(
    {
        "model": _NON_EMPTY,
        "n": _COUNT,
        "diff": _MAYBE_NUMBER,
        "se": _MAYBE_NUMBER,
        "ci_low": _MAYBE_NUMBER,
        "ci_high": _MAYBE_NUMBER,
        "bootstrap_ci_low": _MAYBE_NUMBER,
        "bootstrap_ci_high": _MAYBE_NUMBER,
        "correlation": _MAYBE_NUMBER,
        "b": _MAYBE_COUNT,
        "c": _MAYBE_COUNT,
        "p": _MAYBE_NUMBER,
        "p_method": {"enum": list(P_METHODS)},
        "p_holm": _MAYBE_NUMBER,
        "reject": {"type": "boolean"},
    }
)
_REPORT_PAIR = _closed(
    {
        "a": _NON_EMPTY,
        "b": _NON_EMPTY,
        "n": _COUNT,
        "diff": _MAYBE_NUMBER,
        "p": _MAYBE_NUMBER,
        "p_method": {"enum": list(P_METHODS)},
        "p_bh": _MAYBE_NUMBER,
        "reject": {"type": "boolean"},
    }
)
_REPORT_CONTINUOUS = _closed(
    {
        "metric": {"enum": list(CONTINUOUS_METRICS)},
        "leader": _MAYBE_TAG,
        "models": {
            "type": "array",
            "items": _closed(
                {"model": _NON_EMPTY, "mean": _MAYBE_NUMBER, "n": _COUNT, "excluded": _COUNT}
            ),
        },
        "comparisons": {
            "type": "array",
            "items": _closed(
                {
                    "model": _NON_EMPTY,
                    "n": _COUNT,
                    "diff": _MAYBE_NUMBER,
                    "bootstrap_ci_low": _MAYBE_NUMBER,
                    "bootstrap_ci_high": _MAYBE_NUMBER,
                }
            ),
        },
    }
)
_REPORT_SCOPE = _closed(
    {
        "usage": {"enum": [*USAGES, None]},
        "method": {"enum": list(REPORT_METHODS)},
        "units": _COUNT,
        "leader": _MAYBE_TAG,
        "models": {"type": "array", "items": _REPORT_MODEL_STATS},
        "comparisons": {"type": "array", "items": _REPORT_COMPARISON},
        "matrix": {"type": "array", "items": _REPORT_PAIR},
        "continuous": {"oneOf": [_REPORT_CONTINUOUS, {"type": "null"}]},
    }
)
_REPORT_TRACK = _closed(
    {
        "track": {"enum": list(TRACKS)},
        "scopes": {"type": "array", "items": _REPORT_SCOPE},
        "k_bonferroni": _closed(
            {
                "leader": _MAYBE_TAG,
                "usages": _COUNT,
                "alpha_per_test": _MAYBE_NUMBER,
                "models": {
                    "type": "array",
                    "items": _closed({"model": _NON_EMPTY, "wins": _COUNT, "tests": _COUNT}),
                },
            }
        ),
        "spearman": _closed(
            {
                "status": {"enum": ["absent", "computed"]},
                "variant": {"enum": list(AA_VARIANTS)},
                "n": _COUNT,
                "models": {"type": "array", "items": _NON_EMPTY},
                "rho": _MAYBE_NUMBER,
                "p": _MAYBE_NUMBER,
                "ci_low": _MAYBE_NUMBER,
                "ci_high": _MAYBE_NUMBER,
                "conclusion": {"enum": [*SPEARMAN_CONCLUSIONS, None]},
            }
        ),
    }
)

# Résumé statistique d'une campagne (AD-6, AD-17) : agrégats seuls, aucun identifiant ni texte
# de question.
REPORT_V1: dict[str, Any] = _closed(
    {
        "schema": {"const": "qb.report/1"},
        "campaign": _NON_EMPTY,
        "partial": {"type": "boolean"},
        "set": _closed({"id": _NON_EMPTY, "hash": _HASH}),
        "generation_manifest": _HASH,
        "judgment_manifest": {"oneOf": [_HASH, {"type": "null"}]},
        "k": {"type": "integer", "minimum": 1},
        "method": _closed(
            {
                "alpha": _NUMBER,
                "bootstrap_resamples": {"type": "integer", "minimum": 1},
                "bootstrap_seed": _COUNT,
            }
        ),
        "completeness": _closed(
            {
                "expected": _COUNT,
                "retained": _COUNT,
                "generation_missing": _COUNT,
                "generation_discordant": _COUNT,
                "grading_missing": _COUNT,
                "grading_discordant": _COUNT,
                "awaiting_judgment": _COUNT,
                "config_discordant": {"type": "boolean"},
            }
        ),
        "models": {
            "type": "array",
            "items": _closed(
                {
                    "tag": _NON_EMPTY,
                    "digest": _NON_EMPTY,
                    "family": _NON_EMPTY,
                    "tracks": {"type": "array", "items": {"enum": list(TRACKS)}},
                }
            ),
        },
        "tracks": {"type": "array", "items": _REPORT_TRACK},
        "aa_reference": {
            "oneOf": [
                _closed({"path": _NON_EMPTY, "sha256": _HASH, "date": _DATE}),
                {"type": "null"},
            ]
        },
    }
)

# Indices Artificial Analysis datés, fournis hors ligne (AD-17) :
# benchmarks/quality/references/aa-<AAAA-MM-JJ>.json.
AA_REFERENCE_V1: dict[str, Any] = _closed(
    {
        "schema": {"const": "qb.aa_reference/1"},
        "date": _DATE,
        "source": _NON_EMPTY,
        "entries": {
            "type": "array",
            "items": _closed(
                {
                    "tag": _NON_EMPTY,
                    "index": _NUMBER,
                    "status": {"enum": list(AA_STATUSES)},
                    "variant": {"enum": list(AA_VARIANTS)},
                }
            ),
        },
    }
)

# Étiquette humaine de calibration (CAP-6), dans ``calibration/labels.jsonl``, écrit par Anaël
# seul (AD-2) : clé de jugement ``<generation_key>|<critère>`` ; ``label`` nul = à étiqueter.
# Une étiquette posée (vrai, faux ou indécidable) porte son auteur et sa date (jour ou
# horodatage UTC).
LABEL_VALUES = (True, False, "undecidable", None)
_JUDGMENT_KEY = {"type": "string", "pattern": r"^[^|]+(\|[^|]+){5}$"}
_DAY_OR_TIMESTAMP = {
    "type": "string",
    "pattern": r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$",
}
LABEL_V1: dict[str, Any] = {
    **_closed(
        {
            "schema": {"const": "qb.label/1"},
            "key": _JUDGMENT_KEY,
            "label": {"enum": list(LABEL_VALUES)},
            "author": {"type": ["string", "null"]},
            "labeled_at": {"oneOf": [_DAY_OR_TIMESTAMP, {"type": "null"}]},
            "note": {"type": ["string", "null"]},
        }
    ),
    "if": {"properties": {"label": {"const": None}}},
    "then": {},
    "else": {"properties": {"author": _NON_EMPTY, "labeled_at": _DAY_OR_TIMESTAMP}},
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "qb.generation/1": GENERATION_V1,
    "qb.warmup/1": WARMUP_V1,
    "qb.manifest/1": MANIFEST_V1,
    "qb.set_index/1": SET_INDEX_V1,
    "qb.set_manifest/1": SET_MANIFEST_V1,
    "qb.grading/1": GRADING_V1,
    "qb.judgment/1": JUDGMENT_V1,
    "qb.batch/1": BATCH_V1,
    "qb.score/1": SCORE_V1,
    "qb.report/1": REPORT_V1,
    "qb.aa_reference/1": AA_REFERENCE_V1,
    "qb.label/1": LABEL_V1,
}


def _is_strict_integer(_checker: Any, instance: Any) -> bool:
    """Un entier JSON est un ``int`` Python, jamais un flottant entier ni un booléen (AD-4)."""
    return isinstance(instance, int) and not isinstance(instance, bool)


_Validator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine("integer", _is_strict_integer),
)
_VALIDATORS = {name: _Validator(schema) for name, schema in SCHEMAS.items()}


class UnknownSchemaError(ValueError):
    """Champ ``schema`` absent, mal formé ou de version inconnue."""


class SchemaValidationError(ValueError):
    """Enregistrement non conforme à son schéma déclaré."""

    def __init__(self, schema: str, path: str, message: str, kind: str | None = None) -> None:
        self.schema = schema
        self.path = path
        self.kind = kind  # mot-clé JSON Schema en défaut (type, required…), sans valeur
        super().__init__(f"{schema} : champ {path} non conforme ({message})")


def check_schemas() -> None:
    """Vérifie que chaque schéma déclaré est un JSON Schema valide (tests)."""
    for schema in SCHEMAS.values():
        _Validator.check_schema(schema)


def check_schema(schema: Mapping[str, Any]) -> None:
    """Vérifie qu'un schéma défini hors de ce module (``qb.question/1``) est un JSON Schema
    valide pour le même vérificateur que ``validate_with`` (tests)."""
    _Validator.check_schema(dict(schema))


def _json_path(error: Any) -> str:
    path = "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.path)
    return path.lstrip(".") or "(racine)"


def instance_errors(schema: Mapping[str, Any], instance: Any) -> str | None:
    """Chemin JSON et mot-clé du premier défaut d'``instance`` contre un schéma JSON quelconque
    (cible d'une question d'extraction maison), ou ``None`` ; jamais de valeur (questions
    privées). Même vérificateur d'entiers stricts (AD-4)."""
    error = best_match(_Validator(dict(schema)).iter_errors(instance))
    return None if error is None else f"{_json_path(error)} ({error.validator})"


def _no_remote_retrieval(uri: str) -> Any:
    """Aucune résolution distante : seuls les métaschémas embarqués et les références
    internes au schéma se résolvent."""
    raise NoSuchResource(ref=uri)


_LOCAL_REGISTRY = _METASCHEMAS.combine(Registry(retrieve=_no_remote_retrieval))

# Formats vérifiés par conformity_error (json_schema@2), comme le FormatChecker de JSONSchemaBench
# (core/evaluator.py) mais figés : ceux que jsonschema contrôle sans dépendance facultative. Les
# autres (date-time, uri, hostname...) restent des annotations ; `time` est écarté (le contrôle
# de jsonschema sans extra suit le draft 3, pas RFC 3339). `ipv4`, `ipv6` et `uuid` sont
# redéfinis comme dans l'amont (constructeur de `ipaddress` ou `uuid` seul) : jsonschema refuse
# en plus une adresse IPv6 à zone (`fe80::1%eth0`) et un UUID sans tirets ou entre accolades.
# `regex` dépend du moteur `re` de la version de Python, comme dans l'amont.
FORMAT_CHECKED = ("date", "email", "idn-email", "ipv4", "ipv6", "regex", "uuid")
_FORMAT_CHECKER = FormatChecker(("date", "email", "idn-email", "regex"))


def _upstream_format(name: str, parse: Any, raises: Any) -> None:
    def check(instance: object) -> bool:
        if isinstance(instance, str):  # `format` ne contraint que les chaînes
            parse(instance)
        return True

    _FORMAT_CHECKER.checks(name, raises=raises)(check)


_upstream_format("ipv4", ipaddress.IPv4Address, ValueError)
_upstream_format("ipv6", ipaddress.IPv6Address, ValueError)
_upstream_format("uuid", uuid.UUID, ValueError)


def conformity_error(schema: Any, instance: Any) -> str | None:
    """Chemin JSON et mot-clé du premier défaut d'``instance`` (sortie de modèle) contre le
    schéma d'une question d'extraction, ou ``None`` s'il est conforme.

    Validateur de la version que déclare ``$schema`` (2020-12 par défaut), entiers JSON de
    cette version (``1.0`` est un entier à partir du draft 6 ; les drafts 3 et 4 le refusent),
    aucune résolution distante, mots-clés `format` de `FORMAT_CHECKED` vérifiés.
    Un schéma invérifiable (référence introuvable, motif invalide) lève l'exception de
    ``jsonschema`` ou de ``referencing`` : c'est une erreur du banc, jamais un échec du modèle.
    """
    validator_class = validators.validator_for(schema, default=Draft202012Validator)
    validator = validator_class(schema, registry=_LOCAL_REGISTRY, format_checker=_FORMAT_CHECKER)
    error = best_match(validator.iter_errors(instance))
    return None if error is None else f"{_json_path(error)} ({error.validator})"


def validate_with(name: str, schema: Mapping[str, Any], record: Mapping[str, Any]) -> None:
    """Valide ``record`` contre ``schema``, un schéma défini hors de ce module (``qb.question/1``
    vit dans ``questions/schema.py``, AD-5) ; même vérificateur d'entiers stricts (AD-4) et
    même ``SchemaValidationError`` que ``validate``."""
    error = best_match(_Validator(dict(schema)).iter_errors(dict(record)))
    if error is not None:
        path = "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.path)
        raise SchemaValidationError(
            name, path.lstrip(".") or "(racine)", error.message, str(error.validator)
        )


def validate(record: Mapping[str, Any]) -> str:
    """Valide ``record`` contre le schéma que nomme son champ ``schema`` ; rend ce nom."""
    if not isinstance(record, Mapping):
        raise UnknownSchemaError("Enregistrement qui n'est pas un objet JSON")
    name = record.get("schema")
    if not isinstance(name, str) or not _SCHEMA_ID_RE.match(name):
        raise UnknownSchemaError(f"Champ « schema » absent ou mal formé : {name!r}")
    validator = _VALIDATORS.get(name)
    if validator is None:
        raise UnknownSchemaError(f"Schéma inconnu de cette version du banc : {name}")
    error = best_match(validator.iter_errors(dict(record)))
    if error is not None:
        path = "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.path)
        raise SchemaValidationError(
            name, path.lstrip(".") or "(racine)", error.message, str(error.validator)
        )
    return name
