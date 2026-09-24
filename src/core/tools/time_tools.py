# src/core/tools/time_tools.py
"""Outils liés au temps."""

import datetime

from langchain_core.tools import tool

TOOL_METADATA = {
    "name": "🕒 Time",
    "description": "Heure système",
    "category": "system",
    "requires_config": False,
}


@tool
def get_current_time() -> str:
    """
    Retourne la date et l'heure actuelles.

    Returns:
        Date et heure au format ISO
    """
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")
