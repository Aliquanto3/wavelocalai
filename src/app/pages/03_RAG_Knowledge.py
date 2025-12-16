"""
RAG Knowledge Tab - Sprint 1 (Onboarding & Ingestion)
Changements :
- Upload via st.dialog (Modal)
- Sidebar nettoyée (Options avancées repliées)
- Gestion de l'état vide ("Empty State")
"""

import time

import nest_asyncio
import streamlit as st

# UI COMPONENTS
from src.app.tabs.rag.chat import render_rag_chat_tab
from src.app.tabs.rag.eval import render_rag_eval_tab
from src.core.config import DATA_DIR
from src.core.eval_engine import EvalEngine
from src.core.llm_provider import LLMProvider
from src.core.models_db import get_friendly_name_from_tag
from src.core.rag.strategies.hyde import HyDERetrievalStrategy
from src.core.rag.strategies.naive import NaiveRetrievalStrategy
from src.core.rag.strategies.self_rag import SelfRAGStrategy
from src.core.rag_engine import RAGEngine

# PATCH ASYNCIO
nest_asyncio.apply()

st.set_page_config(page_title="RAG Knowledge Base", page_icon="🧠", layout="wide")

# --- CSS CUSTOM (Empty State & Metrics) ---
st.markdown(
    """
<style>
    div[data-testid="stMetricValue"] { font-size: 1.2rem; }
    .big-icon { font-size: 4rem; text-align: center; display: block; margin-bottom: 1rem; }
    .empty-state-box {
        border: 2px dashed #4b4b4b;
        border-radius: 10px;
        padding: 3rem;
        text-align: center;
        margin-top: 2rem;
        background-color: #262730;
    }
</style>
""",
    unsafe_allow_html=True,
)


# --- 0. HELPERS ---
def get_local_models(subfolder: str):
    path = DATA_DIR / "models" / subfolder
    if not path.exists():
        return []
    return [d.name for d in path.iterdir() if d.is_dir()]


# --- 1. INITIALISATION SERVICES ---
if "rag_engine" not in st.session_state:
    with st.spinner("🚀 Démarrage du moteur RAG..."):
        avail_emb = get_local_models("embeddings")
        default_emb = (
            "bge-m3"
            if "bge-m3" in avail_emb
            else (avail_emb[0] if avail_emb else "all-MiniLM-L6-v2")
        )
        avail_rerank = get_local_models("rerankers")
        default_rerank = avail_rerank[0] if avail_rerank else None

        st.session_state.rag_engine = RAGEngine(
            embedding_model_name=default_emb, reranker_model_name=default_rerank
        )

if "eval_engine" not in st.session_state:
    try:
        st.session_state.eval_engine = EvalEngine()
    except Exception:
        # Optionnel : loguer l'erreur pour le débogage
        # print(f"Erreur lors de la lecture du système: {e}")
        st.session_state.eval_engine = None

if "rag_messages" not in st.session_state:
    st.session_state.rag_messages = []


# --- 2. MODAL D'INGESTION (NOUVEAU) ---
@st.dialog("📂 Gestion de la Base de Connaissance")
def open_knowledge_manager():
    st.caption("Ajoutez des documents PDF, TXT ou MD pour nourrir le cerveau de l'IA.")

    # Zone d'upload large
    uploaded_files = st.file_uploader(
        "Sélectionner des fichiers", type=["pdf", "txt", "md", "docx"], accept_multiple_files=True
    )

    if uploaded_files:
        st.info(f"📄 {len(uploaded_files)} fichier(s) prêt(s) à être indexé(s).")

        if st.button("🚀 Indexer maintenant", type="primary", use_container_width=True):
            # Simulation d'ingestion (Remplacer par votre appel réel rag_engine.add_documents)
            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                # Exemple de boucle d'ingestion
                for i, file in enumerate(uploaded_files):
                    status_text.text(f"Traitement de {file.name}...")
                    # --- CODE D'INGESTION RÉEL ICI ---
                    # rag_engine.ingest(file)
                    # ---------------------------------
                    time.sleep(0.5)  # Fake work pour la démo UX
                    progress_bar.progress((i + 1) / len(uploaded_files))

                st.success("✅ Indexation terminée avec succès !")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Erreur lors de l'indexation : {e}")

    st.divider()
    st.caption("Statistiques actuelles :")
    stats = st.session_state.rag_engine.get_stats()
    st.markdown(f"**{stats['count']} documents** dans la collection active.")

    if st.button("🗑️ Tout supprimer (Reset)", type="secondary"):
        st.session_state.rag_engine.clear_database()
        st.rerun()


