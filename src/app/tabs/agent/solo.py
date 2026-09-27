"""
Mode « Agent seul » des Agents autonomes.

- CO₂ en texte, sans code couleur par seuil
- État vide avec actions rapides en cartes
- Structure de PROMPT_LIBRARY vérifiée par les tests
"""

import streamlit as st

from src.app.formatting import format_unit
from src.app.states import (
    LOADING_HINT,
    LOADING_LABEL,
    generation_failure_advice,
    render_error,
    render_no_models,
)
from src.core.agent_engine import AgentEngine
from src.core.agent_tools import TOOLS_METADATA
from src.core.llm_provider import LLMProvider
from src.core.resource_manager import ResourceManager
from src.core.utils import extract_thought

# --- PROMPT DATA (STRUCTURE CORRIGÉE) ---
PROMPT_LIBRARY = {
    "Analyse": {
        "Fichier CSV de mesures": {
            "prompt": "Analyse 'data/benchmarks_data.csv', donne un aperçu et la moyenne de ram_usage_gb",
            "required_tools": ["analyze_csv", "calculator"],
            "description": "Analyse d'un fichier CSV benchmark avec calculs statistiques",
        },
        "Audit du système": {
            "prompt": "Vérifie le système (CPU/RAM) et génère un graphique d'état.",
            "required_tools": ["system_monitor", "generate_chart"],
            "description": "Diagnostic système complet avec visualisation graphique",
        },
    },
    "Rédaction": {
        "Rapport Word": {
            "prompt": "Crée un document Word sur 'L'impact des SLM' (Intro/Dev/Concl).",
            "required_tools": ["generate_document"],
            "description": "Génération d'un rapport professionnel au format DOCX",
        },
        "Synthèse Markdown": {
            "prompt": "Fais un rapport Markdown sur l'état système actuel.",
            "required_tools": ["system_monitor", "generate_markdown_report"],
            "description": "Rapport technique système au format Markdown",
        },
    },
    "Enchaînement": {
        "Chaîne complète": {
            "prompt": "1) Vérifie le système 2) Analyse 'data/benchmarks_data.csv' 3) Fais un graphique des performances 4) Rédige un rapport DOCX.",
            "required_tools": [
                "system_monitor",
                "analyze_csv",
                "generate_chart",
                "generate_document",
            ],
            "description": "Pipeline complet : audit → analyse → visualisation → documentation",
        },
    },
}


def _tool_label(tool_id: str) -> str:
    """Nom affiché d'un outil (TOOLS_METADATA), à défaut son identifiant."""
    return TOOLS_METADATA.get(tool_id, {}).get("name", tool_id)


# --- MODAL: PROMPT LIBRARY ---
@st.dialog("Scénarios")
def open_prompt_library():
    st.caption("Choisissez un scénario : sa consigne et ses outils sont préremplis.")

    # Grid Layout for cards
    for cat, prompts in PROMPT_LIBRARY.items():
        st.subheader(cat)
        cols = st.columns(2)
        for i, (title, data) in enumerate(prompts.items()):
            with cols[i % 2], st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(data["prompt"][:60] + "…")
                if st.button("Utiliser", key=f"use_{title}", width="stretch"):
                    st.session_state.use_prompt = data["prompt"]
                    # Auto-select tools (required_tools)
                    if "selected_tools" not in st.session_state:
                        st.session_state.selected_tools = []
                    for t in data.get("required_tools", []):
                        if t not in st.session_state.selected_tools:
                            st.session_state.selected_tools.append(t)
                    st.rerun()

    if st.button("Fermer"):
        st.rerun()


