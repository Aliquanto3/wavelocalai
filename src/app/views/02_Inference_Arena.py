import streamlit as st

from src.app.tabs.inference.arena import render_arena_tab

# IMPORT DES NOUVEAUX TABS
from src.app.tabs.inference.chat import render_chat_tab
from src.app.tabs.inference.lab import render_lab_tab
from src.app.tabs.inference.manager import render_manager_tab
from src.app.modules import ARENA
from src.app.ui import FAVICON_PATH, model_options
from src.core.llm_provider import LLMProvider

# --- Configuration de la Page ---
st.set_page_config(page_title=ARENA.title, page_icon=FAVICON_PATH, layout="wide")

# Contrôle global « Autoriser le cloud », rendu par le routeur (Accueil.py).
cloud_enabled = st.session_state.get("cloud_enabled", True)

# ==========================================
# CHARGEMENT CENTRALISÉ DES MODÈLES
# ==========================================
installed_models_list = LLMProvider.list_models(cloud_enabled=cloud_enabled)

# Maps pour les sélecteurs (libellés « Nom · Local » / « Nom · Cloud »)
display_to_tag, tag_to_friendly, sorted_display_names = model_options(installed_models_list)

st.title(ARENA.title)
st.caption("Converser avec un modèle, tester un scénario, comparer des modèles et les installer.")

# --- SESSION STATE INITIALIZATION ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "lab_result" not in st.session_state:
    st.session_state.lab_result = None
if "lab_metrics" not in st.session_state:
    st.session_state.lab_metrics = None

# --- TABS ---
tab_chat, tab_lab, tab_arena, tab_manager = st.tabs(
    ["Chat libre", "Banc d'essai", "Arène", "Gestion des modèles"]
)

# ==========================================
# APPEL DES MODULES
# ==========================================
with tab_chat:
    # On calcule une valeur par défaut pour le chat (premier modèle de la liste)
    default_selected_display = sorted_display_names[0] if sorted_display_names else None
    default_selected_tag = display_to_tag.get(default_selected_display)

    # On passe les données nécessaires au composant
    render_chat_tab(
        selected_tag=default_selected_tag,
        selected_display=default_selected_display,
        display_to_tag=display_to_tag,
        sorted_display_names=sorted_display_names,
    )

with tab_lab:
    render_lab_tab(
        sorted_display_names=sorted_display_names,
        display_to_tag=display_to_tag,
        tag_to_friendly=tag_to_friendly,
    )

with tab_arena:
    render_arena_tab(
        sorted_display_names=sorted_display_names,
        display_to_tag=display_to_tag,
        tag_to_friendly=tag_to_friendly,
    )

with tab_manager:
    render_manager_tab(installed_models_list=installed_models_list)
