"""
Mode « Équipe d'agents » des Agents autonomes.

- Vérification avant lancement : estimation de la mémoire vive nécessaire
- Alerte si la mémoire vive manque
- Déduction du budget carbone de la session
- Structure de CREW_PROMPT_LIBRARY vérifiée par les tests
"""

import io
import re
import threading
import time
import traceback
from contextlib import redirect_stdout

import graphviz
import psutil
import streamlit as st

from src.app.formatting import format_duration, format_gb, format_unit, pluralize
from src.core.agent_tools import TOOLS_METADATA
from src.core.crew_engine import CrewFactory
from src.core.green_monitor import GreenTracker
from src.core.model_profiles import estimate_mission_ram_gb, get_ram_risk_level

# ========================================
# 1. DONNÉES & CONFIGURATION (STRUCTURE CORRIGÉE)
# ========================================

CREW_PROMPT_LIBRARY = {
    "Analyse de marché": {
        "Étude concurrentielle": {
            "prompt": "Analyser le marché des SLM en 2024 : acteurs, tendances, opportunités",
            "description": "Recherche complète du marché avec collecte de données, calcul d'indicateurs et rédaction d'un rapport stratégique",
            "suggested_crew": [
                {
                    "role": "Chercheur",
                    "goal": "Collecter données marché",
                    "backstory": "Expert en veille stratégique et analyse concurrentielle",
                    "tools": ["get_current_time", "search_wavestone_internal"],
                },
                {
                    "role": "Analyste",
                    "goal": "Calculer les indicateurs",
                    "backstory": "Analyste quantitatif spécialisé en métriques business",
                    "tools": ["calculator", "analyze_csv"],
                },
                {
                    "role": "Rédacteur",
                    "goal": "Rédiger la synthèse",
                    "backstory": "Consultant senior expert en communication stratégique",
                    "tools": ["generate_document"],
                },
            ],
        }
    },
    "Science des données": {
        "Audit des mesures": {
            "prompt": "Analyser data/benchmarks_data.csv et produire un rapport avec graphiques",
            "description": "Analyse statistique complète d'un dataset avec visualisation et documentation technique",
            "suggested_crew": [
                {
                    "role": "Analyste de données",
                    "goal": "Analyse statistique du CSV",
                    "backstory": "Data scientist spécialisé en analyse exploratoire et statistiques",
                    "tools": ["analyze_csv", "calculator"],
                },
                {
                    "role": "Expert en visualisation",
                    "goal": "Générer les graphiques",
                    "backstory": "Expert en visualisation de données et storytelling visuel",
                    "tools": ["generate_chart"],
                },
                {
                    "role": "Rédacteur technique",
                    "goal": "Documentation technique",
                    "backstory": "Rédacteur technique spécialisé en documentation data",
                    "tools": ["generate_markdown_report"],
                },
            ],
        }
    },
    "Coûts et carbone": {
        "Comparaison carbone": {
            "prompt": "Comparer coûts et CO₂ entre modèles locaux et cloud.",
            "description": "Analyse comparative des coûts et du carbone avec recommandations d'optimisation",
            "suggested_crew": [
                {
                    "role": "Analyste des coûts",
                    "goal": "Estimer les coûts du cloud et du local",
                    "backstory": "Expert en optimisation des coûts du cloud",
                    "tools": ["calculator"],
                },
                {
                    "role": "Expert carbone",
                    "goal": "Calculer l'impact CO₂",
                    "backstory": "Spécialiste en informatique durable et empreinte carbone",
                    "tools": ["system_monitor"],
                },
                {
                    "role": "Consultant",
                    "goal": "Synthèse stratégique",
                    "backstory": "Consultant senior en transformation numérique responsable",
                    "tools": ["generate_document"],
                },
            ],
        }
    },
}

# ========================================
# 2. UTILITAIRES UX
# ========================================


