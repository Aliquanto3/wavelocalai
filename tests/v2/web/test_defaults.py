"""`GET /api/models/defaults` : usages, raison, cloud, `no_model`, préférence (AD-9, AD-15)."""

from __future__ import annotations

import json
import time

import httpx
from fastapi.testclient import TestClient

from wavelocalai.hardware.memory import MemoryAdvisor, MemoryReading
from wavelocalai.models.ollama_api import OllamaHttpSource
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.store.preferences import InMemoryPreferenceStore
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, closed_port, make_settings

BASE = f"http://127.0.0.1:{TEST_PORT}"
GB = 1024**3


def _item(tag, digest, size_gb, family="llama", params="3B"):
    return {
        "model": tag,
        "digest": digest,
        "size": int(size_gb * GB),
        "details": {"family": family, "parameter_size": params},
    }


EMBED = _item("nomic-embed-text:latest", "d4", 0.25, family="nomic-bert", params="137M")
TAGS = {
    "models": [
        _item("small:1b", "d1", 1.0, params="1B"),
        _item("mid:4b", "d2", 3.0, params="4B"),
        _item("big:9b", "d3", 7.0, params="9B"),
        EMBED,
    ]
}


def _transport(tags):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=tags)
        if request.url.path == "/api/show":
            tag = json.loads(request.content)["model"]
            caps = ["embedding"] if "embed" in tag else ["completion", "tools"]
            return httpx.Response(200, json={"capabilities": caps, "model_info": {}})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _app(tmp_path, tags=TAGS, preferences=None, env=None):
    settings = make_settings(
        tmp_path,
        environ=env or {},
        cloud={"models": {"anthropic": ["claude-opus-5-5"]}},
    )
    registry = ModelRegistry(
        settings,
        source=OllamaHttpSource(settings.ollama.host, transport=_transport(tags)),
        advisor=MemoryAdvisor(lambda: MemoryReading(32.0, 12.0)),
        wait_s=2.0,
    )
    return create_app(settings, registry=registry, preferences=preferences)


def test_every_purpose_returns_tags_and_a_reason_in_french(tmp_path):
    client = TestClient(_app(tmp_path), base_url=BASE)
    for purpose in ("chat", "arena", "judge", "agent", "rag"):
        body = client.get("/api/models/defaults", params={"purpose": purpose}).json()
        assert body["purpose"] == purpose
        assert body["tags"] and body["reason"].strip() and body["source"] == "rule"
        assert "nomic-embed-text:latest" not in body["tags"]
    assert len(client.get("/api/models/defaults?purpose=arena").json()["tags"]) >= 2
    assert client.get("/api/models/defaults?purpose=judge").json()["tags"] == ["big:9b"]


def test_cloud_defaults_need_allow_cloud(tmp_path):
    env = {"ANTHROPIC_API_KEY": "sk-ant-test0123456789"}
    client = TestClient(_app(tmp_path, env=env), base_url=BASE)
    assert client.get("/api/models/defaults?purpose=judge").json()["tags"] == ["big:9b"]
    allowed = client.get("/api/models/defaults?purpose=judge&allow_cloud=true").json()
    assert allowed["tags"] == ["anthropic/claude-opus-5-5"]


def test_no_chat_model_installed_answers_no_model(tmp_path):
    client = TestClient(_app(tmp_path, tags={"models": [EMBED]}), base_url=BASE)
    response = client.get("/api/models/defaults?purpose=chat")
    body = response.json()
    assert response.status_code == 404 and body["code"] == "no_model"
    assert body["message"] and body["action"] and body["detail"]["purpose"] == "chat"


def test_unknown_purpose_is_an_invalid_request(tmp_path):
    client = TestClient(_app(tmp_path), base_url=BASE)
    response = client.get("/api/models/defaults?purpose=poesie")
    assert response.status_code == 422 and response.json()["code"] == "invalid_request"


def test_a_stored_preference_wins_for_its_purpose_only(tmp_path):
    prefs = InMemoryPreferenceStore()
    prefs.put("default_model.chat", {"tags": ["mid:4b"]})
    client = TestClient(_app(tmp_path, preferences=prefs), base_url=BASE)
    chat = client.get("/api/models/defaults?purpose=chat").json()
    assert chat["tags"] == ["mid:4b"] and chat["source"] == "preference"
    assert client.get("/api/models/defaults?purpose=judge").json()["source"] == "rule"


def test_ollama_down_answers_from_cache_under_300_ms(tmp_path):
    settings = make_settings(tmp_path, ollama={"host": f"http://127.0.0.1:{closed_port()}"})
    client = TestClient(create_app(settings), base_url=BASE)
    client.get("/api/models/defaults")  # mise en température
    started = time.perf_counter()
    response = client.get("/api/models/defaults?purpose=arena")
    assert time.perf_counter() - started < 0.3
    assert response.status_code == 404 and response.json()["code"] == "no_model"


def test_the_route_is_in_the_openapi_schema_so_the_budget_test_finds_it(tmp_path):
    assert "/api/models/defaults" in _app(tmp_path).openapi()["paths"]
