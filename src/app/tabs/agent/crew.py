"""
Crew Agent Tab - Interface pour équipes multi-agents avec sélection d'outils par agent.

Corrections :
- Clé unique pour les logs (utilisation d'un compteur au lieu du hash)
- Nettoyage des codes ANSI dans les logs
- Historique complet des logs avec scroll
"""

import io
import re
import time
import traceback
from contextlib import redirect_stdout

import psutil
import streamlit as st

from src.core.agent_tools import TOOLS_METADATA
from src.core.crew_engine import CrewFactory
from src.core.green_monitor import GreenTracker
from src.core.resource_manager import ResourceManager

# ========================================
# BIBLIOTHÈQUE DE WORKFLOWS MULTI-AGENTS
# ========================================

CREW_PROMPT_LIBRARY = {
    "📊 Analyse de Marché": {
        "Étude concurrentielle complète": {
            "prompt": "Analyser le marché des SLM en 2024 : acteurs, tendances, opportunités",
            "description": "Analyse approfondie avec recherche, calculs et rapport",
            "suggested_crew": [
                {
                    "role": "Chercheur de Marché",
                    "goal": "Collecter des données factuelles sur le marché des SLM",
                    "backstory": "Expert en veille concurrentielle, tu utilises tous les outils de recherche disponibles.",
                    "tools": ["get_current_time", "search_wavestone_internal", "system_monitor"],
                },
                {
                    "role": "Analyste Financier",
                    "goal": "Calculer les métriques clés et ROI",
                    "backstory": "Spécialiste en analyse financière et calculs complexes.",
                    "tools": ["calculator", "analyze_csv", "generate_chart"],
                },
                {
                    "role": "Rédacteur Senior",
                    "goal": "Synthétiser les résultats en rapport professionnel",
                    "backstory": "Expert en communication écrite, tu produis des documents impeccables.",
                    "tools": ["generate_document", "generate_markdown_report"],
                },
            ],
        },
    },
    "🔬 Analyse de Données": {
        "Pipeline d'analyse complète": {
            "prompt": "Analyser les benchmarks dans data/benchmarks_data.csv et produire un rapport complet avec graphiques",
            "description": "Analyse de données, visualisation et documentation",
            "suggested_crew": [
                {
                    "role": "Data Analyst",
                    "goal": "Analyser en profondeur le fichier CSV de benchmarks",
                    "backstory": "Spécialiste en traitement de données, tu maîtrises l'analyse statistique.",
                    "tools": ["analyze_csv", "calculator", "system_monitor"],
                },
                {
                    "role": "Data Visualizer",
                    "goal": "Créer des graphiques percutants à partir des données",
                    "backstory": "Expert en visualisation, tu transformes les chiffres en insights visuels.",
                    "tools": ["generate_chart", "analyze_csv"],
                },
                {
                    "role": "Technical Writer",
                    "goal": "Documenter l'analyse dans un rapport structuré",
                    "backstory": "Rédacteur technique senior, tu produis une documentation claire et professionnelle.",
                    "tools": ["generate_document", "generate_markdown_report"],
                },
            ],
        },
        "Monitoring système automatisé": {
            "prompt": "Surveiller l'état du système, détecter les anomalies et envoyer un rapport par email",
            "description": "Monitoring, analyse et notification",
            "suggested_crew": [
                {
                    "role": "System Monitor",
                    "goal": "Surveiller en continu les métriques système (CPU, RAM, Disque)",
                    "backstory": "Expert en infrastructure, tu détectes les moindres anomalies.",
                    "tools": ["system_monitor", "get_current_time"],
                },
                {
                    "role": "Alert Manager",
                    "goal": "Analyser les métriques et identifier les problèmes critiques",
                    "backstory": "Spécialiste en SRE, tu établis des diagnostics précis.",
                    "tools": ["calculator", "system_monitor"],
                },
                {
                    "role": "Communication Manager",
                    "goal": "Rédiger et envoyer les rapports de monitoring",
                    "backstory": "Responsable communication, tu assures la bonne diffusion de l'information.",
                    "tools": ["generate_markdown_report", "send_email"],
                },
            ],
        },
    },
    "📈 Reporting Automatisé": {
        "Rapport exécutif complet": {
            "prompt": "Produire un rapport exécutif sur les performances des SLM avec données, graphiques et recommandations",
            "description": "Collecte, analyse, visualisation et synthèse",
            "suggested_crew": [
                {
                    "role": "Data Collector",
                    "goal": "Collecter toutes les données pertinentes sur les performances",
                    "backstory": "Spécialiste en collecte de données, tu ne laisses rien au hasard.",
                    "tools": ["analyze_csv", "search_wavestone_internal", "system_monitor"],
                },
                {
                    "role": "Performance Analyst",
                    "goal": "Analyser les métriques et calculer les KPIs",
                    "backstory": "Expert en métriques de performance, tu identifies les tendances clés.",
                    "tools": ["calculator", "analyze_csv", "generate_chart"],
                },
                {
                    "role": "Executive Reporter",
                    "goal": "Synthétiser en rapport exécutif pour la direction",
                    "backstory": "Consultant senior, tu communiques efficacement aux décideurs.",
                    "tools": ["generate_document", "generate_chart"],
                },
                {
                    "role": "Distributor",
                    "goal": "Distribuer le rapport aux parties prenantes",
                    "backstory": "Coordinateur projet, tu assures la diffusion de l'information.",
                    "tools": ["send_email"],
                },
            ],
        },
    },
    "🎯 Workflows Spécialisés": {
        "Benchmark FinOps / GreenOps": {
            "prompt": "Comparer les coûts et émissions CO2 entre modèles locaux et cloud, puis générer un rapport détaillé",
            "description": "Analyse comparative approfondie",
            "suggested_crew": [
                {
                    "role": "FinOps Analyst",
                    "goal": "Analyser les coûts de chaque solution (Local vs Cloud)",
                    "backstory": "Expert FinOps, tu optimises les dépenses cloud et infrastructure.",
                    "tools": ["calculator", "analyze_csv", "search_wavestone_internal"],
                },
                {
                    "role": "GreenOps Specialist",
                    "goal": "Mesurer et comparer l'impact carbone",
                    "backstory": "Spécialiste en IT durable, tu quantifies l'empreinte environnementale.",
                    "tools": ["calculator", "system_monitor", "generate_chart"],
                },
                {
                    "role": "Strategic Advisor",
                    "goal": "Synthétiser les analyses et formuler des recommandations",
                    "backstory": "Consultant stratégie IT, tu guides les décisions d'architecture.",
                    "tools": ["generate_document", "generate_markdown_report"],
                },
            ],
        },
        "Documentation projet complète": {
            "prompt": "Créer une documentation technique complète pour le projet WaveLocalAI",
            "description": "Documentation multi-formats avec architecture et guides",
            "suggested_crew": [
                {
                    "role": "Tech Lead",
                    "goal": "Définir l'architecture et les composants techniques",
                    "backstory": "Architecte logiciel senior, tu conçois des systèmes robustes.",
                    "tools": ["system_monitor", "analyze_csv"],
                },
                {
                    "role": "Technical Writer",
                    "goal": "Rédiger la documentation technique détaillée",
                    "backstory": "Expert en documentation, tu produis des guides clairs et complets.",
                    "tools": ["generate_document", "generate_markdown_report"],
                },
                {
                    "role": "Diagram Specialist",
                    "goal": "Créer les schémas et visualisations d'architecture",
                    "backstory": "Spécialiste en modélisation, tu illustres les concepts complexes.",
                    "tools": ["generate_chart"],
                },
            ],
        },
    },
}


