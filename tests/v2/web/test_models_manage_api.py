"""Décharger, supprimer un modèle et choisir ses défauts (story 5.4). L'app est la vraie (hub,
registre, préférences) ; Ollama est un faux (`FakeOllama`, y compris `DELETE /api/delete`) : aucun
vrai modèle n'est supprimé, aucune requête ne part vers le vrai Ollama."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import httpx
import pytest

from wavelocalai.hardware.memory import MemoryAdvisor, MemoryReading
from wavelocalai.models.ollama_api import OllamaHttpSource
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.models import LeafResult
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..fake_ollama import FakeOllama
from ..producers import LOCAL_CO2

BASE = f"http://127.0.0.1:{TEST_PORT}"
GB = 1024**3
CLOUD = "groq/openai/gpt-oss-120b"
CATALOG = {
    "models": {
        "Petit 1B": {"ollama_tag": "small:1b", "size_gb": "0.8 GB", "params_tot": "1B",
                     "params_act": "1B", "capabilities": ["chat"]},
        "Moyen 7B": {"ollama_tag": "mid:7b", "size_gb": "4.7 GB", "params_tot": "7B",
                     "params_act": "7B", "capabilities": ["chat", "tools"],
                     "measured_loaded_gb": 5.0},
        "Autre 4B": {"ollama_tag": "other:4b", "size_gb": "2.5 GB", "params_tot": "4B",
                     "params_act": "4B", "capabilities": ["chat", "tools"]},
        "Plongement": {"ollama_tag": "nomic-embed-text", "size_gb": "0.3 GB",
                       "params_tot": "0.1B", "capabilities": ["embedding"]},
    }
}  # fmt: skip
TAGS = ["small:1b", "mid:7b", "other:4b", "nomic-embed-text"]


def ollama(**fields) -> FakeOllama:
    return FakeOllama(
        **{"tags": list(TAGS), "sizes": {"mid:7b": int(4.7 * GB), "small:1b": GB}, **fields}
    )


@contextlib.asynccontextmanager
async def manage_app(tmp_path: Path, server: FakeOllama, *, available_gb: float = 12.0):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(CATALOG), encoding="utf-8")
    config = make_settings(
        tmp_path,
        environ={"WAVELOCALAI_TESTING": "1", "GROQ_API_KEY": "gsk_test_0123456789"},
        cloud={"models": {"groq": ["openai/gpt-oss-120b"]}},
    )
    memory = lambda: MemoryReading(total_gb=32.0, available_gb=available_gb)  # noqa: E731
    registry = ModelRegistry(
        config,
        source=OllamaHttpSource(config.ollama.host, transport=server.transport),
        advisor=MemoryAdvisor(memory),
        catalog_path=catalog,
    )
    app = create_app(
        config,
        registry=registry,
        ollama_client=server.client(),
        ollama_transport=server.transport,
        memory_reader=memory,
    )
    async with app.router.lifespan_context(app):
        await registry.refresh()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url=BASE, headers={"Origin": BASE}
        ) as client:
            yield app, client, registry


async def _defaults(client, purpose, allow_cloud=False):
    response = await client.get(
        "/api/models/defaults", params={"purpose": purpose, "allow_cloud": allow_cloud}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _tags(client):
    return [m["tag"] for m in (await client.get("/api/models")).json()["models"]]


# --- Éligibilité à l'usage (décision du 2026-10-19, n° 17) ----------------------------------------


async def test_the_defaults_say_which_models_are_eligible_to_each_purpose(tmp_path):
    async with manage_app(tmp_path, ollama()) as (_, client, _r):
        chat = (await _defaults(client, "chat"))["eligible"]
        agent = (await _defaults(client, "agent"))["eligible"]
        rag = (await _defaults(client, "rag"))["eligible"]
        arena = (await _defaults(client, "arena", allow_cloud=True))["eligible"]
        judge = (await _defaults(client, "judge", allow_cloud=True))["eligible"]
    assert sorted(chat) == ["mid:7b", "other:4b", "small:1b"]  # jamais un modèle d'embedding
    assert sorted(agent) == ["mid:7b", "other:4b"]  # outils vérifiés et 3 B actifs
    assert sorted(rag) == ["mid:7b", "other:4b"]  # 3 B actifs
    assert CLOUD not in arena and sorted(arena) == ["mid:7b", "other:4b", "small:1b"]
    assert CLOUD in judge


# --- Choisir un défaut ---------------------------------------------------------------------------


async def test_a_choice_is_written_to_the_preferences_and_read_back_with_its_reason(tmp_path):
    async with manage_app(tmp_path, ollama()) as (app, client, _r):
        before = await _defaults(client, "agent")
        assert before["source"] == "rule"
        response = await client.put("/api/models/defaults/agent", json={"tags": ["other:4b"]})
        assert response.status_code == 200
        body = response.json()
        assert (body["tags"], body["source"], body["reason"]) == (
            ["other:4b"],
            "preference",
            "Choisi par vous",
        )
        assert app.state.preferences.get("default_model.agent") == {"tags": ["other:4b"]}
        read = await _defaults(client, "agent")
        assert (read["tags"], read["source"], read["reason"]) == (
            ["other:4b"],
            "preference",
            "Choisi par vous",
        )
        assert (await _defaults(client, "chat"))[
            "source"
        ] == "rule"  # un autre usage garde la règle


async def test_reverting_clears_the_preference_and_the_rule_applies_again(tmp_path):
    async with manage_app(tmp_path, ollama()) as (app, client, _r):
        automatic = await _defaults(client, "chat")
        await client.put("/api/models/defaults/chat", json={"tags": ["mid:7b"]})
        response = await client.delete("/api/models/defaults/chat")  # pas pris pour un modèle
        assert response.status_code == 204 and response.content == b""
        assert app.state.preferences.get("default_model.chat") is None
        again = await _defaults(client, "chat")
        assert again["source"] == "rule" and again["tags"] == automatic["tags"]
        assert (await client.delete("/api/models/defaults/chat")).status_code == 204  # idempotent


async def test_an_ineligible_model_is_refused_and_nothing_is_stored(tmp_path):
    async with manage_app(tmp_path, ollama()) as (app, client, _r):
        agent = await client.put("/api/models/defaults/agent", json={"tags": ["small:1b"]})
        rag = await client.put("/api/models/defaults/rag", json={"tags": ["small:1b"]})
        embedding = await client.put(
            "/api/models/defaults/chat", json={"tags": ["nomic-embed-text"]}
        )
        for response in (agent, rag, embedding):
            assert response.status_code == 422, response.text
            assert response.json()["code"] == "model_not_eligible"
        assert agent.json()["detail"]["purpose"] == "agent"
        assert agent.json()["detail"]["tag"] == "small:1b"
        assert "{" not in agent.json()["message"] and "small:1b" in agent.json()["message"]
        for purpose in ("agent", "rag", "chat"):
            assert app.state.preferences.get(f"default_model.{purpose}") is None


async def test_an_unknown_model_a_cloud_model_without_consent_and_a_bad_count_are_refused(tmp_path):
    async with manage_app(tmp_path, ollama()) as (app, client, _r):
        unknown = await client.put("/api/models/defaults/chat", json={"tags": ["gone:7b"]})
        assert (unknown.status_code, unknown.json()["code"]) == (404, "model_not_found")
        no_consent = await client.put("/api/models/defaults/judge", json={"tags": [CLOUD]})
        assert (no_consent.status_code, no_consent.json()["code"]) == (403, "cloud_not_allowed")
        arena_cloud = await client.put(
            "/api/models/defaults/arena",
            json={"tags": ["small:1b", CLOUD], "allow_cloud": True},
        )
        assert arena_cloud.json()["code"] == "model_not_eligible"  # l'Arène reste locale
        two_for_chat = await client.put(
            "/api/models/defaults/chat", json={"tags": ["small:1b", "mid:7b"]}
        )
        assert two_for_chat.json()["code"] == "invalid_request"
        one_for_arena = await client.put("/api/models/defaults/arena", json={"tags": ["mid:7b"]})
        assert one_for_arena.json()["code"] == "invalid_request"
        empty = await client.put("/api/models/defaults/chat", json={"tags": []})
        four = await client.put("/api/models/defaults/arena", json={"tags": list("abcd")})
        assert empty.status_code == four.status_code == 422
        assert (
            await client.put("/api/models/defaults/nope", json={"tags": ["a"]})
        ).status_code == 422
        assert app.state.preferences.get("default_model.chat") is None


async def test_an_arena_choice_keeps_two_or_three_local_models(tmp_path):
    async with manage_app(tmp_path, ollama()) as (_, client, _r):
        response = await client.put(
            "/api/models/defaults/arena", json={"tags": ["mid:7b", "small:1b", "mid:7b"]}
        )
        assert response.status_code == 200
        assert response.json()["tags"] == ["mid:7b", "small:1b"]  # un modèle une seule fois
        assert (await _defaults(client, "arena"))["source"] == "preference"


async def test_a_cloud_choice_is_kept_only_with_allow_cloud_and_says_it_is_inactive(tmp_path):
    async with manage_app(tmp_path, ollama()) as (_, client, _r):
        response = await client.put(
            "/api/models/defaults/judge", json={"tags": [CLOUD], "allow_cloud": True}
        )
        assert response.status_code == 200 and response.json()["tags"] == [CLOUD]
        on = await _defaults(client, "judge", allow_cloud=True)
        assert (on["tags"], on["source"], on["inactive"]) == ([CLOUD], "preference", [])
        off = await _defaults(client, "judge", allow_cloud=False)
        assert off["source"] == "rule" and CLOUD not in off["tags"]  # jamais de cloud sans accord
        assert off["inactive"] == [
            CLOUD
        ]  # l'écran dit « inactif tant que le cloud n'est pas autorisé »
        await client.delete("/api/models/defaults/judge")
        assert (await _defaults(client, "judge"))["inactive"] == []


async def test_writing_a_default_from_another_origin_is_refused(tmp_path):
    async with manage_app(tmp_path, ollama()) as (app, client, _r):
        foreign = {"Origin": "http://evil.example"}
        put = await client.put(
            "/api/models/defaults/chat", json={"tags": ["mid:7b"]}, headers=foreign
        )
        delete = await client.delete("/api/models/mid:7b", headers=foreign)
        for response in (put, delete):
            assert (response.status_code, response.json()["code"]) == (403, "forbidden_origin")
        assert app.state.preferences.get("default_model.chat") is None
        assert "mid:7b" in await _tags(client)


# --- Supprimer un modèle -------------------------------------------------------------------------


async def test_deleting_a_model_removes_it_from_ollama_the_list_and_returns_it_to_the_catalog(
    tmp_path,
):
    server = ollama()
    async with manage_app(tmp_path, server) as (_, client, _r):
        assert "mid:7b" not in [
            m["tag"] for m in (await client.get("/api/models/catalog")).json()["models"]
        ]
        response = await client.delete("/api/models/mid:7b")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["tag"] == "mid:7b" and body["freed_gb"] == pytest.approx(4.7, abs=0.01)
        assert body["reverted"] == []
        assert server.deleted == ["mid:7b"]
        assert "mid:7b" not in await _tags(client)
        catalog = (await client.get("/api/models/catalog")).json()["models"]
        assert "mid:7b" in [m["tag"] for m in catalog]  # un modèle supprimé revient au catalogue


async def test_a_loaded_model_is_unloaded_before_it_is_deleted(tmp_path):
    server = ollama(loaded=["mid:7b"])
    async with manage_app(tmp_path, server) as (_, client, _r):
        assert (await client.delete("/api/models/mid:7b")).status_code == 200
    assert server.unloaded == ["mid:7b"] and server.deleted == ["mid:7b"]


async def test_a_cold_model_is_deleted_without_a_keep_alive_request(tmp_path):
    # `keep_alive: 0` sur un modèle froid le chargerait d'abord (revue story 5.4) : `/api/ps`
    # décide.
    server = ollama(loaded=["small:1b"])
    async with manage_app(tmp_path, server) as (_, client, _r):
        assert (await client.delete("/api/models/nomic-embed-text")).status_code == 200
    assert server.unloaded == [] and server.deleted == ["nomic-embed-text"]


async def test_a_tag_with_slashes_is_deleted_as_a_whole(tmp_path):
    tag = "hf.co/utilisateur/depot:Q4_K_M"
    server = ollama(tags=[*TAGS, tag])
    async with manage_app(tmp_path, server) as (_, client, _r):
        assert tag in await _tags(client)
        assert (await client.delete(f"/api/models/{tag}")).status_code == 200
        assert tag not in await _tags(client)
    assert server.deleted == [tag]


async def test_a_deleted_default_falls_back_to_the_rule_and_does_not_come_back(tmp_path):
    server = ollama()
    async with manage_app(tmp_path, server) as (app, client, _r):
        await client.put("/api/models/defaults/agent", json={"tags": ["mid:7b"]})
        await client.put("/api/models/defaults/rag", json={"tags": ["mid:7b"]})
        await client.put("/api/models/defaults/chat", json={"tags": ["small:1b"]})
        await client.put("/api/models/defaults/arena", json={"tags": ["mid:7b", "small:1b"]})
        response = await client.delete("/api/models/mid:7b")
        assert sorted(response.json()["reverted"]) == ["agent", "arena", "rag"]
        agent = await _defaults(client, "agent")
        assert agent["source"] == "rule" and agent["tags"] == ["other:4b"]
        assert "Choisi par vous" not in agent["reason"] and agent["reason"]  # la raison de la règle
        assert (await _defaults(client, "arena"))["source"] == "rule"
        assert (await _defaults(client, "chat"))["tags"] == ["small:1b"]  # un autre choix reste
        for purpose in ("agent", "rag", "arena"):
            assert app.state.preferences.get(f"default_model.{purpose}") is None
        # Réinstallé, le modèle ne redevient pas un défaut sans un nouveau geste (décision Q2).
        server.tags.append("mid:7b")
        app.state.registry.invalidate()
        await app.state.registry.refresh()
        assert (await _defaults(client, "agent"))["source"] == "rule"


async def test_a_model_used_by_an_active_run_cannot_be_deleted(tmp_path):
    server = ollama(loaded=["mid:7b"])
    async with manage_app(tmp_path, server) as (app, client, _r):
        handle = await app.state.hub.create_run("chat", models=["mid:7b"], user_message="Q ?")
        response = await client.delete("/api/models/mid:7b")
        assert (response.status_code, response.json()["code"]) == (409, "model_in_use")
        assert response.json()["detail"]["tag"] == "mid:7b"
        assert response.json()["detail"]["run_id"] == handle.run_id
        assert "mid:7b" in response.json()["message"]
        assert server.deleted == [] and server.unloaded == []  # ni supprimé ni déchargé
        assert "mid:7b" in await _tags(client)
        # Un autre modèle, lui, se supprime pendant ce run.
        assert (await client.delete("/api/models/small:1b")).status_code == 200
        await app.state.hub.finish_leaf(handle.run_id, LeafResult(origin="local"), LOCAL_CO2)
        assert (await client.delete("/api/models/mid:7b")).status_code == 200


async def test_the_system_stream_says_which_models_a_run_uses(tmp_path):
    async with manage_app(tmp_path, ollama()) as (app, _client, _r):
        assert (await app.state.system_sampler.sample())["models_in_use"] == {}
        handle = await app.state.hub.create_run("chat", models=["mid:7b"], user_message="Q ?")
        state = await app.state.system_sampler.sample()
        assert state["models_in_use"] == {"mid:7b": handle.run_id}


@pytest.mark.parametrize(
    ("fields", "status", "code"),
    [
        ({"delete_status": 500}, 502, "model_delete_failed"),
        ({"delete_status": "connect"}, 503, "ollama_down"),
    ],
)
async def test_a_refusal_or_a_silent_ollama_leaves_the_list_unchanged(
    tmp_path, fields, status, code
):
    server = ollama(**fields)
    async with manage_app(tmp_path, server) as (_, client, _r):
        response = await client.delete("/api/models/mid:7b")
        assert (response.status_code, response.json()["code"]) == (status, code)
        assert "mid:7b" in await _tags(client)
        if code == "model_delete_failed":
            assert response.json()["detail"]["tag"] == "mid:7b"
            assert "500" in response.json()["detail"]["technical"]


async def test_an_unknown_or_cloud_tag_is_not_found_and_ollama_is_not_called(tmp_path):
    server = ollama()
    async with manage_app(tmp_path, server) as (_, client, _r):
        for tag in ("gone:7b", CLOUD):
            response = await client.delete(f"/api/models/{tag}")
            assert (response.status_code, response.json()["code"]) == (404, "model_not_found")
    assert server.deleted == []


async def test_a_model_ollama_no_longer_knows_is_still_removed_from_the_list(tmp_path):
    server = ollama()
    async with manage_app(tmp_path, server) as (_, client, _r):
        server.tags.remove("small:1b")  # supprimé ailleurs : la liste du registre est en retard
        assert "small:1b" in await _tags(client)
        response = await client.delete("/api/models/small:1b")  # Ollama répond 404 : c'est fait
        assert response.status_code == 200
        assert "small:1b" not in await _tags(client)


async def test_deleting_publishes_the_system_state_without_waiting_for_the_tick(tmp_path):
    server = ollama(loaded=["small:1b"])
    async with manage_app(tmp_path, server) as (app, client, _r):
        published = []
        original = app.state.system_feed.publish
        app.state.system_feed.publish = lambda *args, **kwargs: (
            published.append(args),
            original(*args, **kwargs),
        )[1]
        await client.delete("/api/models/small:1b")
    assert published and published[-1][0] == "system_state"
    assert "models_in_use" in published[-1][1]


async def test_only_the_delete_route_and_the_default_writes_reach_ollama_for_a_removal(tmp_path):
    """Lire l'écran (liste, catalogue, défauts) n'appelle jamais `/api/delete`."""
    server = ollama()
    async with manage_app(tmp_path, server) as (_, client, _r):
        await client.get("/api/models")
        await client.get("/api/models/catalog")
        for purpose in ("chat", "arena", "judge", "agent", "rag"):
            await _defaults(client, purpose)
        await client.put("/api/models/defaults/chat", json={"tags": ["mid:7b"]})
        await client.delete("/api/models/defaults/chat")
        await client.post("/api/models/unload")
    assert server.deleted == [] and server.tags == TAGS
