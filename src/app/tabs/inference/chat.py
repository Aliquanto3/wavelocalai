"""
Onglet « Chat libre » de l'Arène des modèles : conversation avec un modèle et métadonnées
(badge Local ou Cloud, CO₂, débit, chargement, durée totale) sous chaque réponse.
"""

import asyncio
import time

import streamlit as st

from src.app.formatting import format_co2, format_duration, format_throughput, mg_to_grams
from src.app.states import (
    THROUGHPUT_HELP,
    finish_loading_status,
    inference_error_message,
    render_error,
    render_no_models,
    start_loading_status,
)
from src.app.ui import ModelMenu, badge_markdown, is_cloud_model, render_badge

# --- Import SSOT carbone ---
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
        # Débit = eval_count / eval_duration pour Ollama (D3).
        "speed": metrics.tokens_per_second,
        "speed_estimated": metrics.throughput_estimated,
        "duration": metrics.total_duration_s,
        # Chargement du modèle : mesuré par Ollama seulement (None pour le cloud).
        "load": metrics.load_duration_s if metrics.load_measured else None,
    }


def _model_history(messages: list[dict]) -> list[dict]:
    """Historique envoyé au modèle : sans les tours en échec (message d'erreur et question
    restée sans réponse), qui restent affichés mais ne sont pas des échanges."""
    history = []
    for msg in messages:
        if msg.get("error"):
            if history and history[-1]["role"] == "user":
                history.pop()
            continue
        history.append(msg)
    return history


def _render_message_footer(metrics: dict, is_cloud: bool | None = None):
    """Affiche la ligne de métadonnées sous le message : badge Local ou Cloud du modèle qui a
    répondu, puis CO₂, débit et durées (texte, sans code couleur par seuil)."""
    if not metrics:
        return

    parts = [
        badge_markdown(is_cloud),
        format_co2(mg_to_grams(metrics.get("co2_mg"))),
        format_throughput(metrics.get("speed"), metrics.get("speed_estimated", False)),
    ]
    if metrics.get("load") is not None:
        parts.append(f"Chargement {format_duration(metrics['load'])}")
    parts.append(f"Durée totale {format_duration(metrics.get('duration'))}")
    st.caption(" · ".join(parts), help=THROUGHPUT_HELP)


def render_chat_tab(
    selected_tag: str,
    selected_display: str,
    display_to_tag: dict,
    sorted_display_names: list,
    menu: ModelMenu | None = None,
):
    if not sorted_display_names:
        render_no_models(in_arena=True)
        return

    # --- 1. HEADER DE CONTRÔLE (Horizontal) ---
    with st.container(border=True):
        c_mod, c_temp, c_stat, c_reset = st.columns([3, 2, 2, 2])

        with c_mod:
            # Sélecteur Modèle
            local_display = st.selectbox(
                "Modèle actif",
                sorted_display_names,
                index=(
                    sorted_display_names.index(selected_display)
                    if selected_display in sorted_display_names
                    else 0
                ),
                label_visibility="collapsed",
            )
            active_tag = display_to_tag.get(local_display)
            # Badge du modèle choisi, dérivé de son fournisseur réel.
            active_is_cloud = is_cloud_model(active_tag, menu)
            render_badge(active_is_cloud)

        with c_temp:
            # Température compacte
            temp = st.slider(
                "Créativité",
                0.0,
                1.0,
                0.7,
                label_visibility="collapsed",
                help="Température : plus elle est haute, plus les réponses varient.",
            )

        with c_stat:
            # Mini Stats Session
            total_co2_mg = 0.0
            for m in st.session_state.messages:
                if m.get("role") == "assistant" and "metrics_data" in m:
                    total_co2_mg += m["metrics_data"].get("co2_mg", 0.0)

            st.caption(f"Session : **{format_co2(mg_to_grams(total_co2_mg))}**")

        with c_reset:
            if st.button("Effacer la conversation", icon=":material/delete:", width="stretch"):
                st.session_state.messages = []
                st.rerun()

    # --- 2. ZONE DE CHAT (Pleine largeur) ---
    chat_container = st.container()

    with chat_container:
        if not st.session_state.messages:
            st.header("Chat libre", anchor=False, text_alignment="center")
            st.caption(
                "Testez la réactivité et l'impact environnemental d'un modèle en direct.",
                text_alignment="center",
            )

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                # Tour en échec : conservé dans l'historique, rendu en alert-error.
                if msg.get("error"):
                    render_error(msg["content"], msg.get("detail"))
                    continue

                if msg.get("thought"):
                    with st.expander("Raisonnement", expanded=False):
                        st.markdown(msg["thought"])

                st.markdown(msg["content"])

                # Footer Badges
                if msg["role"] == "assistant" and "metrics_data" in msg:
                    _render_message_footer(msg["metrics_data"], msg.get("is_cloud"))

    # --- 3. INPUT USER ---
    if prompt := st.chat_input("Écrivez votre message"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            # Premier chargement : indicateur avant la génération, clos au premier token.
            state = {"current_text": "", "loading": start_loading_status(active_tag)}
            msg_container = st.empty()

            async def on_token(token: str):
                if state["loading"] is not None:
                    finish_loading_status(state["loading"])
                    state["loading"] = None
                state["current_text"] += token
                msg_container.markdown(state["current_text"] + "▌")

            callbacks = InferenceCallbacks(on_token=on_token)

            # Inférence
            result = asyncio.run(
                InferenceService.run_inference(
                    model_tag=active_tag,
                    messages=_model_history(st.session_state.messages),
                    temperature=temp,
                    callbacks=callbacks,
                )
            )

            # Échec (délai dépassé, Ollama arrêté…) : aucune réponse vide ; le tour est gardé
            # dans l'historique, marqué en erreur (rendu en alert-error, jamais envoyé au
            # modèle), pour que la question ne reste pas sans explication au rerun suivant.
            if result.error:
                finish_loading_status(state["loading"], ok=False)
                msg_container.empty()
                error_turn = {
                    "role": "assistant",
                    "error": True,
                    "content": inference_error_message(result, active_tag),
                    "detail": result.error,
                    "model_friendly": local_display,
                }
                render_error(error_turn["content"], error_turn["detail"])
                st.session_state.messages.append(error_turn)
                return
            finish_loading_status(state["loading"])

            # Affichage Final
            msg_container.markdown(result.clean_text)
            if result.thought:
                msg_container.empty()
                with msg_container.container():
                    with st.expander("Raisonnement", expanded=True):
                        st.markdown(result.thought)
                    st.markdown(result.clean_text)

            # Calculs
            metrics_data = _calculate_metrics(result.metrics, local_display)
            _render_message_footer(metrics_data, active_is_cloud)

            # Save
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": result.clean_text,
                    "thought": result.thought,
                    "metrics_data": metrics_data,
                    "model_friendly": local_display,
                    "model_tag": active_tag,
                    "is_cloud": active_is_cloud,
                }
            )

            # Update stats session header
            time.sleep(0.1)
            st.rerun()
