"""Vocabulaire du hub des runs : genres, statuts, résultat d'une feuille et champ `co2` (AD-5, AD-10).

Ces listes sont closes ; elles reprennent les contraintes `CHECK` de `0001_hub.sql` (un test
vérifie qu'elles concordent).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ROOT_KINDS = ("chat", "arena", "rag", "agent", "ingest", "pull", "eval", "bench")
LEAF_KINDS = ("generation", "judge", "embedding")
RUN_KINDS = ROOT_KINDS + LEAF_KINDS
CONVERSATION_KINDS = ("chat", "rag", "agent")  # un run de ce genre peut ouvrir une conversation

STATUSES = ("running", "awaiting_approval", "ok", "error", "cancelled", "interrupted")
FINAL_STATUSES = ("ok", "error", "cancelled")  # ceux qu'un service peut fixer ; `interrupted`
# est réservé au démarrage du serveur

CO2_METHODS = ("codecarbon", "ecologits", "unmeasurable")
CO2_ALLOCATIONS = ("direct", "prorata_tokens")
TPS_SOURCES = ("ollama_eval", "wallclock")
ORIGINS = ("local", "cloud")

# Événements que le hub seul publie (AD-5, AD-6) : un service ne les publie jamais.
RESERVED_EVENTS = ("run_started", "run_ended")


@dataclass(frozen=True)
class Co2:
    """Champ `co2` unique d'AD-10. `mg` nul exige une `reason` : jamais 0 pour un inconnu."""

    mg: float | None
    method: str
    estimated: bool = False
    range_mg: dict[str, float] | None = None  # {"low": …, "high": …}
    allocation: str = "direct"
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.method not in CO2_METHODS:
            raise ValueError(f"co2.method inconnue : {self.method!r}")
        if self.allocation not in CO2_ALLOCATIONS:
            raise ValueError(f"co2.allocation inconnue : {self.allocation!r}")
        if self.mg is None and not self.reason:
            raise ValueError("co2.reason est requis quand co2.mg est nul")
        if self.method == "unmeasurable" and self.mg is not None:
            raise ValueError("un co2 « unmeasurable » n'a pas de valeur : mg doit être nul")
        if self.range_mg is not None and set(self.range_mg) != {"low", "high"}:
            raise ValueError("co2.range_mg vaut {low, high}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "mg": self.mg,
            "method": self.method,
            "estimated": self.estimated,
            "range_mg": self.range_mg,
            "allocation": self.allocation,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AssistantMessage:
    """Message assistant que le hub écrit avec le statut final (AD-5)."""

    content: str = ""
    reasoning: str | None = None
    tool_calls: list[dict[str, Any]] | None = None

    def is_empty(self) -> bool:
        return not (self.content or self.reasoning or self.tool_calls)


@dataclass(frozen=True)
class LeafResult:
    """Ce qu'un service rend à `hub.finish_leaf` : statut, métriques, erreur, message."""

    status: str = "ok"
    origin: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    ttft_s: float | None = None
    load_s: float | None = None
    eval_s: float | None = None
    total_s: float | None = None
    tps: float | None = None
    tps_source: str | None = None
    energy_wh: float | None = None
    error: dict[str, Any] | None = None  # enveloppe d'AD-18
    assistant: AssistantMessage | None = None  # pour une feuille racine seulement

    def __post_init__(self) -> None:
        if self.status not in FINAL_STATUSES:
            raise ValueError(f"statut de fin inconnu : {self.status!r}")
        if self.origin is not None and self.origin not in ORIGINS:
            raise ValueError(f"origin inconnue : {self.origin!r}")
        if self.tps_source is not None and self.tps_source not in TPS_SOURCES:
            raise ValueError(f"tps_source inconnue : {self.tps_source!r}")


@dataclass(frozen=True)
class RunHandle:
    run_id: str
    conversation_id: str | None = None


@dataclass(frozen=True)
class StoredMessage:
    """Un message de conversation tel que le hub l'a écrit (rôle et texte seulement)."""

    role: str
    content: str
