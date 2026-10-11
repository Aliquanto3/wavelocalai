"""Schémas JSON des lignes et des manifestes (AD-7, AD-8) : seule définition du banc.

Chaque ligne et chaque manifeste porte ``schema: "qb.<type>/<n>"``. ``validate(record)`` lit ce
champ, refuse un ``<n>`` inconnu (``UnknownSchemaError``) et vérifie l'enregistrement contre le
schéma correspondant (``additionalProperties: false`` partout). Un changement de champ
incrémente ``<n>`` : le schéma précédent reste lisible tant qu'il figure dans ``SCHEMAS``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import best_match

USAGES = ("reasoning", "instructions", "tools", "extraction", "rag", "abstention", "writing")
TRACKS = ("think_off", "think_on")
GENERATION_STATUSES = ("ok", "truncated", "context_exceeded", "error")
MANIFEST_PHASES = ("generation", "judgment")

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

SCHEMAS: dict[str, dict[str, Any]] = {
    "qb.generation/1": GENERATION_V1,
    "qb.manifest/1": MANIFEST_V1,
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

    def __init__(self, schema: str, path: str, message: str) -> None:
        self.schema = schema
        self.path = path
        super().__init__(f"{schema} : champ {path} non conforme ({message})")


def check_schemas() -> None:
    """Vérifie que chaque schéma déclaré est un JSON Schema valide (tests)."""
    for schema in SCHEMAS.values():
        _Validator.check_schema(schema)


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
        raise SchemaValidationError(name, path.lstrip(".") or "(racine)", error.message)
    return name
