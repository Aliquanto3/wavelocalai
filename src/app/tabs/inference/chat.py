"""
Inference Chat Tab - Sprint 2 (Immersive & Badges)
Refonte UX : Suppression sidebar, Header horizontal, Badges GreenOps visuels.
"""

import asyncio
import time

import streamlit as st

# --- Import SSOT GreenOps ---
from src.core.green_monitor import CarbonCalculator
from src.core.inference_service import InferenceCallbacks, InferenceService
from src.core.models_db import get_model_info
from src.core.utils import extract_params_billions as _extract_params_billions


def _calculate_metrics(metrics, model_friendly_name: str):
    """Calcule les métriques pour le badge."""
    if not metrics:
        return {}

    info = get_model_info(model_friendly_name) or {}
    carbon_g = 0.0

    if info.get("type") == "api" and metrics.output_tokens > 0:
        raw_params = info.get("params_act") or info.get("params_tot", "0")
        active_params = _extract_params_billions(raw_params)
        carbon_g = CarbonCalculator.compute_mistral_impact_g(active_params, metrics.output_tokens)
    else:
        carbon_g = CarbonCalculator.compute_local_theoretical_g(metrics.output_tokens)

    return {
        "co2_mg": carbon_g * 1000.0,  # Conversion directe en mg
        "speed": metrics.tokens_per_second,
        "duration": metrics.total_duration_s,
    }


def _render_message_footer(metrics: dict):
    """Affiche des badges stylisés sous le message."""
    if not metrics:
        return

    co2 = metrics["co2_mg"]
    speed = metrics["speed"]

    # Code couleur dynamique pour le CO2
    if co2 < 10:
        color = "#d1fae5"  # Vert clair
    elif co2 < 50:
        color = "#fef3c7"  # Jaune
    else:
        color = "#fee2e2"  # Rouge clair
    text_color = "#065f46" if co2 < 10 else ("#92400e" if co2 < 50 else "#991b1b")

    st.markdown(
        f"""
        <div style="display: flex; gap: 10px; margin-top: 8px; font-size: 0.85em; font-family: monospace;">
            <span style="background-color: {color}; color: {text_color}; padding: 2px 8px; border-radius: 12px; font-weight: bold;">
                🌱 {co2:.2f} mgCO₂
            </span>
            <span style="background-color: #f3f4f6; color: #374151; padding: 2px 8px; border-radius: 12px;">
                ⚡ {speed:.1f} t/s
            </span>
            <span style="color: #9ca3af; padding: 2px;">
                ⏱️ {metrics['duration']:.2f}s
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chat_tab(
    selected_tag: str, selected_display: str, display_to_tag: dict, sorted_display_names: list
):
    # --- 1. HEADER DE CONTRÔLE (Horizontal) ---
    with st.container(border=True):
        c_mod, c_temp, c_stat, c_reset = st.columns([3, 2, 2, 1])

        with c_mod:
            # Sélecteur Modèle
            local_display = st.selectbox(
                "🤖 Modèle Actif",
                sorted_display_names,
                index=(
                    sorted_display_names.index(selected_display)
                    if selected_display in sorted_display_names
                    else 0
                ),
                label_visibility="collapsed",
            )
            active_tag = display_to_tag.get(local_display)

        with c_temp:
            # Température compacte
            temp = st.slider("Créativité", 0.0, 1.0, 0.7, label_visibility="collapsed")

        with c_stat:
            # Mini Stats Session
            total_co2_mg = 0.0
            for m in st.session_state.messages:
                if m.get("role") == "assistant" and "metrics_data" in m:
                    total_co2_mg += m["metrics_data"].get("co2_mg", 0.0)

            st.caption(f"📊 Session: **{total_co2_mg:.1f} mgCO₂**")

        with c_reset:
            if st.button("🗑️", help="Effacer l'historique"):
                st.session_state.messages = []
                st.rerun()

    # --- 2. ZONE DE CHAT (Pleine largeur) ---
    chat_container = st.container()

    with chat_container:
        if not st.session_state.messages:
            st.markdown(
                """
                <div style="text-align: center; color: gray; margin-top: 50px; margin-bottom: 50px;">
                    <h3>💬 Playground Inférence</h3>
                    <p>Testez la réactivité et l'impact écologique des modèles en direct.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "🤖"):
                if msg.get("thought"):
                    with st.expander("💭 Pensée (CoT)", expanded=False):
                        st.markdown(msg["thought"])

                st.markdown(msg["content"])

                # Footer Badges
                if msg["role"] == "assistant" and "metrics_data" in msg:
                    _render_message_footer(msg["metrics_data"])

    # --- 3. INPUT USER ---
    if prompt := st.chat_input("Votre message..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar="🤖"):
            msg_container = st.empty()

            # Placeholder pour le stream
            state = {"current_text": ""}

            async def on_token(token: str):
                state["current_text"] += token
                msg_container.markdown(state["current_text"] + "▌")

            callbacks = InferenceCallbacks(on_token=on_token)

            # Inférence
            result = asyncio.run(
                InferenceService.run_inference(
                    model_tag=active_tag,
                    messages=st.session_state.messages,
                    temperature=temp,
                    callbacks=callbacks,
                )
            )

            # Affichage Final
            msg_container.markdown(result.clean_text)
            if result.thought:
                msg_container.empty()
                with msg_container.container():
                    with st.expander("💭 Pensée", expanded=True):
                        st.markdown(result.thought)
                    st.markdown(result.clean_text)

            # Calculs
            metrics_data = _calculate_metrics(result.metrics, local_display)
            _render_message_footer(metrics_data)

            # Save
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": result.clean_text,
                    "thought": result.thought,
                    "metrics_data": metrics_data,
                    "model_friendly": local_display,
                }
            )

            # Update stats session header
            time.sleep(0.1)
            st.rerun()
