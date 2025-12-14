import streamlit as st

from src.app.tabs.inference.arena import render_arena_tab

# IMPORT DES NOUVEAUX TABS
from src.app.tabs.inference.chat import render_chat_tab
from src.app.tabs.inference.lab import render_lab_tab
from src.app.tabs.inference.manager import render_manager_tab
from src.core.llm_provider import LLMProvider
from src.core.models_db import get_friendly_name_from_tag

# --- Configuration de la Page ---
st.set_page_config(page_title="Inférence & Arena", page_icon="🧠", layout="wide")

# --- CSS Custom ---
st.markdown(
    """
<style>
    [data-testid="stMetricValue"] { font-size: 24px; }
    .stTextArea textarea { font-family: monospace; }
</style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 1. SIDEBAR & CONFIGURATION GLOBALE
# ==========================================
with st.sidebar:
    st.header("⚙️ Configuration")

    # Global Cloud Toggle (Persistant)
    if "cloud_enabled" not in st.session_state:
        st.session_state.cloud_enabled = True

    cloud_enabled = st.toggle(
        "Activer Cloud (Mistral)",
        value=st.session_state.cloud_enabled,
        help="Si désactivé, seuls les modèles locaux (Ollama) seront accessibles.",
    )
    st.session_state.cloud_enabled = cloud_enabled
    st.divider()

    if not cloud_enabled:
        st.caption("🔒 Mode Local Strict")
    else:
        st.caption("☁️ Mode Hybride")

# ==========================================
# 2. CHARGEMENT CENTRALISÉ DES MODÈLES
# ==========================================
installed_models_list = LLMProvider.list_models(cloud_enabled=cloud_enabled)


def format_model_label(model_data):
    """Helper pour l'affichage avec icônes dans les SelectBox"""
    tag = model_data["model"]
    is_cloud = model_data.get("type") == "cloud"
    friendly = get_friendly_name_from_tag(tag)
    icon = "☁️" if is_cloud else "💻"
    return f"{icon} {friendly}"


# Maps pour les sélecteurs
display_to_tag = {format_model_label(m): m["model"] for m in installed_models_list}
tag_to_friendly = {
    m["model"]: get_friendly_name_from_tag(m["model"]) for m in installed_models_list
}
sorted_display_names = sorted(display_to_tag.keys())

st.title("🧠 Inférence & Model Arena")
st.caption("Benchmark technique et fonctionnel des SLM.")

# --- SESSION STATE INITIALIZATION ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "lab_result" not in st.session_state:
    st.session_state.lab_result = None
if "lab_metrics" not in st.session_state:
    st.session_state.lab_metrics = None

# --- TABS ---
tab_chat, tab_lab, tab_arena, tab_manager = st.tabs(
    ["💬 Chat Libre", "🧪 Labo de Tests", "⚔️ Arena", "⚙️ Gestion Modèles"]
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
