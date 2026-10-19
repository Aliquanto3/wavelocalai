"""Port `ChatModel` (AD-8) : ce que voit un service, quel que soit l'adaptateur.

Un adaptateur n'écrit pas en base, ne calcule pas de CO2 et ne lit pas `allow_cloud`. L'annulation
est celle de la tâche asyncio : l'adaptateur ferme son flux dans un `finally`. Un refus fournisseur
lève `ProviderError(code)` (`wavelocalai.errors`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

Origin = Literal["local", "cloud", "unknown"]
Kind = Literal["chat", "embedding", "reranker"]


@dataclass(frozen=True)
class ModelRef:
    tag: str
    provider: str
    origin: Origin
    kind: Kind


Channel = Literal["answer", "thought"]
TpsSource = Literal["ollama_eval", "wallclock"]


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ChatRequest:
    messages: list[ChatMessage]
    tools: list[dict[str, Any]] = field(default_factory=list)  # schéma JSON neutre
    temperature: float = 0.2
    max_tokens: int | None = None
    think: bool = False
    response_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class ChatResult:
    finish_reason: str = "stop"
    input_tokens: int | None = None
    output_tokens: int | None = None
    ttft_s: float | None = None
    load_s: float | None = None
    eval_s: float | None = None
    total_s: float | None = None
    tps: float | None = None
    tps_source: TpsSource | None = None
    # Lecture du prompt (prefill), à part du débit D3 : écart additif à AD-8 (story 2.1), renseigné
    # par l'adaptateur Ollama seulement (`prompt_eval_count / prompt_eval_duration`).
    prefill_s: float | None = None
    prefill_tps: float | None = None


@dataclass(frozen=True)
class LoadState:
    phase: Literal["loading", "loaded"]
    duration_s: float | None = None


@dataclass(frozen=True)
class TextDelta:
    text: str
    channel: Channel = "answer"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Done:
    """Émis une seule fois, en dernier."""

    result: ChatResult


ChatChunk = LoadState | TextDelta | ToolCall | Done


@runtime_checkable
class ChatModel(Protocol):
    ref: ModelRef

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]: ...


@runtime_checkable
class Embedder(Protocol):
    """Port d'embedding (AD-8) : vecteurs de textes, locaux seulement (Ollama `/api/embed`).

    Un adaptateur ne mesure pas, ne stocke pas et ne lit pas `allow_cloud`. Il lève
    `ProviderError(code)` en cas de refus ; un appel annulé se ferme dans son `finally`."""

    ref: ModelRef

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
