import asyncio

import streamlit as st

from src.core.inference_service import InferenceCallbacks, InferenceService


def render_chat_tab(
    selected_tag: str, selected_display: str, display_to_tag: dict, sorted_display_names: list
):
    col_chat_params, col_chat_main = st.columns([1, 3])

    with col_chat_params:
        st.subheader("Paramètres")
        # On utilise une clé unique pour éviter les conflits avec d'autres sélecteurs
        local_display = st.selectbox(
            "Modèle actif",
            sorted_display_names,
            index=(
                sorted_display_names.index(selected_display)
                if selected_display in sorted_display_names
                else 0
            ),
            key="chat_model_select_internal",
        )
        # Mise à jour du tag si l'utilisateur change ici (optionnel, ou on garde celui de la sidebar)
        # Ici on permet de surcharger la sélection de la sidebar pour cet onglet
        active_tag = display_to_tag.get(local_display)

        temp = st.slider("Température", 0.0, 1.0, 0.7, key="chat_temp")

        st.info("Ce mode conserve l'historique.")
        if st.button("🗑️ Nouvelle conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    with col_chat_main:
        # Historique
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if "thought" in msg and msg["thought"]:
                    with st.expander("💭 Raisonnement (CoT)", expanded=False):
                        st.markdown(msg["thought"])
                st.markdown(msg["content"])

        # Input
        if prompt := st.chat_input("Discutez avec le modèle..."):
            st.session_state.messages.append({"role": "user", "content": prompt})

            with st.chat_message("assistant"):
                msg_container = st.empty()
                state = {"current_text": ""}

                async def on_token(token: str):
                    state["current_text"] += token
                    msg_container.markdown(state["current_text"] + "▌")

                callbacks = InferenceCallbacks(on_token=on_token)

                result = asyncio.run(
                    InferenceService.run_inference(
                        model_tag=active_tag,
                        messages=st.session_state.messages,
                        temperature=temp,
                        callbacks=callbacks,
                    )
                )

                msg_container.empty()
                if result.thought:
                    with msg_container.container(), st.expander("💭 Raisonnement", expanded=False):
                        st.markdown(result.thought)
                    st.markdown(result.clean_text)
                else:
                    msg_container.markdown(result.clean_text)

                st.session_state.messages.append(
                    {"role": "assistant", "content": result.clean_text, "thought": result.thought}
                )
                st.rerun()