class StreamlitCapture(io.StringIO):
    """Capture les logs stdout pour les afficher proprement dans l'UI."""

    def __init__(self, container):
        super().__init__()
        self.container = container
        self.full_text = ""
        # On utilise des regex pour colorer les logs importants
        self.ansi_pattern = re.compile(r"\x1b\[[0-9;]*[mHJK]|\x1b\([0-9;]*m")
        self.action_pattern = re.compile(
            r"\[(\w+)\]\s*(\w+): (.*)"
        )  # [TASK] Chercheur: Tâche en cours

    def write(self, s):
        self.full_text += s

        # Mise à jour périodique et propre
        if len(self.full_text) % 500 < 50:
            clean = self.ansi_pattern.sub("", self.full_text)

            # --- MODIFICATION ICI : Simuler un terminal propre ---

            # Split par lignes pour analyse
            lines = clean.split("\n")
            display_lines = []

            for line in lines[-10:]:  # N'affiche que les 10 dernières lignes pour la performance
                match = self.action_pattern.match(line)
                if match:
                    # Rendre les étapes Crew plus lisibles
                    action, role, desc = match.groups()
                    if action == "TASK":
                        display_lines.append(f"**{role}** : *{desc}*")
                    elif action == "INFO":
                        display_lines.append(f"{desc}")
                    elif action == "SUCCESS":
                        display_lines.append(f"Succès {role} : {desc}")
                    elif action == "ERROR":
                        display_lines.append(f"Erreur {role} : {desc}")
                    else:
                        display_lines.append(line)
                else:
                    display_lines.append(line)

            # Utiliser un markdown pour la lisibilité (plus propre que st.code)
            self.container.markdown("\n".join(display_lines))


def render_crew_diagram(agents):
    if not agents:
        return
    try:
        graph = graphviz.Digraph()
        # Aucune couleur en dur : rendu Graphviz par défaut (fond blanc, encre noire),
        # lisible en thème clair comme en sombre.
        graph.attr(rankdir="LR")
        graph.attr("node", shape="box", style="rounded")
        graph.node("Start", "Début", shape="circle")
        prev_node = "Start"
        for i, agent in enumerate(agents):
            tools_count = len(agent.get("tools", []))
            tools = pluralize(tools_count, "outil")
            label = f"<{agent['role']}<BR/><FONT POINT-SIZE='10'>({tools})</FONT>>"
            node_id = f"agent_{i}"
            graph.node(node_id, label)
            graph.edge(prev_node, node_id)
            prev_node = node_id
        graph.node("End", "Rapport", shape="doublecircle")
        graph.edge(prev_node, "End")
        st.graphviz_chart(graph, width="stretch")
    except Exception:
        st.caption("Impossible d'afficher le schéma : Graphviz est-il installé ?")


# ========================================
# 3. MODALE BIBLIOTHÈQUE
# ========================================


@st.dialog("Charger une équipe")
def open_crew_library(installed_models_list):
    st.caption("Choisissez une équipe préconfigurée : ses agents et sa mission sont préremplis.")
    for cat, workflows in CREW_PROMPT_LIBRARY.items():
        st.subheader(f"{cat}")
        cols = st.columns(2)
        for i, (name, data) in enumerate(workflows.items()):
            with cols[i % 2], st.container(border=True):
                st.markdown(f"**{name}**")
                st.caption(data["description"])
                if st.button("Charger", key=f"load_{name}", width="stretch"):
                    default_tag = installed_models_list[0]["model"] if installed_models_list else ""
                    st.session_state.crew_agents = []
                    for agent in data["suggested_crew"]:
                        st.session_state.crew_agents.append(
                            {
                                "role": agent["role"],
                                "goal": agent["goal"],
                                "backstory": agent.get(
                                    "backstory", "Expert qualifié dans son domaine"
                                ),
                                "model_tag": default_tag,
                                "tools": agent.get("tools", []),
                            }
                        )
                    st.session_state.crew_topic = data["prompt"]
                    st.session_state.crew_library_loaded = True
                    st.rerun()

    if st.button("Fermer"):
        st.rerun()


# ========================================
# 4. RENDU PRINCIPAL
# ========================================


