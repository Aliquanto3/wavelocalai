"""Routes du système : flux d'état en direct, fiche machine, CO2 de session (AD-6, AD-10, AD-15).

`GET /api/system/stream` : même enveloppe que les runs (`run_id: null`), sans `id:` ni rejeu. Le
client reçoit l'état toutes les 2 s et les événements des services (`carbon_updated`) dès qu'ils
sont publiés. L'abonnement se referme dans le `finally` : une déconnexion ne laisse rien derrière
elle, et la mesure s'arrête avec le dernier client.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from wavelocalai.greenops.equivalence import car_equivalence
from wavelocalai.greenops.session import empty_summary, session_summary
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
