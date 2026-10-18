"""Classement d'un modèle par son tag et ses détails Ollama (sans appel réseau).

`is_embedding_model` est la règle de la v1 (PR #30, `src/core/model_defaults.py`), recopiée.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REASONING_MARKERS = ("thinking", "reasoning")
REMOTE_TAG_VARIANT = "cloud"
REMOTE_TAG_SUFFIX = "-cloud"


def base_tag(tag: str) -> str:
    """Tag sans la variante `:latest` (clé de correspondance avec le catalogue)."""
    return tag.removesuffix(":latest")


def is_embedding_model(model: Mapping[str, Any]) -> bool:
    """Modèle d'embedding (`nomic-embed-text`), inapte à générer du texte : « embed » dans le
    tag (insensible à la casse) ou famille BERT dans les détails d'Ollama."""
    if "embed" in str(model.get("model") or model.get("name") or "").lower():
        return True
    details = model.get("details")
    family = details.get("family") if isinstance(details, Mapping) else None
    return "bert" in str(family or "").lower()


def is_reranker_model(tag: str) -> bool:
    """Reranker : « rerank » dans le tag. Ollama n'a pas d'API de reranking : ce type vient du
    cache fastembed (AD-17) ou d'un modèle nommé ainsi."""
    return "rerank" in tag.lower()


def is_remote_tag(model: Mapping[str, Any]) -> bool:
    """Tag distant servi par Ollama (`glm-4.6:cloud`, `gpt-oss:120b-cloud`) : ses données
    quittent la machine, il compte comme cloud."""
    if model.get("remote_host"):
        return True
    name, _, variant = str(model.get("model") or model.get("name") or "").lower().partition(":")
    return (
        variant == REMOTE_TAG_VARIANT
        or variant.endswith(REMOTE_TAG_SUFFIX)
        or name.endswith(REMOTE_TAG_SUFFIX)
    )


def is_dedicated_reasoning(*names: str | None) -> bool:
    """Modèle dédié au raisonnement : « thinking » ou « reasoning » dans l'un de ses noms."""
    text = " ".join(n for n in names if n).lower()
    return any(marker in text for marker in REASONING_MARKERS)


_PARAMS = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*([kmbt])?\s*$", re.IGNORECASE)
_SCALE = {"": 1e-9, "k": 1e-6, "m": 1e-3, "b": 1.0, "t": 1e3}


def parse_params_b(value: Any) -> float | None:
    """Paramètres en milliards depuis « 2.3B », « 873.44M » ou « 137M » ; `None` si illisible."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) * 1e-9 if value > 0 else None
    match = _PARAMS.match(str(value))
    if match is None:
        return None
    number = float(match.group(1).replace(",", "."))
    result = number * _SCALE[(match.group(2) or "").lower()]
    return result if result > 0 else None
