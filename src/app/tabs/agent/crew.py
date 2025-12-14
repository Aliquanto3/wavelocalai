import io
import time
import traceback
from contextlib import redirect_stdout

import psutil
import streamlit as st

from src.core.crew_engine import CrewFactory
from src.core.green_monitor import GreenTracker
from src.core.resource_manager import ResourceManager


# Helper pour capturer les logs de CrewAI
class StreamlitCapture(io.StringIO):
    def __init__(self, container):
        super().__init__()
        self.container = container
        self.text = ""

    def write(self, s):
        self.text += s
        if s.strip():
            # Affiche les 3000 derniers caractères pour éviter de saturer
            self.container.code(self.text[-3000:], language="text")


def render_agent_crew_tab(installed_models_list: list, display_to_tag: dict, sorted_labels: list):
    """
    Rendu de l'onglet Multi-Agent.
    sorted_labels: Liste des noms friendly déjà triés (✅ en premier)
    """
    st.subheader("🤖 Orchestration Multi-Agents (Dynamique)")
    st.caption("Composez votre équipe, assignez les modèles et observez la collaboration.")

    # --- 1. CONFIGURATION DE L'ÉQUIPE ---
    with st.expander("👥 Composition de l'équipe", expanded=True):

        # Initialisation par défaut
        if "crew_agents" not in st.session_state:
            default_tag = installed_models_list[0]["model"] if installed_models_list else ""
            st.session_state.crew_agents = [
                {
                    "role": "Chercheur",
                    "goal": "Chercher des faits",
                    "model_tag": default_tag,
                    "backstory": "Tu es un expert factuel. Tu utilises toujours tes outils avant de répondre.",
                }
            ]

        agents_to_remove = []
        for i, agent in enumerate(st.session_state.crew_agents):
            st.markdown(f"**Agent #{i+1}**")
            c1, c2, c3 = st.columns([1, 1, 1])

            with c1:
                agent["role"] = st.text_input("Rôle", agent["role"], key=f"role_{i}")
                agent["goal"] = st.text_input("Objectif", agent["goal"], key=f"goal_{i}")

            with c2:
                # LOGIQUE SELECTION MODELE (Trié)
                current_tag = agent.get("model_tag")
                # Recherche inverse du nom friendly
                current_friendly = next(
                    (k for k, v in display_to_tag.items() if v == current_tag), None
                )

                # Fallback
                if current_friendly not in sorted_labels:
                    current_friendly = sorted_labels[0] if sorted_labels else None

                if sorted_labels and current_friendly:
                    selected = st.selectbox(
                        "Modèle",
                        sorted_labels,
                        index=sorted_labels.index(current_friendly),
                        key=f"model_{i}",
                    )
                    agent["model_tag"] = display_to_tag[selected]
                else:
                    st.error("Aucun modèle")

            with c3:
                # Prompt Système (Backstory)
                agent["backstory"] = st.text_area(
                    "Prompt Système (Backstory)",
                    agent.get("backstory", ""),
                    height=108,
                    key=f"back_{i}",
                )

            col_del = st.columns([6, 1])
            if col_del[1].button("🗑️ Supprimer", key=f"del_{i}"):
                agents_to_remove.append(i)

            st.divider()

        # Suppression effective
        for i in reversed(agents_to_remove):
            st.session_state.crew_agents.pop(i)
            st.rerun()

        if st.button("➕ Ajouter un Agent"):
            default_tag = installed_models_list[0]["model"] if installed_models_list else ""
            st.session_state.crew_agents.append(
                {
                    "role": "Analyste",
                    "goal": "Synthétiser",
                    "model_tag": default_tag,
                    "backstory": "Tu es concis et analytique.",
                }
            )
            st.rerun()

    crew_topic = st.text_input("🎯 Mission Globale", "Analyser l'impact de l'IA sur le conseil.")

    # --- 2. EXECUTION ---
    if st.button("🚀 Lancer la Mission Multi-Agents", type="primary"):
        if not st.session_state.crew_agents:
            st.error("Il faut au moins un agent !")
            st.stop()

        # Pre-Flight Check RAM
        total_ram_needed = 0
        tags_used = [a["model_tag"] for a in st.session_state.crew_agents]
        for tag in set(tags_used):
            total_ram_needed += ResourceManager.estimate_model_ram(tag)

        avail = ResourceManager.get_available_ram_gb()
        if avail < total_ram_needed:
            st.warning(
                f"⚠️ Attention : Besoin estimé {total_ram_needed:.1f}GB vs Dispo {avail:.1f}GB. Risque de swap."
            )

        # --- EXECUTION ---
        log_container = st.empty()
        output_capture = StreamlitCapture(log_container)

        with (
            st.spinner("🤝 Collaboration en cours... (Voir logs ci-dessous)"),
            redirect_stdout(output_capture),
        ):

            t_start = time.perf_counter()
            ram_start = psutil.virtual_memory().used / (1024**3)

            with GreenTracker("crew_mission"):
                try:
                    crew = CrewFactory.create_custom_crew(
                        agents_config=st.session_state.crew_agents, topic=crew_topic
                    )

                    result = crew.kickoff()

                    # End Metrics
                    duration = time.perf_counter() - t_start
                    ram_end = psutil.virtual_memory().used / (1024**3)
                    ram_peak = max(0, ram_end - ram_start)

                    # --- FIX METRIQUES ---
                    usage_stats = getattr(result, "token_usage", None)
                    tokens_val = "N/A"
                    if usage_stats:
                        if isinstance(usage_stats, dict):
                            tokens_val = usage_stats.get("total_tokens", "N/A")
                        else:
                            tokens_val = getattr(usage_stats, "total_tokens", "N/A")

                    # --- AFFICHAGE ---
                    st.success("✅ Mission Terminée !")

                    st.markdown("### 📝 Rapport Final")
                    st.markdown(str(result))

                    st.markdown("---")
                    st.subheader("📊 Métriques de Session")
                    m1, m2, m3, m4 = st.columns(4)

                    m1.metric("⏱️ Durée", f"{duration:.1f} s")
                    m2.metric("🔢 Tokens Totaux", f"{tokens_val}")
                    m3.metric("💾 RAM (Delta)", f"{ram_peak:.2f} GB")
                    m4.info("🌱 Check Dashboard GreenIT")

                except Exception as e:
                    st.error(f"Erreur durant l'exécution : {e}")
                    st.code(traceback.format_exc())
