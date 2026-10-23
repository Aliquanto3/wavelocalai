"""Préférences sur le store SQLite : survie au redémarrage, écrivain unique, dates ISO (AD-12, AD-15)."""

from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

from wavelocalai.models.facts import facts_from_ollama
from wavelocalai.models.facts_store import SqliteFactsStore
from wavelocalai.store.db import Store, db_path
from wavelocalai.store.migrate import migrate
from wavelocalai.store.preferences import SqlitePreferenceStore
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_a_preference_survives_closing_and_reopening_the_store(tmp_path):
    path = db_path(tmp_path)
    migrate(path)
    store = Store.open(path)
    prefs = SqlitePreferenceStore(lambda: store)
    prefs.put("default_model.chat", {"tags": ["mid:4b"]})
    prefs.put("default_model.arena", {"tags": ["é:1b", "b:2b"]})
    assert prefs.get("default_model.chat") == {"tags": ["mid:4b"]}  # visible tout de suite
    store.close()  # attend les écritures en file

    reopened = Store.open(path)
    fresh = SqlitePreferenceStore(lambda: reopened)
    assert fresh.get("default_model.chat") == {"tags": ["mid:4b"]}
    assert fresh.get("default_model.arena") == {"tags": ["é:1b", "b:2b"]}
    assert fresh.get("default_model.judge") is None
    rows = reopened.read("SELECT updated_at FROM preferences")
    reopened.close()
    assert rows and all(ISO_Z.match(row["updated_at"]) for row in rows)


def test_put_replaces_and_delete_removes_across_a_restart(tmp_path):
    path = db_path(tmp_path)
    migrate(path)
    store = Store.open(path)
    prefs = SqlitePreferenceStore(lambda: store)
    prefs.put("k", {"tags": ["a"]})
    prefs.put("k", {"tags": ["b"]})
    prefs.put("gone", {"tags": ["x"]})
    prefs.delete("gone")
    assert prefs.get("gone") is None
    store.close()

    reopened = Store.open(path)
    fresh = SqlitePreferenceStore(lambda: reopened)
    assert fresh.get("k") == {"tags": ["b"]} and fresh.get("gone") is None
    assert json.loads(reopened.read("SELECT value FROM preferences WHERE key='k'")[0][0]) == {
        "tags": ["b"]
    }
    reopened.close()


def test_without_a_store_preferences_live_in_memory_only():
    prefs = SqlitePreferenceStore(lambda: None)
    assert prefs.get("k") is None
    prefs.put("k", [1, 2])
    assert prefs.get("k") == [1, 2]
    prefs.delete("k")
    assert prefs.get("k") is None


def test_the_stored_value_is_a_copy():
    prefs = SqlitePreferenceStore(lambda: None)
    value = {"tags": ["a"]}
    prefs.put("k", value)
    value["tags"].append("b")
    prefs.get("k")["tags"].append("c")
    assert prefs.get("k") == {"tags": ["a"]}


def test_create_app_uses_the_persisted_preference_after_a_restart(tmp_path):
    settings = make_settings(tmp_path)
    base = f"http://127.0.0.1:{TEST_PORT}"
    path = db_path(settings.data_dir)
    migrate(path)
    seed = Store.open(path)
    facts = SqliteFactsStore(lambda: seed)
    for tag, digest in [("small:1b", "d1"), ("mid:4b", "d2")]:
        item = {"model": tag, "digest": digest, "size": 2 * 1024**3}
        facts.put(facts_from_ollama(item, {"capabilities": ["completion", "tools"]}))
    seed.close()

    app = create_app(settings)
    with TestClient(app, base_url=base) as client:  # Ollama injoignable : liste de `model_facts`
        before = client.get("/api/models/defaults?purpose=chat").json()
        assert before["source"] == "rule"
        SqlitePreferenceStore(lambda: app.state.store).put(
            "default_model.chat", {"tags": ["mid:4b"]}
        )
    # Arrêt de l'app : le store se ferme et vide la file d'écriture.

    with TestClient(create_app(settings), base_url=base) as client:
        after = client.get("/api/models/defaults?purpose=chat").json()
        other = client.get("/api/models/defaults?purpose=judge").json()
    assert after["tags"] == ["mid:4b"] and after["source"] == "preference"
    assert other["source"] == "rule"


def test_the_app_never_writes_the_toml(tmp_path):
    toml = tmp_path / "wavelocalai.toml"
    toml.write_text("[server]\nport = 8502\n", encoding="utf-8")
    before = toml.read_bytes()
    prefs = SqlitePreferenceStore(lambda: None)
    prefs.put("default_model.chat", {"tags": ["a"]})
    assert toml.read_bytes() == before
