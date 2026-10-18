"""Budget de lecture (AD-15) : toute route `GET` sans paramètre de chemin, hors SSE, répond en
moins de 300 ms Ollama injoignable. La liste vient de l'app : une route ajoutée par une story
suivante entre dans le test d'elle-même."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.sse import EventSourceResponse
from fastapi.testclient import TestClient
from starlette.routing import Route

from wavelocalai.config import Settings
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, closed_port, make_settings

BUDGET_S = 0.3


def discover_read_routes(app: FastAPI) -> list[str]:
    """Chemins des routes `GET` sans paramètre de chemin, hors flux SSE.

    Lus dans le schéma OpenAPI de l'app (`app.openapi()`, API publique : FastAPI range les routes
    d'un `include_router` dans des structures internes), plus les routes Starlette directes.
    """
    paths: set[str] = set()
    for path, operations in app.openapi()["paths"].items():
        get = operations.get("get")
        if get is None:
            continue
        streams = any(
            "text/event-stream" in response.get("content", {})
            for response in get.get("responses", {}).values()
        )
        if not streams:
            paths.add(path)
    for route in app.routes:  # routes hors schéma (include_in_schema=False, Starlette pur)
        if not isinstance(route, Route) or "GET" not in (route.methods or ()):
            continue
        if getattr(route, "include_in_schema", False) and isinstance(route, APIRoute):
            continue  # déjà lue dans le schéma, SSE écartés compris
        response_class = getattr(route, "response_class", None)
        response_class = getattr(response_class, "value", response_class)
        if isinstance(response_class, type) and issubclass(response_class, EventSourceResponse):
            continue
        paths.add(route.path)
    return sorted(path for path in paths if "{" not in path)


# Découverte à la collecte : aucun accès disque, aucun réseau (`Settings` par défaut).
ROUTES = discover_read_routes(create_app(Settings(env_file=Path("absent.env"))))


def test_the_health_route_is_discovered():
    assert "/api/health" in ROUTES


@pytest.mark.parametrize("path", ROUTES)
def test_read_route_answers_under_300_ms_with_ollama_down(tmp_path, path):
    # Ollama injoignable : port fermé, aucune connexion réelle hors de la boucle locale.
    settings = make_settings(tmp_path, ollama={"host": f"http://127.0.0.1:{closed_port()}"})
    app = create_app(settings)
    client = TestClient(app, base_url=f"http://127.0.0.1:{TEST_PORT}")
    # Mise en température hors mesure (imports, schémas) sur une autre app.
    TestClient(create_app(settings), base_url=f"http://127.0.0.1:{TEST_PORT}").get(path)

    started = time.perf_counter()
    response = client.get(path)  # première requête de l'app : cache de sonde vide
    elapsed = time.perf_counter() - started

    assert response.status_code < 500, response.text
    assert elapsed < BUDGET_S, f"{path} : {elapsed * 1000:.0f} ms (budget {BUDGET_S * 1000:.0f} ms)"


def test_discovery_includes_new_get_routes_and_skips_sse_and_path_params(tmp_path):
    app = create_app(make_settings(tmp_path))

    @app.get("/api/ajoutee-plus-tard")
    async def later():
        return {}

    @app.get("/api/runs/{run_id}")
    async def with_param(run_id: str):
        return {}

    @app.get("/api/flux", response_class=EventSourceResponse)
    async def stream():
        yield {"x": 1}

    found = discover_read_routes(app)
    assert "/api/ajoutee-plus-tard" in found
    assert "/api/runs/{run_id}" not in found and "/api/flux" not in found
