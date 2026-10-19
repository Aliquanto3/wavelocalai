"""Faits sur un modèle installé, mis en cache par `(tag, digest)` (table `model_facts`, AD-15).

`FactsStore` est l'interface que le registre consomme ; l'implémentation en mémoire sert aux
tests et d'ici au branchement sur le store SQLite (migration `0002_model_facts.sql`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from wavelocalai.models.classify import parse_params_b
from wavelocalai.store.db import utc_now_iso


@dataclass(frozen=True)
class ModelFacts:
    """Colonnes de `model_facts` (mêmes noms)."""

    tag: str
    digest: str
    size_bytes: int | None
    family: str | None
    parameter_size: str | None
    quantization: str | None
    context_length: int | None
    capabilities: tuple[str, ...]
    params_total_b: float | None
    expert_count: int | None
    expert_used_count: int | None
    fetched_at: str  # ISO 8601 UTC avec `Z`
    parameters: str | None = None  # `parameters` de `/api/show` ; `None` : détails non lus

    @property
    def default_temperature(self) -> float | None:
        """Créativité conseillée par le fabricant (ligne `temperature` des paramètres), sinon `None`."""
        return parse_temperature(self.parameters)


class FactsStore(Protocol):
    def get(self, tag: str, digest: str) -> ModelFacts | None: ...

    def put(self, facts: ModelFacts) -> None: ...

    def latest_per_tag(self) -> list[ModelFacts]:
        """Dernière ligne connue de chaque tag (liste à servir Ollama arrêté)."""
        ...

    def delete_tag(self, tag: str) -> None:
        """Efface toutes les lignes d'un tag (un modèle supprimé du poste, story 5.4) : il ne
        réapparaît plus quand la liste est reconstruite sans Ollama."""
        ...


class InMemoryFactsStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], ModelFacts] = {}

    def get(self, tag: str, digest: str) -> ModelFacts | None:
        return self._rows.get((tag, digest))

    def put(self, facts: ModelFacts) -> None:
        self._rows[(facts.tag, facts.digest)] = facts

    def delete_tag(self, tag: str) -> None:
        for key in [key for key in self._rows if key[0] == tag]:
            del self._rows[key]

    def latest_per_tag(self) -> list[ModelFacts]:
        latest: dict[str, ModelFacts] = {}
        for facts in self._rows.values():
            current = latest.get(facts.tag)
            if current is None or facts.fetched_at >= current.fetched_at:
                latest[facts.tag] = facts
        return list(latest.values())


_TEMPERATURE = re.compile(r"^\s*temperature\s+(\S+)\s*$", re.MULTILINE)
MAX_TEMPERATURE = 2.0  # borne du curseur « Créativité » ; au-delà, la valeur est ignorée


def parse_temperature(parameters: str | None) -> float | None:
    """Valeur de `temperature` dans le texte des paramètres d'Ollama ; `None` si absente ou hors
    de 0 à 2 (le curseur ne la représenterait pas)."""
    match = _TEMPERATURE.search(parameters or "")
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    return value if 0.0 <= value <= MAX_TEMPERATURE else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def facts_from_ollama(
    listed: Mapping[str, Any],
    show: Mapping[str, Any] | None,
    *,
    now: str | None = None,
) -> ModelFacts:
    """Faits d'un modèle de `/api/tags` (`listed`) et, si on l'a, de `/api/show` (`show`)."""
    tag = str(listed.get("model") or listed.get("name") or "")
    raw_details = listed.get("details")
    details: Mapping[str, Any] = raw_details if isinstance(raw_details, Mapping) else {}
    raw_info = (show or {}).get("model_info")
    info: Mapping[str, Any] = raw_info if isinstance(raw_info, Mapping) else {}
    arch = info.get("general.architecture")
    capabilities = (show or {}).get("capabilities")
    raw_parameters = (show or {}).get("parameters")
    count = info.get("general.parameter_count")
    total_b = float(count) * 1e-9 if isinstance(count, (int, float)) and count > 0 else None
    parameter_size = details.get("parameter_size")
    quantization = details.get("quantization_level")
    family = details.get("family")
    context = info.get(f"{arch}.context_length") if arch else None
    return ModelFacts(
        tag=tag,
        digest=str(listed.get("digest") or ""),
        size_bytes=_int(listed.get("size")),
        family=family if isinstance(family, str) else None,
        parameter_size=parameter_size if isinstance(parameter_size, str) else None,
        quantization=quantization if isinstance(quantization, str) else None,
        context_length=_int(context) or _int(details.get("context_length")),
        capabilities=(
            tuple(c for c in capabilities if isinstance(c, str))
            if isinstance(capabilities, list)
            else ()
        ),
        params_total_b=total_b or parse_params_b(parameter_size),
        expert_count=_int(info.get(f"{arch}.expert_count")) if arch else None,
        expert_used_count=_int(info.get(f"{arch}.expert_used_count")) if arch else None,
        fetched_at=utc_now_iso() if now is None else now,
        parameters=(
            raw_parameters if isinstance(raw_parameters, str) else "" if show is not None else None
        ),
    )
