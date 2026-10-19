"""Supprimer un modèle (story 5.4) : `model_facts` purgé (le modèle ne réapparaît pas au démarrage à
froid), appel `DELETE /api/delete` d'Ollama, éligibilité des défauts. Aucun vrai modèle supprimé."""

from __future__ import annotations

import json

import httpx
import pytest

from wavelocalai.errors import ERRORS
from wavelocalai.models.defaults import AGENT_MIN_PARAMS_B, ModelDefaults, is_eligible
from wavelocalai.models.facts import InMemoryFactsStore, facts_from_ollama
from wavelocalai.models.facts_store import SqliteFactsStore
from wavelocalai.models.ollama_api import OllamaUnavailableError
from wavelocalai.models.ollama_delete import DeleteError, delete_model
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.store.db import Store, db_path
from wavelocalai.store.preferences import InMemoryPreferenceStore

from ..conftest import make_settings
from .test_defaults import BIG, EMBED, MID, SMALL, FakeRegistry, info
from .test_registry import FakeOllama, _fixture_source

HOST = "http://127.0.0.1:11434"


def _facts(tag: str, digest: str, now: str):
    return facts_from_ollama(
        {"model": tag, "digest": digest, "size": 5}, {"capabilities": []}, now=now
    )


# --- model_facts purgé -----------------------------------------------------------------------------


def test_deleting_a_tag_purges_every_digest_of_that_tag_only(tmp_path):
    store = Store.open(db_path(tmp_path))
    facts = SqliteFactsStore(lambda: store)
    for fact in (
        _facts("m", "d1", "2026-10-19T10:00:01.000Z"),
        _facts("m", "d2", "2026-10-19T10:00:02.000Z"),
        _facts("other", "d9", "2026-10-19T10:00:03.000Z"),
    ):
        facts.put(fact)
    facts.delete_tag("m")  # attend l'écrivain : la ligne est partie quand l'appel rend
    assert facts.get("m", "d1") is None and facts.get("m", "d2") is None
    store.close()
    again = Store.open(db_path(tmp_path))
    fresh = SqliteFactsStore(lambda: again)  # sans mémoire des écritures : ce que lit un démarrage
    assert [f.tag for f in fresh.latest_per_tag()] == ["other"]
    again.close()


def test_the_in_memory_store_forgets_a_tag_too():
    facts = InMemoryFactsStore()
    facts.put(_facts("m", "d1", "2026-10-19T10:00:01.000Z"))
    facts.put(_facts("m", "d2", "2026-10-19T10:00:02.000Z"))
    facts.delete_tag("m")
    assert facts.latest_per_tag() == []


async def test_a_deleted_model_does_not_come_back_at_a_cold_start_with_ollama_down(tmp_path):
    path = db_path(tmp_path)
    store = Store.open(path)
    source = _fixture_source()
    registry = ModelRegistry(
        make_settings(tmp_path), source=source, facts=SqliteFactsStore(lambda: store)
    )
    await registry.refresh()
    assert "qwen3.5:2b" in [m.tag for m in (await registry.list_models()).models]
    source.listed = [m for m in source.listed if m["model"] != "qwen3.5:2b"]  # Ollama l'a supprimé
    await registry.forget("qwen3.5:2b")
    assert "qwen3.5:2b" not in [m.tag for m in (await registry.list_models()).models]
    store.close()

    reopened = Store.open(path)  # redémarrage, Ollama injoignable : la liste vient de `model_facts`
    down = FakeOllama([])
    down.down = True
    restarted = ModelRegistry(
        make_settings(tmp_path), source=down, facts=SqliteFactsStore(lambda: reopened)
    )
    result = await restarted.list_models()
    reopened.close()
    tags = {m.tag for m in result.models}
    assert result.ollama_up is False
    assert "qwen3.5:2b" not in tags  # ses lignes sont purgées
    assert {"nomic-embed-text:latest", "moe:30b"} <= tags  # les autres modèles restent