def render_agent_solo_tab(sorted_labels: list, display_to_tag: dict):

    if not sorted_labels:
        render_no_models()
        return

    # --- 1. CONFIGURATION BAR ---
    c1, c2, c3 = st.columns([2, 4, 1])

    with c1:
        # Model Selector
        selected_label = st.selectbox("Modèle", sorted_labels, label_visibility="collapsed")
        selected_tag = display_to_tag.get(selected_label)

    with c2:
        # Tool Selector (Pills) : wrap=True replie les 9 pastilles sur plusieurs lignes au lieu
        # de les faire défiler sur une seule (5 sur 9 masquées à 1440 px sinon).
        tool_map = {meta["name"]: name for name, meta in TOOLS_METADATA.items()}
        tool_display_names = list(tool_map.keys())

        if "selected_tools" not in st.session_state:
            st.session_state.selected_tools = list(TOOLS_METADATA.keys())

        current_display = [
            meta["name"]
            for name, meta in TOOLS_METADATA.items()
            if name in st.session_state.selected_tools
        ]

        try:
            sel_display = st.pills(
                "Outils",
                tool_display_names,
                default=current_display,
                selection_mode="multi",
                label_visibility="collapsed",
                wrap=True,
            )
        except Exception:
            # Optionnel : loguer l'erreur pour le débogage
            # print(f"Erreur lors de la lecture du système: {e}")
            sel_display = st.multiselect(
                "Outils", tool_display_names, default=current_display, label_visibility="collapsed"
            )

        st.session_state.selected_tools = [tool_map[n] for n in sel_display]

    with c3:
        # Library Button
        if st.button(
            "Scénarios",
            icon=":material/library_books:",
            help="Ouvrir la bibliothèque de scénarios",
            width="stretch",
        ):
            open_prompt_library()

    st.divider()

    # --- 2. CONVERSATION AREA ---
    chat_container = st.container()

    with chat_container:
        # EMPTY STATE AMÉLIORÉ
        if not st.session_state.agent_messages:
            st.header("👋 Bonjour !", anchor=False, text_alignment="center")
            st.caption(
                "L'agent est prêt. Choisissez une action rapide ou tapez votre demande.",
                text_alignment="center",
            )

            # Quick Actions (Cartes)
            ac1, ac2, ac3 = st.columns(3)
            with ac1, st.container(border=True):
                st.markdown("**Audit du système**")
                if st.button("Lancer l'audit", key="start_audit", width="stretch"):
                    st.session_state.use_prompt = (
                        "Vérifie l'état du système (CPU/RAM) et fais un résumé."
                    )
                    st.rerun()
            with ac2, st.container(border=True):
                st.markdown("**Analyse de données**")
                if st.button("Analyser les données", key="start_csv", width="stretch"):
                    st.session_state.use_prompt = (
                        "Analyse data/benchmarks_data.csv et donne les tendances."
                    )
                    st.rerun()
            with ac3, st.container(border=True):
                st.markdown("**Sobriété**")
                st.caption("Les requêtes locales émettent moins de CO₂.")

        # LOOP MESSAGES
        for i, msg in enumerate(st.session_state.agent_messages):
            with st.chat_message(msg["role"]):
                if msg.get("type") == "tool_log":
                    status_state = "complete" if msg.get("done") else "running"
                    # Pas de « with » : à sa sortie, st.status passe de running à complete.
                    st.status(_tool_label(msg["tool"]), state=status_state).code(msg["content"])
                elif msg.get("thought"):
                    with st.expander("Raisonnement", expanded=False):
                        st.markdown(msg["thought"])

                if msg.get("content"):
                    st.markdown(msg["content"])
                    if msg.get("blocked"):
                        st.caption("Question bloquée par le garde-fou mémoire, non envoyée.")

                    # --- ACTION BAR FOR ASSISTANT ---
                    if msg["role"] == "assistant":
                        col_d1, col_d2 = st.columns([1, 5])
                        with col_d1:
                            st.download_button(
                                "Télécharger",
                                msg["content"],
                                file_name=f"result_agent_{i}.md",
                                icon=":material/download:",
                                help="Télécharger en Markdown",
                                key=f"dl_btn_{i}",
                            )
                        # GREENOPS : texte, sans code couleur par seuil
                        if "carbon_mg" in msg:
                            with col_d2:
                                st.caption(format_unit(msg["carbon_mg"], "mgCO₂", 2))

    # --- 3. INPUT & EXECUTION ---
    user_input = st.chat_input("Décrivez la tâche à confier à l'agent")

    # Handle Prompt Injection (Library or Quick Action)
    final_prompt = None
    if "use_prompt" in st.session_state:
        final_prompt = st.session_state.use_prompt
        del st.session_state.use_prompt
    elif user_input:
        final_prompt = user_input

    if final_prompt:
        if not selected_tag:
            st.toast("Choisissez un modèle.", icon=":material/error:")
            st.stop()

        # La question entre dans l'historique avant le garde-fou mémoire : bloquée, elle
        # reste visible (et réutilisable) au lieu de disparaître.
        user_turn = {"role": "user", "content": final_prompt}
        st.session_state.agent_messages.append(user_turn)
        with chat_container.chat_message("user"):
            st.markdown(final_prompt)

        check = ResourceManager.check_resources(selected_tag, n_instances=1)
        if not check.allowed:
            # Marquée bloquée : affichée, mais jamais renvoyée au moteur comme tour orphelin.
            user_turn["blocked"] = True
            # Mémoire nécessaire, mémoire libre, deux issues (modèle plus petit, libérer).
            st.warning(check.message, icon=":material/memory:")
            st.stop()

        with chat_container.chat_message("assistant"):
            # L'agent n'affiche rien tant qu'il n'a pas commencé à générer
            # On affiche un placeholder de status vide pour le remplissage.
            # Premier chargement : annoncé avant la génération (rien si `ps()` échoue).
            status_placeholder = st.empty()
            loading = LLMProvider.is_model_loaded(selected_tag) is False
            if loading:
                status_box = status_placeholder.status(LOADING_LABEL, expanded=True)
                status_box.write(LOADING_HINT)
            else:
                status_box = status_placeholder.status("L'agent réfléchit…", expanded=True)

            engine = AgentEngine(selected_tag, enabled_tools=st.session_state.selected_tools)
            full_resp = ""
            thought = None

            try:
                # Assuming system prompt is hidden/default for Sprint 2 to save space
                sys_prompt = "Tu es un assistant expert Wavestone. Réponds en Markdown propre."
                history = [m for m in st.session_state.agent_messages if not m.get("blocked")]
                stream = engine.run_stream(final_prompt, history, system_prompt=sys_prompt)

                current_tool_log = None  # Pour gérer l'ajout d'un seul log par tool_call
                finished = False  # Réponse finale ou erreur reçue

                for event in stream:
                    ev_type = event["type"]
                    if loading:
                        # Premier événement : le modèle est chargé, l'agent travaille.
                        status_box.update(label="L'agent réfléchit…")
                        loading = False

                    if ev_type == "tool_call":
                        status_box.write(
                            f"**{_tool_label(event['tool'])}** (arguments : {event['args']})"
                        )
                        log_content = f"Arguments : {event['args']}\nEn attente du résultat…"

                        # Création d'un placeholder de log pour la mise à jour
                        current_tool_log = {
                            "role": "assistant",
                            "type": "tool_log",
                            "tool": event["tool"],
                            "args": event["args"],
                            "content": log_content,
                        }
                        st.session_state.agent_messages.append(current_tool_log)

                    elif ev_type == "tool_result":
                        content = event["content"]

                        # Mise à jour du dernier log créé
                        if current_tool_log:
                            # Marque de fin explicite (lue par le rendu du log, pas le texte)
                            current_tool_log["content"] = f"Résultat de l'outil :\n{content}"
                            current_tool_log["done"] = True

                        status_box.write("Résultat de l'outil reçu.")

                        if ".png" in content or ".jpg" in content:
                            if "outputs/" in content:
                                st.image(content.strip())
                                st.toast("Image générée.", icon=":material/image:")
                        elif len(content) > 500:
                            st.toast(
                                "Document généré ou analysé : voir le journal de l'outil.",
                                icon=":material/article:",
                            )

                    elif ev_type == "final_answer":
                        finished = True
                        # Mise à jour de la boîte de statut uniquement à la fin
                        status_placeholder.empty()
                        status_box = st.status("Terminé", state="complete", expanded=False)

                        thought, clean = extract_thought(event["content"])
                        full_resp = clean
                        if thought:
                            with st.expander("Raisonnement"):
                                st.markdown(thought)
                        st.markdown(full_resp)

                    elif ev_type == "error":
                        finished = True
                        status_placeholder.empty()
                        status_box = st.status("Erreur", state="error")
                        st.error(event["content"])

                # Flux terminé sans réponse finale : le statut (« Chargement… » ou
                # « L'agent réfléchit… ») ne reste pas ouvert.
                if not finished:
                    status_box.update(
                        label="L'agent s'est arrêté sans réponse", state="error", expanded=False
                    )

                # ... (Carbon Calc et st.rerun inchangés) ...
            except Exception as e:
                status_box.update(label="Échec", state="error", expanded=False)
                render_error(
                    "L'agent s'est arrêté avant de répondre. "
                    + generation_failure_advice(selected_tag),
                    f"{type(e).__name__}: {e}",
                )
