"""`POST /api/chat/runs` : lance une réponse en flux, rend `{run_id, conversation_id}` aussitôt.

Le flux lui-même se lit par `GET /api/runs/{id}/events` (AD-6) ; le front du chat est la story 2.2.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from wavelocalai.errors import AppError
from wavelocalai.inference.chat import ChatCommand, ChatService

router = APIRouter(prefix="/api")

MAX_MESSAGE_CHARS = 100_000


class ChatBody(BaseModel):
    conversation_id: str | None = None
    model: str = Field(min_length=1)
    message: str = Field(max_length=MAX_MESSAGE_CHARS)
    temperature: float = Field(0.2, ge=0.0, le=2.0)
    allow_cloud: bool = False

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("le message est vide")
        return value


class Started(BaseModel):
    run_id: str
    conversation_id: str | None


@router.post("/chat/runs")
async def start_chat_run(body: ChatBody, request: Request) -> Started:
    service: ChatService | None = request.app.state.chat
    if service is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le service de chat n'est pas démarré.")
    handle = await service.start(ChatCommand(**body.model_dump()))
    return Started(run_id=handle.run_id, conversation_id=handle.conversation_id)
