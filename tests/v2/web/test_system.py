"""Flux système, fiche machine et CO2 de session (AD-6, AD-10, AD-15).

Le flux est lu par un client ASGI brut : httpx met la réponse en mémoire jusqu'à sa fin, ce qui
interdit de lire un flux ouvert ou de simuler une déconnexion.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from wavelocalai.models.ollama_probe import OllamaProbe
from wavelocalai.runs.models import LeafResult
from wavelocalai.web.app import create_app
from wavelocalai.web.system_state import SystemSampler

from ..conftest import TEST_PORT, make_settings
from ..producers import LOCAL_CO2, produce_arena, produce_chat

BASE = f"http://127.0.0.1:{TEST_PORT}"


def ollama_transport(models: list[dict[str, Any]], version: str = "0.40.6") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": version})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": models})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


class Stream:
    """Une requête ASGI ouverte : trames lues au fil de l'eau, déconnexion à la demande."""

    def __init__(self, app, path: str, headers: dict[str, str] | None = None) -> None:
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self.finished = asyncio.Event()
        self._disconnect = asyncio.Event()
        self._chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self._buffer = ""
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [(b"host", f"127.0.0.1:{TEST_PORT}".encode())]
            + [(k.encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", TEST_PORT),
            "state": {},
        }
        self._task = asyncio.create_task(self._run(app, scope))

    async def _run(self, app, scope) -> None:
        async def receive():
            await self._disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message) -> None:
            if message["type"] == "http.response.start":
                self.status = message["status"]
                self.headers = {k.decode(): v.decode() for k, v in message["headers"]}
            elif message["type"] == "http.response.body":
                self._chunks.put_nowait(message.get("body", b""))

        try:
            await app(scope, receive, send)
        finally:
            self.finished.set()

    async def frame(self, timeout: float = 3.0) -> dict[str, Any]:
        """Prochaine trame `data:` (les commentaires de maintien sont ignorés)."""
        async with asyncio.timeout(timeout):
            while True:
                while "\n\n" in self._buffer:
                    block, _, self._buffer = self._buffer.partition("\n\n")
                    lines = [
                        line for line in block.split("\n") if line and not line.startswith(":")
                    ]
                    if lines:
                        return {
                            "fields": sorted({line.partition(":")[0] for line in lines}),
                            "data": json.loads(
                                "\n".join(ln.partition(":")[2].removeprefix(" ") for ln in lines)
                            ),
                        }
                self._buffer += (await self._chunks.get()).decode()

    async def disconnect(self) -> None:
        self._disconnect.set()
        async with asyncio.timeout(3):
            await self.finished.wait()
        await asyncio.gather(self._task, return_exceptions=True)


@pytest.fixture
async def system(tmp_path):
    """(app, client) avec Ollama simulé : un modèle chargé."""
    settings = make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"})
    transport = ollama_transport(
        [{"name": "qwen3:1.7b", "size": 2 * 1024**3, "size_vram": 1024**3}]
    )
    probe = OllamaProbe(settings.ollama.host, transport=transport, wait_s=1.0)
    app = create_app(settings, probe)
    app.state.system_sampler._ps_transport = transport  # `/api/ps` simulé comme la sonde
    transport_app = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport_app, base_url=BASE) as client,
    ):
        yield app, client


async def test_stream_sends_the_system_state_envelope_without_id_or_event(system):
    app, _ = system
    stream = Stream(app, "/api/system/stream")
    first = await stream.frame()
    assert stream.status == 200 and stream.headers["content-type"].startswith("text/event-stream")
    assert first["fields"] == ["data"]  # ni `id:` ni `event:`
    envelope = first["data"]
    assert set(envelope) == {"seq", "run_id", "type", "ts", "data"}
    assert envelope["run_id"] is None and envelope["type"] == "system_state"
    data = envelope["data"]
    assert data["ollama"]["up"] is True and data["ollama"]["version"] == "0.40.6"
    assert 0.0 <= data["cpu_percent"] <= 100.0
    assert 0 < data["memory"]["used_gb"] <= data["memory"]["total_gb"]
    assert data["models_loaded"] == [{"tag": "qwen3:1.7b", "size_gb": 2.0, "vram_gb": 1.0}]
    assert data["runs_active"] == []
    await stream.disconnect()


async def test_stream_is_refreshed_every_interval_and_reports_the_active_runs(system):
    app, _ = system
    app.state.system_feed._interval_s = 0.02
    handle = await app.state.hub.create_run("chat", models=["fake:1b"], user_message="Q ?")
    stream = Stream(app, "/api/system/stream")
    first, second = await stream.frame(), await stream.frame()
    assert second["data"]["seq"] > first["data"]["seq"]
    expected = [{"run_id": handle.run_id, "kind": "chat", "status": "running"}]
    assert first["data"]["data"]["runs_active"] == expected
    await app.state.hub.finish_leaf(handle.run_id, LeafResult(origin="local"), LOCAL_CO2)
    deadline = asyncio.get_running_loop().time() + 3
    while (await stream.frame())["data"]["data"]["runs_active"]:
        assert asyncio.get_running_loop().time() < deadline
    await stream.disconnect()


async def test_stream_ignores_last_event_id_and_never_replays(system):
    app, _ = system
    feed = app.state.system_feed
    feed.publish("carbon_updated", {"total_mg": 9})  # personne n'écoute : perdu
    stream = Stream(app, "/api/system/stream", headers={"Last-Event-ID": "1"})
    first = await stream.frame()
    assert first["data"]["type"] == "system_state"
    await stream.disconnect()