# ========================================
# HELPER POUR CAPTURER LES LOGS
# ========================================


class StreamlitCapture(io.StringIO):
    """
    Capture les logs CrewAI avec nettoyage ANSI et historique complet.

    CORRECTION : Utilisation d'un compteur d'updates au lieu du hash pour éviter les clés dupliquées.
    """

    # Compteur de classe pour générer des clés uniques
    _update_counter = 0

    def __init__(self, container):
        super().__init__()
        self.container = container
        self.full_text = ""
        self.max_display = 15000  # Caractères max à afficher

        # Pattern regex pour les codes ANSI
        self.ansi_pattern = re.compile(r"\x1b\[[0-9;]*[mHJK]|\x1b\([0-9;]*m")

        # Pattern pour les caractères de box drawing
        self.box_chars = str.maketrans(
            {
                "─": "-",
                "│": "|",
                "┌": "+",
                "┐": "+",
                "└": "+",
                "┘": "+",
                "├": "+",
                "┤": "+",
                "┬": "+",
                "┴": "+",
                "┼": "+",
                "╭": "+",
                "╮": "+",
                "╰": "+",
                "╯": "+",
                "╔": "+",
                "╗": "+",
                "╚": "+",
                "╝": "+",
                "═": "=",
                "║": "|",
                "╠": "+",
                "╣": "+",
                "╦": "+",
                "╩": "+",
                "╬": "+",
            }
        )

    def clean_ansi(self, text: str) -> str:
        """Nettoie les codes ANSI et caractères de box drawing."""
        # Suppression des codes couleur ANSI
        text = self.ansi_pattern.sub("", text)

        # Remplacement des caractères de box drawing
        text = text.translate(self.box_chars)

        return text

    def write(self, s):
        """Capture et affiche les logs avec nettoyage."""
        self.full_text += s

        if s.strip():
            # Nettoyage des codes ANSI
            clean_text = self.clean_ansi(self.full_text)

            # Limitation pour l'affichage
            display_text = clean_text[-self.max_display :]

            # Indicateur si tronqué
            if len(clean_text) > self.max_display:
                hidden_chars = len(clean_text) - self.max_display
                display_text = (
                    f"[... {hidden_chars} caractères d'historique masqués ...]\n\n" + display_text
                )

            # CORRECTION : Utilisation d'un compteur au lieu du hash
            StreamlitCapture._update_counter += 1

            # Affichage avec scroll
            self.container.text_area(
                "📜 Historique des logs de collaboration",
                value=display_text,
                height=500,  # Hauteur fixe pour le scroll
                key=f"crew_logs_update_{StreamlitCapture._update_counter}",  # Clé unique avec compteur
                disabled=True,
                help="Logs complets avec scroll - Les codes de couleur ANSI ont été nettoyés pour une meilleure lisibilité",
            )


