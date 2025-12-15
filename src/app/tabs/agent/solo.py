"""
Solo Agent Tab - Interface pour agent solo avec sélection d'outils.

Nouvelles fonctionnalités :
1. Affichage de la liste des outils disponibles avec sélection
2. Librairie de prompts prédéfinis nécessitant différents outils
3. Interface optimisée pour la configuration
"""

import streamlit as st

from src.core.agent_engine import AgentEngine
from src.core.agent_tools import TOOLS_METADATA
from src.core.resource_manager import ResourceManager

# ========================================
# PROMPTS PRÉDÉFINIS PAR CATÉGORIE
# ========================================

PROMPT_LIBRARY = {
    "🔍 Analyse de Données": {
        "Analyse de benchmark CSV": {
            "prompt": "Analyse le fichier 'data/benchmarks_data.csv' et donne-moi un aperçu des données, puis calcule la moyenne de ram_usage_gb",
            "required_tools": ["analyze_csv", "calculator"],
            "description": "Analyse un fichier CSV de benchmarks et calcule des statistiques",
        },
        "Rapport système + graphique": {
            "prompt": "Vérifie l'état actuel du système avec system_monitor, puis génère un graphique montrant l'utilisation CPU et RAM",
            "required_tools": ["system_monitor", "generate_chart"],
            "description": "Monitoring système avec visualisation",
        },
    },
    "📊 Génération de Contenu": {
        "Rapport professionnel DOCX": {
            "prompt": "Crée un document Word professionnel sur 'L'impact des SLM dans le conseil' avec une introduction, 3 sections d'analyse et une conclusion",
            "required_tools": ["generate_document"],
            "description": "Génère un document Word structuré",
        },
        "Rapport Markdown complet": {
            "prompt": "Génère un rapport Markdown sur l'état actuel du système, incluant les métriques CPU, RAM et des recommandations",
            "required_tools": ["system_monitor", "generate_markdown_report"],
            "description": "Rapport technique en Markdown",
        },
    },
    "🧮 Calculs et Recherche": {
        "Calculs multiples avec recherche": {
            "prompt": "Quelle heure est-il ? Calcule 154 * 45, puis cherche qui est Anaël chez Wavestone",
            "required_tools": ["get_current_time", "calculator", "search_wavestone_internal"],
            "description": "Combine heure, calculs et recherche interne",
        },
        "Analyse financière": {
            "prompt": "Calcule le ROI d'un projet : coût initial 50000€, revenus mensuels 8000€. Combien de mois pour l'amortir ? Génère un graphique de l'évolution.",
            "required_tools": ["calculator", "generate_chart"],
            "description": "Calculs financiers avec visualisation",
        },
    },
    "📧 Communication": {
        "Email de rapport": {
            "prompt": "Vérifie l'état du système, puis envoie un email de rapport à admin@wavestone.com avec un résumé des métriques",
            "required_tools": ["system_monitor", "send_email"],
            "description": "Monitoring + notification par email",
        },
    },
    "🎯 Workflows Complets": {
        "Pipeline analyse complète": {
            "prompt": "1) Vérifie l'état système 2) Analyse le fichier 'data/benchmarks_data.csv' 3) Génère un graphique des performances 4) Crée un rapport DOCX avec l'analyse complète",
            "required_tools": [
                "system_monitor",
                "analyze_csv",
                "generate_chart",
                "generate_document",
            ],
            "description": "Pipeline d'analyse de bout en bout",
        },
        "Rapport automatisé avec email": {
            "prompt": "Analyse les benchmarks dans 'data/benchmarks_data.csv', génère un rapport Markdown, puis envoie-le par email à team@wavestone.com",
            "required_tools": ["analyze_csv", "generate_markdown_report", "send_email"],
            "description": "Analyse + rapport + notification",
        },
    },
}


def extract_thought(text: str) -> tuple[str | None, str]:
    """Extrait la pensée si présente dans le texte."""
    if "<thinking>" in text and "</thinking>" in text:
        start = text.find("<thinking>") + len("<thinking>")
        end = text.find("</thinking>")
        thought = text[start:end].strip()
        clean = text[: text.find("<thinking>")] + text[end + len("</thinking>") :]
        return thought, clean.strip()
    return None, text


def render_agent_solo_tab(sorted_labels: list, display_to_tag: dict):
    """
    Rendu de l'onglet Agent Solo avec sélection d'outils et prompts prédéfinis.
    """

    # ========================================
    # SECTION 1 : CONFIGURATION DE L'AGENT
    # ========================================

    st.subheader("⚙️ Configuration de l'Agent")

    col_model, col_tools = st.columns([1, 2])

    with col_model:
        selected_label = st.selectbox("🧠 Cerveau de l'Agent", sorted_labels)
        selected_tag = display_to_tag[selected_label]

        # Prompt Système
        with st.expander("🛠️ Prompt Système (Identité)", expanded=False):
            default_sys = (
                "Tu es un assistant expert et autonome. "
                "Tu disposes d'outils spécialisés. Utilise-les dès que nécessaire pour répondre précisément. "
                "Réponds en Français."
            )
            system_prompt = st.text_area("Instructions", value=default_sys, height=100)

    with col_tools:
        st.markdown("🧰 **Outils Disponibles**")

        # Initialisation de l'état
        if "selected_tools" not in st.session_state:
            # Par défaut, tous les outils sont sélectionnés
            st.session_state.selected_tools = list(TOOLS_METADATA.keys())

        # Organisation des outils par catégorie
        tools_by_category = {}
        for tool_name, metadata in TOOLS_METADATA.items():
            category = metadata.get("category", "other")
            if category not in tools_by_category:
                tools_by_category[category] = []
            tools_by_category[category].append((tool_name, metadata))

        # Affichage des outils par catégorie avec checkboxes
        cols = st.columns(3)

        for idx, (category, tools) in enumerate(tools_by_category.items()):
            with cols[idx % 3]:
                st.markdown(f"**{category.title()}**")
                for tool_name, metadata in tools:
                    # Checkbox pour chaque outil
                    is_selected = tool_name in st.session_state.selected_tools

                    # Indicateur de configuration requise
                    label = metadata["name"]
                    if metadata.get("requires_config", False):
                        label += " ⚙️"

                    if st.checkbox(
                        label,
                        value=is_selected,
                        key=f"tool_check_{tool_name}",
                        help=metadata["description"],
                    ):
                        if tool_name not in st.session_state.selected_tools:
                            st.session_state.selected_tools.append(tool_name)
                    else:
                        if tool_name in st.session_state.selected_tools:
                            st.session_state.selected_tools.remove(tool_name)

        # Boutons de sélection rapide
        col_select_all, col_select_none = st.columns(2)
        with col_select_all:
            if st.button("✅ Tout sélectionner"):
                st.session_state.selected_tools = list(TOOLS_METADATA.keys())
                st.rerun()
        with col_select_none:
            if st.button("❌ Tout désélectionner"):
                st.session_state.selected_tools = []
                st.rerun()

    # Compteur d'outils sélectionnés
    st.info(f"🔧 **{len(st.session_state.selected_tools)}** outil(s) activé(s)")

    # NOUVEAU : Guide détaillé des outils
    with st.expander("📖 Guide des outils disponibles"):
        st.markdown("### Description complète de chaque outil")

        for tool_name, metadata in TOOLS_METADATA.items():
            # Récupération de l'outil réel pour avoir la description complète
            from src.core.agent_tools import AVAILABLE_TOOLS

            tool = next((t for t in AVAILABLE_TOOLS if t.name == tool_name), None)

            if tool:
                st.markdown(f"#### {metadata['name']}")
                st.markdown(f"*Catégorie : {metadata['category']}*")

                # Description courte (métadonnée)
                st.write(f"**Résumé :** {metadata['description']}")

                # Description complète (docstring de l'outil)
                if hasattr(tool, "description") and tool.description:
                    with st.expander("Voir la description détaillée"):
                        st.markdown(tool.description)

                # Indicateur de configuration
                if metadata.get("requires_config", False):
                    config_vars = metadata.get("config_vars", [])
                    st.warning(f"⚙️ Requiert configuration : {', '.join(config_vars)}")

                st.divider()

    st.divider()

    # ========================================
    # SECTION 2 : LIBRAIRIE DE PROMPTS
    # ========================================

    st.subheader("📚 Librairie de Prompts Prédéfinis")

    # Sélection par catégorie
    selected_category = st.selectbox("Catégorie", options=list(PROMPT_LIBRARY.keys()), index=0)

    # Affichage des prompts de la catégorie
    prompts_in_category = PROMPT_LIBRARY[selected_category]

    # Grid de cartes pour les prompts
    cols_prompts = st.columns(2)

    for idx, (prompt_name, prompt_data) in enumerate(prompts_in_category.items()):
        with cols_prompts[idx % 2], st.container(border=True):
            st.markdown(f"**{prompt_name}**")
            st.caption(prompt_data["description"])

            # Affichage des outils requis
            required_tools = prompt_data["required_tools"]
            tools_display = ", ".join(
                [TOOLS_METADATA[t]["name"] for t in required_tools if t in TOOLS_METADATA]
            )
            st.markdown(f"🔧 *Outils : {tools_display}*")

            # Vérification que tous les outils requis sont activés
            missing_tools = [t for t in required_tools if t not in st.session_state.selected_tools]

            if missing_tools:
                missing_names = [
                    TOOLS_METADATA[t]["name"] for t in missing_tools if t in TOOLS_METADATA
                ]
                st.warning(f"⚠️ Outils manquants : {', '.join(missing_names)}")

            # Bouton pour utiliser ce prompt
            if st.button("🚀 Utiliser", key=f"prompt_{idx}_{prompt_name}"):
                st.session_state.use_prompt = prompt_data["prompt"]
                st.rerun()

    st.divider()

    # ========================================
    # SECTION 3 : CONVERSATION
    # ========================================

    st.subheader("💬 Conversation")

    # Affichage de l'historique
    for msg in st.session_state.agent_messages:
        with st.chat_message(msg["role"]):
            if msg.get("type") == "tool_log":
                with st.status(f"🛠️ {msg['tool']}", state="complete"):
                    st.write(f"Args: `{msg['args']}`")
                    st.write(f"Result: {msg['content']}")
            elif msg.get("thought"):
                with st.expander("💭 Pensée", expanded=False):
                    st.markdown(msg["thought"])
            st.markdown(msg["content"])

    # Zone de saisie
    prompt = st.chat_input("Votre instruction pour l'agent...")

    # Logique de déclenchement (Input user OU Prompt prédéfini)
    final_prompt = None

    if "use_prompt" in st.session_state:
        final_prompt = st.session_state.use_prompt
        del st.session_state.use_prompt
    elif prompt:
        final_prompt = prompt

    # ========================================
    # SECTION 4 : EXÉCUTION
    # ========================================

    if final_prompt:
        if not selected_tag:
            st.error("❌ Aucun modèle sélectionné.")
            st.stop()

        if not st.session_state.selected_tools:
            st.warning("⚠️ Aucun outil sélectionné. L'agent ne pourra utiliser aucun outil.")

        # Pre-Flight Check RAM
        check = ResourceManager.check_resources(selected_tag, n_instances=1)
        if not check.allowed:
            st.error(f"⚠️ {check.message}")

            # NOUVEAU : Recommandations
            with st.expander("💡 Conseils pour libérer de la RAM"):
                st.markdown(
                    """
                **Options disponibles :**

                1. **Libérer la RAM Ollama** : Utilisez le bouton dans la sidebar (💾 Gestion Mémoire)

                2. **Choisir un modèle plus léger** :
                - Qwen 2.5 0.5B (0.8 GB) - Très léger
                - Qwen 2.5 1.5B (1.3 GB) - Équilibré
                - SmolLM2 1.7B (3.2 GB) - Compact

                3. **Fermer d'autres applications** : Libérez de la RAM système

                4. **Redémarrer Ollama** : `ollama stop` puis `ollama serve`

                5. **Utiliser un modèle API** : Mistral Large/Small ne consomment pas de RAM locale
                """
                )

            st.stop()

        st.session_state.agent_messages.append({"role": "user", "content": final_prompt})
        with st.chat_message("user"):
            st.markdown(final_prompt)

        with st.chat_message("assistant"):
            container = st.container()

            # Création de l'agent avec les outils sélectionnés
            engine = AgentEngine(selected_tag, enabled_tools=st.session_state.selected_tools)

            full_resp = ""
            thought = None

            try:
                # Exécution du stream
                stream = engine.run_stream(
                    final_prompt, st.session_state.agent_messages, system_prompt=system_prompt
                )

                for event in stream:
                    ev_type = event["type"]

                    if ev_type == "tool_call":
                        with container.status(f"🔨 Outil : {event['tool']}", expanded=True):
                            st.write(f"Args : `{event['args']}`")
                        st.session_state.agent_messages.append(
                            {
                                "role": "assistant",
                                "type": "tool_log",
                                "tool": event["tool"],
                                "args": event["args"],
                                "content": "...",
                            }
                        )

                    elif ev_type == "tool_result":
                        content = event["content"]

                        # NOUVEAU : Détection si le résultat contient un chemin d'image
                        if ".png" in content or ".jpg" in content or ".jpeg" in content:
                            # Extraire le chemin du fichier (format: "✅ Graphique créé : outputs/chart_XXXXXX.png")
                            import re

                            match = re.search(r"(outputs/[^\s]+\.(?:png|jpg|jpeg))", content)

                            if match:
                                image_path = match.group(1)

                                # Vérifier que le fichier existe
                                from pathlib import Path

                                if Path(image_path).exists():
                                    # Afficher l'image
                                    with st.chat_message("assistant"):
                                        st.image(image_path, caption="Graphique généré")
                                        st.caption(content)
                                else:
                                    # Fallback : afficher juste le texte
                                    with st.chat_message("assistant"):
                                        st.markdown(f"🔧 **Résultat :** {content}")
                            else:
                                # Pas d'image trouvée, affichage normal
                                with st.chat_message("assistant"):
                                    st.markdown(f"🔧 **Résultat :** {content}")
                        else:
                            # Pas une image, affichage normal
                            with st.chat_message("assistant"):
                                st.markdown(f"🔧 **Résultat :** {content}")

                    elif ev_type == "final_answer":
                        thought, clean = extract_thought(event["content"])
                        full_resp = clean
                        if thought:
                            with container.expander("💭 Pensée", expanded=True):
                                st.markdown(thought)
                        container.markdown(full_resp)

                    elif ev_type == "error":
                        container.error(event["content"])

                if full_resp:
                    st.session_state.agent_messages.append(
                        {"role": "assistant", "content": full_resp, "thought": thought}
                    )

            except Exception as e:
                container.error(f"💥 Crash Agent : {e}")
