"""`POST /api/arena/runs` : lance une comparaison de 2 à 4 modèles, rend `{run_id}` aussitôt.

Le flux se lit par `GET /api/runs/{id}/events` (AD-6), l'écran est la story 3.2. L'Arène n'ouvre pas
de conversation : la réponse ne porte pas de `conversation_id`.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from wavelocalai.errors import AppError
from wavelocalai.inference.arena import ArenaCommand, ArenaService

router = APIRouter(prefix="/api")

MAX_PROMPT_CHARS = 100_000


class ArenaBody(BaseModel):
    models: list[str]  # 2 à 4 modèles distincts : vérifié par le service, qui résout les tags
    prompt: str = Field(max_length=MAX_PROMPT_CHARS)
    judge: str | None = None
    criteria: list[str] = Field(default_factory=list)
    allow_cloud: bool = False

    @field_validator("prompt")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("la question est vide")
        return value


class ArenaStarted(BaseModel):
    run_id: str


@router.post("/arena/runs")
async def start_arena_run(body: ArenaBody, request: Request) -> ArenaStarted:
    service: ArenaService | None = request.app.state.arena
    if service is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le service de l'Arène n'est pas démarré.")
    handle = await service.start(ArenaCommand(**body.model_dump()))
    return ArenaStarted(run_id=handle.run_id)