# ========================================
# INTERFACE PRINCIPALE
# ========================================


def render_agent_crew_tab(installed_models_list: list, display_to_tag: dict, sorted_labels: list):
    """
    Rendu de l'onglet Multi-Agent avec sélection d'outils par agent et prompts prédéfinis.
    """

    # IMPORTANT : Réinitialiser le compteur au début de chaque rendu
    StreamlitCapture._update_counter = 0

    st.subheader("🤖 Orchestration Multi-Agents (Dynamique)")
    st.caption(
        "Composez votre équipe, assignez les outils et modèles, et observez la collaboration."
    )

    # ========================================
    # SECTION 1 : BIBLIOTHÈQUE DE WORKFLOWS
    # ========================================

    with st.expander("📚 Bibliothèque de Workflows Prédéfinis", expanded=False):
        st.markdown("*Sélectionnez un workflow pour pré-configurer une équipe d'agents optimisée*")

        # Sélection par catégorie
        workflow_category = st.selectbox(
            "Catégorie de workflow",
            options=list(CREW_PROMPT_LIBRARY.keys()),
            key="workflow_category",
        )

        workflows_in_category = CREW_PROMPT_LIBRARY[workflow_category]

        # Affichage des workflows disponibles
        for workflow_name, workflow_data in workflows_in_category.items():
            with st.container(border=True):
                col_info, col_action = st.columns([3, 1])

                with col_info:
                    st.markdown(f"**{workflow_name}**")
                    st.caption(workflow_data["description"])
                    st.info(f"🎯 Mission : *{workflow_data['prompt']}*")
                    st.caption(f"👥 {len(workflow_data['suggested_crew'])} agent(s) suggéré(s)")

                with col_action:
                    if st.button("🚀 Charger", key=f"load_{workflow_name}"):
                        # Chargement de l'équipe pré-configurée
                        default_tag = (
                            installed_models_list[0]["model"] if installed_models_list else ""
                        )

                        st.session_state.crew_agents = []
                        for agent_config in workflow_data["suggested_crew"]:
                            st.session_state.crew_agents.append(
                                {
                                    "role": agent_config["role"],
                                    "goal": agent_config["goal"],
                                    "backstory": agent_config["backstory"],
                                    "model_tag": default_tag,
                                    "tools": agent_config.get("tools", []),
                                }
                            )

                        st.session_state.crew_topic = workflow_data["prompt"]
                        if "mission_input_key" not in st.session_state:
                            st.session_state.mission_input_key = 0
                        st.session_state.mission_input_key += 1

                        st.success(
                            f"✅ Équipe chargée ! {len(st.session_state.crew_agents)} agent(s) prêt(s)"
                        )
                        st.rerun()

    st.divider()

    # ========================================
    # SECTION 2 : COMPOSITION DE L'ÉQUIPE
    # ========================================

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
                    "tools": [],  # Pas d'outils par défaut
                }
            ]

        agents_to_remove = []

        for i, agent in enumerate(st.session_state.crew_agents):
            st.markdown(f"**Agent #{i+1}**")
            c1, c2, c3, c4 = st.columns([1, 1, 1, 1])

            with c1:
                agent["role"] = st.text_input("Rôle", agent["role"], key=f"role_{i}")
                agent["goal"] = st.text_input("Objectif", agent["goal"], key=f"goal_{i}")

            with c2:
                # Sélection du modèle
                current_tag = agent.get("model_tag")
                current_friendly = next(
                    (k for k, v in display_to_tag.items() if v == current_tag), None
                )

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
                # Sélection des outils pour cet agent
                st.markdown("🧰 **Outils**")

                # Liste des outils disponibles
                available_tool_names = list(TOOLS_METADATA.keys())
                tool_labels = [TOOLS_METADATA[t]["name"] for t in available_tool_names]

                # Récupération des outils actuels de l'agent
                current_tools = agent.get("tools", [])

                # Multiselect pour choisir les outils
                selected_tool_labels = st.multiselect(
                    "Sélectionner",
                    options=tool_labels,
                    default=[
                        TOOLS_METADATA[t]["name"] for t in current_tools if t in TOOLS_METADATA
                    ],
                    key=f"tools_{i}",
                    help="Sélectionnez les outils que cet agent pourra utiliser",
                )

                # Conversion des labels en noms techniques
                label_to_name = {TOOLS_METADATA[t]["name"]: t for t in available_tool_names}
                agent["tools"] = [
                    label_to_name[label] for label in selected_tool_labels if label in label_to_name
                ]

                # Affichage du nombre d'outils
                st.caption(f"🔧 {len(agent['tools'])} outil(s)")

            with c4:
                # Prompt Système (Backstory)
                agent["backstory"] = st.text_area(
                    "Backstory",
                    agent.get("backstory", ""),
                    height=90,
                    key=f"back_{i}",
                )

            # Bouton de suppression
            col_del = st.columns([6, 1])
            if col_del[1].button("🗑️ Supprimer", key=f"del_{i}"):
                agents_to_remove.append(i)

            st.divider()

        # Suppression effective
        for i in reversed(agents_to_remove):
            st.session_state.crew_agents.pop(i)
            st.rerun()

        # Bouton d'ajout
        if st.button("➕ Ajouter un Agent"):
            default_tag = installed_models_list[0]["model"] if installed_models_list else ""
            st.session_state.crew_agents.append(
                {
                    "role": "Analyste",
                    "goal": "Synthétiser",
                    "model_tag": default_tag,
                    "backstory": "Tu es concis et analytique.",
                    "tools": [],  # Pas d'outils par défaut
                }
            )
            st.rerun()

    # ========================================
    # SECTION 3 : MISSION GLOBALE
    # ========================================

    # Initialisation du topic
    if "crew_topic" not in st.session_state:
        st.session_state.crew_topic = "Analyser l'impact de l'IA sur le conseil."

    crew_topic = st.text_input(
        "🎯 Mission Globale",
        value=st.session_state.crew_topic,
        key=f"mission_input_{st.session_state.get('mission_input_key', 0)}",  # Key dynamique
    )
    st.session_state.crew_topic = crew_topic

    # ========================================
    # SECTION 4 : EXÉCUTION
    # ========================================

    if st.button("🚀 Lancer la Mission Multi-Agents", type="primary"):
        if not st.session_state.crew_agents:
            st.error("❌ Il faut au moins un agent !")
            st.stop()

        # Affichage du résumé de l'équipe
        with st.expander("📋 Résumé de l'équipe", expanded=True):
            for i, agent in enumerate(st.session_state.crew_agents):
                st.markdown(
                    f"""
                **Agent {i+1} : {agent['role']}**
                - Objectif : {agent['goal']}
                - Modèle : {agent['model_tag']}
                - Outils : {', '.join([TOOLS_METADATA[t]['name'] for t in agent['tools']]) if agent['tools'] else 'Aucun'}
                """
                )

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

        # Exécution
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
                    # Création de la Crew avec la config utilisateur
                    crew = CrewFactory.create_custom_crew(st.session_state.crew_agents, crew_topic)

                    # Lancement
                    result = crew.kickoff()

                    # Fin du tracking
                    t_end = time.perf_counter()
                    ram_end = psutil.virtual_memory().used / (1024**3)
                    ram_peak = max(0, ram_end - ram_start)

                    # Affichage des résultats
                    st.success("✅ Mission terminée !")

                    col_m1, col_m2, col_m3 = st.columns(3)
                    with col_m1:
                        st.metric("⏱️ Durée", f"{t_end - t_start:.2f} s")
                    with col_m2:
                        st.metric("👥 Agents", len(st.session_state.crew_agents))
                    with col_m3:
                        st.metric("💾 RAM (Delta)", f"{ram_peak:.2f} GB")

                    st.divider()

                    # Résultat final
                    st.subheader("📄 Résultat de la Collaboration")
                    st.markdown(result)

                except Exception as e:
                    st.error(f"💥 Erreur lors de l'exécution : {e}")
                    with st.expander("🔍 Traceback complet"):
                        st.code(traceback.format_exc())
