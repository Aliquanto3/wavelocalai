# src/core/tools/__init__.py
"""
Outils disponibles pour les agents autonomes.

Ce module centralise tous les outils utilisables par les agents LangGraph et CrewAI.
"""

from src.core.tools.calculator import TOOL_METADATA as CALCULATOR_META
from src.core.tools.calculator import calculator
from src.core.tools.data_tools import TOOL_METADATA_ANALYZE as ANALYZE_CSV_META
from src.core.tools.data_tools import TOOL_METADATA_CHART as GENERATE_CHART_META
from src.core.tools.data_tools import (
    analyze_csv,
    generate_chart,
)
from src.core.tools.document_tools import TOOL_METADATA_DOC as GENERATE_DOC_META
from src.core.tools.document_tools import TOOL_METADATA_MD as GENERATE_MD_META
from src.core.tools.document_tools import (
    generate_document,
    generate_markdown_report,
)
from src.core.tools.email_tools import TOOL_METADATA as EMAIL_META
from src.core.tools.email_tools import send_email
from src.core.tools.search_tools import TOOL_METADATA as SEARCH_META
from src.core.tools.search_tools import search_wavestone_internal
from src.core.tools.system_tools import TOOL_METADATA as SYSTEM_META
from src.core.tools.system_tools import system_monitor
from src.core.tools.time_tools import TOOL_METADATA as TIME_META
from src.core.tools.time_tools import get_current_time

# Liste de tous les outils disponibles
AVAILABLE_TOOLS = [
    calculator,
    get_current_time,
    system_monitor,
    analyze_csv,
    generate_chart,
    generate_document,
    generate_markdown_report,
    send_email,
    search_wavestone_internal,
]

# Index par nom pour recherche rapide
_TOOLS_BY_NAME = {tool.name: tool for tool in AVAILABLE_TOOLS}


def _build_tools_metadata() -> dict[str, dict]:
    """
    Agrège les métadonnées de tous les outils.

    Returns:
        Dictionnaire {tool_name: metadata}
    """
    return {
        "calculator": CALCULATOR_META,
        "get_current_time": TIME_META,
        "system_monitor": SYSTEM_META,
        "analyze_csv": ANALYZE_CSV_META,
        "generate_chart": GENERATE_CHART_META,
        "generate_document": GENERATE_DOC_META,
        "generate_markdown_report": GENERATE_MD_META,
        "send_email": EMAIL_META,
        "search_wavestone_internal": SEARCH_META,
    }


TOOLS_METADATA = _build_tools_metadata()


def get_tools_by_names(names: list[str]) -> list:
    """Retourne une liste d'outils filtrés par leurs noms."""
    return [_TOOLS_BY_NAME[name] for name in names if name in _TOOLS_BY_NAME]


def list_tool_names() -> list[str]:
    """Retourne la liste des noms d'outils disponibles."""
    return list(_TOOLS_BY_NAME.keys())


def get_tools_by_category(category: str) -> list[str]:
    """Retourne les noms d'outils d'une catégorie donnée."""
    return [name for name, meta in TOOLS_METADATA.items() if meta.get("category") == category]


__all__ = [
    # Outils
    "calculator",
    "get_current_time",
    "system_monitor",
    "analyze_csv",
    "generate_chart",
    "generate_document",
    "generate_markdown_report",
    "send_email",
    "search_wavestone_internal",
    # Collections et helpers
    "AVAILABLE_TOOLS",
    "TOOLS_METADATA",
    "get_tools_by_names",
    "list_tool_names",
    "get_tools_by_category",
]
