"""
Onglet « Chat libre » de l'Arène des modèles : conversation avec un modèle et métadonnées
(badge Local ou Cloud, CO₂, débit, chargement, durée totale) sous chaque réponse.
"""

import asyncio
import time

import streamlit as st

from src.app.formatting import format_co2, format_duration, format_throughput, mg_to_grams
from src.app.states import (
    RETRY_MESSAGE,
    THROUGHPUT_HELP,
    finish_loading_status,
    inference_error_message,
    render_answer,
    render_error,
    render_no_models,
    start_loading_status,
)
from src.app.ui import ModelMenu, badge_markdown, is_cloud_model, render_badge

from src.core.answer_carbon import answer_carbon_mg
from src.core.inference_service import InferenceCallbacks, InferenceService


def _calculate_metrics(
    metrics, model_tag: str | None, is_cloud: bool | None = None, interrupted_tokens: int = 0
):
    """Calcule les métriques pour le badge. La formule de CO₂ suit `is_cloud`, l'origine réelle
    du modèle (celle du badge) ; à défaut, le type du catalogue. La fiche est cherchée par le
    nom du catalogue, jamais par le libellé du sélecteur (« Nom · Cloud »). Le CO₂ compte aussi
    `interrupted_tokens`, les tokens d'une tentative coupée puis relancée."""
    if not metrics:
        return {}

    return {
        # Règle unique du cœur (src/core/answer_carbon.py) ; None si le CO₂ est inconnu.
        "co2_mg": answer_carbon_mg(model_tag, metrics.output_tokens + interrupted_tokens, is_cloud),
        # Débit = eval_count / eval_duration pour Ollama (D3).
        "speed": metrics.tokens_per_second,
        "speed_estimated": metrics.throughput_estimated,
        "duration": metrics.total_duration_s,
        # Chargement du modèle : mesuré par Ollama seulement (None pour le cloud).
        "load": metrics.load_duration_s if metrics.load_measured else None,
    }


def session_co2_mg(messages: list[dict]) -> float | None:
    """CO₂ de la session (mg) : somme des réponses au CO₂ connu, les inconnus (cloud de taille
    inconnue) ignorés. None (« — ») si aucune réponse n'a de CO₂ connu, jamais 0 pour un
    inconnu ; 0.0 pour une session sans réponse."""
    answers = [
        m["metrics_data"].get("co2_mg")
        for m in messages
        if m.get("role") == "assistant" and "metrics_data" in m
    ]
    values = [v for v in answers if mg_to_grams(v) is not None]
    if answers and not values:
        return None
    return float(sum(values))


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
            total_co2_mg = session_co2_mg(st.session_state.messages)
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

                if msg["role"] == "assistant":
                    render_answer(msg["content"])
                else:
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

            async def on_retry(_err):
                # Génération coupée, relancée une fois : le texte partiel n'est plus montré.
                # Coupure avant tout texte : le chargement est fini, comme dans `on_token`.
                if state["loading"] is not None:
                    finish_loading_status(state["loading"])
                    state["loading"] = None
                state["current_text"] = ""
                msg_container.caption(RETRY_MESSAGE)

            callbacks = InferenceCallbacks(on_token=on_token, on_retry=on_retry)

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
                wasted_mg = (
                    answer_carbon_mg(active_tag, result.interrupted_output_tokens, active_is_cloud)
                    if result.interrupted_output_tokens
                    else None
                )
                if wasted_mg is not None:
                    # Tokens générés avant les coupures : comptés dans le CO₂ de la session,
                    # sans pied de réponse (un tour en erreur n'en affiche pas). CO₂ inconnu :
                    # rien de stocké, pour ne pas passer le total de session à « — ».
                    error_turn["metrics_data"] = {"co2_mg": wasted_mg}
                render_error(error_turn["content"], error_turn["detail"])
                st.session_state.messages.append(error_turn)
                return
            finish_loading_status(state["loading"])

            # Affichage Final
            with msg_container.container():
                if result.thought:
                    with st.expander("Raisonnement", expanded=True):
                        st.markdown(result.thought)
                render_answer(result.clean_text)

            # Calculs
            metrics_data = _calculate_metrics(
                result.metrics,
                active_tag,
                active_is_cloud,
                interrupted_tokens=result.interrupted_output_tokens,
            )
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
