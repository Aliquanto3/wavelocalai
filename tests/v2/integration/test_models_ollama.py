"""Registre contre le vrai Ollama du poste (marqueur `integration`, aucun cloud, aucun run)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from wavelocalai.config import load_settings
from wavelocalai.hardware.memory import MemoryAdvisor
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT

pytestmark = pytest.mark.integration


@pytest.fixture
def real_settings(tmp_path):
    # Hôte par défaut du `.toml` versionné (127.0.0.1) ; ni `.env` ni clé cloud.
    return load_settings(
        env_file=tmp_path / "absent.env",
        environ={},
        overrides={"data": {"dir": tmp_path / "data"}},
    )


async def test_real_ollama_models_have_kind_size_and_fit(real_settings):
    registry = ModelRegistry(real_settings, advisor=MemoryAdvisor())
    await registry.refresh()
    result = await registry.list_models()
    if not result.ollama_up or not result.models:
        pytest.skip("Ollama ne répond pas ou n'a aucun modèle installé")
    assert all(m.origin == "local" and m.size_gb for m in result.models)
    assert any(m.kind == "chat" and m.fits is not None for m in result.models)
    embeddings = [m for m in result.models if m.kind == "embedding"]
    assert all("embed" in m.tag.lower() or m.fits is not None for m in embeddings)
    chat = next(m for m in result.models if m.kind == "chat")
    assert registry.resolve(chat.tag).tag == chat.tag


def test_real_route_is_fast_once_cached(real_settings):
    with TestClient(create_app(real_settings), base_url=f"http://127.0.0.1:{TEST_PORT}") as client:
        first = client.get("/api/models").json()
        if not first["ollama_up"]:
            time.sleep(1.5)  # le premier rafraîchissement lit les détails de chaque modèle
            first = client.get("/api/models").json()
        started = time.perf_counter()
        second = client.get("/api/models")
        assert time.perf_counter() - started < 0.3
        assert second.status_code == 200
