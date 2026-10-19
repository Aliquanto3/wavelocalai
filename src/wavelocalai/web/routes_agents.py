"""`POST /api/agents/runs` : lance un agent seul, rend `{run_id, conversation_id}` aussitôt.

Les étapes (`step`) et la réponse se lisent par `GET /api/runs/{id}/events` (AD-6) ; l'écran de
l'agent est la story 6.4, la liste des outils `GET /api/agents/tools` la story 6.2.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from wavelocalai.agents.service import AgentCommand, AgentService
from wavelocalai.errors import AppError

router = APIRouter(prefix="/api")

MAX_PROMPT_CHARS = 100_000
MAX_TOOLS = 32


class AgentBody(BaseModel):
    mode: Literal["solo"]  # `crew` : story 6.5
    model: str = Field(min_length=1)
    prompt: str = Field(max_length=MAX_PROMPT_CHARS)
    tools: list[str] = Field(default_factory=list, max_length=MAX_TOOLS)
    conversation_id: str | None = None
    allow_cloud: bool = False
    temperature: float = Field(0.2, ge=0.0, le=2.0)

    @field_validator("prompt")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("la tâche est vide")
        return value


class Started(BaseModel):
    run_id: str
    conversation_id: str | None


@router.post("/agents/runs")
async def start_agent_run(body: AgentBody, request: Request) -> Started:
    service: AgentService | None = request.app.state.agents
    if service is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le service d'agents n'est pas démarré.")
    handle = await service.start(
        AgentCommand(
            model=body.model,
            prompt=body.prompt,
            tools=tuple(body.tools),
            temperature=body.temperature,
            allow_cloud=body.allow_cloud,
            conversation_id=body.conversation_id,
            mode=body.mode,
        )
    )
    return Started(run_id=handle.run_id, conversation_id=handle.conversation_id)
