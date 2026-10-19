"""Faux serveur Ollama pour les tests du chat : transport httpx simulé sous un vrai `AsyncClient`.

Il répond à `/api/chat` (flux NDJSON scripté), `/api/ps` et `/api/tags`/`/api/show` pour le
registre. Chaque appel à `/api/chat` consomme le « plan » suivant : des fragments, puis une fin
(`done` normal, flux coupé sans `done`, erreur de lecture, attente infinie, refus HTTP, connexion
refusée). Le faux compte les flux ouverts et fermés : une annulation doit fermer le flux HTTP.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from ollama import AsyncClient

NS = 1_000_000_000


def part(text: str = "", *, thinking: str | None = None) -> dict[str, Any]:
    """Un fragment de génération (`done: false`)."""
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if thinking is not None:
        message["thinking"] = thinking
    return {"model": "m", "created_at": "2026-10-18T10:00:00Z", "message": message, "done": False}


def final(
    *,
    eval_count: int = 20,
    eval_s: float | None = 0.5,
    load_s: float | None = 0.2,
    prompt_eval_count: int = 7,
    prompt_eval_s: float | None = 0.1,
    total_s: float | None = 1.0,
) -> dict[str, Any]:
    """Le fragment final (`done: true`) avec les compteurs et durées d'Ollama (en ns)."""
    chunk: dict[str, Any] = {
        "model": "m",
        "created_at": "2026-10-18T10:00:01Z",
        "message": {"role": "assistant", "content": ""},
        "done": True,
        "done_reason": "stop",
        "eval_count": eval_count,
        "prompt_eval_count": prompt_eval_count,
    }
    for name, value in (
        ("eval_duration", eval_s),
        ("load_duration", load_s),
        ("prompt_eval_duration", prompt_eval_s),
        ("total_duration", total_s),
    ):
        if value is not None:
            chunk[name] = int(value * NS)
    return chunk


@dataclass
class Plan:
    """Un appel à `/api/chat`. `end` : `done` (le dernier fragment de `lines` doit être `final`),
    `cut` (flux fermé proprement sans `done`), `error` (coupure de lecture), `hang` (plus rien),
    `http_error` (statut `status` et corps `body`), `refuse` (connexion refusée)."""

    lines: Sequence[dict[str, Any]] = ()
    end: str = "done"
    status: int = 200
    body: str = ""
    hold: asyncio.Event | None = None  # le flux ne part qu'une fois l'événement levé


@dataclass
class FakeOllama:
    plans: list[Plan] = field(default_factory=list)
    loaded: list[str] = field(default_factory=list)  # `/api/ps`
    ps_fails: str | None = None  # `connect` (refus de connexion) ou `http` (statut 500)
    tags: list[str] = field(default_factory=lambda: ["qwen2.5:1.5b"])
    sizes: dict[str, int] = field(default_factory=dict)  # taille d'un modèle (octets), 1 Go sinon
    unload_fails: bool = False  # `/api/generate` et `/api/embed` refusent le déchargement
    generate_refuses: set[str] = field(default_factory=set)  # modèles d'embedding : 400 au generate
    unloaded: list[str] = field(default_factory=list)  # modèles déchargés (`keep_alive: 0`)
    parameters: dict[str, str] = field(default_factory=dict)  # tag -> `parameters` de `/api/show`
    chat_requests: list[dict[str, Any]] = field(default_factory=list)
    opened: int = 0
    closed: int = 0

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def client(self, host: str = "http://127.0.0.1:11434") -> AsyncClient:
        return AsyncClient(host=host, transport=self.transport)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/ps":
            if self.ps_fails == "connect":
                raise httpx.ConnectError("refusé", request=request)
            if self.ps_fails == "http":
                return httpx.Response(500, text="boum")
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "model": t,
                            "name": t,
                            "size": self.sizes.get(t, 1_000_000_000),
                            "size_vram": 0,
                        }
                        for t in self.loaded
                    ]
                },
            )
        if path in ("/api/generate", "/api/embed"):
            body = json.loads(request.content)
            assert body.get("keep_alive") == 0, body
            if self.unload_fails:
                return httpx.Response(500, text="boum")
            if path == "/api/generate" and body["model"] in self.generate_refuses:
                return httpx.Response(400, json={"error": "does not support generate"})
            self.unloaded.append(body["model"])
            if body["model"] in self.loaded:
                self.loaded.remove(body["model"])
            return httpx.Response(200, json={"model": body["model"], "done": True})
        if path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [_listed(t, self.sizes.get(t, 1_000_000_000)) for t in self.tags]},
            )
        if path == "/api/show":
            tag = json.loads(request.content).get("model")
            shown: dict[str, Any] = {"capabilities": ["completion"], "model_info": {}}
            if tag in self.parameters:
                shown["parameters"] = self.parameters[tag]
            return httpx.Response(200, json=shown)
        assert path == "/api/chat", path
        self.chat_requests.append(json.loads(request.content))
        plan = self.plans.pop(0) if self.plans else Plan([part("ok"), final()])
        if plan.end == "refuse":
            raise httpx.ConnectError("connexion refusée", request=request)
        if plan.end == "http_error":
            return httpx.Response(plan.status, text=plan.body)
        self.opened += 1
        return httpx.Response(200, stream=_Stream(self, plan))


def _listed(tag: str, size: int = 1_000_000_000) -> dict[str, Any]:
    return {
        "model": tag,
        "digest": f"d-{tag}",
        "size": size,
        "details": {"family": "qwen2", "parameter_size": "1.5B", "quantization_level": "Q4_K_M"},
    }


class _Stream(httpx.AsyncByteStream):
    def __init__(self, owner: FakeOllama, plan: Plan) -> None:
        self._owner = owner
        self._plan = plan

    async def __aiter__(self) -> AsyncIterator[bytes]:
        plan = self._plan
        if plan.hold is not None:
            await plan.hold.wait()
        for line in plan.lines:
            yield (json.dumps(line) + "\n").encode()
            await asyncio.sleep(0)
        if plan.end == "hang":
            await asyncio.Event().wait()
        if plan.end == "error":
            raise httpx.ReadError("connexion coupée")

    async def aclose(self) -> None:
        self._owner.closed += 1