async def test_services_publish_to_the_stream_through_the_port(system):
    app, _ = system
    stream = Stream(app, "/api/system/stream")
    await stream.frame()
    app.state.system_feed.publish("carbon_updated", {"total_mg": 1.5})
    while True:
        envelope = (await stream.frame())["data"]
        if envelope["type"] == "carbon_updated":
            break
    assert envelope["run_id"] is None and envelope["data"] == {"total_mg": 1.5}
    await stream.disconnect()


async def test_disconnect_releases_the_subscriber_and_pauses_the_measure(system):
    app, _ = system
    feed = app.state.system_feed
    streams = [Stream(app, "/api/system/stream") for _ in range(3)]
    for stream in streams:
        await stream.frame()
    assert feed.subscriber_count == 3 and feed.sampling
    for stream in streams[:2]:
        await stream.disconnect()
    assert feed.subscriber_count == 1 and feed.sampling  # un client reste : la mesure continue
    await streams[2].disconnect()
    assert feed.subscriber_count == 0 and not feed.sampling
    again = Stream(app, "/api/system/stream")  # reprise à la reconnexion
    assert (await again.frame())["data"]["type"] == "system_state"
    assert feed.subscriber_count == 1
    await again.disconnect()
    assert feed.subscriber_count == 0


async def test_server_shutdown_ends_the_open_streams(tmp_path):
    app = create_app(make_settings(tmp_path))
    stream = None
    async with app.router.lifespan_context(app):
        stream = Stream(app, "/api/system/stream")
        await stream.frame()
    async with asyncio.timeout(3):
        await stream.finished.wait()  # le flux s'est terminé de lui-même, sans déconnexion
    assert app.state.system_feed.subscriber_count == 0


async def test_ollama_down_gives_a_state_without_models(tmp_path):
    app = create_app(make_settings(tmp_path))
    async with app.router.lifespan_context(app):
        stream = Stream(app, "/api/system/stream")
        data = (await stream.frame())["data"]["data"]
        await stream.disconnect()
    assert data["ollama"] == {"up": False, "version": None, "latency_ms": None}
    assert data["models_loaded"] is None  # inconnu, pas « aucun modèle »
    assert data["memory"]["total_gb"] > 0


async def test_identity_returns_the_machine_card_without_any_network_call(system, monkeypatch):
    app, client = system
    import socket

    def refuse(*args, **kwargs):
        raise AssertionError("appel réseau interdit")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(app.state.probe, "status", refuse)  # ni sonde ni `/api/ps`
    app.state.system_sampler.ollama_version = "0.40.6"
    response = await client.get("/api/system/identity")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "os", "cpu", "cpu_cores_physical", "cpu_cores_logical", "ram_gb", "accelerator",
        "ollama_version",
    }  # fmt: skip
    assert body["os"] and body["cpu"] and body["ram_gb"] > 0
    assert set(body["accelerator"]) >= {"kind", "name"}
    assert body["ollama_version"] == "0.40.6"


async def test_identity_has_no_ollama_version_before_the_probe_saw_it(tmp_path):
    app = create_app(make_settings(tmp_path))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            body = (await client.get("/api/system/identity")).json()
    assert body["ollama_version"] is None


async def test_carbon_session_empty_then_sums_leaves_and_never_the_composite_parent(system):
    app, client = system
    hub = app.state.hub
    empty = (await client.get("/api/carbon/session")).json()
    assert empty["total_mg"] == 0.0 and empty["unmeasurable_runs"] == 0
    assert empty["app_session"]["id"] == hub.app_session_id

    parent, leaves = await produce_arena(hub, ("a:1b", "b:1b"))
    for leaf in leaves:
        await hub.finish_leaf(leaf.run_id, LeafResult(origin="local"), LOCAL_CO2)
    await hub.finish_run(parent.run_id)
    await produce_chat(hub)
    body = (await client.get("/api/carbon/session")).json()
    assert body["total_mg"] == pytest.approx(4.5)  # 2 feuilles d'arène + 1 chat, parent exclu
    assert body["by_module"]["arena"]["runs"] == 2 and body["by_module"]["chat"]["runs"] == 1
    assert body["by_origin"]["local"]["runs"] == 3 and body["by_origin"]["cloud"]["runs"] == 0


async def test_carbon_session_follows_a_reset(system):
    app, client = system
    await produce_chat(app.state.hub)
    assert (await client.get("/api/carbon/session")).json()["total_mg"] == pytest.approx(1.5)
    await app.state.hub.new_app_session("reset")
    body = (await client.get("/api/carbon/session")).json()
    assert body["total_mg"] == 0.0 and body["app_session"]["reason"] == "reset"


async def test_sampler_does_not_wait_for_ollama_when_it_is_down(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings)
    sampler: SystemSampler = app.state.system_sampler
    loop = asyncio.get_running_loop()
    started = loop.time()
    state = await sampler.sample()
    assert loop.time() - started < 0.3 and state["ollama"]["up"] is False


def test_new_get_routes_enter_the_read_budget_and_the_stream_stays_out(tmp_path):
    from .test_read_budget import discover_read_routes

    found = discover_read_routes(create_app(make_settings(tmp_path)))
    assert "/api/system/identity" in found and "/api/carbon/session" in found
    assert "/api/system/stream" not in found  # flux SSE exclu du budget (AD-15)
