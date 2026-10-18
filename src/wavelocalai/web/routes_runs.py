"""Routes des runs : flux SSE rejouable, annulation, instantané (AD-5, AD-6).

`GET /api/runs/{id}/events` suit un run : trame `id: <seq>` + `data: <enveloppe>` sans champ
`event:`, reprise par `Last-Event-ID` ou `?after=` (mémoire du hub si le run est actif, base
sinon), `204` si le curseur a déjà atteint la fin d'un run terminé, commentaire de maintien toutes
les 15 s par `fastapi.sse.EventSourceResponse`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from wavelocalai.errors import AppError
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.snapshot import run_snapshot, stream_state

router = APIRouter(prefix="/api")


class NoContentError(Exception):
    """Le curseur est à la fin d'un run terminé : rien à rejouer (`204`, AD-6)."""


def _hub(request: Request) -> RunHub:
    hub = request.app.state.hub
    if hub is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le hub des runs n'est pas démarré.")
    return hub


async def resume_cursor(
    run_id: str,
    request: Request,
    after: Annotated[int | None, Query(ge=0)] = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> int:
    """Dernier `seq` déjà reçu par le client : `?after=` d'abord, sinon `Last-Event-ID`, sinon 0.
    Écarte ici (avant le flux) l'inconnu (`404`) et la fin déjà lue (`204`)."""
    cursor = after
    if cursor is None and last_event_id not in (None, ""):
        try:
            cursor = int(str(last_event_id))
        except ValueError:
            raise AppError("invalid_request", "Last-Event-ID n'est pas un entier.") from None
        if cursor < 0:
            raise AppError("invalid_request", "Last-Event-ID est négatif.")
    cursor = cursor or 0
    hub = _hub(request)
    if hub.watch(run_id) is not None:
        return cursor  # run actif : le flux part de la mémoire
    state = await stream_state(request.app.state.store, run_id)
    if state is None or state[1] is not None:  # inconnu, ou feuille (le parent publie seul)
        raise AppError("not_found", f"Aucun flux pour le run {run_id}.")
    if cursor >= state[2]:
        raise NoContentError
    return cursor


@router.get("/runs/{run_id}/events", response_class=EventSourceResponse)
async def run_events(
    run_id: str, request: Request, cursor: Annotated[int, Depends(resume_cursor)]
) -> AsyncIterator[ServerSentEvent]:
    hub = _hub(request)
    while True:
        # Prendre l'abonnement *avant* de lire : un événement publié entre les deux le déclenche.
        signal = hub.watch(run_id)
        for envelope in await hub.events_after(run_id, cursor):
            cursor = envelope["seq"]
            yield ServerSentEvent(data=envelope, id=str(cursor))
            if envelope["type"] == "run_ended":
                return
        if signal is None:  # run clos et tout rejoué
            return
        await signal.wait()


class CancelResult(BaseModel):
    run_id: str
    cancelled: bool  # faux si le run n'était pas (ou plus) actif
    status: str


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request) -> CancelResult:
    hub = _hub(request)
    store = request.app.state.store
    if await stream_state(store, run_id) is None:
        raise AppError("not_found", f"Run {run_id} inconnu.")
    cancelled = await hub.cancel(run_id)
    state = await stream_state(store, run_id)
    return CancelResult(run_id=run_id, cancelled=cancelled, status=state[0] if state else "")


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    snapshot = await run_snapshot(request.app.state.store, run_id)
    if snapshot is None:
        raise AppError("not_found", f"Run {run_id} inconnu.")
    return snapshot
