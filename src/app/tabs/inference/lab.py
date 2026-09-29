"""
Onglet « Banc d'essai » de l'Arène des modèles : un scénario, un modèle, une réponse mesurée.
Deux colonnes (configuration, résultat), métriques sous le résultat.
"""

import asyncio

import streamlit as st

from src.app.formatting import (
    format_co2,
    format_duration,
    format_number,
    format_throughput,
    mg_to_grams,
)
from src.app.states import (
    RETRY_MESSAGE,
    THROUGHPUT_HELP,
    finish_loading_status,
    render_answer,
    render_inference_error,
    render_no_models,
    start_loading_status,
)
from src.app.ui import ModelMenu, is_cloud_model, render_badge
from src.core.answer_carbon import answer_carbon_mg
from src.core.inference_service import InferenceCallbacks, InferenceService

# --- DONNÉES SCÉNARIOS ---
USE_CASES = {
    "Classification (JSON)": {
        "system": """Tu es un expert en analyse de sentiment. Réponds UNIQUEMENT avec un JSON : {"sentiment": "Positif"|"Neutre"|"Négatif", "categorie": "..."}.""",
        "user": """Analyse ce feedback : "La formation était top, mais la salle trop chaude." """,
    },
    "Traduction technique": {
        "system": 'Traduis en Anglais, Espagnol, Allemand. Format JSON : {"en": "...", "es": "...", "de": "..."}.',
        "user": "L'inférence locale garantit la confidentialité des données.",
    },
    "Extraction (JSON)": {
        "system": "Extrais les entités (Date, Montant, Vendeur). Réponds UNIQUEMENT en JSON.",
        "user": "Facture du 12/12/2024 de Wavestone pour 500€.",
    },
    "Assistant de code (Python)": {
        "system": "Tu es un expert Python. Génère du code typé et documenté.",
        "user": "Fonction asynchrone pour appeler une API REST avec retry.",
    },
    "Raisonnement pas à pas": {
        "system": "Utilise la méthode Chain of Thought : pense étape par étape avant de répondre.",
        "user": "J'ai 3 pommes. J'en mange une. J'en achète deux. J'en jette une. Combien m'en reste-t-il ?",
    },
    "Résumé": {
        "system": "Fais un résumé exécutif en bullet points.",
        "user": "Compte rendu de réunion : Le projet est en retard à cause de la validation API. On décale la livraison de 2 semaines.",
    },
}


def _render_result_text(
    res, expanded_thought: bool, model_tag: str | None = None, is_cloud: bool | None = None
) -> None:
    """Réponse du Banc d'essai, avec le badge Local ou Cloud du modèle qui l'a produite, ou
    `alert-error` si l'inférence a échoué."""
    if res.error:
        render_inference_error(res, model_tag)
        return
    if res.thought:
        with st.expander("Raisonnement du modèle", expanded=expanded_thought):
            st.markdown(res.thought)
    st.subheader("Réponse")
    render_badge(is_cloud)
    render_answer(res.clean_text)


def _render_metrics(res, model_tag: str | None, is_cloud: bool | None = None) -> None:
    """Débit, CO₂, chargement, durée totale et tokens sous le résultat ; rien si l'inférence
    n'a pas de mesures. « Chargement » seulement quand le fournisseur le mesure (Ollama).
    La fiche du modèle est trouvée par son tag, jamais par le libellé « Nom (tag) » ; la
    formule de CO₂ suit l'origine réelle du modèle (`is_cloud`, celle du badge)."""
    m = res.metrics
    if res.error or m is None:
        return

    st.divider()

    # CO₂ : règle unique du cœur, tokens d'une tentative coupée puis relancée compris ; « — »
    # s'il est inconnu (tag distant hors catalogue).
    wasted = getattr(res, "interrupted_output_tokens", 0) or 0
    carbon_mg = answer_carbon_mg(model_tag, m.output_tokens + wasted, is_cloud)
    carbon_help = (
        f"Compte aussi environ {format_number(wasted, 0)} tokens (fragments reçus) d'une "
        "génération coupée par Ollama, puis relancée."
        if wasted
        else None
    )

    # Affichage en grille ; débit = eval_count / eval_duration pour Ollama (D3).
    cells = [
        ("Débit", format_throughput(m.tokens_per_second, m.throughput_estimated), THROUGHPUT_HELP),
        ("CO₂", format_co2(mg_to_grams(carbon_mg)), carbon_help),
    ]
    if m.load_measured:
        cells.append(("Chargement", format_duration(m.load_duration_s), None))
    cells += [
        ("Durée totale", format_duration(m.total_duration_s), None),
        ("Tokens générés", format_number(m.output_tokens, 0), None),
    ]
    for col, (label, value, help_text) in zip(st.columns(len(cells)), cells, strict=True):
        col.metric(label, value, help=help_text)


