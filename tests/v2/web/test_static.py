"""Service de la coquille : `GET /` et `/static/` (story 1.8), avec la sécurité locale de 1.2."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wavelocalai.web.app import create_app
from wavelocalai.web.routes_static import STATIC_DIR

from ..conftest import TEST_PORT, make_settings

BASE = f"http://127.0.0.1:{TEST_PORT}"


@pytest.fixture
def client(tmp_path) -> TestClient:
    return TestClient(create_app(make_settings(tmp_path)), base_url=BASE)


def test_root_serves_the_shell_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<html lang="fr">' in response.text and 'id="main"' in response.text


def test_page_and_files_forbid_any_resource_outside_the_origin(client):
    for path in ("/", "/static/main.js", "/static/tokens.css"):
        headers = client.get(path).headers
        policy = headers["content-security-policy"]
        assert "default-src 'self'" in policy and "script-src 'self'" in policy
        assert "connect-src 'self'" in policy and "frame-ancestors 'none'" in policy
        assert headers["cache-control"] == "no-cache"
        assert headers["x-content-type-options"] == "nosniff"
        assert not any(name.lower().startswith("access-control-") for name in headers)


@pytest.mark.parametrize(
    ("path", "media_type"),
    [
        ("/static/main.js", "text/javascript"),
        ("/static/core/router.js", "text/javascript"),
        ("/static/tokens.css", "text/css"),
        ("/static/icons.svg", "image/svg+xml"),
        ("/static/i18n/fr/shell.json", "application/json"),
        ("/static/fonts/InterVariable.woff2", "font/woff2"),
    ],
)
def test_files_have_the_media_type_modules_need(client, path, media_type):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == media_type


def test_revalidation_answers_304_with_the_same_headers(client):
    first = client.get("/static/base.css")
    second = client.get("/static/base.css", headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 304
    assert second.headers["cache-control"] == "no-cache"


def test_every_shipped_file_is_served(client):
    files = [p for p in STATIC_DIR.rglob("*") if p.is_file()]
    assert files
    for path in files:
        url = "/static/" + path.relative_to(STATIC_DIR).as_posix()
        assert client.get(url).status_code == 200, url


def test_unknown_static_file_uses_the_error_envelope(client):
    response = client.get("/static/absent.js")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


@pytest.mark.parametrize(
    "path", ["/static/../app.py", "/static/%2e%2e/app.py", "/static/..%5capp.py"]
)
def test_path_traversal_never_leaves_the_static_folder(client, path):
    response = client.get(path)
    assert response.status_code in (400, 404)
    assert "create_app" not in response.text


def test_shell_obeys_the_local_security_rules(client):
    refused = client.get("/", headers={"Host": "evil.example:8502"})
    assert refused.status_code == 403 and refused.json()["code"] == "forbidden_host"
    refused = client.get("/static/main.js", headers={"Host": "evil.example:8502"})
    assert refused.status_code == 403
    assert client.post("/").status_code == 405
