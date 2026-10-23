"""Sécurité locale (AD-19) : Host, Origin d'écriture, aucun en-tête CORS."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings

ENVELOPE_KEYS = {"code", "message", "action", "detail"}


@pytest.fixture
def client(tmp_path):
    app = create_app(make_settings(tmp_path))
    return TestClient(app, base_url=f"http://127.0.0.1:{TEST_PORT}")


@pytest.mark.parametrize(
    "host", [f"127.0.0.1:{TEST_PORT}", f"localhost:{TEST_PORT}", f"LOCALHOST:{TEST_PORT}"]
)
def test_local_hosts_are_accepted(client, host):
    assert client.get("/api/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:8502",
        "127.0.0.1",
        "127.0.0.1:9999",
        "0.0.0.0:8502",
        "[::1]:8502",
        "",
    ],
)
def test_foreign_hosts_are_refused_with_the_envelope(client, host):
    response = client.get("/api/health", headers={"Host": host})
    assert response.status_code == 403
    body = response.json()
    assert set(body) == ENVELOPE_KEYS and body["code"] == "forbidden_host"
    assert body["detail"]["host"] == host


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_writes_with_a_foreign_origin_are_refused(client, method):
    response = getattr(client, method)("/api/health", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    body = response.json()
    assert set(body) == ENVELOPE_KEYS and body["code"] == "forbidden_origin"
    assert body["detail"]["origin"] == "https://evil.example"


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        f"https://127.0.0.1:{TEST_PORT}",
        f"http://localhost:{TEST_PORT + 1}",
        f"http://localhost:{TEST_PORT}.evil.example",
    ],
)
def test_lookalike_origins_are_refused(client, origin):
    assert client.post("/api/health", headers={"Origin": origin}).status_code == 403


@pytest.mark.parametrize("origin", [None, f"http://127.0.0.1:{TEST_PORT}"])
def test_same_origin_or_no_origin_writes_pass_the_guard(client, origin):
    headers = {"Origin": origin} if origin else {}
    # La route n'accepte pas POST : le garde a laissé passer, c'est la route qui répond 405.
    response = client.post("/api/health", headers=headers)
    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


def test_reads_with_a_foreign_origin_pass_but_never_get_cors_headers(client):
    for headers in ({"Origin": "https://evil.example"}, {}):
        response = client.get("/api/health", headers=headers)
        assert response.status_code == 200
        assert not [h for h in response.headers if h.lower().startswith("access-control-")]


def test_preflight_gets_no_cors_headers(client):
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 405
    assert not [h for h in response.headers if h.lower().startswith("access-control-")]


def test_refusals_carry_no_cors_headers_either(client):
    response = client.get(
        "/api/health", headers={"Host": "evil.example", "Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert not [h for h in response.headers if h.lower().startswith("access-control-")]
