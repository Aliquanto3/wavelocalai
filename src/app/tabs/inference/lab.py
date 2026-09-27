"""
Onglet « Banc d'essai » de l'Arène des modèles : un scénario, un modèle, une réponse mesurée.
Deux colonnes (configuration, résultat), métriques sous le résultat.
"""

import asyncio

import streamlit as st

from src.app.formatting import format_duration, format_number, format_unit
from src.core.green_monitor import CarbonCalculator
from src.core.inference_service import InferenceCallbacks, InferenceService
from src.core.models_db import get_model_info
from src.core.utils import extract_params_billions as _extract_params_billions

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


def render_lab_tab(sorted_display_names: list, display_to_tag: dict, tag_to_friendly: dict):

    # --- LAYOUT ASYMÉTRIQUE (40% Input / 60% Output) ---
    col_input, col_output = st.columns([2, 3])

    # === COLONNE GAUCHE : CONFIGURATION ===
    with col_input:
        st.header("Configuration")

        # Sélection Modèle & Cas
        lab_model_display = st.selectbox("Modèle", sorted_display_names, key="lab_model_select")
        lab_model_tag = display_to_tag.get(lab_model_display)
        lab_model_friendly = tag_to_friendly.get(lab_model_tag, "Modèle inconnu")

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
                placeholder = st.empty()
                state = {"text": ""}

                async def on_token(token: str):
                    state["text"] += token
                    placeholder.markdown(state["text"] + "▌")

                callbacks = InferenceCallbacks(on_token=on_token)

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

                # Affichage Final (Clean)
                placeholder.empty()
                if result.thought:
                    with st.expander("Raisonnement du modèle", expanded=True):
                        st.markdown(result.thought)

                st.subheader("Réponse")
                st.markdown(result.clean_text)

                # Sauvegarde état pour affichage persistant
                st.session_state.lab_last_result = result
                st.session_state.lab_last_model = lab_model_friendly

        # Affichage Persistant (si un résultat existe déjà)
        elif "lab_last_result" in st.session_state:
            res = st.session_state.lab_last_result
            with res_container:
                if res.thought:
                    with st.expander("Raisonnement du modèle", expanded=False):
                        st.markdown(res.thought)
                st.subheader("Réponse")
                st.markdown(res.clean_text)

        # === ZONE MÉTRIQUES (Sous le résultat) ===
        if "lab_last_result" in st.session_state:
            res = st.session_state.lab_last_result
            model_name = st.session_state.lab_last_model
            m = res.metrics
            info = get_model_info(model_name) or {}

            st.divider()

            # Calcul CO2
            is_api = info.get("type") == "api"
            carbon_mg = 0.0
            if is_api and m.output_tokens > 0:
                p = _extract_params_billions(info.get("params_act") or info.get("params_tot", "0"))
                carbon_mg = CarbonCalculator.compute_mistral_impact_g(p, m.output_tokens) * 1000
            else:
                carbon_mg = CarbonCalculator.compute_local_theoretical_g(m.output_tokens) * 1000

            # Affichage en Grid
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Débit", format_unit(m.tokens_per_second, "tokens/s"))
            c2.metric("CO₂", format_unit(carbon_mg, "mg", 2))
            c3.metric("Durée totale", format_duration(m.total_duration_s))
            c4.metric("Tokens générés", format_number(m.output_tokens, 0))

        else:
            with res_container:
                st.info("Choisissez un scénario, puis lancez le test pour voir le résultat.")