def render_lab_tab(
    sorted_display_names: list,
    display_to_tag: dict,
    tag_to_friendly: dict,
    menu: ModelMenu | None = None,
):

    if not sorted_display_names:
        render_no_models(in_arena=True)
        return

    # --- LAYOUT ASYMÉTRIQUE (40% Input / 60% Output) ---
    col_input, col_output = st.columns([2, 3])

    # === COLONNE GAUCHE : CONFIGURATION ===
    with col_input:
        st.header("Configuration")

        # Sélection Modèle & Cas
        lab_model_display = st.selectbox("Modèle", sorted_display_names, key="lab_model_select")
        lab_model_tag = display_to_tag.get(lab_model_display)
        lab_is_cloud = is_cloud_model(lab_model_tag, menu)
        render_badge(lab_is_cloud)

        selected_use_case = st.selectbox("Scénario prédéfini", list(USE_CASES.keys()))
        default_sys = USE_CASES[selected_use_case]["system"]
        default_user = USE_CASES[selected_use_case]["user"]

        # Paramètres avancés cachés
        with st.expander("Réglages avancés", expanded=False):
            system_prompt = st.text_area(
                "Consigne système",
                value=default_sys,
                height=100,
                help="Prompt système : consigne donnée au modèle avant la question.",
            )
            lab_temp = st.slider("Température", 0.0, 1.0, 0.2)

        # Zone de Prompt User
        st.markdown("**Entrée utilisateur**")
        user_prompt = st.text_area(
            "Entrée utilisateur", value=default_user, height=200, label_visibility="collapsed"
        )

        # Bouton Action
        if st.button("Lancer le test", type="primary", width="stretch"):
            if lab_model_tag:
                st.session_state.lab_trigger = True
            else:
                st.warning("Choisissez un modèle.")

    # === COLONNE DROITE : RÉSULTAT ===
    with col_output:
        st.header("Résultat")

        # Container de résultat
        res_container = st.container(border=True)

        if st.session_state.get("lab_trigger"):
            # Reset trigger
            st.session_state.lab_trigger = False

            with res_container:
                # Premier chargement : indicateur avant la génération, clos au premier token.
                state = {"text": "", "loading": start_loading_status(lab_model_tag)}
                placeholder = st.empty()

                async def on_token(token: str):
                    if state["loading"] is not None:
                        finish_loading_status(state["loading"])
                        state["loading"] = None
                    state["text"] += token
                    placeholder.markdown(state["text"] + "▌")

                async def on_retry(_err):
                    # Génération coupée, relancée une fois : le texte partiel n'est plus montré.
                    # Coupure avant tout texte : le chargement est fini, comme dans `on_token`.
                    if state["loading"] is not None:
                        finish_loading_status(state["loading"])
                        state["loading"] = None
                    state["text"] = ""
                    placeholder.caption(RETRY_MESSAGE)

                callbacks = InferenceCallbacks(on_token=on_token, on_retry=on_retry)

                # RUN
                with st.spinner("Génération…"):
                    result = asyncio.run(
                        InferenceService.run_inference(
                            model_tag=lab_model_tag,
                            messages=[{"role": "user", "content": user_prompt}],
                            temperature=lab_temp,
                            system_prompt=system_prompt,
                            callbacks=callbacks,
                        )
                    )
                finish_loading_status(state["loading"], ok=not result.error)

                # Affichage Final (Clean), ou erreur lisible (délai dépassé…)
                placeholder.empty()
                _render_result_text(
                    result, expanded_thought=True, model_tag=lab_model_tag, is_cloud=lab_is_cloud
                )

                # Sauvegarde état pour affichage persistant (échec compris : au rerun
                # suivant, l'erreur s'affiche de nouveau, sans métriques).
                st.session_state.lab_last_result = result
                st.session_state.lab_last_tag = lab_model_tag
                st.session_state.lab_last_is_cloud = lab_is_cloud

        # Affichage Persistant (si un résultat existe déjà)
        elif "lab_last_result" in st.session_state:
            with res_container:
                _render_result_text(
                    st.session_state.lab_last_result,
                    expanded_thought=False,
                    model_tag=st.session_state.get("lab_last_tag"),
                    is_cloud=st.session_state.get("lab_last_is_cloud"),
                )

        # === ZONE MÉTRIQUES (Sous le résultat) ===
        if "lab_last_result" in st.session_state:
            _render_metrics(
                st.session_state.lab_last_result,
                st.session_state.get("lab_last_tag"),
                st.session_state.get("lab_last_is_cloud"),
            )

        else:
            with res_container:
                st.info("Choisissez un scénario, puis lancez le test pour voir le résultat.")
