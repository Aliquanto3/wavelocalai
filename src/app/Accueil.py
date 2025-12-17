import logging
import sys
from pathlib import Path

import psutil
import streamlit as st

# --- IMPORT SSOT ---
try:
    from src.core.green_monitor import GreenTracker
except ImportError:
    GreenTracker = None

# --- CONFIGURATION INITIALE ---
st.set_page_config(
    page_title="WaveLocalAI | GenAI Souveraine",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- SETUP PATH & LOGGING ---
root_path = Path(__file__).parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

logger = logging.getLogger(__name__)

# --- GESTION ÉTAT (Cloud vs Local) ---
if "cloud_enabled" not in st.session_state:
    st.session_state.cloud_enabled = True

# --- INIT TRACKER (Singleton) ---
if "tracker" not in st.session_state and GreenTracker:
    st.session_state.tracker = GreenTracker(project_name="wavelocal_session")
    st.session_state.tracker.start()
    st.session_state.tracking_active = True


# ==========================================
# NOUVEAU CALLBACK POUR SYNCHRONISATION
# ==========================================
def update_cloud_state():
    """
    Callback exécuté immédiatement après le changement de st.toggle.
    Ceci garantit que la session state est mise à jour AVANT le rerun,
    évitant l'effet de désynchronisation.
    """
    # La valeur du toggle est passée via la clé 'global_cloud_toggle'
    st.session_state.cloud_enabled = st.session_state.global_cloud_toggle
    # Le rerun n'est pas nécessaire ici car Streamlit le fera après le callback,
    # mais la mise à jour immédiate est cruciale.


def get_system_health():
    """Petit check rapide pour l'accueil."""
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory().percent
    return cpu, mem


def main():
    # --- HERO SECTION ---
    st.title("🌊 WaveLocalAI Workbench")
    st.markdown(
        "### Le démonstrateur d'IA Générative **Souveraine**, **Frugale** et **Sécurisée**."
    )

    st.divider()

    # --- KPI STATUS BAR (DYNAMIQUE) ---
    cpu, mem = get_system_health()

    # Logique d'affichage Confidentialité
    # Elle lit directement la st.session_state mise à jour par le callback
    if st.session_state.cloud_enabled:
        privacy_label = "Mode Hybride ☁️"
        privacy_val = "API Active"
        privacy_help = "⚠️ Attention : Les modèles Cloud (Mistral/OpenAI) sont activés. Les données envoyées à ces modèles quittent votre infrastructure."
    else:
        privacy_label = "Confidentialité"
        privacy_val = "100% Local 🔒"
        privacy_help = "✅ Sécurisé : Tous les modèles tournent sur cette machine (Ollama). Aucune donnée ne sort."

    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

    with col_kpi1:
        st.metric("Système", "Opérationnel 🟢", help="Tous les services sont actifs")
    with col_kpi2:
        st.metric("Charge CPU", f"{cpu}%", help="Charge actuelle du processeur")
    with col_kpi3:
        st.metric("Mémoire RAM", f"{mem}%", help="Occupation de la mémoire vive")
    with col_kpi4:
        st.metric(privacy_label, privacy_val, help=privacy_help)

    st.divider()

    # --- NAVIGATION GRID (2x2) ---
    st.subheader("📍 Modules d'exploration")

    row1_1, row1_2 = st.columns(2)
    row2_1, row2_2 = st.columns(2)

    # CARD 1 : HARDWARE
    with row1_1, st.container(border=True):
        c_ico, c_txt = st.columns([1, 5])
        with c_ico:
            st.markdown("# 🔋")
        with c_txt:
            st.markdown("#### 01. Cockpit GreenOps")
            st.caption(
                "Monitoring temps réel de la consommation énergétique et des ressources machine."
            )
            st.page_link("pages/01_Socle_Hardware.py", label="Accéder au Cockpit", icon="📊")

    # CARD 2 : INFERENCE
    with row1_2, st.container(border=True):
        c_ico, c_txt = st.columns([1, 5])
        with c_ico:
            st.markdown("# 🧠")
        with c_txt:
            st.markdown("#### 02. Inférence & Arena")
            st.caption(
                "Benchmark et chat avec des modèles SLM quantizés (Llama 3, Mistral, Gemma)."
            )
            st.page_link("pages/02_Inference_Arena.py", label="Entrer dans l'Arène", icon="⚔️")

    # CARD 3 : RAG
    with row2_1, st.container(border=True):
        c_ico, c_txt = st.columns([1, 5])
        with c_ico:
            st.markdown("# 📚")
        with c_txt:
            st.markdown("#### 03. Base de Connaissance (RAG)")
            st.caption("Interrogation documentaire sécurisée sans fuite de données.")
            st.page_link("pages/03_RAG_Knowledge.py", label="Gérer les Documents", icon="📂")

    # CARD 4 : AGENTS
    with row2_2, st.container(border=True):
        c_ico, c_txt = st.columns([1, 5])
        with c_ico:
            st.markdown("# 🤖")
        with c_txt:
            st.markdown("#### 04. Agents Autonomes")
            st.caption("Orchestration d'équipes d'agents pour des tâches complexes (CrewAI).")
            st.page_link("pages/04_Agent_Lab.py", label="Lancer les Agents", icon="🚀")

    # --- FOOTER ---
    st.markdown("---")

    # Toggle global pour contrôler la confidentialité depuis l'accueil
    c_toggle, c_copyright = st.columns([1, 3])
    with c_toggle:
        # 1. Utilisation de on_change=update_cloud_state
        # 2. Key simple pour le lire dans le callback
        st.session_state.cloud_enabled = st.toggle(
            "Autoriser les API Cloud (Mistral/OpenAI)",
            value=st.session_state.cloud_enabled,
            key="global_cloud_toggle",
            on_change=update_cloud_state,  # L'élément clé
            help="Désactivez pour forcer un mode strictement local sur toutes les pages.",
        )
        if not st.session_state.cloud_enabled:
            st.caption("🔒 Mode Local Strict activé")

    with c_copyright:
        st.caption("© 2025 WaveLocalAI - Wavestone Tech Lab | v2.0.0 (Stable)")


if __name__ == "__main__":
    main()
