"""Routes du système : flux d'état en direct, fiche machine, CO2 de session, historique et remise à
zéro du compteur (AD-6, AD-10, AD-15).

`GET /api/system/stream` : même enveloppe que les runs (`run_id: null`), sans `id:` ni rejeu. Le
client reçoit l'état toutes les 2 s et les événements des services (`carbon_updated`) dès qu'ils
sont publiés. L'abonnement se referme dans le `finally` : une déconnexion ne laisse rien derrière
elle, et la mesure s'arrête avec le dernier client.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from wavelocalai.greenops.equivalence import car_equivalence
from wavelocalai.greenops.history import carbon_history
from wavelocalai.greenops.session import announce_carbon_updated, empty_summary, session_summary
from wavelocalai.runs.system_bus import SystemFeed
from wavelocalai.web.system_state import SystemSampler

router = APIRouter(prefix="/api")


@router.get("/system/stream", response_class=EventSourceResponse)
async def system_stream(request: Request) -> AsyncIterator[ServerSentEvent]:
    feed: SystemFeed = request.app.state.system_feed
    with feed.subscribe() as queue:
        while True:
            envelope = await queue.get()
            if envelope is None:  # arrêt du serveur
                return
            yield ServerSentEvent(data=envelope)  # ni `id:` ni `event:`


@router.get("/system/identity")
async def system_identity(request: Request) -> dict[str, Any]:
    sampler: SystemSampler = request.app.state.system_sampler
    return await sampler.identity()


@router.get("/carbon/session")
async def carbon_session(request: Request) -> dict[str, Any]:
    hub = request.app.state.hub
    store = request.app.state.store
    if hub is None or store is None or hub.app_session_id is None:
        return empty_summary()  # serveur hors de son cycle de vie : aucune session, aucun run
    return await session_summary(store, hub.app_session_id)


@router.get("/carbon/method")
async def carbon_method(request: Request) -> dict[str, Any]:
    """Panneau « Comment ces chiffres sont calculés » (story 5.1, D-38) : l'équivalence parlante du
    CO2 de la session en distance en voiture, calculée ici avec son facteur, sa source et sa date.
    `equivalence` est nul sans réglage `carbon.car_equivalence`."""
    summary = await carbon_session(request)
    setting = request.app.state.settings.carbon.car_equivalence
    return {"equivalence": car_equivalence(setting, summary["total_mg"], summary["measured_runs"])}


@router.get("/carbon/history")
async def carbon_history_route(
    request: Request, window: Literal["7d", "30d", "all"] = "7d"
) -> dict[str, Any]:
    """Une ligne par session close de la fenêtre (story 5.2, D-37) ; la session en cours n'y figure
    pas. Une fenêtre inconnue est refusée (`invalid_request`)."""
    hub = request.app.state.hub
    store = request.app.state.store
    if hub is None or store is None:
        return {"window": window, "sessions": []}
    return await carbon_history(store, hub.app_session_id, window)


@router.post("/carbon/session/reset")
async def carbon_session_reset(request: Request) -> dict[str, Any]:
    """Remet le compteur à zéro (story 5.2) : le hub ouvre une nouvelle `app_session` ; la session
    close entre dans l'historique, rien n'est effacé (AD-13). Un run actif reste compté dans la
    session où il a commencé. Publie `carbon_updated` (somme nulle) et rend la nouvelle session."""
    state = request.app.state
    hub = state.hub
    if hub is None or state.store is None or hub.app_session_id is None:
        return empty_summary()  # serveur hors de son cycle de vie : aucune session à ouvrir
    session_id = await hub.new_app_session("reset")
    return await announce_carbon_updated(state.system_feed, state.store, session_id)
