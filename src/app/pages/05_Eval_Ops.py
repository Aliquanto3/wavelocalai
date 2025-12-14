import asyncio
import logging

import nest_asyncio
import streamlit as st

from src.core.eval_engine import EvalEngine
from src.core.llm_provider import LLMProvider
from src.core.models_db import get_friendly_name_from_tag
from src.core.resource_manager import ResourceManager

# --- PATCH ASYNCIO (CRITIQUE POUR RAGAS DANS STREAMLIT) ---
nest_asyncio.apply()

# Config Logging Page
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Eval Ops & Quality", page_icon="🎯", layout="wide")
# ... le reste du fichier reste IDENTIQUE, copie-le depuis ta version actuelle ...
st.title("🎯 Eval Ops : RAG Quality Audit")
st.caption("Évaluation 'LLM-as-a-Judge' utilisant Mistral AI pour noter vos modèles locaux.")

# --- INITIALISATION LAZY ---
if "rag_engine" not in st.session_state:
    st.warning(
        "⚠️ Le moteur RAG n'est pas initialisé. Veuillez passer par la page '03 RAG Knowledge' d'abord."
    )
    st.stop()

if "eval_engine" not in st.session_state:
    try:
        st.session_state.eval_engine = EvalEngine()
    except ValueError as e:
        st.error(f"❌ Configuration manquante : {e}")
        st.info("Ajoutez MISTRAL_API_KEY dans votre fichier .env")
        st.stop()
    except ImportError:
        st.error("❌ Librairie 'ragas' manquante. Installez-la via requirements.txt")
        st.stop()

# --- CONFIGURATION DU TEST ---
col_conf, col_run = st.columns([1, 2])

with col_conf:
    st.subheader("1. Candidat (Local)")

    # Sélection du modèle Élève
    installed = LLMProvider.list_models()
    local_models = [m for m in installed if m.get("type") == "local"]
    model_map = {get_friendly_name_from_tag(m["model"]): m["model"] for m in local_models}

    selected_friendly = st.selectbox("Modèle à évaluer", sorted(model_map.keys()))
    candidate_tag = model_map.get(selected_friendly)

    # Affichage info RAM (Resource Manager UI)
    if candidate_tag:
        ram_check = ResourceManager.check_resources(candidate_tag)
        if ram_check.allowed:
            st.success(
                f"RAM Dispo : {ram_check.ram_available_gb:.1f} GB (Besoin ~{ram_check.ram_required_gb:.1f} GB)"
            )
        else:
            st.error(f"⚠️ {ram_check.message}")
            st.stop()

    st.markdown("---")
    st.subheader("2. Juge (Cloud)")
    st.info("🤖 **Mistral Large** (API)")
    st.caption("Le juge utilise l'API pour ne pas surcharger la RAM locale.")

with col_run:
    st.subheader("3. Protocole de Test")

    query = st.text_area(
        "Question de test",
        "Quelle est la politique de confidentialité du projet WaveLocalAI ?",
        help="Posez une question dont la réponse se trouve dans vos documents RAG.",
    )

    if st.button("🚀 Lancer l'Audit Qualité", type="primary"):
        if not candidate_tag:
            st.error("Sélectionnez un modèle.")
            st.stop()

        status = st.status("audit en cours...", expanded=True)

        try:
            # ÉTAPE A : RAG RETRIEVAL
            status.write("🔍 1. Recherche des contextes (Vector Store)...")
            retrieved_docs = st.session_state.rag_engine.search(query, k=3)
            contexts = [doc.page_content for doc in retrieved_docs]

            if not contexts:
                status.update(label="❌ Erreur : Aucun contexte trouvé !", state="error")
                st.stop()

            status.write(f"   ✅ {len(contexts)} chunks récupérés.")

            # ÉTAPE B : GENERATION CANDIDAT
            status.write(f"🎤 2. Génération de la réponse par {selected_friendly}...")

            # Construction prompt simple pour le test
            prompt_rag = f"Contexte:\n{chr(10).join(contexts)}\n\nQuestion: {query}\nRéponse:"
            messages = [{"role": "user", "content": prompt_rag}]

            # Appel via InferenceService ou LLMProvider directement (ici Provider pour simplicité)
            # On utilise un wrapper async pour appeler le provider
            async def get_response():
                resp_text = ""
                stream = LLMProvider.chat_stream(candidate_tag, messages, temperature=0.1)
                async for chunk in stream:
                    if isinstance(chunk, str):
                        resp_text += chunk
                return resp_text

            generated_answer = asyncio.run(get_response())
            status.write("   ✅ Réponse générée.")

            # ÉTAPE C : JUGEMENT (RAGAS)
            status.write("⚖️ 3. Délibération du Juge (Mistral Large)...")
            eval_result = st.session_state.eval_engine.evaluate_single_turn(
                query=query, response=generated_answer, retrieved_contexts=contexts
            )

            status.update(label="✅ Audit Terminé !", state="complete", expanded=False)

            # --- RÉSULTATS ---
            st.divider()

            # 1. Scorecard (Mise à jour pour 2 métriques)
            c1, c2, c3 = st.columns(3)
            c1.metric("Note Globale", f"{eval_result.global_score * 100:.0f}/100")
            c2.metric(
                "Fidélité (Faithfulness)",
                f"{eval_result.faithfulness:.2f}",
                help="La réponse respecte-t-elle strictement le contexte ?",
            )
            c3.metric(
                "Pertinence Réponse",
                f"{eval_result.answer_relevancy:.2f}",
                help="La réponse adresse-t-elle la question ?",
            )

            # 2. Détails
            col_res, col_ctx = st.columns(2)

            with col_res:
                st.markdown("### 🤖 Réponse du Candidat")
                st.info(generated_answer)

            with col_ctx:
                st.markdown("### 📄 Contextes Soumis")
                for i, ctx in enumerate(contexts):
                    with st.expander(f"Source {i+1}", expanded=False):
                        st.caption(ctx)

        except Exception as e:
            status.update(label="❌ Erreur Critique", state="error")
            st.error(f"Détail de l'erreur : {str(e)}")
            logger.exception("EvalOps Failure")
