import nest_asyncio
import streamlit as st

from src.app.tabs.agent.crew import render_agent_crew_tab

# IMPORT DES NOUVEAUX TABS
from src.app.tabs.agent.solo import render_agent_solo_tab
from src.core.llm_provider import LLMProvider
from src.core.models_db import get_friendly_name_from_tag, get_model_info

nest_asyncio.apply()

st.set_page_config(page_title="Agent Lab", page_icon="🧪", layout="wide")
st.title("🧪 Agent Lab : Orchestration")
st.caption("Environnement d'exécution pour Agents Autonomes (LangGraph) et Équipes (CrewAI).")

if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = []

# --- 1. PRÉPARATION DES DONNÉES (GLOBAL) ---
installed = LLMProvider.list_models()

# Construction du dictionnaire : Clé (Nom Joli) -> Valeur (Tag Technique)
# + Logique de Tri : Les ✅ (Verified) d'abord
verified_models = []
other_models = []

for m in installed:
    tag = m["model"]
    friendly = get_friendly_name_from_tag(tag)
    info = get_model_info(friendly)

    # Vérification Capability "tools"
    is_verified = info and "tools" in info.get("capabilities", [])

    # Formatage du label
    label = f"✅ {friendly}" if is_verified else f"⚠️ {friendly}"

    if is_verified:
        verified_models.append((label, tag))
    else:
        other_models.append((label, tag))

# Liste triée finale (pour les menus déroulants)
sorted_options = sorted(verified_models, key=lambda x: x[0]) + sorted(
    other_models, key=lambda x: x[0]
)

# Dictionnaire de lookup pour les onglets
display_to_tag = dict(sorted_options)
# Liste des labels triés
sorted_labels = [label for label, tag in sorted_options]


# --- 2. SIDEBAR (Allégée) ---
with st.sidebar:
    st.header("⚙️ Configuration")

    agent_mode = st.radio(
        "Architecture",
        ["Solo (LangGraph)", "Crew (Multi-Agent)"],
        captions=["Rapide • Tâches simples", "Puissant • Recherche & Synthèse"],
    )

    st.divider()

    # NOUVEAU : Section de gestion mémoire
    with st.expander("💾 Gestion Mémoire", expanded=False):
        col_mem1, col_mem2 = st.columns(2)

        with col_mem1:
            # Affichage RAM disponible
            from src.core.resource_manager import ResourceManager

            avail_ram = ResourceManager.get_available_ram_gb()
            st.metric("RAM Disponible", f"{avail_ram:.1f} GB")

        with col_mem2:
            # Bouton de nettoyage
            if st.button("🧹 Libérer RAM", help="Décharge les modèles Ollama inactifs"):
                try:
                    import ollama

                    # Récupération des modèles en cours
                    running = ollama.ps()
                    if running.get("models"):
                        for model in running["models"]:
                            st.info(f"Déchargement de {model['name']}...")
                        # Force le garbage collection
                        import gc

                        gc.collect()
                        st.success("✅ Mémoire libérée")
                        st.rerun()
                    else:
                        st.info("Aucun modèle en cours d'exécution")
                except Exception as e:
                    st.error(f"Erreur : {e}")

    st.divider()

    # NOUVEAU : Information dynamique sur les outils
    from src.core.agent_tools import TOOLS_METADATA

    nb_tools = len(TOOLS_METADATA)
    st.info(
        f"""
        **🧰 {nb_tools} outils disponibles**

        Configurez les outils dans l'interface principale selon le mode :
        - **Solo** : Sélection globale des outils
        - **Crew** : Sélection par agent
        """
    )

    if st.button("🗑️ Reset Mémoire Conversation"):
        st.session_state.agent_messages = []
        st.rerun()

# --- 3. APPEL DES MODULES ---
if agent_mode == "Solo (LangGraph)":
    render_agent_solo_tab(sorted_labels, display_to_tag)
else:
    render_agent_crew_tab(installed, display_to_tag, sorted_labels)
