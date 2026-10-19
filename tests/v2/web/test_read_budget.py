"""Budget de lecture (AD-15) : toute route `GET` sans paramètre de chemin, hors SSE, répond en
moins de 300 ms Ollama injoignable. La liste vient de l'app : une route ajoutée par une story
suivante entre dans le test d'elle-même, qu'elle soit dans le schéma OpenAPI ou non, dans un
routeur inclus ou non (C2), et les `Mount` de fichiers sont échantillonnés (C3)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.sse import EventSourceResponse
from fastapi.testclient import TestClient
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from wavelocalai.config import Settings
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, closed_port, make_settings
from .route_discovery import discover, read_paths, static_samples

BUDGET_S = 0.3


def discover_read_routes(app: FastAPI) -> list[str]:
    """Chemins des routes `GET` sans paramètre de chemin, hors flux SSE (voir `route_discovery`)."""
    return read_paths(app)


def static_paths(app: FastAPI) -> list[str]:
    """Échantillon de fichiers de chaque `Mount` de fichiers (C3)."""
    _, mounts = discover(app)
    return sorted({path for mount in mounts for path in static_samples(mount)})


# Découverte à la collecte : aucun accès disque, aucun réseau (`Settings` par défaut).
_APP = create_app(Settings(env_file=Path("absent.env")))
ROUTES = discover_read_routes(_APP)
STATIC_ROUTES = static_paths(_APP)


def test_the_health_route_is_discovered():
    assert "/api/health" in ROUTES


def test_hidden_routes_and_static_mounts_are_discovered():
    """Routes hors schéma de l'app réelle (`/`, texte français) et fichiers du `Mount` statique."""
    assert "/" in ROUTES and "/static/i18n/fr.json" in ROUTES
    assert any(path.endswith(".js") for path in STATIC_ROUTES), STATIC_ROUTES
    assert any(path.endswith(".css") for path in STATIC_ROUTES), STATIC_ROUTES


def test_discovery_matches_the_openapi_schema():
    """Recoupement avec l'API publique : toute route documentée est trouvée par la découverte
    (si une montée de FastAPI change la structure des routeurs inclus, ce test rougit)."""
    routes, _ = discover(_APP)
    found = {(r.path, method) for r in routes for method in r.methods}
    for path, operations in _APP.openapi()["paths"].items():
        for method in operations:
            assert (path, method.upper()) in found, f"{method.upper()} {path} non découverte"


# Essais, chacun sur une app neuve : un poste chargé ne tient pas le budget à tout coup.
ATTEMPTS = 3


def _first_request(settings: Settings, path: str) -> tuple[float, int, str]:
    """Durée de la première requête d'une app neuve (cache de sonde et de registre vides)."""
    client = TestClient(create_app(settings), base_url=f"http://127.0.0.1:{TEST_PORT}")
    started = time.perf_counter()
    response = client.get(path)
    return time.perf_counter() - started, response.status_code, response.text


@pytest.mark.parametrize("path", [*ROUTES, *STATIC_ROUTES])
def test_read_route_answers_under_300_ms_with_ollama_down(tmp_path, path):
    """Le budget (300 ms) reste celui d'AD-15 : on retient le meilleur de trois premières requêtes,
    chacune sur une app neuve. Un pic de charge du poste (CI Windows) gonfle un essai ; une route
    réellement lente dépasse le budget aux trois."""
    # Ollama injoignable : port fermé, aucune connexion réelle hors de la boucle locale.
    settings = make_settings(tmp_path, ollama={"host": f"http://127.0.0.1:{closed_port()}"})
    # Mise en température hors mesure (imports, schémas) sur une autre app.
    TestClient(create_app(settings), base_url=f"http://127.0.0.1:{TEST_PORT}").get(path)

    timings = [_first_request(settings, path) for _ in range(ATTEMPTS)]
    for _, status, text in timings:
        assert status < 500, text
    elapsed = min(seconds for seconds, _, _ in timings)
    detail = ", ".join(f"{seconds * 1000:.0f}" for seconds, _, _ in timings)
    assert elapsed < BUDGET_S, f"{path} : {detail} ms (budget {BUDGET_S * 1000:.0f} ms)"


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


def test_discovery_includes_hidden_routes_of_an_included_router(tmp_path):
    """C2 : un `GET` en `include_in_schema=False` posé par un routeur inclus (avec préfixe)."""
    app = create_app(make_settings(tmp_path))
    router = APIRouter(prefix="/api")

    @router.get("/cachee", include_in_schema=False)
    async def hidden():
        return {}

    @router.get("/flux-cache", include_in_schema=False, response_class=EventSourceResponse)
    async def hidden_stream():
        yield {"x": 1}

    app.include_router(router)
    app.include_router(router, prefix="/v2")  # préfixe ajouté à l'inclusion
    found = discover_read_routes(app)
    assert "/api/cachee" in found and "/v2/api/cachee" in found
    assert "/api/flux-cache" not in found and "/v2/api/flux-cache" not in found


def test_discovery_measures_the_files_of_a_mount(tmp_path):
    """C3 : un `Mount` de fichiers est découvert, gros fichiers et une extension chacun."""
    files = tmp_path / "files"
    files.mkdir()
    (files / "grand.js").write_text("x" * 100, encoding="utf-8")
    (files / "petit.css").write_text("x", encoding="utf-8")
    (files / "autre.svg").write_text("xx", encoding="utf-8")
    app = create_app(make_settings(tmp_path))
    app.mount("/fichiers", StaticFiles(directory=files), name="fichiers")
    assert any(isinstance(route, Mount) and route.path == "/fichiers" for route in app.routes)
    found = static_paths(app)
    assert {"/fichiers/grand.js", "/fichiers/petit.css", "/fichiers/autre.svg"} <= set(found)


def test_discovery_fails_loudly_on_a_route_it_cannot_cover(tmp_path):
    """Revue : une route WebSocket n'est ni mesurée ni contrôlée : la découverte rougit."""
    app = create_app(make_settings(tmp_path))

    @app.websocket("/api/ws")
    async def ws(websocket):  # pragma: no cover - jamais servie
        await websocket.close()

    with pytest.raises(AssertionError, match="route non couverte"):
        discover(app)