# --- 3. SIDEBAR (NETTOYÉE) ---
with st.sidebar:
    st.header("🎛️ Configuration RAG")

    # A. Mode Cloud/Local
    if "cloud_enabled" not in st.session_state:
        st.session_state.cloud_enabled = True
    st.session_state.cloud_enabled = st.toggle(
        "Activer Cloud (Mistral)",
        value=st.session_state.cloud_enabled,
        help="Si désactivé, seuls les modèles locaux (Ollama) seront accessibles.",
    )
    if not st.session_state.cloud_enabled:
        st.caption("🔒 Local Only (Ollama)")

    st.divider()

    # B. Action Principale (Gros Bouton)
    st.markdown("#### 📚 Base de Connaissance")
    if st.button("📂 Gérer les Documents", type="primary", use_container_width=True, icon="📂"):
        open_knowledge_manager()

    # Stats Rapides
    stats = st.session_state.rag_engine.get_stats()
    st.caption(f"📊 **{stats['count']}** chunks indexés")

    st.divider()

    # C. Paramètres Avancés (Repliés)
    with st.expander("⚙️ Réglages Avancés (Experts)", expanded=False):
        # 1. Embedding
        st.caption("Cerveau Documentaire (Embedding)")
        avail_emb = get_local_models("embeddings") or ["sentence-transformers/all-MiniLM-L6-v2"]
        curr_emb = st.session_state.rag_engine.current_embedding_name
        sel_emb = st.selectbox(
            "Modèle",
            avail_emb,
            index=avail_emb.index(curr_emb) if curr_emb in avail_emb else 0,
            label_visibility="collapsed",
        )

        if sel_emb != curr_emb:
            st.session_state.rag_engine.set_models(embedding_name=sel_emb)
            st.rerun()

        st.markdown("---")

        # 2. Stratégie
        st.caption("Stratégie de Recherche")
        strat_mode = st.radio("Mode", ["Naive RAG", "HyDE", "Self-RAG"], index=0)
        k_retrieval = st.slider("Top-K Chunks", 1, 10, 4)

        # 3. Reranker
        st.caption("Reranker (Affinement)")
        avail_rerank = ["Aucun"] + get_local_models("rerankers")
        curr_rerank = st.session_state.rag_engine.current_reranker_name
        sel_rerank = st.selectbox(
            "Modèle",
            avail_rerank,
            index=avail_rerank.index(curr_rerank) if curr_rerank in avail_rerank else 0,
        )

        # Apply logic
        if strat_mode == "Naive RAG":
            st.session_state.rag_engine.set_strategy(NaiveRetrievalStrategy())
        elif strat_mode == "HyDE":
            st.session_state.rag_engine.set_strategy(HyDERetrievalStrategy())
        elif strat_mode == "Self-RAG":
            st.session_state.rag_engine.set_strategy(SelfRAGStrategy())

        # Reranker change logic would go here if needed per existing code

# --- 4. MAIN PAGE LOGIC ---

st.title("🧠 Assistant Documentaire")

# Vérification de l'état vide
doc_count = st.session_state.rag_engine.get_stats()["count"]

if doc_count == 0:
    # --- EMPTY STATE UI ---
    st.markdown(
        """
        <div class="empty-state-box">
            <div class="big-icon">📭</div>
            <h2>Votre base de connaissances est vide</h2>
            <p style="color: #cccccc;">Pour commencer à discuter avec vos documents, vous devez d'abord les importer.</p>
        </div>
    """,
        unsafe_allow_html=True,
    )

    col_center = st.columns([1, 2, 1])
    with col_center[1]:
        if st.button("🚀 Commencer l'ingestion", type="primary", use_container_width=True):
            open_knowledge_manager()

    st.markdown("### 💡 Pourquoi utiliser le RAG ?")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info(
            "**🔒 Confidentialité**\n\nVos documents restent en local, aucune fuite de données."
        )
    with c2:
        st.info("**⚡ Précision**\n\nLe modèle répond uniquement basé sur VOS sources vérifiées.")
    with c3:
        st.info(
            "**🌱 GreenOps**\n\nUtilisez des petits modèles précis plutôt que des monstres énergivores."
        )

else:
    # --- NORMAL UI (TABS) ---
    installed_models_list = LLMProvider.list_models(cloud_enabled=st.session_state.cloud_enabled)

    def format_model_label(m):
        icon = "☁️" if m.get("type") in ["cloud", "api"] else "💻"
        return f"{icon} {get_friendly_name_from_tag(m['model'])}"

    display_to_tag = {format_model_label(m): m["model"] for m in installed_models_list}
    tag_to_friendly = {
        m["model"]: get_friendly_name_from_tag(m["model"]) for m in installed_models_list
    }
    sorted_display_names = sorted(display_to_tag.keys())

    tab_chat, tab_eval = st.tabs(["💬 Discussion", "⚖️ Benchmark & Qualité"])

    with tab_chat:
        render_rag_chat_tab(
            st.session_state.rag_engine,
            display_to_tag,
            tag_to_friendly,
            sorted_display_names,
            k_retrieval,
        )

    with tab_eval:
        render_rag_eval_tab(
            st.session_state.rag_engine,
            st.session_state.eval_engine,
            display_to_tag,
            tag_to_friendly,
            sorted_display_names,
        )
