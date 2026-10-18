"""Routes des conversations : lecture, export JSON et Markdown, effacement (AD-5, AD-13).

- `GET /api/conversations` : les plus récentes (l'écran rouvre la dernière du genre `chat`).
- `GET /api/conversations/{id}` : messages, raisonnement, mesures et CO2 de chaque réponse.
- `GET /api/conversations/{id}.json` et `.md` : export en pièce jointe (`Content-Disposition`).
- `DELETE /api/conversations/{id}` : efface le texte (`messages`, `run_events`), garde les lignes
  `runs` sans texte ; `409 conversation_busy` si un run est actif. Le hub écrit, rien ici.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from wavelocalai.config import get_version
from wavelocalai.errors import AppError
from wavelocalai.runs.conversation_export import export_document, to_json, to_markdown
from wavelocalai.runs.conversations import conversation_view, list_conversations
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import CONVERSATION_KINDS
from wavelocalai.store.db import Store, utc_now_iso

router = APIRouter(prefix="/api")


def _store(request: Request) -> Store:
    store = request.app.state.store
    if store is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "La base n'est pas ouverte.")
    return store


def _hub(request: Request) -> RunHub:
    hub = request.app.state.hub
    if hub is None:
        raise AppError("internal", "Le hub des runs n'est pas démarré.")
    return hub


def _not_found(conversation_id: str) -> AppError:
    return AppError("not_found", f"Conversation {conversation_id} inconnue.")


@router.get("/conversations")
async def conversations(
    request: Request,
    kind: Annotated[str | None, Query(pattern="^(" + "|".join(CONVERSATION_KINDS) + ")$")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    store = request.app.state.store
    if store is None:  # hors du cycle de vie : rien à lister
        return {"conversations": []}
    return {"conversations": await list_conversations(store, kind, limit)}


# Les exports d'abord : `{conversation_id}` seul accepterait aussi « abc.json ».
async def _export(conversation_id: str, request: Request) -> dict[str, Any]:
    view = await conversation_view(_store(request), conversation_id)
    if view is None:
        raise _not_found(conversation_id)
    settings = request.app.state.settings
    return export_document(view, utc_now_iso(), get_version(), settings.secret_values())


def _attachment(body: str, media_type: str, conversation_id: str, extension: str) -> Response:
    return Response(
        body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="conversation-{conversation_id[:8]}.{extension}"'
        },
    )


@router.get("/conversations/{conversation_id}.json")
async def export_json(conversation_id: str, request: Request) -> Response:
    document = await _export(conversation_id, request)
    return _attachment(to_json(document), "application/json", conversation_id, "json")


@router.get("/conversations/{conversation_id}.md")
async def export_markdown(conversation_id: str, request: Request) -> Response:
    document = await _export(conversation_id, request)
    return _attachment(to_markdown(document), "text/markdown; charset=utf-8", conversation_id, "md")


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    view = await conversation_view(_store(request), conversation_id)
    if view is None:
        raise _not_found(conversation_id)
    return view


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, request: Request) -> Response:
    await _hub(request).erase_conversation(conversation_id)
    return Response(status_code=204)
