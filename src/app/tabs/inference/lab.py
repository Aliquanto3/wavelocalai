import asyncio

import streamlit as st

from src.core.inference_service import InferenceCallbacks, InferenceService
from src.core.models_db import get_model_info

# Données statiques (Cas d'usage)
USE_CASES = {
    "📊 Classification Verbatims (JSON)": {
        "system": """Tu es un expert en analyse de feedback post-formation.
    Ton objectif est d'analyser une liste de commentaires bruts au format JSON.
    Pour chaque commentaire, tu dois produire un objet JSON contenant deux champs :
    1. "sentiment" : Uniquement 'Positif', 'Neutre' ou 'Négatif'.
    2. "categorie" : La thématique principale parmi ['Contenu', 'Animateur', 'Logistique', 'Applicabilité', 'Technique'].

    Réponds UNIQUEMENT avec le JSON final minifié, sans markdown, sans introduction.""",
        "user": """{
        "1": "La formation était top, j'ai tout compris sur les prompts.",
        "2": "Le formateur parlait trop vite, difficile de suivre.",
        "3": "Copilot est impressionnant mais je ne vois pas l'usage dans mon métier.",
        "4": "La salle était trop chaude, impossible de se concentrer.",
        "5": "Très utile, je gagne déjà du temps sur mes mails.",
        "6": "L'outil a planté deux fois pendant la démo...",
        "7": "C'était correct, sans plus.",
        "8": "Les exemples concrets sur Excel étaient pertinents.",
        "9": "Je n'ai pas reçu le support de présentation promis.",
        "10": "Génial, mais ça fait peur pour l'avenir de nos jobs !"
    }""",
    },
    "🇬🇧 Traduction Technique": {
        "system": 'Tu es un expert en traduction technique. Traduis le texte suivant en Anglais, Espagnol et Allemand. Sois précis sur la terminologie informatique. Réponds au format JSON : {"en": "...", "es": "...", "de": "..."}.',
        "user": "L'architecture 'Local First' permet de réduire la latence réseau et d'améliorer la confidentialité des données en traitant les inférences directement sur le CPU de l'utilisateur, sans appel API vers le cloud.",
    },
    "📄 Extraction Structurée (JSON)": {
        "system": "Tu es un extracteur de données strict. Extrais les entités du texte (Date, Montant, Vendeur, Articles). Réponds UNIQUEMENT avec un JSON valide. Pas de texte avant ni après.",
        "user": "FACTURE N° 2024-001\nDate : 12 décembre 2024\nVendeur : Wavestone Tech\n\nArticles :\n- 1x Audit Green IT (500€)\n- 3x Licences Copilot (90€)\n\nTotal TTC : 590€",
    },
    "💻 Assistant Coding (Python)": {
        "system": "Tu es un Tech Lead Python expérimenté. Génère du code propre, typé (Type Hints) et documenté (Docstrings). Inclus une gestion d'erreur robuste.",
        "user": "Écris une fonction Python asynchrone qui interroge une API REST avec la librairie 'httpx', gère les retries en cas d'erreur 500, et retourne le résultat en dictionnaire.",
    },
    "🧮 Raisonnement (Chain of Thought)": {
        "system": "Tu es un expert en logique. Pour répondre, tu dois IMPÉRATIVEMENT utiliser la méthode 'Chain of Thought' : explique ton raisonnement étape par étape avant de donner la réponse finale.",
        "user": "J'ai 3 pommes. Hier j'en ai mangé une. Aujourd'hui j'en achète deux autres, mais j'en fais tomber une dans la boue que je jette. Combien de pommes puis-je manger maintenant ?",
    },
    "📝 Résumé Exécutif": {
        "system": "Tu es un assistant de direction. Fais un résumé concis (bullet points) du texte fourni, en te concentrant sur les décisions clés et les actions à entreprendre.",
        "user": "Compte rendu de réunion - Projet Alpha.\nLa réunion a débuté à 10h. L'équipe a convenu que le budget initial était insuffisant. Marc doit revoir le fichier Excel d'ici mardi. Sophie a soulevé un risque de sécurité sur l'API, il faut auditer le module d'auth. La deadline du projet est repoussée de 2 semaines pour permettre ces ajustements. Le client a validé le nouveau design.",
    },
}


def render_lab_tab(sorted_display_names: list, display_to_tag: dict, tag_to_friendly: dict):
    col_lab_config, col_lab_run, col_lab_metrics = st.columns([1, 2, 1])

    with col_lab_config:
        st.subheader("1. Scénario")
        lab_model_display = st.selectbox(
            "Modèle de Test", sorted_display_names, key="lab_model_select"
        )
        lab_model_tag = display_to_tag.get(lab_model_display)
        lab_model_friendly = tag_to_friendly.get(lab_model_tag, "Inconnu")

        selected_use_case = st.selectbox("Cas d'Usage", list(USE_CASES.keys()))
        default_sys = USE_CASES[selected_use_case]["system"]
        default_user = USE_CASES[selected_use_case]["user"]

        lab_temp = st.slider(
            "Température",
            0.0,
            1.0,
            0.2,
            key="lab_temp",
            help="Basse pour extraction/code, Haute pour créativité",
        )

    with col_lab_run:
        st.subheader("2. Entrées & Sorties")
        with st.expander("🛠️ Prompt Système", expanded=True):
            system_prompt = st.text_area("Instruction Système", value=default_sys, height=100)
        user_prompt = st.text_area("Prompt Utilisateur", value=default_user, height=150)

        if st.button("🚀 Lancer le Test (One-Shot)", use_container_width=True):
            if lab_model_tag:
                placeholder = st.empty()
                state = {"current_text": ""}

                async def on_token(token: str):
                    state["current_text"] += token
                    placeholder.markdown(state["current_text"] + "▌")

                callbacks = InferenceCallbacks(on_token=on_token)
                messages = [{"role": "user", "content": user_prompt}]

                with st.spinner("Inférence en cours..."):
                    result = asyncio.run(
                        InferenceService.run_inference(
                            model_tag=lab_model_tag,
                            messages=messages,
                            temperature=lab_temp,
                            system_prompt=system_prompt,
                            callbacks=callbacks,
                        )
                    )

                placeholder.empty()
                if result.thought:
                    with placeholder.container(), st.expander("💭 Raisonnement", expanded=True):
                        st.markdown(result.thought)
                    st.markdown(result.clean_text)
                else:
                    placeholder.markdown(result.clean_text)

                st.session_state.lab_result = result.raw_text
                st.session_state.lab_metrics = result.metrics
            else:
                st.warning("Sélectionnez un modèle.")

    with col_lab_metrics:
        st.subheader("3. Audit")
        m = st.session_state.lab_metrics
        if m:
            info = get_model_info(lab_model_friendly)
            size_gb = info["size_gb"] if info else "?"

            st.markdown("#### ⚡ Performance")
            st.metric(
                "Débit (t/s)",
                f"{m.tokens_per_second}",
                delta="Fluide" if m.tokens_per_second > 20 else "Lent",
            )
            st.metric("Latence Totale", f"{m.total_duration_s} s")

            st.markdown("#### 💻 Technique")
            st.text(f"Load Time: {m.load_duration_s}s")
            st.text(f"In Tokens: {m.input_tokens}")
            st.text(f"Out Tokens: {m.output_tokens}")
            st.metric("RAM Modèle", size_gb)

            st.markdown("#### 🌱 Impact")
            st.progress(0.1, text="Calcul CodeCarbon...")
        else:
            st.info("Lancez un test pour voir les métriques.")
