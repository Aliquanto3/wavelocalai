"""Sortie structurée du port `ChatModel` (AD-8) : `ChatRequest.response_schema`.

Chaque adaptateur transmet le schéma à son fournisseur à sa façon (Ollama : `format` ; OpenAI,
Groq et Mistral : `response_format` en schéma JSON ; Anthropic : un outil forcé), puis émet le JSON
produit comme du texte de réponse (`TextDelta`, canal `answer`). Une fois le flux fini, l'adaptateur
vérifie la sortie avec `StructuredCheck` : un texte qui n'est pas du JSON, ou qui ne respecte pas le
schéma, lève `ProviderError("invalid_output")`. Le service lit ensuite la valeur avec
`parse_structured`.

Validateur minimal volontaire (`type`, `required`, `properties`, `additionalProperties: false`,
`enum`, `minimum`, `maximum`, `items`) : `jsonschema` n'est qu'une dépendance de développement.
"""

from __future__ import annotations

import json
import re
from typing import Any

from wavelocalai.errors import ProviderError

_FENCE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?```$", re.DOTALL)
_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def _is(value: Any, name: str) -> bool:
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    if name == "integer" and isinstance(value, float):
        return value.is_integer()
    return isinstance(value, _TYPES.get(name, ()))


def schema_errors(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Écarts de `value` au schéma (liste vide : valide)."""
    errors: list[str] = []
    wanted = schema.get("type")
    if wanted is not None:
        names = [wanted] if isinstance(wanted, str) else list(wanted)
        if not any(_is(value, n) for n in names):
            return [f"{path} : type attendu {'/'.join(names)}"]
    if "enum" in schema and value not in schema["enum"]:
        allowed = ", ".join(v if isinstance(v, str) else json.dumps(v) for v in schema["enum"])
        errors.append(f"{path} : valeur hors de la liste permise ({allowed})")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path} : inférieur à {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path} : supérieur à {schema['maximum']}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        errors += [
            f"{path}.{k} : champ requis absent"
            for k in schema.get("required", ())
            if k not in value
        ]
        for key, item in value.items():
            if key in properties:
                errors += schema_errors(item, properties[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key} : champ non prévu")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors += schema_errors(item, schema["items"], f"{path}[{i}]")
    return errors


def strip_fence(text: str) -> str:
    """`text` sans espaces autour ni clôture Markdown autour du JSON (tolérée par les adaptateurs
    et par le verdict du Banc d'essai, story 7.4)."""
    body = text.strip()
    fenced = _FENCE.match(body)
    return fenced.group(1).strip() if fenced else body


def parse_structured(text: str, schema: dict[str, Any]) -> Any:
    """JSON de `text` validé par `schema`. Lève `ProviderError("invalid_output")`. Une clôture
    Markdown autour du JSON est tolérée."""
    body = strip_fence(text)
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ProviderError("invalid_output", f"JSON illisible : {exc}") from exc
    errors = schema_errors(value, schema)
    if errors:
        raise ProviderError("invalid_output", "; ".join(errors[:5]))
    return value


class StructuredCheck:
    """Accumule le texte de réponse d'un appel et le vérifie à la fin. Inactif sans schéma."""

    def __init__(self, schema: dict[str, Any] | None) -> None:
        self._schema = schema
        self._parts: list[str] = []

    def add(self, text: str) -> None:
        if self._schema is not None:
            self._parts.append(text)

    def done(self) -> None:
        if self._schema is not None:
            parse_structured("".join(self._parts), self._schema)
