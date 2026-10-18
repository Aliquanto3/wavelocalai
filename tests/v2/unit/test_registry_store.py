"""Registre branché sur le store : `model_facts` survit au redémarrage, débit lu dans `runs`."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from wavelocalai.models.facts import facts_from_ollama
from wavelocalai.models.facts_store import SqliteFactsStore
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.models.run_stats import SqliteRunStats
from wavelocalai.store.db import Store, db_path, utc_now_iso
from wavelocalai.store.migrate import migrate
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from .test_registry import FakeOllama, _fixture_source

NOW = "2026-10-18T12:00:00.000Z"


async def test_model_facts_survive_a_restart_with_ollama_down(tmp_path):
    path = db_path(tmp_path)
    store = Store.open(path)
    registry = ModelRegistry(
        make_settings(tmp_path),
        source=_fixture_source(),
        facts=SqliteFactsStore(lambda: store),
    )
    await registry.refresh()
    store.close()  # attend les écritures en file

    reopened = Store.open(path)  # même base, Ollama injoignable
    down = FakeOllama([])
    down.down = True
    restarted = ModelRegistry(
        make_settings(tmp_path), source=down, facts=SqliteFactsStore(lambda: reopened)
    )
    result = await restarted.list_models()
    reopened.close()

    assert result.ollama_up is False
    tags = {m.tag: m for m in result.models}
    assert {"qwen3.5:2b", "nomic-embed-text:latest", "moe:30b"} <= set(tags)
    assert (
        tags["qwen3.5:2b"].reasoning is True and tags["nomic-embed-text:latest"].kind == "embedding"
    )
    assert tags["moe:30b"].params_total_b == 30.0


def test_facts_roundtrip_and_digest_keying(tmp_path):
    store = Store.open(db_path(tmp_path))
    facts_store = SqliteFactsStore(lambda: store)
    old = facts_from_ollama(
        {"model": "m", "digest": "d1", "size": 5}, {"capabilities": ["tools"]}, now=1.0
    )
    new = facts_from_ollama({"model": "m", "digest": "d2"}, None, now=2.0)
    facts_store.put(old)
    facts_store.put(new)
    store.close()
    again = Store.open(db_path(tmp_path))
    fresh = SqliteFactsStore(lambda: again)  # sans mémoire des écritures
    assert fresh.get("m", "d1") == old and fresh.get("m", "d2") == new
    assert fresh.get("m", "d3") is None
    assert fresh.latest_per_tag() == [new]
    again.close()


def _insert_run(conn: sqlite3.Connection, run_id: str, **columns):
    values = {
        "id": run_id, "kind": "generation", "app_session": "s", "status": "ok",
        "started_at": NOW, "model": "qwen3.5:2b", "tps": 10.0, "tps_source": "ollama_eval",
    }  # fmt: skip
    values.update(columns)
    conn.execute(
        f"INSERT INTO runs ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",  # noqa: S608
        tuple(values.values()),
    )


async def test_throughput_is_the_median_of_ok_ollama_eval_leaves_in_runs(tmp_path):
    store = Store.open(db_path(tmp_path))

    def fill(conn: sqlite3.Connection) -> None:
        conn.execute("INSERT INTO app_sessions VALUES ('s', ?, 'startup')", (utc_now_iso(),))
        for index, tps in enumerate((10.0, 40.0, 20.0)):
            _insert_run(conn, f"ok{index}", tps=tps)
        _insert_run(conn, "failed", status="error", tps=900.0)  # pas `ok`
        _insert_run(conn, "wall", tps=900.0, tps_source="wallclock")  # pas Ollama
        _insert_run(conn, "chat", kind="chat", tps=900.0)  # racine, pas une feuille
        _insert_run(conn, "zero", tps=None)
        _insert_run(conn, "other", model="moe:30b", tps=7.0)

    await store.awrite(fill)
    assert SqliteRunStats(lambda: store).medians() == {"qwen3.5:2b": 20.0, "moe:30b": 7.0}
    registry = ModelRegistry(
        make_settings(tmp_path), source=_fixture_source(), run_stats=SqliteRunStats(lambda: store)
    )
    await registry.refresh()
    by_tag = {m.tag: m for m in (await registry.list_models()).models}
    store.close()
    assert by_tag["qwen3.5:2b"].throughput_tps == 20.0
    assert by_tag["bge-reranker-base"].throughput_tps is None  # aucun run


def test_without_a_store_stats_are_empty():
    assert SqliteRunStats(lambda: None).medians() == {}


def test_create_app_serves_the_persisted_list_with_ollama_down(tmp_path):
    settings = make_settings(tmp_path)
    path = db_path(settings.data_dir)
    migrate(path)
    store = Store.open(path)
    facts_store = SqliteFactsStore(lambda: store)
    for item, show in [
        ({"model": "qwen3.5:2b", "digest": "d1", "size": 2 * 1024**3}, {"capabilities": ["tools"]}),
    ]:
        facts_store.put(facts_from_ollama(item, show))
    store.close()

    with TestClient(create_app(settings), base_url=f"http://127.0.0.1:{TEST_PORT}") as client:
        body = client.get("/api/models").json()
    assert body["ollama_up"] is False
    assert [m["tag"] for m in body["models"]] == ["qwen3.5:2b"]