def render_agent_crew_tab(
    installed_models_list: list, display_to_tag: dict, sorted_labels: list, avail_ram_gb: float
):

    # Init session_state
    if "crew_agents" not in st.session_state:
        default_tag = installed_models_list[0]["model"] if installed_models_list else ""
        st.session_state.crew_agents = [
            {
                "role": "Analyste principal",
                "goal": "Réaliser l'analyse demandée",
                "model_tag": default_tag,
                "backstory": "Expert consultant Wavestone spécialisé en IA",
                "tools": ["calculator", "system_monitor"],
            }
        ]
    if "crew_topic" not in st.session_state:
        st.session_state.crew_topic = "Analyser l'impact de l'IA."

    if st.session_state.get("crew_library_loaded"):
        st.toast("Équipe chargée.", icon=":material/check_circle:")
        st.session_state.crew_library_loaded = False

    # --- A. TOP BAR ---
    with st.container(border=True):
        c_dash_1, c_dash_2, c_dash_3 = st.columns([4, 2, 2])
        with c_dash_1:
            st.markdown(f"**Mission :** {st.session_state.crew_topic}")
            st.caption(f"Équipe de {pluralize(len(st.session_state.crew_agents), 'agent')}")
        with c_dash_2:
            main_agent_model = st.session_state.crew_agents[0].get("model_tag", "N/A")
            friendly_lbl = next(
                (k for k, v in display_to_tag.items() if v == main_agent_model), "Plusieurs modèles"
            )
            st.markdown("**Modèle principal**")
            st.caption(friendly_lbl)
        with c_dash_3:
            if st.button("Charger une équipe", icon=":material/library_books:", width="stretch"):
                open_crew_library(installed_models_list)

    # --- B. CONFIGURATION ---
    with st.expander("Configurer l'équipe", expanded=False):
        st.markdown("**Objectif global**")
        new_topic = st.text_input(
            "Sujet de la mission", value=st.session_state.crew_topic, label_visibility="collapsed"
        )
        st.session_state.crew_topic = new_topic

        st.divider()
        st.markdown("**Membres de l'équipe**")

        n_agents = len(st.session_state.crew_agents)
        tabs = st.tabs(
            [a["role"] or f"Agent {i + 1}" for i, a in enumerate(st.session_state.crew_agents)]
            + ["Ajouter un agent"]
        )

        for i, agent in enumerate(st.session_state.crew_agents):
            with tabs[i]:
                c_conf_1, c_conf_2 = st.columns([2, 1])
                with c_conf_1:
                    agent["role"] = st.text_input("Rôle", agent["role"], key=f"role_{i}")
                    agent["goal"] = st.text_area(
                        "Objectif individuel", agent["goal"], key=f"goal_{i}", height=100
                    )
                    agent["backstory"] = st.text_area(
                        "Profil",
                        agent.get("backstory", ""),
                        key=f"back_{i}",
                        height=68,
                        help="Backstory : contexte donné à l'agent (CrewAI).",
                    )

                with c_conf_2:
                    cur_tag = agent.get("model_tag")
                    cur_lbl = next(
                        (k for k, v in display_to_tag.items() if v == cur_tag),
                        sorted_labels[0] if sorted_labels else "",
                    )
                    new_lbl = st.selectbox(
                        "Modèle",
                        sorted_labels,
                        index=sorted_labels.index(cur_lbl) if cur_lbl in sorted_labels else 0,
                        key=f"mod_{i}",
                    )
                    agent["model_tag"] = display_to_tag[new_lbl]

                    all_tools = list(TOOLS_METADATA.keys())
                    tool_names = [TOOLS_METADATA[t]["name"] for t in all_tools]
                    cur_tools = [
                        TOOLS_METADATA[t]["name"]
                        for t in agent.get("tools", [])
                        if t in TOOLS_METADATA
                    ]

                    st.markdown("**Outils**")
                    try:
                        sel_tools = st.pills(
                            "Outils",
                            tool_names,
                            default=cur_tools,
                            selection_mode="multi",
                            key=f"pills_{i}",
                            label_visibility="collapsed",
                        )
                    except Exception:
                        # Optionnel : loguer l'erreur pour le débogage
                        # print(f"Erreur lors de la lecture du système: {e}")
                        sel_tools = st.multiselect(
                            "Outils",
                            tool_names,
                            default=cur_tools,
                            key=f"pills_{i}",
                            label_visibility="collapsed",
                        )
                    name_to_id = {v["name"]: k for k, v in TOOLS_METADATA.items()}
                    agent["tools"] = [name_to_id[n] for n in sel_tools]

                    st.markdown("")
                    if st.button(
                        "Retirer l'agent",
                        key=f"del_{i}",
                        type="secondary",
                        icon=":material/delete:",
                        width="stretch",
                    ):
                        st.session_state.crew_agents.pop(i)
                        st.rerun()

        with tabs[n_agents]:
            st.info("Ajoutez un agent à la fin de l'enchaînement.")
            if st.button("Ajouter un agent", icon=":material/person_add:"):
                def_tag = installed_models_list[0]["model"] if installed_models_list else ""
                st.session_state.crew_agents.append(
                    {
                        "role": "Nouvel expert",
                        "goal": "Réaliser une tâche spécifique",
                        "model_tag": def_tag,
                        "backstory": "Expert qualifié.",
                        "tools": [],
                    }
                )
                st.rerun()

    # --- C. VISUALISATION DU FLUX ---
    st.header("Enchaînement des agents")
    render_crew_diagram(st.session_state.crew_agents)

    # --- D. EXÉCUTION & PRE-FLIGHT CHECK (NOUVEAU) ---

    # 1. Calcul Prédictif
    est_ram = estimate_mission_ram_gb(
        st.session_state.crew_agents[0]["model_tag"], num_agents=len(st.session_state.crew_agents)
    )
    risk_level = get_ram_risk_level(est_ram, avail_ram_gb)
    is_risky = risk_level in ("warning", "critical")

    # 2. Affichage Estimation (accord sur la valeur affichée, arrondie à 0,1 Go)
    avail_plural = round(avail_ram_gb, 1) >= 2
    with st.container(border=True):
        ce_1, ce_2 = st.columns([3, 1])
        with ce_1:
            st.markdown("**Vérification avant lancement**")
            if is_risky:
                st.error(
                    f"Cette mission demande environ {format_gb(est_ram)} de mémoire vive ; "
                    f"{format_gb(avail_ram_gb)} "
                    f"{'sont disponibles' if avail_plural else 'est disponible'}."
                )
                st.caption("Libérez la mémoire depuis la barre latérale ou retirez des agents.")
            else:
                st.success(
                    f"**Système prêt.** Estimation : environ {format_gb(est_ram)} "
                    f"({format_gb(avail_ram_gb)} "
                    f"{'disponibles' if avail_plural else 'disponible'})"
                )
        with ce_2:
            launch_label = "Lancer malgré le risque" if is_risky else "Lancer l'équipe"
            launch_type = "secondary" if is_risky else "primary"
            launch_btn = st.button(
                launch_label,
                type=launch_type,
                icon=":material/warning:" if is_risky else ":material/play_arrow:",
                width="stretch",
                disabled=False,
            )  # On laisse clickable mais avec warning visuel

    if launch_btn:
        if not st.session_state.crew_agents:
            st.error("Ajoutez au moins un agent.")
            st.stop()

        st.divider()
        status_box = st.status("Les agents travaillent…", expanded=True)

        with st.expander("Journal d'exécution", expanded=False):
            log_box = st.empty()
            output_capture = StreamlitCapture(log_box)

        with redirect_stdout(output_capture):
            t_start = time.perf_counter()
            tracker = GreenTracker("crew_mission")
            tracker.start()

            ram_start = psutil.virtual_memory().used
            peak_container = {"val": ram_start}
            stop_evt = threading.Event()

            def mon():
                while not stop_evt.is_set():
                    peak_container["val"] = max(peak_container["val"], psutil.virtual_memory().used)
                    time.sleep(0.5)

            threading.Thread(target=mon).start()

            try:
                status_box.write("Les agents collaborent…")

                crew = CrewFactory.create_custom_crew(
                    st.session_state.crew_agents, st.session_state.crew_topic
                )
                result = crew.kickoff()

                stop_evt.set()
                emissions_mg = tracker.stop() * 1000.0
                t_end = time.perf_counter()
                ram_gb_peak_delta = (peak_container["val"] - ram_start) / (1024**3)

                # UPDATE BUDGET GAMIFICATION
                if "carbon_budget" in st.session_state:
                    impact_percent = emissions_mg / 1000.0  # 1g = 1% arbitraire
                    st.session_state.carbon_budget -= impact_percent

                status_box.update(label="Mission terminée", state="complete", expanded=False)

                st.success("Mission terminée. Voici le rapport :")

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Durée totale", format_duration(t_end - t_start))
                k2.metric("Pic de mémoire", format_gb(ram_gb_peak_delta, 2))
                # Texte, sans code couleur par seuil ; déduit du budget carbone de la session.
                k3.metric("CO₂", format_unit(emissions_mg, "mg", 2))

                k4.download_button(
                    "Télécharger",
                    data=str(result),
                    file_name="rapport.md",
                    icon=":material/download:",
                )

                st.divider()
                st.markdown(result)

            except Exception as e:
                stop_evt.set()
                status_box.update(label="Échec", state="error")
                st.error(f"La mission a échoué : {e}")
                with st.expander("Détails techniques"):
                    st.code(traceback.format_exc())
