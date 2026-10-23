"""Toute erreur, prévue ou non, suit `{code, message, action, detail}` en français (AD-18)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wavelocalai.errors import AppError
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings

FAKE_KEY = "sk-proj-AbCdEf0123456789XyZ"
PLAIN_KEY = "plainkey-9876543210"  # clé configurée sans préfixe reconnaissable


@pytest.fixture
def client(tmp_path):
    settings = make_settings(tmp_path, environ={"MISTRAL_API_KEY": PLAIN_KEY})
    app = create_app(settings)

    @app.get("/test/ollama-down")
    async def ollama_down():
        raise AppError("ollama_down", f"connexion refusée (clé {FAKE_KEY})")

    @app.get("/test/boom")
    async def boom():
        raise RuntimeError(f"échec imprévu avec {FAKE_KEY} et {PLAIN_KEY}")

    @app.get("/test/typed")
    async def typed(count: int):
        return {"count": count}

    return TestClient(app, base_url=f"http://127.0.0.1:{TEST_PORT}", raise_server_exceptions=False)


def _check_envelope(body: dict, code: str):
    assert set(body) == {"code", "message", "action", "detail"}
    assert body["code"] == code
    assert body["message"] and body["action"]
    assert isinstance(body["detail"], dict) and "technical" in body["detail"]


def test_known_error_uses_the_envelope_and_masks_keys(client):
    response = client.get("/test/ollama-down")
    assert response.status_code == 503
    _check_envelope(response.json(), "ollama_down")
    assert FAKE_KEY not in response.text and "sk-proj" not in response.text
    assert "***" in response.json()["detail"]["technical"]


def test_unexpected_exception_becomes_internal_with_masked_detail(client):
    response = client.get("/test/boom")
    assert response.status_code == 500
    body = response.json()
    _check_envelope(body, "internal")
    assert "RuntimeError" in body["detail"]["technical"]
    assert (
        FAKE_KEY not in response.text and PLAIN_KEY not in response.text
    )  # y compris la clé configurée


def test_unknown_route_and_validation_errors_use_the_envelope(client):
    missing = client.get("/api/nexiste-pas")
    assert missing.status_code == 404
    _check_envelope(missing.json(), "not_found")

    invalid = client.get("/test/typed", params={"count": "abc"})
    assert invalid.status_code == 422
    _check_envelope(invalid.json(), "invalid_request")
    assert "count" in invalid.json()["detail"]["technical"]


def test_unexpected_exception_is_logged_without_the_key(client, caplog):
    with caplog.at_level("ERROR", logger="wavelocalai.web"):
        client.get("/test/boom")
    assert any("Erreur non prévue" in r.message for r in caplog.records)
