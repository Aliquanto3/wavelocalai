"""Défauts contre le vrai Ollama du poste (marqueur `integration`, aucun cloud)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from wavelocalai.config import load_settings
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT

pytestmark = pytest.mark.integration


def test_real_defaults_have_a_reason_and_are_local_chat_models(tmp_path):
    settings = load_settings(
        env_file=tmp_path / "absent.env",
        environ={},
        overrides={"data": {"dir": tmp_path / "data"}},
    )
    with TestClient(create_app(settings), base_url=f"http://127.0.0.1:{TEST_PORT}") as client:
        models = client.get("/api/models").json()
        if not models["ollama_up"]:
            time.sleep(1.5)
            models = client.get("/api/models").json()
        if not any(m["kind"] == "chat" for m in models["models"]):
            pytest.skip("Ollama ne répond pas ou n'a aucun modèle de conversation")
        chat_tags = {m["tag"] for m in models["models"] if m["kind"] == "chat"}
        for purpose in ("chat", "arena", "judge", "agent", "rag"):
            started = time.perf_counter()
            response = client.get("/api/models/defaults", params={"purpose": purpose})
            assert time.perf_counter() - started < 0.3
            body = response.json()
            assert response.status_code == 200, body
            assert body["reason"] and set(body["tags"]) <= chat_tags
