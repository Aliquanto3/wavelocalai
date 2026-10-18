"""Adaptateur du port `ChatModel` pour les API compatibles OpenAI : OpenAI et Groq (AD-8).

Groq parle l'API Chat Completions d'OpenAI : même SDK (`openai`, `AsyncOpenAI`), autre `base_url`.
Copie adaptée du streaming de `src/core/providers/openai_provider.py` (v1), sans
`get_langchain_model` et sans importer la v1. Le SDK n'est importé que dans la fonction (AD-4).

L'adaptateur émet des `TextDelta` (raisonnement `reasoning` de Groq sur le canal `thought`), puis un
seul `Done` avec `tps_source = "wallclock"`. Il ne calcule pas de CO2, n'écrit pas en base et ne lit
pas `allow_cloud`. L'annulation est celle de la tâche : le flux HTTP et le client sont fermés dans
un `finally`. Aucune nouvelle tentative du SDK (`max_retries=0`) : une panne remonte aussitôt, avec
le nom du fournisseur.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from wavelocalai.models.cloud import (
    CONNECT_TIMEOUT_S,
    HttpClientFactory,
    WallClock,
    chat_text_messages,
    close_quietly,
    key_missing,
    model_of,
    translate_error,
)
from wavelocalai.models.port import ChatChunk, ChatRequest, Done, ModelRef, TextDelta

logger = logging.getLogger("wavelocalai.models")

BASE_URLS: dict[str, str | None] = {
    "openai": None,  # le SDK vise api.openai.com
    "groq": "https://api.groq.com/openai/v1",
}
# Modèles OpenAI de raisonnement : ils refusent un `temperature` autre que celui par défaut.
_NO_TEMPERATURE_PREFIXES = ("gpt-5", "gpt-6", "o1", "o3", "o4")


def _field(obj: Any, name: str) -> Any:
    """Champ d'un objet du SDK (modèle pydantic, champs hors schéma compris), `None` s'il manque."""
    return getattr(obj, name, None)


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class OpenAICompatChatModel:
    """`ChatModel` pour un modèle OpenAI (`openai/<modèle>`) ou Groq (`groq/<modèle>`)."""

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

    def _options(self, request: ChatRequest) -> dict[str, Any]:
        options: dict[str, Any] = {}
        model = model_of(self.ref.tag)
        if self.ref.provider != "openai" or not model.startswith(_NO_TEMPERATURE_PREFIXES):
            options["temperature"] = request.temperature
        if request.max_tokens is not None:
            options["max_completion_tokens"] = request.max_tokens
        return options

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        provider = self.ref.provider
        if not self._api_key:
            raise key_missing(provider)
        from openai import AsyncOpenAI, Timeout  # import paresseux (AD-4)

        clock = WallClock(self._clock)
        client_args: dict[str, Any] = {
            "api_key": self._api_key,
            "base_url": BASE_URLS.get(provider),
            "max_retries": 0,
            "timeout": Timeout(None, connect=CONNECT_TIMEOUT_S),
        }
        if self._http_client is not None:
            client_args["http_client"] = self._http_client()
        client = AsyncOpenAI(**client_args)
        upstream: Any = None
        fragments = 0
        finish: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        try:
            upstream = await client.chat.completions.create(
                model=model_of(self.ref.tag),
                messages=chat_text_messages(request.messages),  # type: ignore[arg-type]
                stream=True,
                stream_options={"include_usage": True},
                **self._options(request),
            )
            async for chunk in upstream:
                usage = _field(chunk, "usage") or _field(_field(chunk, "x_groq"), "usage")
                if usage is not None:
                    input_tokens = _count(_field(usage, "prompt_tokens")) or input_tokens
                    output_tokens = _count(_field(usage, "completion_tokens")) or output_tokens
                choices = _field(chunk, "choices") or []
                if not choices:
                    continue
                choice = choices[0]
                delta = _field(choice, "delta")
                thought = _field(delta, "reasoning") or _field(delta, "reasoning_content")
                if isinstance(thought, str) and thought:
                    clock.note(thought)
                    fragments += 1
                    yield TextDelta(thought, "thought")
                content = _field(delta, "content")
                if isinstance(content, str) and content:
                    clock.note(content)
                    fragments += 1
                    yield TextDelta(content, "answer")
                finish = _field(choice, "finish_reason") or finish
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            mapped = translate_error(provider, exc, self._api_key, fragments=fragments)
            if mapped is exc:
                raise
            raise mapped from exc
        finally:
            await close_quietly(upstream)
            await close_quietly(client)
        yield Done(
            clock.result(
                finish_reason=finish, input_tokens=input_tokens, output_tokens=output_tokens
            )
        )
