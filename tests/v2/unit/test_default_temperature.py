"""Créativité par défaut d'un modèle (D-12, AD-15) : lue des paramètres publiés par Ollama, sinon du
catalogue, sinon `null` ; mise en cache dans `model_facts` (migration 0004)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from wavelocalai.models.facts import (
    InMemoryFactsStore,
    ModelFacts,
    facts_from_ollama,
    parse_temperature,
)
from wavelocalai.models.facts_store import SqliteFactsStore
from wavelocalai.models.ollama_api import OllamaUnavailableError
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.store.db import Store, db_path
from wavelocalai.store.migrate import migrate

from ..conftest import make_settings
from .test_registry import FakeOllama, _listed

OLD = "2026-10-01T00:00:00.000Z"


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [
        ('stop                           "<|im_end|>"\ntemperature                    0.7', 0.7),
        ("temperature 1", 1.0),
        ("  temperature\t0.0  ", 0.0),
        ("temperature 2", 2.0),
        ("temperature 2.5", None),  # hors du curseur
        ("temperature -1", None),
        ("temperature chaud", None),
        ("temperature nan", None),
        ("top_k 40\nnum_ctx 4096", None),
        ('stop "temperature 0.9"', None),  # une ligne qui n'est pas le paramètre
        ("", None),
        (None, None),
    ],
)
def test_the_temperature_is_read_from_the_parameters_text(parameters, expected):
    assert parse_temperature(parameters) == expected


def test_facts_keep_the_parameters_and_tell_unread_from_empty():
    listed = {"model": "m:1b", "digest": "d"}
    read = facts_from_ollama(listed, {"parameters": "temperature 0.6"})
    assert read.parameters == "temperature 0.6" and read.default_temperature == 0.6
    empty = facts_from_ollama(listed, {"capabilities": []})
    assert empty.parameters == "" and empty.default_temperature is None  # lus, aucun paramètre
    unread = facts_from_ollama(listed, None)
    assert unread.parameters is None  # détails non lus : pas de cache, on réessaiera


def _catalog(tmp_path, **extra):
    entry = {"ollama_tag": "cat:1b", "type": "local", "params_tot": "1B", **extra}
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"models": {"Cat": entry}}), encoding="utf-8")
    return path


async def _models(tmp_path, source, **kwargs):
    registry = ModelRegistry(make_settings(tmp_path), source=source, **kwargs)
    await registry.refresh()
    return {m.tag: m for m in (await registry.list_models()).models}


async def test_the_registry_serves_the_ollama_temperature_then_the_catalog_then_null(tmp_path):
    source = FakeOllama(
        [_listed("a:1b", "da", 1), _listed("b:1b", "db", 1), _listed("cat:1b", "dc", 1)],
        {
            "a:1b": {"parameters": "temperature 0.7"},
            "cat:1b": {"parameters": "top_k 40"},  # Ollama n'en donne pas : le catalogue
        },
    )
    catalog = _catalog(tmp_path, default_temperature=0.4)
    models = await _models(tmp_path, source, catalog_path=catalog)
    assert models["a:1b"].default_temperature == 0.7
    assert models["b:1b"].default_temperature is None  # ni Ollama ni catalogue
    assert models["cat:1b"].default_temperature == 0.4


async def test_ollama_wins_over_the_catalog_and_bad_catalog_values_are_ignored(tmp_path):
    source = FakeOllama([_listed("cat:1b", "dc", 1)], {"cat:1b": {"parameters": "temperature 0.9"}})
    catalog = _catalog(tmp_path, default_temperature=0.1)
    assert (await _models(tmp_path, source, catalog_path=catalog))[
        "cat:1b"
    ].default_temperature == 0.9
    for bad in (5, -1, "0.5", True, None):
        silent = FakeOllama([_listed("cat:1b", "dc", 1)])
        catalog = _catalog(tmp_path, default_temperature=bad)
        models = await _models(tmp_path, silent, catalog_path=catalog)
        assert models["cat:1b"].default_temperature is None


async def test_the_versioned_catalog_needs_no_temperature_field(tmp_path):
    source = FakeOllama([_listed("granite4:350m", "dg", 0.7)])
    real = Path(__file__).resolve().parents[3] / "config" / "models_catalog.json"
    models = await _models(tmp_path, source, catalog_path=real)
    assert (
        models["granite4:350m"].in_catalog and models["granite4:350m"].default_temperature is None
    )


async def test_a_cloud_model_has_no_default_temperature(tmp_path):
    settings = make_settings(
        tmp_path, environ={"GROQ_API_KEY": "gsk_test"}, cloud={"models": {"groq": ["m"]}}
    )
    registry = ModelRegistry(settings, source=FakeOllama([]))
    await registry.refresh()
    listed = (await registry.list_models(allow_cloud=True)).models
    cloud = [m for m in listed if m.origin == "cloud"]
    assert cloud and all(m.default_temperature is None for m in cloud)


def _old_row(tag="a:1b", digest="da") -> ModelFacts:
    """Ligne d'avant la migration 0004 : détails jamais lus (`parameters` à `None`)."""
    return ModelFacts(
        tag=tag, digest=digest, size_bytes=1, family=None, parameter_size="1B",
        quantization=None, context_length=None, capabilities=(), params_total_b=1.0,
        expert_count=None, expert_used_count=None, fetched_at=OLD,
    )  # fmt: skip


async def test_a_cached_row_without_parameters_is_read_again_once(tmp_path):
    facts = InMemoryFactsStore()
    facts.put(_old_row())
    source = FakeOllama([_listed("a:1b", "da", 1)], {"a:1b": {"parameters": "temperature 0.3"}})
    registry = ModelRegistry(make_settings(tmp_path), source=source, facts=facts)
    await registry.refresh()
    assert source.show_calls == ["a:1b"]
    assert (await registry.list_models()).models[0].default_temperature == 0.3
    await registry.refresh()
    assert source.show_calls == ["a:1b"]  # relu une fois, puis servi du cache


async def test_an_old_row_is_kept_when_ollama_cannot_show_it(tmp_path):
    facts = InMemoryFactsStore()
    facts.put(_old_row())

    class NoShow(FakeOllama):
        async def show(self, tag):
            raise OllamaUnavailableError("trop lent")

    source = NoShow([_listed("a:1b", "da", 1)])
    registry = ModelRegistry(make_settings(tmp_path), source=source, facts=facts)
    await registry.refresh()
    models = (await registry.list_models()).models
    assert [m.tag for m in models] == ["a:1b"] and models[0].default_temperature is None


def test_the_parameters_survive_the_sqlite_cache(tmp_path):
    store = Store.open(db_path(tmp_path))
    facts = facts_from_ollama(
        {"model": "m", "digest": "d1"}, {"parameters": "temperature 0.8"}, now=OLD
    )
    SqliteFactsStore(lambda: store).put(facts)
    store.close()
    again = Store.open(db_path(tmp_path))
    back = SqliteFactsStore(lambda: again).get("m", "d1")
    again.close()
    assert back == facts and back.default_temperature == 0.8


def test_migration_0004_adds_the_column_and_keeps_old_rows_unread(tmp_path):
    path = tmp_path / "wavelocalai.db"
    migrate(path, target=3)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO model_facts (tag, digest, fetched_at) VALUES ('m', 'd', ?)", (OLD,)
        )
    assert migrate(path) == 4
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT parameters FROM model_facts").fetchall() == [(None,)]
