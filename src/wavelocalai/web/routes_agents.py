"""`POST /api/agents/runs` : lance un agent seul ou une équipe, rend `{run_id, conversation_id}`
aussitôt. Story 6.5 : `GET /api/agents/crews`, `POST /api/agents/crews/validate`, et la
modification d'une équipe (`PUT`) ou son retour à l'origine (`DELETE`) dans `/api/agents/crews/{id}`.

Les étapes (`step`) et la réponse se lisent par `GET /api/runs/{id}/events` (AD-6) ; l'écran de
l'agent est la story 6.4. Story 6.2 : `GET /api/agents/tools` liste les outils avec leur
disponibilité, `GET /api/outputs/{name}` sert les fichiers qu'ils ont produits (dossier de travail
des agents, jamais un chemin libre).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from wavelocalai.agents.crews import MAX_AGENTS, CrewAgent, CrewLibrary, agent_from
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
    """Agent seul (`mode: "solo"`, `model` et `prompt` obligatoires) ou équipe (`mode: "crew"`,
    `crew` et `topic` obligatoires ; `model` est alors le modèle des agents qui n'ont pas le leur).
    """

    mode: Literal["solo", "crew"]
    model: str | None = None
    prompt: str = Field("", max_length=MAX_PROMPT_CHARS)
    tools: list[str] = Field(default_factory=list, max_length=MAX_TOOLS)
    crew: str | None = None
    topic: str = Field("", max_length=MAX_PROMPT_CHARS)
    conversation_id: str | None = None
    allow_cloud: bool = False
    temperature: float = Field(0.2, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def _required_fields(self) -> AgentBody:
        if self.mode == "solo":
            if not self.model:
                raise ValueError("model : le modèle est obligatoire")
            if not self.prompt.strip():
                raise ValueError("prompt : la tâche est vide")
        else:
            if not self.crew:
                raise ValueError("crew : l'équipe est obligatoire")
            if not self.topic.strip():
                raise ValueError("topic : le sujet de la mission est vide")
            if self.tools:
                raise ValueError("tools : les outils sont ceux des agents de l'équipe")
        return self


class AgentIn(BaseModel):
    """Un agent d'équipe tel qu'envoyé par l'écran (`validate`, enregistrement)."""

    role: str = ""
    goal: str = ""
    backstory: str | None = None
    tools: list[str] = Field(default_factory=list, max_length=MAX_TOOLS)
    model: str | None = None

    def agent(self) -> CrewAgent:
        found = agent_from(self.model_dump())
        assert found is not None
        return found


class CrewBody(BaseModel):
    agents: list[AgentIn] = Field(default_factory=list, max_length=50)
    allow_cloud: bool = False

    def crew_agents(self) -> list[CrewAgent]:
        return [a.agent() for a in self.agents]


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
            model=body.model or "",
            prompt=body.prompt,
            crew=body.crew,
            topic=body.topic,
            tools=tuple(body.tools),
            temperature=body.temperature,
            allow_cloud=body.allow_cloud,
            conversation_id=body.conversation_id,
            mode=body.mode,
        )
    )
    return Started(run_id=handle.run_id, conversation_id=handle.conversation_id)


def _crews(request: Request) -> CrewLibrary:
    return request.app.state.agent_crews


@router.get("/agents/crews")
async def list_crews(request: Request) -> dict[str, object]:
    """Les équipes en vigueur (origine ou modification de l'utilisateur), agents et tâches ordonnés,
    plus `max_agents` (D-36)."""
    return {"crews": _crews(request).listing(), "max_agents": MAX_AGENTS}


@router.post("/agents/crews/validate")
async def validate_crew(body: CrewBody, request: Request) -> dict[str, object]:
    """Valide une composition sans l'enregistrer : `{valid, errors: [{field, message}]}`, un message
    par champ (`agents`, `agents[i].role|goal|tools|model`)."""
    errors = _crews(request).validate(body.crew_agents(), allow_cloud=body.allow_cloud)
    return {"valid": not errors, "errors": errors}


@router.put("/agents/crews/{crew_id}")
async def save_crew(crew_id: str, body: CrewBody, request: Request) -> dict[str, object]:
    """Enregistre la modification de l'utilisateur (validée : `422` sinon) ; rend l'équipe."""
    library = _crews(request)
    library.save(crew_id, body.crew_agents(), allow_cloud=body.allow_cloud)
    return library.view(crew_id)


@router.delete("/agents/crews/{crew_id}")
async def reset_crew(crew_id: str, request: Request) -> dict[str, object]:
    """« Revenir à l'équipe d'origine » : efface la modification ; rend l'équipe d'origine."""
    library = _crews(request)
    library.reset(crew_id)
    return library.view(crew_id)


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
