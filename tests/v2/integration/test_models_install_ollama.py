"""Catalogue installable contre le vrai Ollama du poste (marqueur `integration`), en lecture seule.

Aucun téléchargement : le transport vers Ollama refuse `/api/pull`, et ce test ne lance pas
d'installation. Seul `GET /api/models/catalog` est lu, avec le vrai catalogue du dépôt et la vraie
mémoire du poste.
"""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from wavelocalai.config import load_settings
from wavelocalai.models.classify import base_tag
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT

pytestmark = pytest.mark.integration


def test_the_real_catalog_leaves_out_what_is_installed_and_never_asks_for_a_pull(tmp_path):
    seen: list[str] = []

    def forward(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        assert request.url.path != "/api/pull", "un test ne télécharge jamais un modèle"
        with httpx.Client(trust_env=False, timeout=5.0) as real:
            return real.send(real.build_request(request.method, str(request.url)))

    settings = load_settings(
        env_file=tmp_path / "absent.env",
        environ={},
        overrides={"data": {"dir": tmp_path / "data"}},
    )
    app = create_app(settings, ollama_transport=httpx.MockTransport(forward))
    with TestClient(app, base_url=f"http://127.0.0.1:{TEST_PORT}") as client:
        models = client.get("/api/models").json()
        if not models["ollama_up"]:
            time.sleep(1.5)
            models = client.get("/api/models").json()
        if not models["models"]:
            pytest.skip("Ollama ne répond pas ou n'a aucun modèle")
        started = time.perf_counter()
        response = client.get("/api/models/catalog")
        assert time.perf_counter() - started < 1.0
        body = response.json()
    assert response.status_code == 200, body
    installed = {base_tag(m["tag"]) for m in models["models"]}
    assert body["models"], "le catalogue du dépôt n'est pas vide"
    assert not installed & {base_tag(m["tag"]) for m in body["models"]}
    for entry in body["models"]:
        assert entry["tag"] and entry["name"]
        assert entry["fits"] is None or isinstance(entry["fits"], bool)
        assert (entry["fits"] is False) == (entry["short_gb"] is not None)
    assert body["free_gb"] is not None and body["free_gb"] > 0
    assert "/api/pull" not in seen
