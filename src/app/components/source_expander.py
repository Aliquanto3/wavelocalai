# src/app/components/source_expander.py
"""
Composant d'affichage des sources RAG.
"""

from typing import Any

import streamlit as st


def render_sources_expander(
    sources: list[dict[str, Any]],
    title: str = "📚 Sources utilisées",
    expanded: bool = False,
    max_sources: int = 5,
) -> None:
    """
    Affiche les sources utilisées par le RAG dans un expander.

    Args:
        sources: Liste des documents sources
        title: Titre de l'expander
        expanded: État initial
        max_sources: Nombre max de sources à afficher
    """
    if not sources:
        return

    with st.expander(f"{title} ({len(sources)})", expanded=expanded):
        for i, source in enumerate(sources[:max_sources]):
            _render_source_item(source, i + 1)

        if len(sources) > max_sources:
            st.caption(f"... et {len(sources) - max_sources} autres sources")


def _render_source_item(source: dict[str, Any], index: int) -> None:
    """Affiche un item de source."""
    # Extraire les métadonnées
    content = source.get("page_content", source.get("content", ""))
    metadata = source.get("metadata", {})

    filename = metadata.get("source", metadata.get("filename", f"Source {index}"))
    page = metadata.get("page")
    score = source.get("score", source.get("relevance_score"))

    # Construire le titre
    title_parts = [f"**{index}. {filename}**"]
    if page is not None:
        title_parts.append(f"(p.{page})")
    if score is not None:
        title_parts.append(f"- Score: {score:.2f}")

    st.markdown(" ".join(title_parts))

    # Afficher un extrait du contenu
    if content:
        preview = content[:300] + "..." if len(content) > 300 else content
        st.caption(preview)

    st.divider()


def render_source_chips(
    sources: list[dict[str, Any]],
    max_chips: int = 3,
) -> None:
    """
    Affiche les sources sous forme de chips compacts.

    Args:
        sources: Liste des documents sources
        max_chips: Nombre max de chips à afficher
    """
    if not sources:
        return

    chips = []
    for source in sources[:max_chips]:
        metadata = source.get("metadata", {})
        filename = metadata.get("source", metadata.get("filename", "?"))
        # Raccourcir le nom si trop long
        if len(filename) > 20:
            filename = filename[:17] + "..."
        chips.append(f"`📄 {filename}`")

    if len(sources) > max_chips:
        chips.append(f"`+{len(sources) - max_chips}`")

    st.markdown(" ".join(chips))
