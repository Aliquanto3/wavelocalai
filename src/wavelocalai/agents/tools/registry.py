"""Outils d'un agent : définition, registre et exécution (story 6.1, AD-9).

Un outil est une coroutine `run(arguments) -> texte` et son schéma neutre (`name`, `description`,
`parameters` : schéma JSON d'un objet) que les adaptateurs traduisent (`models/tool_format.py`).
Le registre de l'application porte les outils de la v1 (`builtin.py`, story 6.2), avec leur
disponibilité, et la route `GET /api/agents/tools` les liste. Un outil `sensitive` ne s'exécute jamais sans approbation
explicite (AD-9, story 6.3) : en 6.1 la boucle le refuse.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from wavelocalai.errors import AppError

# Nom vu par le modèle : accepté par les quatre fournisseurs (`^[a-zA-Z0-9_-]{1,64}$`).
TOOL_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
EMPTY_PARAMETERS: dict[str, Any] = {"type": "object", "properties": {}}


class ToolError(Exception):
    """Échec attendu d'un outil : son message (français, sans nom de classe) est le `tool_result`
    en échec que l'agent lit et peut contourner."""


@dataclass(frozen=True)
class ToolOutput:
    """Résultat d'un outil qui produit aussi un fichier : `artifact_url` figure dans l'étape
    `tool_result` (story 6.2)."""

    text: str
    artifact_url: str | None = None


ToolFunction = Callable[[dict[str, Any]], Awaitable[str | ToolOutput]]


@dataclass(frozen=True)
class AgentTool:
    id: str
    description: str
    run: ToolFunction
    parameters: dict[str, Any] = field(default_factory=lambda: dict(EMPTY_PARAMETERS))
    label: str | None = None  # libellé du lexique (story 6.2) ; `id` sinon
    summary: str | None = None  # description courte pour l'écran (`GET /api/agents/tools`)
    sensitive: bool = False
    available: bool = True
    reason: str | None = None  # pourquoi l'outil est indisponible

    def __post_init__(self) -> None:
        if not TOOL_ID.match(self.id):
            raise ValueError(f"Identifiant d'outil invalide : {self.id!r}")

    def listing(self) -> dict[str, Any]:
        """Ligne de `GET /api/agents/tools` : ce que l'écran affiche, jamais le schéma ni le code."""
        return {
            "id": self.id,
            "label": self.label or self.id,
            "description": self.summary or self.description,
            "available": self.available,
            "reason": None if self.available else self.reason,
            "sensitive": self.sensitive,
        }

    def spec(self) -> dict[str, Any]:
        """Schéma neutre passé au port (`ChatRequest.tools`)."""
        return {"name": self.id, "description": self.description, "parameters": self.parameters}


class ToolRegistry:
    """Les outils connus de l'application, par identifiant."""

    def __init__(self, tools: Iterable[AgentTool] = ()) -> None:
        self._tools: dict[str, AgentTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: AgentTool) -> None:
        if tool.id in self._tools:
            raise ValueError(f"Outil déjà inscrit : {tool.id}")
        self._tools[tool.id] = tool

    def all(self) -> list[AgentTool]:
        return list(self._tools.values())

    def get(self, ids: Sequence[str]) -> list[AgentTool]:
        """Les outils demandés, dans l'ordre. Un identifiant inconnu, répété ou un outil indisponible
        lève `invalid_request` (422) : rien n'est lancé."""
        chosen: list[AgentTool] = []
        for tool_id in ids:
            tool = self._tools.get(tool_id)
            if tool is None:
                raise AppError("invalid_request", f"tools : outil inconnu « {tool_id} ».")
            if tool in chosen:
                raise AppError("invalid_request", f"tools : outil répété « {tool_id} ».")
            if not tool.available:
                raise AppError(
                    "invalid_request",
                    f"tools : « {tool_id} » est indisponible"
                    + (f" ({tool.reason})." if tool.reason else "."),
                )
            chosen.append(tool)
        return chosen
