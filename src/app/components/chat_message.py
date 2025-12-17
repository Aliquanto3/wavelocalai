# src/app/components/chat_message.py
"""
Composants d'affichage des messages de chat.
"""

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from src.core.models_db import extract_thought


def render_chat_message(
    role: str,
    content: str,
    model_tag: str | None = None,
    show_thinking: bool = True,
    avatar: str | None = None,
) -> None:
    """
    Affiche un message de chat avec gestion du thinking.

    Args:
        role: Rôle ("user", "assistant", "system")
        content: Contenu du message
        model_tag: Tag du modèle (pour l'assistant)
        show_thinking: Afficher le bloc thinking si présent
        avatar: Avatar personnalisé (emoji ou URL)
    """
    # Déterminer l'avatar
    if avatar is None:
        if role == "user":
            avatar = "👤"
        elif role == "assistant":
            avatar = "🤖"
        else:
            avatar = "⚙️"

    # Extraire le thinking si présent
    thought, clean_content = None, content
    if role == "assistant" and show_thinking:
        thought, clean_content = extract_thought(content)

    # Afficher le message
    with st.chat_message(role, avatar=avatar):
        # Afficher le thinking dans un bloc séparé
        if thought:
            render_thinking_block(thought)

        # Afficher le contenu principal
        if clean_content:
            st.markdown(clean_content)

        # Afficher le tag du modèle si fourni
        if model_tag and role == "assistant":
            st.caption(f"_via {model_tag}_")


def render_thinking_block(
    thought: str,
    title: str = "💭 Réflexion",
    expanded: bool = False,
) -> None:
    """
    Affiche un bloc de réflexion (thinking) du modèle.

    Args:
        thought: Contenu de la réflexion
        title: Titre du bloc
        expanded: État initial (ouvert/fermé)
    """
    with st.expander(title, expanded=expanded):
        st.markdown(
            f'<div style="background-color: #f0f0f0; padding: 10px; '
            f'border-radius: 5px; font-style: italic; color: #555;">'
            f"{thought}</div>",
            unsafe_allow_html=True,
        )


def render_streaming_message(
    placeholder: DeltaGenerator,
    content: str,
    is_complete: bool = False,
) -> None:
    """
    Met à jour un message en streaming.

    Args:
        placeholder: Placeholder Streamlit à mettre à jour (retour de st.empty())
        content: Contenu actuel
        is_complete: True si le streaming est terminé
    """
    if is_complete:
        placeholder.markdown(content)
    else:
        # Ajouter un curseur clignotant pendant le streaming
        placeholder.markdown(content + "▌")


def render_error_message(
    error: str,
    suggestion: str | None = None,
) -> None:
    """
    Affiche un message d'erreur formaté.

    Args:
        error: Message d'erreur
        suggestion: Suggestion de résolution
    """
    st.error(f"❌ {error}")

    if suggestion:
        st.info(f"💡 {suggestion}")
