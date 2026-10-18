"""`GET /api/health` : version, instance, Ollama (sonde en cache), fournisseurs cloud."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from wavelocalai.models.ollama_probe import OllamaProbe
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings

BASE = f"http://127.0.0.1:{TEST_PORT}"


def test_ollama_down_shape(tmp_path):
    client = TestClient(create_app(make_settings(tmp_path)), base_url=BASE)
    body = client.get("/api/health").json()
    assert set(body) == {"version", "instance_id", "ollama", "cloud_providers"}
    assert body["ollama"] == {"up": False, "version": None, "latency_ms": None}
    assert body["version"] and len(body["instance_id"]) == 32


def test_ollama_up_with_probe_cached(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"version": "0.40.6"})

    settings = make_settings(tmp_path)
    probe = OllamaProbe(settings.ollama.host, transport=httpx.MockTransport(handler), wait_s=1.0)
    client = TestClient(create_app(settings, probe), base_url=BASE)
    first = client.get("/api/health").json()["ollama"]
    second = client.get("/api/health").json()["ollama"]
    assert first["up"] is True and first["version"] == "0.40.6" and first["latency_ms"] >= 1
    assert second["up"] is True
    assert calls == ["/api/version"]  # cache de 5 s : une seule sonde


def test_instance_id_is_new_at_each_start_and_stable_within_one(tmp_path):
    settings = make_settings(tmp_path)
    one = TestClient(create_app(settings), base_url=BASE)
    two = TestClient(create_app(settings), base_url=BASE)
    first = one.get("/api/health").json()["instance_id"]
    assert one.get("/api/health").json()["instance_id"] == first
    assert two.get("/api/health").json()["instance_id"] != first


def test_cloud_providers_come_from_settings_and_keys_never_leak(tmp_path):
    settings = make_settings(
        tmp_path, environ={"ANTHROPIC_API_KEY": "sk-ant-api03-secretsecret", "OPENAI_API_KEY": ""}
    )
    client = TestClient(create_app(settings), base_url=BASE)
    response = client.get("/api/health")
    providers = {p["id"]: p["configured"] for p in response.json()["cloud_providers"]}
    assert providers == {"openai": False, "groq": False, "anthropic": True, "mistral": False}
    assert "secretsecret" not in response.text


def test_startup_probe_reports_a_slow_ollama_up_on_the_first_request(tmp_path):
    import asyncio
    import time

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)  # Ollama vivant, lent à répondre (démarrage à froid)
        return httpx.Response(200, json={"version": "0.40.6"})

    settings = make_settings(tmp_path)
    probe = OllamaProbe(settings.ollama.host, transport=httpx.MockTransport(handler))
    with TestClient(create_app(settings, probe), base_url=BASE) as client:
        time.sleep(0.5)  # le navigateur s'ouvre
        assert client.get("/api/health").json()["ollama"]["up"] is True
