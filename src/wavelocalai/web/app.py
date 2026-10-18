"""Création de l'application FastAPI : télémétrie coupée, sécurité locale, erreurs uniques."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from wavelocalai.config import Settings, get_version
from wavelocalai.errors import ERRORS, AppError, build_envelope
from wavelocalai.models.fake import fake_models
from wavelocalai.models.ollama_probe import OllamaProbe
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.system_bus import SystemFeed
from wavelocalai.store.datadir import ensure_data_dir
from wavelocalai.store.db import Store, db_path
from wavelocalai.telemetry import disable_telemetry
from wavelocalai.web import routes_health, routes_runs, routes_system, routes_test
from wavelocalai.web.security import LocalOnlyMiddleware
from wavelocalai.web.system_state import SystemSampler, cached_fiche

logger = logging.getLogger("wavelocalai.web")

# Télémétrie native de FastAPI : tout à False (AD-19).
FASTAPI_TELEMETRY = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "operation_spans": False,
    "auto_configure": False,
}

_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def _error_response(
    settings: Settings, code: str, technical: str | None = None, **detail: str
) -> JSONResponse:
    envelope = build_envelope(code, technical, settings.secret_values(), **detail)
    return JSONResponse(envelope, status_code=ERRORS[code].status)


async def stop_streams(app: FastAPI) -> None:
    """Début de l'arrêt, **avant** qu'uvicorn attende la fin des connexions : les flux système se
    terminent et les runs actifs passent à `cancelled` (AD-23), ce qui clôt leurs flux d'événements.
    Sans cela, un flux ouvert retient l'arrêt indéfiniment. Idempotent : le cycle de vie le refait.
    """
    await app.state.system_feed.aclose()
    hub: RunHub | None = app.state.hub
    if hub is not None:
        await hub.stop()


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Démarrage : base migrée, hub démarré (runs orphelins `interrupted`, nouvelle `app_session`).
    Arrêt propre : les runs actifs passent à `cancelled` (AD-23)."""
    settings: Settings = app.state.settings
    owned: Store | None = None
    store: Store | None = app.state.store
    if store is None:  # lancement sans `__main__` (tests) : l'app ouvre et ferme sa base
        owned = store = Store.open(db_path(ensure_data_dir(settings.data_dir)))
        app.state.store = store
    hub = RunHub(store)
    await hub.start()
    app.state.hub = hub
    # Fiche machine préchauffée hors de la boucle (NVML est lent) : la première lecture est prête.
    warmup = asyncio.create_task(asyncio.to_thread(cached_fiche))
    try:
        yield
    finally:
        warmup.cancel()
        await stop_streams(app)  # déjà fait par le serveur réel ; ici pour les autres hôtes ASGI
        if owned is not None:
            owned.close()


def create_app(
    settings: Settings, probe: OllamaProbe | None = None, store: Store | None = None
) -> FastAPI:
    """Crée l'app ; `disable_telemetry` s'exécute avant (AD-19, AD-21).

    `store` : base déjà ouverte par le lanceur (qui la ferme) ; sinon l'app ouvre la sienne au
    démarrage de son cycle de vie.
    """
    disable_telemetry(settings.env_file)
    app = FastAPI(
        lifespan=_lifespan,
        title="wavelocalai v2",
        version=get_version(),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        telemetry=FASTAPI_TELEMETRY,  # type: ignore[arg-type]
    )
    app.state.settings = settings
    app.state.store = store
    app.state.hub = None  # créé au démarrage du cycle de vie
    app.state.models = fake_models(settings)  # le `fake` seulement si `Settings.testing` (AD-8)
    app.state.tasks = set()  # tâches de runs en cours (références fortes)
    app.state.instance_id = uuid.uuid4().hex  # nouveau à chaque démarrage
    app.state.probe = probe or OllamaProbe(
        settings.ollama.host,
        timeout_s=settings.ollama.probe_timeout_s,
        cache_s=settings.ollama.probe_cache_s,
    )
    app.state.system_sampler = SystemSampler(
        app.state.probe, settings.ollama.host, lambda: app.state.hub
    )
    app.state.system_feed = SystemFeed(app.state.system_sampler.sample)  # port SystemBus (AD-6)
    app.add_middleware(
        LocalOnlyMiddleware, port=settings.server.port, secrets=settings.secret_values()
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(settings, exc.code, exc.technical, **exc.detail)

    @app.exception_handler(routes_runs.NoContentError)
    async def _no_content(_: Request, __: routes_runs.NoContentError) -> Response:
        return Response(status_code=204)  # curseur de flux à la fin d'un run terminé (AD-6)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code)
        if code is None:
            code = "internal" if exc.status_code >= 500 else "invalid_request"
        response = _error_response(settings, code, str(exc.detail))
        response.status_code = exc.status_code
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        technical = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])} : {err['msg']}" for err in exc.errors()
        )
        return _error_response(settings, "invalid_request", technical)

    @app.exception_handler(Exception)
    async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.error("Erreur non prévue", exc_info=exc)
        return _error_response(settings, "internal", f"{type(exc).__name__}: {exc}")

    app.include_router(routes_health.router)
    app.include_router(routes_runs.router)
    app.include_router(routes_system.router)
    if settings.testing:  # commande de test : jamais hors `WAVELOCALAI_TESTING`
        app.include_router(routes_test.router)
    return app