async def test_forgetting_a_model_removes_it_from_the_list_at_once(tmp_path):
    source = _fixture_source()
    registry = ModelRegistry(make_settings(tmp_path), source=source)
    await registry.refresh()
    assert "moe:30b" in {m.tag for m in (await registry.list_models()).models}
    source.listed = [m for m in source.listed if m["model"] != "moe:30b"]
    await registry.forget("moe:30b")
    assert "moe:30b" not in {m.tag for m in (await registry.list_models()).models}


# --- DELETE /api/delete ----------------------------------------------------------------------------


def _transport(handler):
    return httpx.MockTransport(handler)


async def test_ollama_delete_sends_the_tag_in_the_body_with_the_delete_method():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200)

    assert await delete_model(HOST, "qwen3.5:2b", transport=_transport(handler)) is True
    assert seen == [("DELETE", "/api/delete", {"model": "qwen3.5:2b"})]


async def test_a_model_ollama_does_not_know_is_not_an_error():
    transport = _transport(lambda request: httpx.Response(404, json={"error": "not found"}))
    assert await delete_model(HOST, "gone:1b", transport=transport) is False


async def test_a_refusal_carries_what_ollama_said_and_a_silent_ollama_is_unavailable():
    refusal = _transport(lambda request: httpx.Response(500, text="disque en lecture seule"))
    with pytest.raises(DeleteError, match="500.*disque en lecture seule"):
        await delete_model(HOST, "m:1b", transport=refusal)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé", request=request)

    with pytest.raises(OllamaUnavailableError):
        await delete_model(HOST, "m:1b", transport=_transport(refused))


# --- Éligibilité et préférences --------------------------------------------------------------------


def test_eligibility_follows_the_purpose_and_never_looks_at_memory():
    no_fit = info("big:70b", params=70.0, fits=False, tools=True)
    cloud = info("openai/gpt-4o-mini", origin="cloud", needed=None, fits=None, params=None)
    assert is_eligible(SMALL, "chat") and is_eligible(no_fit, "chat")  # l'avertissement vient après
    assert not is_eligible(SMALL, "rag") and is_eligible(MID, "rag")
    assert (
        not is_eligible(SMALL, "agent")
        and is_eligible(MID, "agent")
        and is_eligible(no_fit, "agent")
    )
    assert not is_eligible(info("tools:2b", params=2.0, tools=True), "agent")
    assert AGENT_MIN_PARAMS_B == 3.0
    assert is_eligible(cloud, "judge") and is_eligible(cloud, "agent")
    assert not is_eligible(cloud, "arena")  # l'Arène ne compare que des modèles locaux


async def test_forgetting_a_model_clears_the_preferences_that_pointed_at_it():
    prefs = InMemoryPreferenceStore()
    service = ModelDefaults(FakeRegistry([SMALL, MID, BIG, EMBED]), prefs)
    await service.choose("agent", ["mid:4b"])
    await service.choose("chat", ["big:9b"])
    await service.choose("arena", ["small:1b", "mid:4b"])
    assert service.chosen_for("mid:4b") == ["arena", "agent"]
    assert service.forget_model("mid:4b") == ["arena", "agent"]
    assert prefs.get("default_model.agent") is None and prefs.get("default_model.arena") is None
    assert prefs.get("default_model.chat") == {"tags": ["big:9b"]}
    assert service.forget_model("mid:4b") == []


def test_the_new_error_codes_are_in_the_closed_list():
    assert ERRORS["model_in_use"].status == 409
    assert ERRORS["model_in_use"].detail_keys == ("tag", "run_id")
    assert ERRORS["model_not_eligible"].detail_keys == ("tag", "purpose")
    assert ERRORS["model_delete_failed"].status == 502
    assert list(ERRORS)[-3:] == ["model_in_use", "model_not_eligible", "model_delete_failed"]
