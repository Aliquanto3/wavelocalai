# src/core/tools/search_tools.py
"""Outils de recherche."""

import json
import logging
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Chemin vers la base de connaissances interne (exemple)
KNOWLEDGE_BASE_PATH = Path("data/knowledge_base.json")

TOOL_METADATA = {
    "name": "🏢 Wavestone Search",
    "description": "Base interne simulée",
    "category": "data",
    "requires_config": False,
}


@tool
def search_wavestone_internal(query: str) -> str:
    """
    Recherche dans la base de connaissances interne Wavestone.

    Args:
        query: Termes de recherche

    Returns:
        Résultats de la recherche ou message si non trouvé
    """
    try:
        if not KNOWLEDGE_BASE_PATH.exists():
            return (
                f"Base de connaissances non configurée. Recherche pour: '{query}' - Aucun résultat."
            )

        with open(KNOWLEDGE_BASE_PATH, encoding="utf-8") as f:
            knowledge = json.load(f)

        query_lower = query.lower()
        results = []

        for entry in knowledge.get("entries", []):
            title = entry.get("title", "").lower()
            content = entry.get("content", "").lower()

            if query_lower in title or query_lower in content:
                results.append(
                    {"title": entry.get("title"), "excerpt": entry.get("content", "")[:200] + "..."}
                )

        if not results:
            return f"Aucun résultat pour: '{query}'"

        output = f"📚 {len(results)} résultat(s) pour '{query}':\n\n"
        for i, r in enumerate(results[:5], 1):
            output += f"{i}. **{r['title']}**\n   {r['excerpt']}\n\n"

        return output

    except Exception as e:
        return f"Erreur de recherche: {e}"
