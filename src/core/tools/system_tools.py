# src/core/tools/system_tools.py
"""Outils de monitoring système."""

import psutil
from langchain_core.tools import tool

TOOL_METADATA = {
    "name": "💾 System Monitor",
    "description": "Métriques système",
    "category": "system",
    "requires_config": False,
}


@tool
def system_monitor() -> str:
    """
    Retourne les métriques système actuelles (CPU, RAM, Disque).

    Returns:
        Rapport formaté des ressources système
    """
    cpu_percent = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return f"""📊 Métriques Système:
- CPU: {cpu_percent}%
- RAM: {memory.percent}% ({memory.used // (1024**3)}/{memory.total // (1024**3)} GB)
- Disque: {disk.percent}% ({disk.used // (1024**3)}/{disk.total // (1024**3)} GB)"""
