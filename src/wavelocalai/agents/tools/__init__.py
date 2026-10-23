"""Outils des agents (story 6.1 : définition et registre ; story 6.2 : les outils de la v1)."""

from wavelocalai.agents.tools.builtin import build_registry
from wavelocalai.agents.tools.registry import (
    AgentTool,
    ToolError,
    ToolFunction,
    ToolOutput,
    ToolRegistry,
)
from wavelocalai.agents.tools.workspace import Workspace, WorkspaceError

__all__ = [
    "AgentTool",
    "ToolError",
    "ToolFunction",
    "ToolOutput",
    "ToolRegistry",
    "Workspace",
    "WorkspaceError",
    "build_registry",
]
