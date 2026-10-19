"""Adaptateur Ollama du port `ChatModel` : `/api/chat` natif, client async partagé (AD-8).

Seul adaptateur qui produit `tps_source = "ollama_eval"` (`eval_count / eval_duration`, D3). Il ne
calcule pas de CO2, n'écrit pas en base et ne lit pas `allow_cloud`. L'annulation est celle de la
tâche asyncio : le flux HTTP est fermé dans un `finally`. Les pannes deviennent des
`ProviderError` à code fermé :

- Ollama injoignable : `ollama_down` ;
- flux coupé avant le fragment `done` (ou fermé en cours de route) : `generation_interrupted`,
  que le service relance une fois (copie adaptée de `retry_interrupted`, v1) ;
- refus d'Ollama : `model_not_found` (404) ou `ollama_error`.

Le chargement du modèle n'a pas d'événement dans l'API d'Ollama : si `/api/ps` ne le montre pas en
mémoire au départ, l'adaptateur émet `LoadState("loading")`, puis `LoadState("loaded")` au premier
fragment (durée = délai jusqu'à ce fragment, chargement et lecture du prompt compris ; la durée de
chargement exacte d'Ollama est `ChatResult.load_s`).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from ollama import AsyncClient, RequestError, ResponseError

from wavelocalai.errors import ProviderError
from wavelocalai.models.classify import base_tag
from wavelocalai.models.ollama_metrics import chunk_field, ollama_result
from wavelocalai.models.port import (
    ChatChunk,
    ChatRequest,
    Done,
    LoadState,
    ModelRef,
    TextDelta,
    ToolCall,
)
from wavelocalai.models.structured import StructuredCheck
from wavelocalai.models.tool_format import function_tools, new_call_id, ollama_messages

logger = logging.getLogger("wavelocalai.models")

CONNECT_TIMEOUT_S = 5.0
PS_TIMEOUT_S = 1.0  # AD-15 : un appel de sonde ne dépasse pas 1 s

# Pannes de réseau qui disent « Ollama ne répond pas » avant tout fragment.
_DOWN = (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError)
# Flux fermé ou illisible en cours de route : la génération est coupée.
_CUT = (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout, json.JSONDecodeError)


def make_client(host: str) -> AsyncClient:
    """Client Ollama async partagé de l'application : sans proxy système (`trust_env=False`,
    adresse locale), sans délai de lecture (un modèle peut mettre du temps à charger : le délai de
    lane est celui du service)."""
    return AsyncClient(
        host=host.rstrip("/"),
        trust_env=False,
        timeout=httpx.Timeout(None, connect=CONNECT_TIMEOUT_S),
    )


async def close_client(client: AsyncClient) -> None:
    """Ferme le client HTTP sous-jacent (le client Ollama n'expose pas de `close`)."""
    http = getattr(client, "_client", None)
    if http is not None:
        with contextlib.suppress(Exception):
            await http.aclose()


class OllamaChatModel:
    """`ChatModel` pour un tag local servi par Ollama."""

    def __init__(
        self,
        ref: ModelRef,
        client: AsyncClient,
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.ref = ref
        self._client = client
        self._clock = clock

    async def _is_loaded(self) -> bool:
        """Vrai si `/api/ps` montre le modèle en mémoire, ou si on ne peut pas le savoir (aucun
        état de chargement n'est alors annoncé). Connexion refusée : `ollama_down` aussitôt."""
        try:
            async with asyncio.timeout(PS_TIMEOUT_S):
                response = await self._client.ps()
        except _DOWN as exc:  # inutile d'attendre un second refus de connexion avec `/api/chat`
            raise ProviderError("ollama_down", f"{type(exc).__name__}: {exc}") from exc
        except Exception:  # noqa: BLE001 - toute autre panne = pas d'information
            return True
        wanted = base_tag(self.ref.tag)
        names = (getattr(m, "model", None) or getattr(m, "name", None) for m in response.models)
        return any(base_tag(str(name)) == wanted for name in names if name)

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        tag = self.ref.tag
        options: dict[str, Any] = {"temperature": request.temperature}
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        extra: dict[str, Any] = {}
        if request.tools:
            extra["tools"] = function_tools(request.tools)
        if request.response_schema is not None:
            extra["format"] = request.response_schema
        if request.think:  # `think` n'est pas passé sinon : le comportement d'Ollama est inchangé
            extra["think"] = True

        started = self._clock()
        loading = not await self._is_loaded()
        if loading:
            yield LoadState("loading")
        upstream: AsyncIterator[Any] | None = None
        fragments = 0
        text_chars = 0
        ttft_s: float | None = None
        final: Any = None
        structured = StructuredCheck(request.response_schema)
        try:
            upstream = await self._client.chat(
                model=tag,
                messages=ollama_messages(request.messages),
                stream=True,
                options=options,
                **extra,
            )
            async for part in upstream:
                message = chunk_field(part, "message")
                thinking = chunk_field(message, "thinking")
                content = chunk_field(message, "content")
                if (thinking or content) and ttft_s is None:
                    ttft_s = self._clock() - started
                    if loading:
                        loading = False
                        yield LoadState("loaded", round(ttft_s, 3))
                if thinking:
                    fragments += 1
                    yield TextDelta(thinking, "thought")
                if content:
                    fragments += 1
                    text_chars += len(content)
                    structured.add(content)
                    yield TextDelta(content, "answer")
                for call in chunk_field(message, "tool_calls") or ():
                    function = chunk_field(call, "function")
                    yield ToolCall(
                        new_call_id(),  # Ollama ne donne pas d'identifiant d'appel
                        str(chunk_field(function, "name") or ""),
                        dict(chunk_field(function, "arguments") or {}),
                    )
                if chunk_field(part, "done"):
                    final = part
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            mapped = self._provider_error(exc, fragments)
            if mapped is exc:
                raise
            raise mapped from exc
        finally:
            aclose = getattr(upstream, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()  # ferme le flux HTTP, y compris sur annulation

        if final is None:
            # Flux fermé sans fragment `done` (Ollama le fait parfois, en HTTP 200) : réponse
            # tronquée, jamais présentée comme complète.
            raise ProviderError(
                "generation_interrupted",
                f"Flux Ollama clos sans fragment final ({fragments} reçus)",
            )
        structured.done()  # `format` : sortie structurée vérifiée avant `Done`
        load_s = chunk_field(final, "load_duration")
        if loading:  # réponse vide : le chargement est annoncé fini à la fin
            yield LoadState("loaded", round(float(load_s) / 1e9, 3) if load_s else None)
        yield Done(
            ollama_result(
                final,
                self._clock() - started,
                ttft_s=ttft_s,
                fallback_output_tokens=text_chars // 4,
            )
        )

    def _provider_error(self, exc: Exception, fragments: int) -> Exception:
        """Traduit une panne du client en `ProviderError` ; les autres exceptions passent telles
        quelles (le service les range sous `internal`)."""
        if isinstance(exc, ProviderError):
            return exc
        if isinstance(exc, _DOWN):
            return ProviderError("ollama_down", f"{type(exc).__name__}: {exc}")
        if isinstance(exc, ResponseError):
            if exc.status_code == 404:
                return ProviderError("model_not_found", str(exc), tag=self.ref.tag)
            return ProviderError("ollama_error", str(exc))
        if isinstance(exc, RequestError):
            return ProviderError("ollama_error", str(exc))
        if isinstance(exc, _CUT):
            return ProviderError(
                "generation_interrupted",
                f"{type(exc).__name__} après {fragments} fragments : {exc}",
            )
        return exc
