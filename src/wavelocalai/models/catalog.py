"""Catalogue versionné `config/models_catalog.json` : lecture seule (AD-15, AD-22).

Écrit par `scripts/build_catalog.py` dans la v1 ; la v2 ne le modifie jamais. Un fichier absent,
illisible ou au format inattendu donne un catalogue vide (le registre vit de ce qu'Ollama dit).
Les résultats du banc (`qb.results/1`) s'ajouteront ici à l'étape 5.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wavelocalai.models.classify import base_tag, parse_params_b

logger = logging.getLogger("wavelocalai.models")

_SIZE = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*(gb|go|mb|mo)?\s*$", re.IGNORECASE)


def parse_size_gb(value: Any) -> float | None:
    """« 0.7 GB », « 1,2 Go », « 350 MB » ou un nombre (Go) en Go ; `None` si illisible."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    match = _SIZE.match(str(value))
    if match is None:
        return None
    number = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "gb").lower()
    result = number * (1e-3 if unit in {"mb", "mo"} else 1.0)
    return result if result > 0 else None


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    tag: str
    editor: str | None
    size_gb: float | None
    params_total_b: float | None
    params_active_b: float | None
    context_length: int | None
    capabilities: tuple[str, ...]
    measured_loaded_gb: float | None
    description: str | None


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


def _entry(name: str, raw: dict[str, Any]) -> CatalogEntry | None:
    tag = raw.get("ollama_tag")
    if not isinstance(tag, str) or not tag:
        return None
    capabilities = raw.get("capabilities")
    ctx = raw.get("ctx")
    return CatalogEntry(
        name=name,
        tag=tag,
        editor=raw.get("editor") if isinstance(raw.get("editor"), str) else None,
        size_gb=parse_size_gb(raw.get("size_gb")),
        params_total_b=parse_params_b(raw.get("params_tot")),
        params_active_b=parse_params_b(raw.get("params_act")),
        context_length=ctx if isinstance(ctx, int) and not isinstance(ctx, bool) else None,
        capabilities=(
            tuple(c for c in capabilities if isinstance(c, str))
            if isinstance(capabilities, list)
            else ()
        ),
        measured_loaded_gb=_positive(raw.get("measured_loaded_gb")),
        description=raw.get("desc") if isinstance(raw.get("desc"), str) else None,
    )


class Catalog:
    """Entrées indexées par tag de base (la variante `:latest` est ignorée)."""

    def __init__(self, entries: dict[str, CatalogEntry] | None = None) -> None:
        self._by_tag = entries or {}

    def __len__(self) -> int:
        return len(self._by_tag)

    def find(self, tag: str) -> CatalogEntry | None:
        return self._by_tag.get(base_tag(tag))


def load_catalog(path: Path) -> Catalog:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Catalogue de modèles illisible (%s) : %s", path, exc)
        return Catalog()
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict):
        logger.warning("Catalogue de modèles au format inattendu (%s) : ignoré", path)
        return Catalog()
    entries: dict[str, CatalogEntry] = {}
    for name, raw in models.items():
        entry = _entry(str(name), raw) if isinstance(raw, dict) else None
        if entry is not None:
            entries[base_tag(entry.tag)] = entry
    return Catalog(entries)
