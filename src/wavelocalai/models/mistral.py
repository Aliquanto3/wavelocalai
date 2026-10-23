"""Adaptateur du port `ChatModel` pour Mistral, sur le SDK officiel `mistralai` (AD-8).

Copie adaptée du streaming de `src/core/providers/mistral_provider.py` (v1), sans
`get_langchain_model` et sans importer la v1. Le SDK n'est importé que dans la fonction (AD-4) :
`mistralai` 2.x et plus expose `Mistral` dans `mistralai.client`, 1.x dans `mistralai`.

L'adaptateur émet des `TextDelta` (blocs de réflexion `thinking` sur le canal `thought`), les
`ToolCall` assemblés depuis `delta.tool_calls` (story 6.1, `models/tool_format.py`), puis un seul
`Done` avec `tps_source = "wallclock"` ; l'usage de jetons vient du dernier événement du flux.
Il ne calcule pas de CO2, n'écrit pas en base et ne lit pas `allow_cloud`. Flux et client sont
fermés dans un `finally` (annulation comprise).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from wavelocalai.models.cloud import (
    HttpClientFactory,
    WallClock,
    close_quietly,
    key_missing,
    model_of,
    translate_error,
)
from wavelocalai.models.port import ChatChunk, ChatRequest, Done, ModelRef, TextDelta
from wavelocalai.models.structured import StructuredCheck
from wavelocalai.models.tool_format import ToolCallDeltas, chat_messages, function_tools


def _field(obj: Any, name: str) -> Any:
    return getattr(obj, name, None)


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _pieces(content: Any) -> list[tuple[str, str]]:
    """Fragments `(canal, texte)` d'un `delta.content` : une chaîne, ou une liste de blocs
    (`text`, `thinking`)."""
    if isinstance(content, str):
        return [("answer", content)] if content else []
    pieces: list[tuple[str, str]] = []
    for block in content or []:
        text = _field(block, "text")
        if isinstance(text, str) and text:
            pieces.append(("answer", text))
            continue
        for part in _field(block, "thinking") or []:
            thought = _field(part, "text")
            if isinstance(thought, str) and thought:
                pieces.append(("thought", thought))
    return pieces


def _mistral_class() -> Any:
    try:
        from mistralai.client import Mistral
    except ImportError:  # mistralai 1.x
        from mistralai import Mistral  # type: ignore[no-redef]
    return Mistral


class MistralChatModel:
    """`ChatModel` pour un modèle Mistral (`mistral/<modèle>`)."""

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
            raise key_missing("mistral")
        mistral = _mistral_class()  # import paresseux (AD-4)

        clock = WallClock(self._clock)
        client_args: dict[str, Any] = {"api_key": self._api_key}
        http: Any = None
        if self._http_client is not None:
            http = client_args["async_client"] = self._http_client()
        client = mistral(**client_args)
        options: dict[str, Any] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            options["max_tokens"] = request.max_tokens
        if request.tools:
            options["tools"] = function_tools(request.tools)
        if request.response_schema is not None:
            options["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": request.response_schema,
                    "strict": True,
                },
            }
        structured = StructuredCheck(request.response_schema)
        tool_deltas = ToolCallDeltas()
        upstream: Any = None
        fragments = 0
        finish: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        try:
            upstream = await client.chat.stream_async(
                model=model_of(self.ref.tag),
                messages=chat_messages(request.messages, tool_names=True),
                **options,
            )
            async for event in upstream:
                data = _field(event, "data")
                usage = _field(data, "usage")
                if usage is not None:
                    input_tokens = _count(_field(usage, "prompt_tokens")) or input_tokens
                    output_tokens = _count(_field(usage, "completion_tokens")) or output_tokens
                choices = _field(data, "choices") or []
                if not choices:
                    continue
                choice = choices[0]
                for channel, text in _pieces(_field(_field(choice, "delta"), "content")):
                    clock.note(text)
                    fragments += 1
                    if channel == "answer":
                        structured.add(text)
                    yield TextDelta(text, channel)  # type: ignore[arg-type]
                for call in _field(_field(choice, "delta"), "tool_calls") or ():
                    function = _field(call, "function")
                    tool_deltas.add(
                        _field(call, "index"),
                        _field(call, "id"),
                        _field(function, "name"),
                        _field(function, "arguments"),
                    )
                    fragments += 1
                finish = _field(choice, "finish_reason") or finish
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            mapped = translate_error("mistral", exc, self._api_key, fragments=fragments)
            if mapped is exc:
                raise
            raise mapped from exc
        finally:
            await close_quietly(upstream)
            await _close_client(client)
            await close_quietly(http)  # le SDK ne ferme pas un client HTTP qu'on lui a fourni
        structured.done()
        for tool_call in tool_deltas.calls():
            yield tool_call
        yield Done(
            clock.result(
                finish_reason=finish, input_tokens=input_tokens, output_tokens=output_tokens
            )
        )


async def _close_client(client: Any) -> None:
    """Le client Mistral se ferme par `__aexit__` (il n'a pas de `close`)."""
    exit_ = getattr(client, "__aexit__", None)
    if exit_ is None:
        return
    try:
        await exit_(None, None, None)
    except Exception:  # noqa: BLE001 - une fermeture ratée ne masque jamais la vraie panne
        return
