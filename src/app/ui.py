"""
Éléments d'interface partagés par les pages : logo et libellés de modèles.

Le rendu (couleurs, police, rayon) vient de .streamlit/config.toml ; ce module ne contient
aucune couleur.
"""

from pathlib import Path

import streamlit as st

from src.core.models_db import get_friendly_name_from_tag

STATIC_DIR = Path(__file__).resolve().parent / "static"
WORDMARK_PATH = STATIC_DIR / "wordmark.svg"
# Favicon local, commun aux pages : une icône Material en page_icon serait téléchargée
# depuis fonts.gstatic.com par le navigateur.
FAVICON_PATH = STATIC_DIR / "favicon.svg"

LOCAL_SUFFIX = "Local"
CLOUD_SUFFIX = "Cloud"


def render_logo() -> None:
    """Affiche le wordmark « WaveLocalAI » en tête de la barre latérale."""
    st.logo(str(WORDMARK_PATH))


def model_label(friendly_name: str, is_cloud: bool) -> str:
    """Libellé d'un modèle dans un sélecteur : nom, puis « · Local » ou « · Cloud »."""
    return f"{friendly_name} · {CLOUD_SUFFIX if is_cloud else LOCAL_SUFFIX}"


def model_options(
    models: list[dict], cloud_types: tuple[str, ...] = ("cloud",)
) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """
    Options d'un sélecteur de modèles, à partir de LLMProvider.list_models.

    Retourne (display_to_tag, tag_to_friendly, libellés triés). Chaque libellé est construit
    avec son tag dans la même passe. Ordre inchangé : modèles cloud puis locaux, chacun par
    nom (le tri « local d'abord » relève de la story des choix par défaut).
    """
    display_to_tag: dict[str, str] = {}
    tag_to_friendly: dict[str, str] = {}
    sort_keys: dict[str, tuple[bool, str]] = {}
    for m in models:
        tag = m["model"]
        is_cloud = m.get("type") in cloud_types
        friendly = get_friendly_name_from_tag(tag)
        label = model_label(friendly, is_cloud)
        display_to_tag[label] = tag
        tag_to_friendly[tag] = friendly
        sort_keys[label] = (not is_cloud, friendly)
    return display_to_tag, tag_to_friendly, sorted(display_to_tag, key=sort_keys.__getitem__)
