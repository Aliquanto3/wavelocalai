import time

import nest_asyncio
import psutil
import streamlit as st

from src.app.tabs.agent.crew import render_agent_crew_tab
from src.app.tabs.agent.solo import render_agent_solo_tab
from src.core.llm_provider import LLMProvider
from src.core.models_db import get_friendly_name_from_tag, get_model_info

nest_asyncio.apply()

st.set_page_config(page_title="Agent Lab", page_icon="🧪", layout="wide")

# --- INITIALISATION GLOBALE ---
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = []
if "carbon_budget" not in st.session_state:
    st.session_state.carbon_budget = 100.0  # Budget arbitraire pour la session (Gamification)

# --- HEADER ---
col_title, col_status = st.columns([3, 1])
with col_title:
    st.title("🧪 Agent Lab")
    st.caption("Orchestration d'IA Locale : Solo (LangGraph) & Équipes (CrewAI)")

# --- SIDEBAR : COCKPIT GREENOPS ---
with st.sidebar:
    st.header("⚙️ Pilote")

    # A. Paramètres Modèles
    if "cloud_enabled" not in st.session_state:
        st.session_state.cloud_enabled = True

    st.session_state.cloud_enabled = st.toggle(
        "Activer Cloud (Mistral)",
        value=st.session_state.cloud_enabled,
        help="Si désactivé, seuls les modèles locaux (Ollama) seront accessibles.",
    )

    st.divider()

    # B. Architecture
    st.subheader("Architecture")
    agent_mode = st.radio(
        "Mode",
        ["Solo (LangGraph)", "Crew (Multi-Agent)"],
        label_visibility="collapsed",
        captions=["Rapide • Tâches simples", "Puissant • Recherche & Synthèse"],
    )

    st.divider()

    # C. Santé Système (Kritik pour 2.8GB RAM)
    st.subheader("🖥️ Santé Système")

    # Récupération RAM Live
    avail_ram = psutil.virtual_memory().available / (1024**3)
    total_ram = psutil.virtual_memory().total / (1024**3)
    percent_used = psutil.virtual_memory().percent

    # Jauge colorée selon le danger
    ram_color = "normal"
    if avail_ram < 4.0:
        ram_color = "off"  # Gris/Rouge selon theme

    st.metric(
        "RAM Disponible",
        f"{avail_ram:.1f} GB",
        delta=f"{avail_ram - 4.0:.1f} GB vs Requis",
        delta_color="normal" if avail_ram > 4 else "inverse",
    )
    st.caption(f"Utilisation : {percent_used}% de {total_ram:.0f} GB")

    if avail_ram < 1.0:
        st.error("⚠️ RAM CRITIQUE ! Risque de crash.")

    # Bouton de Purge (Mise en avant si critique)
    btn_type = "primary" if avail_ram < 3.0 else "secondary"
    if st.button("🧹 Purger Mémoire & VRAM", type=btn_type, use_container_width=True):
        try:
            import gc

            import torch

            # Nettoyage
            del st.session_state["agent_messages"]
            st.session_state.agent_messages = []
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            st.toast("🧹 Mémoire libérée !", icon="✨")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Erreur purge: {e}")

    st.divider()

    if st.button("🗑️ Reset Chat", use_container_width=True):
        st.session_state.agent_messages = []
        st.rerun()

# --- PRÉPARATION DATA ---
installed = LLMProvider.list_models(cloud_enabled=st.session_state.cloud_enabled)
verified_models = []
other_models = []

for m in installed:
    tag = m["model"]
    friendly = get_friendly_name_from_tag(tag)
    info = get_model_info(friendly)
    is_verified = info and "tools" in info.get("capabilities", [])
    prefix = "☁️" if m.get("type") in ["api", "cloud"] else ("✅" if is_verified else "⚠️")
    label = f"{prefix} {friendly}"
    if is_verified:
        verified_models.append((label, tag))
    else:
        other_models.append((label, tag))

sorted_options = sorted(verified_models, key=lambda x: x[0]) + sorted(
    other_models, key=lambda x: x[0]
)
display_to_tag = dict(sorted_options)
sorted_labels = [label for label, tag in sorted_options]

# --- ROUTING ---
if agent_mode == "Solo (LangGraph)":
    render_agent_solo_tab(sorted_labels, display_to_tag)
else:
    # On passe la RAM dispo à Crew pour le calcul prédictif
    render_agent_crew_tab(installed, display_to_tag, sorted_labels, avail_ram_gb=avail_ram)
