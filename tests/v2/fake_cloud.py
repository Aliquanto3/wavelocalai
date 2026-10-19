"""Faux fournisseurs cloud : transports HTTP simulés sous les vrais SDK (aucun réseau).

Chaque fournisseur a sa forme de flux (OpenAI et Groq : Chat Completions, Anthropic : Messages,
Mistral : Chat Completions avec son propre SDK). `FakeCloud` enregistre les requêtes reçues et
rejoue un « plan » : flux nominal, refus HTTP, connexion impossible, flux coupé, attente infinie.
`factories()` donne les fabriques de client HTTP à passer à `ModelFactory` / `create_app`
(`httpx.AsyncClient` pour openai, `httpx2.AsyncClient` pour anthropic et mistralai).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import httpx2

DONE = b"data: [DONE]\n\n"

FAKE_KEYS = {
    "openai": "sk-test-OPENAI0123456789abcdef",
    "groq": "gsk_testGROQ0123456789abcdef",
    "anthropic": "sk-ant-api03-ANTHROPIC0123456789abcdef",
    "mistral": "MISTRALtest0123456789abcdef",
}
KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}
# (fournisseur, tag complet, identifiant envoyé au fournisseur)
MODELS = [
    ("openai", "openai/gpt-6-luna", "gpt-6-luna"),
    ("groq", "groq/openai/gpt-oss-20b", "openai/gpt-oss-20b"),
    ("anthropic", "anthropic/claude-haiku-5-5", "claude-haiku-5-5"),
    ("mistral", "mistral/mistral-small-latest", "mistral-small-latest"),
]
SETTINGS_CLOUD = {
    "models": {
        "openai": ["gpt-6-luna"],
        "groq": ["openai/gpt-oss-20b"],
        "anthropic": ["claude-haiku-5-5"],
        "mistral": ["mistral-small-latest"],
    },
    "groq_ecologits": {"openai/gpt-oss-20b": "openai/gpt-oss-20b"},
}


def sse(*events: tuple[str | None, dict[str, Any] | str]) -> bytes:
    out = []
    for name, data in events:
        payload = data if isinstance(data, str) else json.dumps(data)
        out.append((f"event: {name}\n" if name else "") + f"data: {payload}\n\n")
    return "".join(out).encode()


def _chat_chunk(delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
    return {
        "id": "c1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def chat_stream(texts: list[str], *, thinking: str | None = None, usage=(11, 5)) -> bytes:
    """Flux Chat Completions (OpenAI, Groq, Mistral) : `texts`, motif de fin, `usage`, `[DONE]`."""
    events: list[tuple[str | None, dict[str, Any] | str]] = [
        (None, _chat_chunk({"role": "assistant", "content": ""}))
    ]
    if thinking is not None:
        events.append((None, _chat_chunk({"reasoning": thinking})))
    events += [(None, _chat_chunk({"content": t})) for t in texts]
    events.append((None, _chat_chunk({}, "stop")))
    if usage:
        events.append(
            (
                None,
                {
                    "id": "c1",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "m",
                    "choices": [],
                    "usage": {
                        "prompt_tokens": usage[0],
                        "completion_tokens": usage[1],
                        "total_tokens": usage[0] + usage[1],
                    },
                },
            )
        )
    events.append((None, "[DONE]"))
    return sse(*events)


def mistral_stream(parts: list[Any], *, usage=(11, 5)) -> bytes:
    """Flux Mistral : `parts` sont des textes ou des listes de blocs (`text`, `thinking`)."""
    events: list[tuple[str | None, dict[str, Any] | str]] = []
    for content in parts:
        events.append((None, _chat_chunk({"role": "assistant", "content": content})))
    last = _chat_chunk({"content": ""}, "stop")
    last["usage"] = {
        "prompt_tokens": usage[0],
        "completion_tokens": usage[1],
        "total_tokens": usage[0] + usage[1],
    }
    events.append((None, last))
    events.append((None, "[DONE]"))
    return sse(*events)


def anthropic_stream(texts: list[str], *, usage=(12, 7), stop="end_turn") -> bytes:
    start = {
        "type": "message_start",
        "message": {
            "id": "m1",
            "type": "message",
            "role": "assistant",
            "model": "m",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": usage[0], "output_tokens": 1},
        },
    }
    events: list[tuple[str | None, dict[str, Any] | str]] = [
        ("message_start", start),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
    ]
    for text in texts:
        events.append(
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": text},
                },
            )
        )
    events += [
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop, "stop_sequence": None},
                "usage": {"output_tokens": usage[1]},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return sse(*events)


def anthropic_tool_stream(json_parts: list[str], *, usage=(12, 7)) -> bytes:
    """Flux Anthropic d'un `tool_use` forcé : le JSON de l'entrée arrive en `input_json_delta`."""
    start = {
        "type": "message_start",
        "message": {
            "id": "m1",
            "type": "message",
            "role": "assistant",
            "model": "m",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": usage[0], "output_tokens": 1},
        },
    }
    events: list[tuple[str | None, dict[str, Any] | str]] = [
        ("message_start", start),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_use", "id": "tu1", "name": "respond", "input": {}},
            },
        ),
    ]
    for part in json_parts:
        events.append(
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "input_json_delta", "partial_json": part},
                },
            )
        )
    events += [
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                "usage": {"output_tokens": usage[1]},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return sse(*events)


def chat_tool_stream(
    calls: list[tuple[str, str, list[str]]], *, text: str | None = None, usage=(11, 5)
) -> bytes:
    """Flux Chat Completions (OpenAI, Groq) d'appels d'outils, comme le SDK les reçoit : le premier
    fragment de chaque appel porte `index`, `id` et `name`, les suivants des morceaux d'`arguments`.
    `calls` : `(id, nom, morceaux de la chaîne JSON des arguments)`."""
    events: list[tuple[str | None, dict[str, Any] | str]] = [
        (None, _chat_chunk({"role": "assistant", "content": ""}))
    ]
    if text:
        events.append((None, _chat_chunk({"content": text})))
    for index, (call_id, name, parts) in enumerate(calls):
        head = {
            "index": index,
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": ""},
        }
        events.append((None, _chat_chunk({"tool_calls": [head]})))
        for part in parts:
            tail = {"index": index, "function": {"arguments": part}}
            events.append((None, _chat_chunk({"tool_calls": [tail]})))
    events.append((None, _chat_chunk({}, "tool_calls")))
    events.append(
        (
            None,
            {
                "id": "c1",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "m",
                "choices": [],
                "usage": {
                    "prompt_tokens": usage[0],
                    "completion_tokens": usage[1],
                    "total_tokens": usage[0] + usage[1],
                },
            },
        )
    )
    events.append((None, "[DONE]"))
    return sse(*events)


def mistral_tool_stream(calls: list[tuple[str | None, str, Any]], *, usage=(11, 5)) -> bytes:
    """Flux Mistral d'appels d'outils : chaque appel arrive entier dans un fragment (`id` absent =
    `"null"` côté SDK) ; `arguments` est une chaîne JSON ou un objet."""
    events: list[tuple[str | None, dict[str, Any] | str]] = []
    for index, (call_id, name, arguments) in enumerate(calls):
        call: dict[str, Any] = {
            "type": "function",
            "function": {"name": name, "arguments": arguments},
            "index": index,
        }
        if call_id is not None:
            call["id"] = call_id
        events.append(
            (None, _chat_chunk({"role": "assistant", "content": "", "tool_calls": [call]}))
        )
    last = _chat_chunk({"content": ""}, "tool_calls")
    last["usage"] = {
        "prompt_tokens": usage[0],
        "completion_tokens": usage[1],
        "total_tokens": usage[0] + usage[1],
    }
    events.append((None, last))
    events.append((None, "[DONE]"))
    return sse(*events)


def anthropic_tool_use_stream(
    calls: list[tuple[str, str, list[str]]], *, text: str | None = None, usage=(12, 7)
) -> bytes:
    """Flux Anthropic d'appels d'outils : un bloc `text` éventuel, puis un bloc `tool_use` par appel
    (`content_block_start`, `input_json_delta`, `content_block_stop`). `calls` : `(id, nom, morceaux
    du JSON de l'entrée)`."""
    start = {
        "type": "message_start",
        "message": {
            "id": "m1",
            "type": "message",
            "role": "assistant",
            "model": "m",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": usage[0], "output_tokens": 1},
        },
    }
    events: list[tuple[str | None, dict[str, Any] | str]] = [("message_start", start)]
    index = 0
    if text:
        events += [
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "text_delta", "text": text},
                },
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": index}),
        ]
        index += 1
    for call_id, name, parts in calls:
        events.append(
            (
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {"type": "tool_use", "id": call_id, "name": name, "input": {}},
                },
            )
        )
        for part in parts:
            events.append(
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "input_json_delta", "partial_json": part},
                    },
                )
            )
        events.append(("content_block_stop", {"type": "content_block_stop", "index": index}))
        index += 1
    events += [
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                "usage": {"output_tokens": usage[1]},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return sse(*events)


def stream_for(provider: str, texts: list[str], **kwargs: Any) -> bytes:
    if provider == "anthropic":
        return anthropic_stream(texts, **kwargs)
    if provider == "mistral":
        return mistral_stream(texts, **kwargs)
    return chat_stream(texts, **kwargs)


def error_body(provider: str, status: int, message: str) -> dict[str, Any]:
    if provider == "anthropic":
        return {"type": "error", "error": {"type": "api_error", "message": message}}
    if provider == "mistral":
        return {"message": message, "request_id": "r1", "type": "invalid_request", "code": status}
    return {"error": {"message": message, "type": "invalid_request_error", "code": None}}


@dataclass
class Plan:
    """Ce que fait le faux fournisseur à un appel."""

    body: bytes = b""
    status: int = 200
    message: str = "erreur"  # texte d'une réponse d'erreur (peut citer la clé, comme le font eux)
    connect_error: bool = False
    cut_after: bytes | None = None  # envoie ce début de flux puis coupe la connexion
    hold: asyncio.Event | None = None  # envoie `body` puis attend (flux ouvert)


@dataclass
class FakeCloud:
    """Un faux fournisseur : `plans` est consommé dans l'ordre (le dernier se répète)."""

    provider: str
    plans: list[Plan] = field(default_factory=list)
    requests: list[httpx.Request | httpx2.Request] = field(default_factory=list)
    bodies: list[dict[str, Any]] = field(default_factory=list)
    clients: list[Any] = field(default_factory=list)

    def _plan(self) -> Plan:
        index = min(len(self.requests) - 1, len(self.plans) - 1)
        return self.plans[index]

    def _handler(self, lib: Any) -> Callable[[Any], Any]:
        async def handler(request: Any) -> Any:
            self.requests.append(request)
            raw = request.content
            self.bodies.append(json.loads(raw) if raw else {})
            plan = self._plan()
            if plan.connect_error:
                raise lib.ConnectError("connexion refusée", request=request)
            if plan.status >= 400:
                body = error_body(self.provider, plan.status, plan.message)
                return lib.Response(plan.status, json=body, request=request)

            async def chunks() -> AsyncIterator[bytes]:
                if plan.cut_after is not None:
                    yield plan.cut_after
                    raise lib.ReadError("flux coupé", request=request)
                # En attente, le flux reste ouvert : sans `[DONE]`, que le SDK lirait pour finir.
                yield plan.body if plan.hold is None else plan.body.replace(DONE, b"")
                if plan.hold is not None:
                    await plan.hold.wait()

            return lib.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_stream_class(lib)(chunks()),
                request=request,
            )

        return handler

    def client(self) -> Any:
        """Client HTTP neuf sur le faux transport (et gardé pour vérifier sa fermeture)."""
        lib = httpx if self.provider in ("openai", "groq") else httpx2
        client = lib.AsyncClient(transport=lib.MockTransport(self._handler(lib)))
        self.clients.append(client)
        return client


def _stream_class(lib: Any) -> type:
    class Stream(lib.AsyncByteStream):
        def __init__(self, chunks: AsyncIterator[bytes]) -> None:
            self._chunks = chunks

        async def __aiter__(self) -> AsyncIterator[bytes]:
            async for chunk in self._chunks:
                yield chunk

        async def aclose(self) -> None:
            return None

    return Stream


def factories(*fakes: FakeCloud) -> dict[str, Callable[[], Any]]:
    return {fake.provider: fake.client for fake in fakes}
