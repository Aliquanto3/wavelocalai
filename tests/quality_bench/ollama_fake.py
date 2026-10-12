"""Ollama simulé sur ``httpx2.MockTransport`` : ``/api/version``, ``/api/tags``, ``/api/show``,
``/api/ps``, ``/api/generate`` (déchargement) et ``/api/chat`` scénarisé. Aucun réseau."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx2

from scripts.quality_bench.ollama.client import OllamaClient

VERSION = "0.40.2"


@dataclass
class FakeModel:
    capabilities: list[str]
    digest: str | None = "d" * 64
    context_length: int | None = None
    remote_host: str | None = None
    show_remote_host: str | None = None
    # ``thinking.values`` de ``/api/show`` (Ollama 0.40.2), absent si ``None``.
    thinking_values: list[bool] | None = None


def reply(
    content: str = "Réponse synthétique.",
    *,
    thinking: str = "",
    tool_calls: list[dict[str, Any]] | None = None,
    done_reason: str = "stop",
    prompt: int = 50,
    cached: int = 0,
    completion: int = 7,
) -> list[dict[str, Any]]:
    """Fragments d'un flux ``/api/chat`` : réflexion, contenu, appels, puis ``done``."""
    chunks: list[dict[str, Any]] = []
    if thinking:
        chunks.append({"message": {"role": "assistant", "content": "", "thinking": thinking}})
    if content:
        chunks.append({"message": {"role": "assistant", "content": content}})
    if tool_calls:
        chunks.append({"message": {"role": "assistant", "content": "", "tool_calls": tool_calls}})
    final = {
        "done": True,
        "done_reason": done_reason,
        "message": {"role": "assistant", "content": ""},
        "prompt_eval_count": prompt,
        "eval_count": completion,
        "total_duration": 9_000_000,
        "load_duration": 1_000_000,
        "prompt_eval_duration": 2_000_000,
        "eval_duration": 5_000_000,
    }
    if cached:
        final["prompt_eval_cached_count"] = cached
    chunks.append(final)
    return chunks


def call(name: str, **arguments: Any) -> dict[str, Any]:
    return {"function": {"name": name, "arguments": arguments}}


class OutageError(Exception):
    """Réponse du scénario : connexion refusée."""


def _ndjson(chunks: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(chunk) + "\n" for chunk in chunks).encode("utf-8")


# Scénario : (corps de la requête, faux service) → fragments, httpx2.Response ou OutageError.
Responder = Callable[[dict[str, Any], "FakeOllama"], Any]


def default_responder(body: dict[str, Any], fake: FakeOllama) -> Any:
    return reply()


@dataclass
class FakeOllama:
    models: dict[str, FakeModel]
    version: str = VERSION
    responder: Responder = default_responder
    # Nombre des prochaines requêtes (tous chemins) qui échouent en connexion refusée.
    down: int = 0
    requests: list[tuple[str, dict[str, Any] | None]] = field(default_factory=list)
    loaded: tuple[str, int] | None = None
    unloads: list[str] = field(default_factory=list)
    warmup_prompt_eval: int = 1_000
    warmup_prompt_ns: int = 2_000_000_000  # 500 tok/s par défaut
    on_request: Callable[[str, dict[str, Any] | None], None] | None = None

    # -- Transport ----------------------------------------------------------------------------

    def client(self) -> OllamaClient:
        return OllamaClient("http://127.0.0.1:11434", transport=httpx2.MockTransport(self))

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.requests.append((path, body))
        if self.on_request is not None:
            self.on_request(path, body)
        if self.down > 0:
            self.down -= 1
            raise httpx2.ConnectError("connexion refusée", request=request)
        handler = {
            "/api/version": self._version,
            "/api/tags": self._tags,
            "/api/show": self._show,
            "/api/ps": self._ps,
            "/api/generate": self._generate,
            "/api/chat": self._chat,
        }.get(path)
        if handler is None:
            return httpx2.Response(404, json={"error": "inconnu"})
        try:
            return handler(body)
        except OutageError:
            raise httpx2.ConnectError("connexion refusée", request=request) from None

    # -- Points d'accès -----------------------------------------------------------------------

    def _version(self, body: Any) -> httpx2.Response:
        return httpx2.Response(200, json={"version": self.version})

    def _tags(self, body: Any) -> httpx2.Response:
        entries = []
        for tag, model in self.models.items():
            entry: dict[str, Any] = {"name": tag, "model": tag}
            if model.digest is not None:
                entry["digest"] = model.digest
            if model.remote_host is not None:
                entry["remote_host"] = model.remote_host
            entries.append(entry)
        return httpx2.Response(200, json={"models": entries})

    def _show(self, body: Any) -> httpx2.Response:
        model = self.models.get(body["model"])
        if model is None:
            return httpx2.Response(404, json={"error": "model not found"})
        info: dict[str, Any] = {"general.architecture": "synth"}
        if model.context_length is not None:
            info["synth.context_length"] = model.context_length
        payload: dict[str, Any] = {"capabilities": list(model.capabilities), "model_info": info}
        if model.show_remote_host is not None:
            payload["remote_host"] = model.show_remote_host
        if model.thinking_values is not None:
            payload["thinking"] = {"values": list(model.thinking_values), "default": True}
        return httpx2.Response(200, json=payload)

    def _ps(self, body: Any) -> httpx2.Response:
        if self.loaded is None:
            return httpx2.Response(200, json={"models": []})
        tag = self.loaded[0]
        return httpx2.Response(
            200,
            json={
                "models": [
                    {
                        "name": tag,
                        "model": tag,
                        "size": 4000,
                        "size_vram": 3000,
                        # Champs vus sur le vrai 0.40.2, ignorés par le client.
                        "context_length": self.loaded[1],
                        "runner": "llamacpp",
                    }
                ]
            },
        )

    def _generate(self, body: Any) -> httpx2.Response:
        assert body.get("keep_alive") == 0
        self.unloads.append(body["model"])
        self.loaded = None
        return httpx2.Response(200, json={"done": True, "done_reason": "unload"})

    def _chat(self, body: Any) -> httpx2.Response:
        self.loaded = (body["model"], body["options"]["num_ctx"])
        if is_warmup(body):
            final = reply("prêt", prompt=self.warmup_prompt_eval)
            final[-1]["prompt_eval_duration"] = self.warmup_prompt_ns
            return httpx2.Response(200, content=_ndjson(final))
        outcome = self.responder(body, self)
        if isinstance(outcome, httpx2.Response):
            return outcome
        return httpx2.Response(200, content=_ndjson(outcome))

    # -- Lecture ------------------------------------------------------------------------------

    def chats(self) -> list[dict[str, Any]]:
        """Corps des requêtes ``/api/chat`` hors chauffe."""
        return [b for p, b in self.requests if p == "/api/chat" and not is_warmup(b)]

    def warmups(self) -> list[dict[str, Any]]:
        return [b for p, b in self.requests if p == "/api/chat" and is_warmup(b)]


def is_warmup(body: dict[str, Any] | None) -> bool:
    return bool(body) and body["options"]["num_predict"] == 1
