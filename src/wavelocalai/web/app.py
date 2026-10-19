"""Création de l'application FastAPI : télémétrie coupée, sécurité locale, erreurs uniques."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator, Callable, Mapping

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from ollama import AsyncClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from wavelocalai.agents.service import AgentService
from wavelocalai.agents.tools import ToolRegistry
from wavelocalai.config import Settings, get_version
from wavelocalai.errors import ERRORS, AppError, build_envelope
from wavelocalai.evaluation.judge import Judge
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.hardware.memory import MemoryAdvisor, MemoryReading, read_memory
from wavelocalai.inference.arena import ArenaService
from wavelocalai.inference.chat import ChatService
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.memory_guard import MemoryGuard
from wavelocalai.models.cloud import HttpClientFactory
from wavelocalai.models.defaults import ModelDefaults
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.facts_store import SqliteFactsStore
from wavelocalai.models.fake import fake_embedders, fake_models
from wavelocalai.models.ollama import close_client, make_client
from wavelocalai.models.ollama_probe import OllamaProbe
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.models.run_stats import SqliteRunStats
from wavelocalai.rag.index import select_index
from wavelocalai.rag.ingest import IngestService
from wavelocalai.rag.manage import RagBaseService
from wavelocalai.rag.query import RagService
from wavelocalai.rag.rerank import RerankerService, cache_dir
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.system_bus import SAMPLE_INTERVAL_S, SystemFeed
from wavelocalai.store.datadir import ensure_data_dir
from wavelocalai.store.db import Store, db_path
from wavelocalai.store.preferences import PreferenceStore, SqlitePreferenceStore
from wavelocalai.telemetry import disable_telemetry
from wavelocalai.web import (
    routes_agents,
    routes_arena,
    routes_chat,
    routes_conversations,
    routes_health,
    routes_models,
    routes_rag,
    routes_rag_base,
    routes_runs,
    routes_system,
    routes_test,
)
from wavelocalai.web.routes_static import mount_shell
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
    app.state.probe.start()  # première sonde avant toute requête (AD-15)
    hub = RunHub(store)
    await hub.start()
    app.state.hub = hub
    # Client Ollama partagé (AD-14) ; l'app ne ferme que celui qu'elle a créé.
    owned_client: AsyncClient | None = None
    client: AsyncClient | None = app.state.ollama_client
    if client is None:
        client = owned_client = make_client(settings.ollama.host)
        app.state.ollama_client = client
    factory = ModelFactory(
        client, app.state.models, app.state.embedders, settings, app.state.cloud_http
    )
    guard: MemoryGuard = app.state.memory_guard
    app.state.chat = ChatService(
        hub,
        app.state.registry,
        factory,
        app.state.local_slot,
        settings,
        meter=app.state.meter,
        bus=app.state.system_feed,
        guard=guard,
    )
    app.state.arena = ArenaService(
        hub,
        app.state.registry,
        factory,
        app.state.local_slot,
        settings,
        meter=app.state.meter,
        bus=app.state.system_feed,
        guard=guard,
        defaults=app.state.defaults,
        judge=Judge(
            hub,
            app.state.local_slot,
            settings,
            meter=app.state.meter,
            bus=app.state.system_feed,
            guard=guard,
        ),
    )
    app.state.agents = AgentService(
        hub,
        app.state.registry,
        factory,
        app.state.local_slot,
        settings,
        app.state.agent_tools,
        meter=app.state.meter,
        bus=app.state.system_feed,
        guard=guard,
    )
    index = select_index(store.vec_available)  # le même pour l'import et la question (repli numpy)
    app.state.rag = RagService(
        hub,
        app.state.registry,
        factory,
        app.state.local_slot,
        settings,
        index,
        meter=app.state.meter,
        bus=app.state.system_feed,
        preferences=app.state.preferences,
        guard=guard,
        reranker=app.state.reranker,
    )
    app.state.ingest = IngestService(
        hub,
        app.state.registry,
        factory,
        app.state.local_slot,
        settings,
        index,
        meter=app.state.meter,
        bus=app.state.system_feed,
        fallback_model=next(iter(app.state.embedders), None),  # le `fake`, `testing` seulement
        preferences=app.state.preferences,
    )
    app.state.rag_base = RagBaseService(
        hub, app.state.registry, settings, index, app.state.preferences, app.state.reranker
    )
    await app.state.ingest.recover()  # documents restés `indexing` après un arrêt brutal
    await app.state.registry.start()  # premier rafraîchissement des modèles, sans l'attendre
    # Fiche machine préchauffée hors de la boucle (NVML est lent) : la première lecture est prête.
    warmup = asyncio.create_task(asyncio.to_thread(cached_fiche))
    # CodeCarbon détecte le matériel au premier tracker (4 à 10 s) : payé ici, hors de la place
    # Ollama de la première réponse locale (un tracker jeté, sous le verrou du compteur, AD-11).
    meter_warmup = asyncio.create_task(app.state.meter.warm_up())
    try:
        yield
    finally:
        warmup.cancel()
        meter_warmup.cancel()
        await stop_streams(app)  # déjà fait par le serveur réel ; ici pour les autres hôtes ASGI
        await app.state.registry.stop()
        await app.state.probe.aclose()
        app.state.chat = None
        app.state.agents = None
        app.state.ingest = None
        app.state.rag = None
        app.state.rag_base = None
        app.state.arena = None
        if owned_client is not None:
            await close_client(owned_client)
            app.state.ollama_client = None
        if owned is not None:
            owned.close()


def create_app(
    settings: Settings,
    probe: OllamaProbe | None = None,
    store: Store | None = None,
    registry: ModelRegistry | None = None,
    preferences: PreferenceStore | None = None,
    ollama_client: AsyncClient | None = None,
    cloud_http: Mapping[str, HttpClientFactory] | None = None,
    meter: LocalMeter | None = None,
    ollama_transport: httpx.AsyncBaseTransport | None = None,
    memory_reader: Callable[[], MemoryReading] | None = None,
) -> FastAPI:
    """Crée l'app ; `disable_telemetry` s'exécute avant (AD-19, AD-21).

    `store` : base déjà ouverte par le lanceur (qui la ferme) ; sinon l'app ouvre la sienne au
    démarrage de son cycle de vie. `registry` : registre des modèles, branché sur la base du store
    (faits d'Ollama et débit mesuré) par défaut. `ollama_client` : client Ollama partagé des
    générations (celui du lanceur ; sinon l'app crée le sien au démarrage de son cycle de vie).
    `cloud_http` : fabriques de client HTTP des SDK cloud par fournisseur (tests : faux transport).
    `meter` : compteur CodeCarbon des réponses locales (AD-11), construit sur le pays et le PUE de
    `Settings` par défaut. `ollama_transport` : transport HTTP des lectures d'`/api/ps` et des
    déchargements (tests : faux Ollama) ; `memory_reader` : lecture de la mémoire du poste du
    garde-fou et de la route de déchargement (tests : mémoire simulée).
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
    app.state.embedders = fake_embedders(settings)  # idem pour le port `Embedder`
    app.state.tasks = set()  # tâches de runs en cours (références fortes)
    app.state.ollama_client = ollama_client
    app.state.cloud_http = dict(cloud_http or {})
    app.state.local_slot = LocalSlot()  # sémaphore « Ollama local » à 1, pris par appel (AD-14)
    app.state.meter = meter or LocalMeter.from_settings(settings.carbon)
    app.state.chat = None  # service de chat, créé au démarrage du cycle de vie
    app.state.agents = None  # service de l'agent seul (story 6.1), idem
    app.state.agent_tools = ToolRegistry()  # outils des agents : ceux de la v1 arrivent en 6.2
    app.state.ingest = None  # service d'ingestion des documents, idem
    app.state.rag = None  # service de questions aux documents, idem
    app.state.rag_base = None  # service de gestion de la base (supprimer, vider, régler), idem
    app.state.arena = None  # service de l'Arène, idem
    # Reranker local (story 4.7, AD-17) : ne charge ni n'importe rien tant qu'aucune question ne le
    # demande ; jamais de téléchargement.
    app.state.reranker = RerankerService(
        settings.rag.reranker_model, cache_dir(settings.data_dir), env_file=settings.env_file
    )
    app.state.registry = registry or ModelRegistry(
        settings,
        extra_refs={
            tag: model.ref
            for tag, model in [*app.state.models.items(), *app.state.embedders.items()]
        },
        facts=SqliteFactsStore(lambda: app.state.store),
        run_stats=SqliteRunStats(lambda: app.state.store),
        advisor=MemoryAdvisor(memory_reader or read_memory),
    )
    # Garde-fou mémoire des inférences locales et déchargement des modèles (story 4.8).
    app.state.ollama_transport = ollama_transport
    app.state.memory_reader = memory_reader or read_memory
    app.state.memory_guard = MemoryGuard(
        app.state.registry,
        settings.ollama.host,
        reader=app.state.memory_reader,
        transport=ollama_transport,
    )
    # Préférences de l'UI (table `preferences`, 0003) : sur la base du store, comme `model_facts`.
    app.state.preferences = preferences or SqlitePreferenceStore(lambda: app.state.store)
    app.state.defaults = ModelDefaults(app.state.registry, app.state.preferences)
    app.state.instance_id = uuid.uuid4().hex  # nouveau à chaque démarrage
    app.state.probe = probe or OllamaProbe(
        settings.ollama.host,
        timeout_s=settings.ollama.probe_timeout_s,
        cache_s=settings.ollama.probe_cache_s,
    )
    # Le flux publie l'état d'Ollama toutes les 2 s : sa sonde garde l'état moins longtemps que
    # l'intervalle, pour qu'un Ollama relancé apparaisse en moins de 3 s (story 1.9). Les routes de
    # lecture gardent le cache de 5 s (AD-15). Une sonde injectée (tests) sert aux deux.
    stream_probe = probe or OllamaProbe(
        settings.ollama.host,
        timeout_s=settings.ollama.probe_timeout_s,
        cache_s=min(settings.ollama.probe_cache_s, SAMPLE_INTERVAL_S / 2),
    )
    app.state.system_sampler = SystemSampler(
        stream_probe, settings.ollama.host, lambda: app.state.hub, ps_transport=ollama_transport
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
    app.include_router(routes_chat.router)
    app.include_router(routes_agents.router)
    app.include_router(routes_arena.router)
    app.include_router(routes_conversations.router)
    app.include_router(routes_rag.router)
    app.include_router(routes_rag_base.router)
    app.include_router(routes_system.router)
    if settings.testing:  # commande de test : jamais hors `WAVELOCALAI_TESTING`
        app.include_router(routes_test.router)
    app.include_router(routes_models.router)
    mount_shell(app)
    return app
