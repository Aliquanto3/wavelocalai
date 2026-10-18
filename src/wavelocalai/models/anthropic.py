"""Adaptateur du port `ChatModel` pour Anthropic (Claude), sur le SDK officiel (AD-8).

Copie adaptée du streaming de `src/core/providers/anthropic_provider.py` (v1), sans
`get_langchain_model` et sans importer la v1 ; la lecture des événements bruts
(`message_start`, `content_block_delta`, `message_delta`) suit celle du harnais
`wavestack/models/anthropic_messages.py`. Le SDK n'est importé que dans la fonction (AD-4).

`temperature` n'est pas envoyée : les modèles Claude actuels refusent les paramètres
d'échantillonnage (erreur 400). Les messages `system` vont dans le champ `system`. L'adaptateur émet
des `TextDelta` (`thinking_delta` sur le canal `thought`), puis un seul `Done` avec
`tps_source = "wallclock"` ; il ne calcule pas de CO2, n'écrit pas en base et ne lit pas
`allow_cloud`. Flux et client sont fermés dans un `finally` (annulation comprise).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from wavelocalai.models.cloud import (
    CONNECT_TIMEOUT_S,
    HttpClientFactory,
    WallClock,
    close_quietly,
    key_missing,
    model_of,
    translate_error,
)
from wavelocalai.models.port import ChatChunk, ChatRequest, Done, ModelRef, TextDelta
from wavelocalai.models.structured import StructuredCheck

STRUCTURED_TOOL = "respond"  # outil forcé qui porte `response_schema` (`tool_use`)
DEFAULT_MAX_TOKENS = 16_000  # `max_tokens` est obligatoire chez Anthropic ; le raisonnement en use


def _field(obj: Any, name: str) -> Any:
    return getattr(obj, name, None)


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _split_messages(request: ChatRequest) -> tuple[str | None, list[dict[str, str]]]:
    system = [m.content for m in request.messages if m.role == "system" and m.content]
    messages = [
        {"role": m.role, "content": m.content}
        for m in request.messages
        if m.role in ("user", "assistant") and m.content
    ]
    return ("\n\n".join(system) or None), messages


class AnthropicChatModel:
    """`ChatModel` pour un modèle Claude (`anthropic/<modèle>`)."""

    def __init__(
        self,
        ref: ModelRef,
        api_key: str | None,
        *,
        http_client: HttpClientFactory | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.ref = ref
        self._api_key = api_key
        self._http_client = http_client
        self._clock = clock

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        if not self._api_key:
            raise key_missing("anthropic")
        from anthropic import AsyncAnthropic, Timeout  # import paresseux (AD-4)

        clock = WallClock(self._clock)
        client_args: dict[str, Any] = {
            "api_key": self._api_key,
            "max_retries": 0,
            "timeout": Timeout(None, connect=CONNECT_TIMEOUT_S),
        }
        if self._http_client is not None:
            client_args["http_client"] = self._http_client()
        client = AsyncAnthropic(**client_args)
        system, messages = _split_messages(request)
        extra: dict[str, Any] = {"system": system} if system else {}
        if request.response_schema is not None:
            extra["tools"] = [
                {
                    "name": STRUCTURED_TOOL,
                    "description": "Rend la réponse sous la forme structurée demandée.",
                    "input_schema": request.response_schema,
                }
            ]
            extra["tool_choice"] = {"type": "tool", "name": STRUCTURED_TOOL}
        structured = StructuredCheck(request.response_schema)
        upstream: Any = None
        fragments = 0
        finish: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        try:
            upstream = await client.messages.create(
                model=model_of(self.ref.tag),
                max_tokens=request.max_tokens or DEFAULT_MAX_TOKENS,
                messages=messages,  # type: ignore[arg-type]
                stream=True,
                **extra,
            )
            async for event in upstream:
                kind = _field(event, "type")
                if kind == "message_start":
                    usage = _field(_field(event, "message"), "usage")
                    input_tokens = _count(_field(usage, "input_tokens")) or input_tokens
                elif kind == "content_block_delta":
                    delta = _field(event, "delta")
                    delta_type = _field(delta, "type")
                    if delta_type == "text_delta" and _field(delta, "text"):
                        text = str(_field(delta, "text"))
                        clock.note(text)
                        fragments += 1
                        yield TextDelta(text, "answer")
                    elif delta_type == "thinking_delta" and _field(delta, "thinking"):
                        text = str(_field(delta, "thinking"))
                        clock.note(text)
                        fragments += 1
                        yield TextDelta(text, "thought")
                    elif delta_type == "input_json_delta" and _field(delta, "partial_json"):
                        # Entrée de l'outil forcé : le JSON de la réponse, émis comme du texte.
                        text = str(_field(delta, "partial_json"))
                        clock.note(text)
                        fragments += 1
                        structured.add(text)
                        yield TextDelta(text, "answer")
                elif kind == "message_delta":
                    finish = _field(_field(event, "delta"), "stop_reason") or finish
                    usage = _field(event, "usage")
                    output_tokens = _count(_field(usage, "output_tokens")) or output_tokens
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            mapped = translate_error("anthropic", exc, self._api_key, fragments=fragments)
            if mapped is exc:
                raise
            raise mapped from exc
        finally:
            await close_quietly(upstream)
            await close_quietly(client)
        if request.response_schema is not None and finish == "tool_use":
            finish = "end_turn"  # l'outil forcé est le mode de réponse, pas un appel d'outil
        if request.response_schema is not None and finish == "tool_use":
            finish = "end_turn"  # l'outil forcé est le mode de réponse, pas un appel d'outil
        structured.done()
        yield Done(
            clock.result(
                finish_reason=finish, input_tokens=input_tokens, output_tokens=output_tokens
            )
        )
