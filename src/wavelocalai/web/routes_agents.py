"""`POST /api/agents/runs` : lance un agent seul, rend `{run_id, conversation_id}` aussitôt.

Les étapes (`step`) et la réponse se lisent par `GET /api/runs/{id}/events` (AD-6) ; l'écran de
l'agent est la story 6.4. Story 6.2 : `GET /api/agents/tools` liste les outils avec leur
disponibilité, `GET /api/outputs/{name}` sert les fichiers qu'ils ont produits (dossier de travail
des agents, jamais un chemin libre).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from wavelocalai.agents.service import AgentCommand, AgentService
from wavelocalai.agents.tools import ToolRegistry, Workspace, WorkspaceError
from wavelocalai.errors import AppError

router = APIRouter(prefix="/api")

MAX_PROMPT_CHARS = 100_000
MAX_TOOLS = 32
# Fichiers que les outils produisent, seuls servis par `GET /api/outputs/{name}`.
OUTPUT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".md": "text/markdown; charset=utf-8",
}


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


@router.get("/agents/tools")
async def list_agent_tools(request: Request) -> dict[str, list[dict[str, object]]]:
    """Les outils des agents : `id`, `label`, `description`, `available`, `reason`, `sensitive`."""
    registry: ToolRegistry = request.app.state.agent_tools
    return {"tools": [tool.listing() for tool in registry.all()]}


@router.get("/outputs/{name}")
async def get_output(name: str, request: Request) -> FileResponse:
    """Fichier produit par un outil, en pièce jointe. Le nom est validé (un seul composant, aucun
    `..`) puis cherché à plat dans le dossier de travail ; un lien ou un autre type de fichier n'est
    pas servi."""
    workspace: Workspace = request.app.state.agent_workspace
    try:
        path = workspace.served_path(name)
    except WorkspaceError as exc:
        raise AppError("invalid_request", f"name : {exc}") from None
    media_type = OUTPUT_TYPES.get(path.suffix.lower()) if path else None
    if path is None or media_type is None:
        raise AppError("not_found", "Ce fichier n'existe pas ou n'est plus disponible.")
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )
