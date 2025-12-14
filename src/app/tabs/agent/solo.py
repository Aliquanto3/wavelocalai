import streamlit as st

from src.core.agent_engine import AgentEngine
from src.core.models_db import extract_thought
from src.core.resource_manager import ResourceManager


def render_agent_solo_tab(sorted_labels: list, display_to_tag: dict):

    # --- CONFIGURATION CENTRALE ---
    col_model, col_sys = st.columns([1, 2])

    with col_model:
        selected_label = st.selectbox("Cerveau de l'Agent", sorted_labels)
        selected_tag = display_to_tag[selected_label]

    with col_sys:
        # Prompt Système éditable
        default_sys = "Tu es un assistant expert et autonome. Tu disposes d'outils (Calculatrice, Recherche, Heure). Utilise-les dès que nécessaire pour répondre précisément. Réponds en Français."
        with st.expander("🛠️ Prompt Système (Identité)", expanded=False):
            system_prompt = st.text_area("Instructions", value=default_sys, height=100)

    st.divider()

    # --- HISTORIQUE ---
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

    # --- ZONE DE SAISIE AVEC EXEMPLE ---

    # Gestion du "Pré-remplissage" via un bouton d'action
    example_prompt = "Quelle heure est-il et quel est le résultat de 154 * 45 ? Cherche aussi qui est Anaël chez Wavestone."
    run_example = False

    # Si l'historique est vide, on propose un helper
    if not st.session_state.agent_messages:
        cols_help = st.columns([4, 1])
        with cols_help[1]:
            if st.button("🎲 Essayer un exemple", help=example_prompt):
                run_example = True

    prompt = st.chat_input("Votre instruction pour l'agent...")

    # Logique de déclenchement (Input user OU Bouton Exemple)
    final_prompt = None
    if prompt:
        final_prompt = prompt
    elif run_example:
        final_prompt = example_prompt

    if final_prompt:
        if not selected_tag:
            st.error("Aucun modèle sélectionné.")
            st.stop()

        # Pre-Flight Check RAM
        check = ResourceManager.check_resources(selected_tag, n_instances=1)
        if not check.allowed:
            st.error(f"⚠️ {check.message}")
            st.stop()

        st.session_state.agent_messages.append({"role": "user", "content": final_prompt})
        with st.chat_message("user"):
            st.markdown(final_prompt)

        with st.chat_message("assistant"):
            container = st.container()
            engine = AgentEngine(selected_tag)

            full_resp = ""
            thought = None

            try:
                # On passe le system_prompt dynamique ici
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
                        if (
                            st.session_state.agent_messages
                            and st.session_state.agent_messages[-1].get("type") == "tool_log"
                        ):
                            st.session_state.agent_messages[-1]["content"] = event["content"]

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

                # Petit hack pour forcer le rafraichissement si on a utilisé le bouton exemple
                if run_example:
                    st.rerun()

            except Exception as e:
                container.error(f"Crash Agent : {e}")
