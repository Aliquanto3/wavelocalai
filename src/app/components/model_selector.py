# src/app/components/model_selector.py
"""
Composant de sélection de modèle.
"""


import streamlit as st

from src.core.llm_provider import LLMProvider
from src.core.model_defaults import is_embedding_model
from src.core.models_db import MODELS_DB


def render_model_selector(
    key: str,
    label: str = "🤖 Modèle",
    include_cloud: bool = True,
    show_details: bool = True,
    default_model: str | None = None,
    help_text: str | None = None,
) -> str | None:
    """
    Affiche un sélecteur de modèle avec informations enrichies.

    Args:
        key: Clé unique pour le widget Streamlit
        label: Label du sélecteur
        include_cloud: Inclure les modèles cloud
        show_details: Afficher les détails du modèle sélectionné
        default_model: Modèle sélectionné par défaut
        help_text: Texte d'aide

    Returns:
        Tag du modèle sélectionné ou None
    """
    # Récupérer la liste des modèles
    try:
        models = LLMProvider.list_models(cloud_enabled=include_cloud)
    except Exception:
        st.error("❌ Impossible de récupérer la liste des modèles")
        return None

    models = [m for m in models if not is_embedding_model(m)]
    if not models:
        st.warning("⚠️ Aucun modèle disponible")
        return None

    # Construire les options
    model_tags = []
    model_labels = {}

    for m in models:
        tag = m.get("model") or m.get("name")
        if not tag:
            continue

        model_tags.append(tag)

        # Construire le label enrichi
        model_type = "☁️" if m.get("type") == "cloud" else "🏠"

        # Chercher des infos supplémentaires dans MODELS_DB
        params = ""
        for _name, info in MODELS_DB.items():
            if info.get("ollama_tag") == tag:
                params = info.get("params", "")
                break

        if params:
            model_labels[tag] = f"{model_type} {tag} ({params})"
        else:
            model_labels[tag] = f"{model_type} {tag}"

    # Déterminer l'index par défaut
    default_index = 0
    if default_model and default_model in model_tags:
        default_index = model_tags.index(default_model)

    # Afficher le sélecteur
    selected_tag = st.selectbox(
        label,
        options=model_tags,
        index=default_index,
        format_func=lambda x: model_labels.get(x, x),
        key=key,
        help=help_text,
    )

    # Afficher les détails si demandé
    if show_details and selected_tag:
        _render_model_details(selected_tag)

    return selected_tag


def _render_model_details(model_tag: str) -> None:
    """Affiche les détails d'un modèle."""
    # Chercher dans MODELS_DB
    model_info = None
    for _name, info in MODELS_DB.items():
        if info.get("ollama_tag") == model_tag:
            model_info = info
            break

    if not model_info:
        return

    with st.container():
        cols = st.columns(4)

        with cols[0]:
            params = model_info.get("params", "?")
            st.caption(f"📊 {params}")

        with cols[1]:
            editor = model_info.get("editor", "?")
            st.caption(f"🏢 {editor}")

        with cols[2]:
            model_type = model_info.get("type", "local")
            if model_type == "api":
                st.caption("☁️ Cloud")
            else:
                st.caption("🏠 Local")

        with cols[3]:
            # Indicateur de capacités
            if model_info.get("supports_tools"):
                st.caption("🔧 Tools")
            if model_info.get("supports_vision"):
                st.caption("👁️ Vision")


def render_model_comparison_selector(
    key_prefix: str,
    num_models: int = 2,
    label: str = "Modèles à comparer",
) -> list[str]:
    """
    Affiche plusieurs sélecteurs pour comparer des modèles.

    Args:
        key_prefix: Préfixe pour les clés des widgets
        num_models: Nombre de modèles à sélectionner
        label: Label de la section

    Returns:
        Liste des tags de modèles sélectionnés
    """
    st.markdown(f"**{label}**")

    selected_models = []
    cols = st.columns(num_models)

    for i, col in enumerate(cols):
        with col:
            model = render_model_selector(
                key=f"{key_prefix}_model_{i}",
                label=f"Modèle {i + 1}",
                show_details=False,
            )
            if model:
                selected_models.append(model)

    return selected_models
