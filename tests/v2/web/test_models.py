"""`GET /api/models` : cache, budget Ollama arrêté, cloud refusé sans `allow_cloud` (AD-9, AD-15)."""

from __future__ import annotations

import json
import time

import httpx
from fastapi import Request
from fastapi.testclient import TestClient

from wavelocalai.hardware.memory import MemoryAdvisor, MemoryReading
from wavelocalai.models.facts import InMemoryFactsStore, facts_from_ollama
from wavelocalai.models.ollama_api import OllamaHttpSource
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings

BASE = f"http://127.0.0.1:{TEST_PORT}"
GB = 1024**3

TAGS = {
    "models": [
        {
            "model": "qwen3.5:2b",
            "digest": "d1",
            "size": int(2.5 * GB),
            "details": {"family": "qwen35", "parameter_size": "2.3B"},
        },
        {
            "model": "nomic-embed-text:latest",
            "digest": "d2",
            "size": int(0.25 * GB),
            "details": {"family": "nomic-bert", "parameter_size": "137M"},
        },
    ]
}
SHOWS = {
    "qwen3.5:2b": {"capabilities": ["completion", "tools", "thinking"], "model_info": {}},
    "nomic-embed-text:latest": {"capabilities": ["embedding"], "model_info": {}},
}


def _ollama_transport(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=TAGS)
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOWS[json.loads(request.content)["model"]])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _app(tmp_path, *, calls=None, **settings_kwargs):
    settings = make_settings(
        tmp_path,
        environ={"GROQ_API_KEY": "gsk_test_0123456789"},
        cloud={"models": {"groq": ["openai/gpt-oss-120b"]}},
        **settings_kwargs,
    )
    source = OllamaHttpSource(
        settings.ollama.host, transport=_ollama_transport([] if calls is None else calls)
    )
    registry = ModelRegistry(
        settings,
        source=source,
        advisor=MemoryAdvisor(lambda: MemoryReading(32.0, 16.0)),
        wait_s=2.0,
    )
    return create_app(settings, registry=registry), registry


def test_models_route_lists_local_models_then_cloud_on_request(tmp_path):
    app, _ = _app(tmp_path)
    client = TestClient(app, base_url=BASE)

    body = client.get("/api/models").json()
    assert body["ollama_up"] is True
    assert [m["tag"] for m in body["models"]] == ["nomic-embed-text:latest", "qwen3.5:2b"]
    qwen = body["models"][1]
    assert set(qwen) >= {
        "tag", "name", "provider", "origin", "kind", "params_total_b", "params_active_b",
        "size_gb", "needed_gb", "fits", "tools_verified", "reasoning", "throughput_tps",
        "accuracy", "co2_method",
    }  # fmt: skip
    assert qwen["origin"] == "local" and qwen["fits"] is True and qwen["accuracy"] is None
    assert qwen["throughput_tps"] is None and qwen["co2_method"] == "codecarbon"

    for query in ("", "?allow_cloud=false"):
        tags = [m["tag"] for m in client.get("/api/models" + query).json()["models"]]
        assert not any("/" in tag for tag in tags)  # aucun cloud sans allow_cloud
    cloud = client.get("/api/models?allow_cloud=true").json()["models"]
    groq = next(m for m in cloud if m["origin"] == "cloud")
    assert groq["tag"] == "groq/openai/gpt-oss-120b" and groq["kind"] == "chat"


def test_models_are_served_from_cache_without_new_ollama_calls(tmp_path):
    calls: list[str] = []
    app, _ = _app(tmp_path, calls=calls)
    client = TestClient(app, base_url=BASE)
    client.get("/api/models")
    before = list(calls)
    for _ in range(3):
        assert client.get("/api/models").status_code == 200
    assert calls == before  # dans les 5 s, ni /api/tags ni /api/show


def test_ollama_down_answers_from_cache_under_300_ms(tmp_path):
    # Ollama injoignable (port fermé de `make_settings`), mais un précédent démarrage a laissé
    # des faits dans `model_facts`.
    settings = make_settings(tmp_path)
    facts = InMemoryFactsStore()
    for item in TAGS["models"]:
        facts.put(facts_from_ollama(item, SHOWS[item["model"]]))
    registry = ModelRegistry(settings, facts=facts)  # vrai client HTTP, vers le port fermé
    client = TestClient(create_app(settings, registry=registry), base_url=BASE)
    TestClient(create_app(settings), base_url=BASE).get("/api/models")  # mise en température

    started = time.perf_counter()
    response = client.get("/api/models")
    elapsed = time.perf_counter() - started

    assert elapsed < 0.3, f"{elapsed * 1000:.0f} ms"
    body = response.json()
    assert body["ollama_up"] is False and body["refreshed_at"] is None
    assert {m["tag"] for m in body["models"]} == {"qwen3.5:2b", "nomic-embed-text:latest"}
    assert all(m["available"] is False for m in body["models"])


def test_resolve_through_a_command_refuses_cloud_without_allow_cloud(tmp_path):
    app, registry = _app(tmp_path)

    @app.post("/api/test-command")
    async def command(request: Request) -> dict[str, str]:  # commande factice
        body = await request.json()
        ref = request.app.state.registry.resolve(body["model"], body.get("allow_cloud"))
        return {"tag": ref.tag, "origin": ref.origin}

    client = TestClient(app, base_url=BASE, headers={"Origin": BASE})
    client.get("/api/models")  # peuple le registre

    refused = client.post("/api/test-command", json={"model": "groq/openai/gpt-oss-120b"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "cloud_not_allowed"
    assert refused.json()["detail"]["tag"] == "groq/openai/gpt-oss-120b"
    explicit = client.post(
        "/api/test-command", json={"model": "groq/openai/gpt-oss-120b", "allow_cloud": False}
    )
    assert explicit.json()["code"] == "cloud_not_allowed"
    allowed = client.post(
        "/api/test-command", json={"model": "groq/openai/gpt-oss-120b", "allow_cloud": True}
    )
    assert allowed.json() == {"tag": "groq/openai/gpt-oss-120b", "origin": "cloud"}

    not_chat = client.post("/api/test-command", json={"model": "nomic-embed-text"})
    assert not_chat.status_code == 422 and not_chat.json()["code"] == "model_not_chat"
    assert client.post("/api/test-command", json={"model": "x:1b"}).status_code == 404


def test_lifespan_starts_and_stops_the_background_refresh(tmp_path):
    calls: list[str] = []
    app, _ = _app(tmp_path, calls=calls)
    with TestClient(app, base_url=BASE) as client:
        client.get("/api/health")
        deadline = time.monotonic() + 2
        while "/api/tags" not in calls and time.monotonic() < deadline:
            time.sleep(0.01)
    assert "/api/tags" in calls
