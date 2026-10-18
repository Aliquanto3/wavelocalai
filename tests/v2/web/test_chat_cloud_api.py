"""`POST /api/chat/runs` avec un modèle cloud : OpenAI, Groq, Anthropic, Mistral (story 2.4).

L'app est la vraie (hub, registre, service de chat, flux SSE) ; chaque fournisseur est simulé sous
son vrai SDK par un faux transport HTTP. Aucun appel réseau, aucune vraie clé.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx
import pytest

from wavelocalai.models.ollama_api import OllamaHttpSource
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..fake_cloud import (
    FAKE_KEYS,
    KEY_ENV,
    MODELS,
    SETTINGS_CLOUD,
    FakeCloud,
    Plan,
    factories,
    stream_for,
)
from ..fake_ollama import FakeOllama
from .conftest import parse_sse

BASE = f"http://127.0.0.1:{TEST_PORT}"
IDS = [provider for provider, _, _ in MODELS]


@contextlib.asynccontextmanager
async def cloud_app(
    tmp_path,
    fakes: list[FakeCloud],
    *,
    keys: list[str] | None = None,
    cloud: dict | None = None,
    **extra,
):
    """(app, client) : clés de `keys` (tous les fournisseurs par défaut) dans l'environnement."""
    providers = keys if keys is not None else [f.provider for f in fakes]
    environ = {KEY_ENV[p]: FAKE_KEYS[p] for p in providers}
    config = make_settings(tmp_path, environ=environ, cloud=cloud or SETTINGS_CLOUD, **extra)
    server = FakeOllama()
    registry = ModelRegistry(
        config, source=OllamaHttpSource(config.ollama.host, transport=server.transport)
    )
    app = create_app(
        config, registry=registry, ollama_client=server.client(), cloud_http=factories(*fakes)
    )
    async with app.router.lifespan_context(app):
        await registry.refresh()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


async def _post(client, tag, *, allow_cloud, message="Bonjour"):
    body = {"model": tag, "message": message, "temperature": 0.2, "allow_cloud": allow_cloud}
    return await client.post("/api/chat/runs", json=body)


