import time

import nest_asyncio
import psutil
import streamlit as st

from src.app.tabs.agent.crew import render_agent_crew_tab
from src.app.tabs.agent.solo import clear_email_drafts, render_agent_solo_tab
from src.app.formatting import format_gb, format_percent, format_unit
from src.app.modules import AGENTS
from src.app.ui import FAVICON_PATH, cloud_enabled, model_menu
from src.core.llm_provider import LLMProvider
from src.core.models_db import get_friendly_name_from_tag, get_model_info

nest_asyncio.apply()

st.set_page_config(page_title=AGENTS.title, page_icon=FAVICON_PATH, layout="wide")

MODE_SOLO = "Agent seul"
MODE_CREW = "Équipe d'agents"
# Mémoire vive recommandée pour lancer un agent (Go).
RECOMMENDED_RAM_GB = 4.0

# --- INITIALISATION GLOBALE ---
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = []
if "carbon_budget" not in st.session_state:
    st.session_state.carbon_budget = 100.0  # Budget arbitraire pour la session (Gamification)

# --- HEADER ---
st.title(AGENTS.title)
st.caption("Confiez une tâche outillée à un agent seul ou à une équipe d'agents.")

# --- BARRE LATÉRALE ---
with st.sidebar:
    st.divider()

    # A. Mode
    # Aide sur le titre : un libellé masqué (collapsed) masque aussi l'aide du widget.
    st.subheader("Mode", help="Agent seul : LangGraph. Équipe d'agents : CrewAI.")
    agent_mode = st.radio(
        "Mode",
        [MODE_SOLO, MODE_CREW],
        label_visibility="collapsed",
        captions=["Rapide, pour les tâches simples", "Pour la recherche et la synthèse"],
    )

    st.divider()

    # B. Mémoire (critique sur les petites machines)
    st.subheader("Santé du système")

    # Récupération RAM Live
    avail_ram = psutil.virtual_memory().available / (1024**3)
    total_ram = psutil.virtual_memory().total / (1024**3)
    percent_used = psutil.virtual_memory().percent

    st.metric(
        "Mémoire disponible",
        format_gb(avail_ram),
        delta=format_unit(avail_ram - RECOMMENDED_RAM_GB, "Go"),
        delta_color="normal" if avail_ram > RECOMMENDED_RAM_GB else "inverse",
        help=f"Écart avec les {format_gb(RECOMMENDED_RAM_GB, 0)} recommandés",
    )
    st.caption(f"Utilisation : {format_percent(percent_used)} de {format_gb(total_ram, 0)}")

    if avail_ram < 1.0:
        st.error("Mémoire vive presque saturée : l'application risque de s'arrêter.")

    # Bouton de Purge (secondaire : l'alerte RAM ci-dessus signale l'urgence, et l'action
    # principale de la vue reste celle du module)
    if st.button("Libérer la mémoire", icon=":material/memory:", width="stretch"):
        try:
            import gc

            import torch

            # Nettoyage, sans effacer la conversation : une question bloquée par le garde-fou
            # mémoire doit rester dans l'historique (« Effacer la conversation » le fait).
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            st.toast("Mémoire libérée.", icon=":material/check_circle:")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Échec de la libération de la mémoire : {e}")

    st.divider()

    if st.button("Effacer la conversation", icon=":material/delete:", width="stretch"):
        st.session_state.agent_messages = []
        # Un brouillon d'email en attente disparaît avec la conversation.
        clear_email_drafts()
        st.rerun()

# --- PRÉPARATION DATA ---
installed = LLMProvider.list_models(cloud_enabled=cloud_enabled())
# Ordre : locaux avant cloud, puis ceux qui tiennent en mémoire, puis outils vérifiés, puis
# la règle commune (le plus rapide en tête) : un modèle cloud ou un local qui ne tient pas ne
# devient jamais le modèle par défaut parce que ses outils sont vérifiés. Tri stable.
menu = model_menu(installed, cloud_types=("api", "cloud"))
options = []
for label in menu.labels:
    tag = menu.display_to_tag[label]
    choice = menu.choices[label]
    # Nom du catalogue (pas le nom affiché, qui peut porter le tag).
    info = get_model_info(get_friendly_name_from_tag(tag))
    is_verified = bool(info and "tools" in info.get("capabilities", []))
    # Remplace l'ancien marqueur emoji : support des outils vérifié dans le catalogue.
    shown = f"{label} · outils vérifiés" if is_verified else label
    options.append(((choice.is_cloud, not choice.fits, not is_verified), shown, tag))

sorted_options = [(label, tag) for _, label, tag in sorted(options, key=lambda o: o[0])]
display_to_tag = dict(sorted_options)
sorted_labels = [label for label, tag in sorted_options]

# --- ROUTING ---
if agent_mode == MODE_SOLO:
    render_agent_solo_tab(sorted_labels, display_to_tag, menu=menu)
else:
    # L'équipe n'envoie jamais d'email : aucun brouillon de l'agent seul ne reste en attente.
    clear_email_drafts()
    # On passe la RAM dispo à Crew pour le calcul prédictif
    render_agent_crew_tab(display_to_tag, sorted_labels, avail_ram_gb=avail_ram, menu=menu)