async def _ended(client, run_id, timeout=5.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


async def _events(client, run_id):
    response = await client.get(f"/api/runs/{run_id}/events")
    return [f["data"] for f in parse_sse(response.text)[0]]


def _fake(provider, plan):
    return FakeCloud(provider, [plan])


@pytest.mark.parametrize(("provider", "tag", "model_id"), MODELS, ids=IDS)
async def test_cloud_model_without_allow_cloud_is_refused_and_the_provider_is_never_called(
    tmp_path, provider, tag, model_id
):
    fake = _fake(provider, Plan(stream_for(provider, ["jamais"])))
    async with cloud_app(tmp_path, [fake]) as (app, client):
        for body_value in (False, None):  # faux, puis champ absent
            body = {"model": tag, "message": "x"}
            if body_value is not None:
                body["allow_cloud"] = body_value
            refused = await client.post("/api/chat/runs", json=body)
            assert refused.status_code == 403 and refused.json()["code"] == "cloud_not_allowed"
            assert refused.json()["detail"]["tag"] == tag
        assert fake.requests == [] and fake.clients == []  # aucun appel, aucun client
        assert app.state.hub.active_runs() == []  # ni run créé
        assert app.state.local_slot.acquired == 0


@pytest.mark.parametrize(("provider", "tag", "model_id"), MODELS, ids=IDS)
async def test_cloud_chat_streams_without_the_local_slot_and_marks_the_run_as_cloud(
    tmp_path, provider, tag, model_id
):
    fake = _fake(provider, Plan(stream_for(provider, ["Bonjour", " nuage"])))
    async with cloud_app(tmp_path, [fake]) as (app, client):
        response = await _post(client, tag, allow_cloud=True, message="Salut nuage")
        assert response.status_code == 200
        started = response.json()
        assert (await _ended(client, started["run_id"]))["status"] == "ok"
        events = await _events(client, started["run_id"])
        types = [e["type"] for e in events]
        assert types[0] == "run_started" and types[-1] == "run_ended"
        tokens = [e["data"] for e in events if e["type"] == "token"]
        assert {t["lane"] for t in tokens} == {tag}
        assert "".join(t["text"] for t in tokens) == "Bonjour nuage"
        metrics = next(e["data"] for e in events if e["type"] == "metrics")
        assert metrics["origin"] == "cloud" and metrics["tps_source"] == "wallclock"
        assert metrics["load_s"] is None and metrics["eval_tokens"] > 0
        co2 = metrics["co2"]  # story 2.5 : estimé par ecologits, avec sa plage, jamais 0
        assert co2["method"] == "ecologits" and co2["estimated"] is True and co2["mg"] > 0
        assert co2["allocation"] == "direct"
        assert co2["reason"] is None or "moins précise" in co2["reason"]  # réserve d'ecologits
        assert 0 < co2["range_mg"]["low"] <= co2["mg"] <= co2["range_mg"]["high"]
        assert events[-1]["data"] == {"status": "ok", "error": None}
        assert app.state.local_slot.acquired == 0  # pas de place du sémaphore local (AD-14)
        assert len(fake.requests) == 1 and fake.bodies[0]["model"] == model_id
        row = app.state.store.read(
            "SELECT origin, model FROM runs WHERE id = ?", (started["run_id"],)
        )
        assert (row[0]["origin"], row[0]["model"]) == ("cloud", tag)
        assert "Salut nuage" not in str(events[0])  # AD-7 : pas de texte saisi dans run_started


async def test_cloud_call_is_not_blocked_by_a_busy_local_slot(tmp_path):
    fake = _fake("openai", Plan(stream_for("openai", ["Vite"])))
    async with cloud_app(tmp_path, [fake]) as (app, client):  # noqa: SIM117
        async with app.state.local_slot:
            started = (await _post(client, MODELS[0][1], allow_cloud=True)).json()
            assert (await _ended(client, started["run_id"], timeout=3))["status"] == "ok"


@pytest.mark.parametrize(("provider", "tag", "model_id"), MODELS, ids=IDS)
async def test_missing_key_ends_the_run_in_cloud_key_missing_without_any_call(
    tmp_path, provider, tag, model_id
):
    fake = _fake(provider, Plan(stream_for(provider, ["jamais"])))
    async with cloud_app(tmp_path, [fake], keys=[]) as (_, client):
        listed = (await client.get("/api/models", params={"allow_cloud": "true"})).json()
        assert tag not in {m["tag"] for m in listed["models"]}  # non proposé sans clé
        started = (await _post(client, tag, allow_cloud=True)).json()
        assert (await _ended(client, started["run_id"]))["status"] == "error"
        error = (await _events(client, started["run_id"]))[-1]["data"]["error"]
        assert error["code"] == "cloud_key_missing"
        assert KEY_ENV[provider] in error["action"] and ".env" in error["action"]
        assert error["detail"]["provider"] == provider
        assert fake.requests == []


@pytest.mark.parametrize(("provider", "tag", "model_id"), MODELS, ids=IDS)
async def test_refused_key_is_cloud_key_refused_and_no_key_leaks_anywhere(
    tmp_path, provider, tag, model_id, caplog
):
    key = FAKE_KEYS[provider]
    fake = _fake(provider, Plan(status=401, message=f"Incorrect API key provided: {key}"))
    with caplog.at_level(logging.DEBUG):
        async with cloud_app(tmp_path, [fake]) as (_, client):
            started = (await _post(client, tag, allow_cloud=True)).json()
            snapshot = await _ended(client, started["run_id"])
            assert snapshot["status"] == "error"
            events = await _events(client, started["run_id"])
            error = events[-1]["data"]["error"]
            assert error["code"] == "cloud_key_refused" and error["detail"]["http_status"] == 401
            assert key not in str(events) and key not in str(snapshot)
            assert key not in (await client.get(f"/api/runs/{started['run_id']}/events")).text
    assert key not in caplog.text


@pytest.mark.parametrize(("provider", "tag", "model_id"), MODELS, ids=IDS)
async def test_unreachable_provider_is_named_and_back_to_local_is_offered(
    tmp_path, provider, tag, model_id
):
    names = {"openai": "OpenAI", "groq": "Groq", "anthropic": "Anthropic", "mistral": "Mistral"}
    fake = _fake(provider, Plan(connect_error=True))
    async with cloud_app(tmp_path, [fake]) as (_, client):
        started = (await _post(client, tag, allow_cloud=True)).json()
        assert (await _ended(client, started["run_id"]))["status"] == "error"
        error = (await _events(client, started["run_id"]))[-1]["data"]["error"]
        assert error["code"] == "cloud_unreachable"
        assert names[provider] in error["message"] and "Local" in error["action"]
        assert error["detail"]["provider"] == provider


async def test_a_rate_limited_provider_has_its_own_code(tmp_path):
    fake = _fake("groq", Plan(status=429, message="Rate limit reached"))
    async with cloud_app(tmp_path, [fake]) as (_, client):
        started = (await _post(client, MODELS[1][1], allow_cloud=True)).json()
        await _ended(client, started["run_id"])
        error = (await _events(client, started["run_id"]))[-1]["data"]["error"]
        assert error["code"] == "cloud_rate_limited" and error["detail"]["http_status"] == 429


async def test_a_second_turn_resends_the_history_to_the_provider(tmp_path):
    fake = FakeCloud(
        "anthropic",
        [Plan(stream_for("anthropic", ["Un"])), Plan(stream_for("anthropic", ["Deux"]))],
    )
    tag = MODELS[2][1]
    async with cloud_app(tmp_path, [fake]) as (_, client):
        first = (await _post(client, tag, allow_cloud=True, message="Premier ?")).json()
        await _ended(client, first["run_id"])
        body = {"model": tag, "message": "Suite ?", "allow_cloud": True}
        body["conversation_id"] = first["conversation_id"]
        second = (await client.post("/api/chat/runs", json=body)).json()
        await _ended(client, second["run_id"])
        sent = [(m["role"], m["content"]) for m in fake.bodies[1]["messages"]]
        assert sent == [("user", "Premier ?"), ("assistant", "Un"), ("user", "Suite ?")]
