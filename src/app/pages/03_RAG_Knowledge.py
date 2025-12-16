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

# STRATEGIES
from src.core.rag.strategies.naive import NaiveRetrievalStrategy
from src.core.rag.strategies.self_rag import SelfRAGStrategy

# CORE IMPORTS
from src.core.rag_engine import RAGEngine

# PATCH ASYNCIO
nest_asyncio.apply()

st.set_page_config(page_title="RAG Knowledge & Eval", page_icon="🧠", layout="wide")

# --- CSS CUSTOM ---
st.markdown(
    """
<style>
    [data-testid="stMetricValue"] { font-size: 20px; }
    .stAlert { padding: 0.5rem; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("🧠 RAG Knowledge Base 2.0")
st.caption("Architecture Modulaire : Multi-Embeddings, Multi-Formats & Stratégies Avancées.")


# --- 0. HELPERS : SCAN MODELS ---
def get_local_models(subfolder: str):
    """Scanne le dossier data/models/{subfolder} pour lister les modèles disponibles."""
    path = DATA_DIR / "models" / subfolder
    if not path.exists():
        return []
    return [d.name for d in path.iterdir() if d.is_dir()]


# --- 1. INITIALISATION SERVICES ---
if "rag_engine" not in st.session_state:
    with st.spinner("🚀 Démarrage du moteur RAG modulaire..."):
        # On cherche un embedding par défaut
        avail_emb = get_local_models("embeddings")
        default_emb = (
            "bge-m3"
            if "bge-m3" in avail_emb
            else (avail_emb[0] if avail_emb else "all-MiniLM-L6-v2")
        )

        # On cherche un reranker par défaut
        avail_rerank = get_local_models("rerankers")
        default_rerank = avail_rerank[0] if avail_rerank else None

        st.session_state.rag_engine = RAGEngine(
            embedding_model_name=default_emb, reranker_model_name=default_rerank
        )

if "eval_engine" not in st.session_state:
    try:
        st.session_state.eval_engine = EvalEngine()
    except Exception:
        st.session_state.eval_engine = None

if "rag_messages" not in st.session_state:
    st.session_state.rag_messages = []

# --- 2. SIDEBAR : CONFIGURATION AVANCÉE ---
with st.sidebar:
    st.header("🎛️ RAG Parameters")

    if "cloud_enabled" not in st.session_state:
        st.session_state.cloud_enabled = True

    cloud_enabled = st.toggle(
        "Activer Cloud (Mistral)",
        value=st.session_state.cloud_enabled,
        help="Si désactivé, seuls les modèles locaux (Ollama) seront accessibles.",
    )
    st.session_state.cloud_enabled = cloud_enabled

    if not cloud_enabled:
        st.caption("🔒 Mode Local Strict")

    st.divider()

    # --- SECTION 1 : MODÈLE ACTIF (Toujours visible) ---
    st.caption("Base Vectorielle Active")
    available_embeddings = get_local_models("embeddings")
    if not available_embeddings:
        available_embeddings = ["sentence-transformers/all-MiniLM-L6-v2"]

    current_emb = st.session_state.rag_engine.current_embedding_name

    selected_emb = st.selectbox(
        "Modèle d'Embedding",
        available_embeddings,
        index=available_embeddings.index(current_emb) if current_emb in available_embeddings else 0,
        label_visibility="collapsed",
    )

    # Logique de changement (inchangée)
    if selected_emb != current_emb:
        with st.spinner(f"🔄 Switching to {selected_emb}..."):
            st.session_state.rag_engine.set_models(embedding_name=selected_emb)
            st.toast(f"Embedding changé : {selected_emb}", icon="🔌")
            time.sleep(0.5)
            st.rerun()

    # Stats compactes
    stats = st.session_state.rag_engine.get_stats()
    col_s1, col_s2 = st.columns([2, 1])

    # Le message du tooltip
    tooltip_msg = (
        f"ℹ️ Note : Les documents sont stockés dans des collections séparées.\n"
        f"Si vous changez de modèle ({selected_emb}), vous ne verrez que les documents indexés avec lui."
    )

    col_s1.metric("Docs Indexés", stats["count"], help=tooltip_msg)  # <--- Ajout de help=

    if col_s2.button("🧹", help="Purger cette base"):
        st.session_state.rag_engine.clear_database()
        st.rerun()

    st.divider()

    # --- SECTION 2 : INGESTION (Caché par défaut) ---
    with st.expander("📥 Ajouter des Documents", expanded=False):
        uploaded_files = st.file_uploader(
            "Upload",
            type=["pdf", "txt", "md", "docx"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )

        if uploaded_files and st.button(
            f"Index {len(uploaded_files)} fichiers", use_container_width=True
        ):
            # ... (Garder ton code d'ingestion ici) ...
            # Code inchangé pour process_uploads...
            pass

    # --- SECTION 3 : STRATÉGIE (Caché par défaut) ---
    with st.expander("🧠 Stratégie de Recherche", expanded=False):
        # Reranker
        available_rerankers = get_local_models("rerankers")
        current_reranker = st.session_state.rag_engine.current_reranker_name
        reranker_options = ["Aucun"] + available_rerankers

        selected_reranker_display = st.selectbox(
            "Reranker (Affinement)",
            reranker_options,
            index=(
                reranker_options.index(current_reranker)
                if current_reranker in reranker_options
                else 0
            ),
        )
        # ... (Logique reranker inchangée) ...

        st.markdown("---")

        # Strategy Selector
        strategy_mode = st.radio(
            "Architecture",
            ["Naive RAG", "HyDE", "Self-RAG"],
            captions=["Rapide", "Créatif", "Correctif (Lent)"],
            index=0,
        )

        k_retrieval = st.slider("Top-K Sources", 1, 10, 4)

        # Application stratégie (inchangée)
        if strategy_mode == "Naive RAG":
            st.session_state.rag_engine.set_strategy(NaiveRetrievalStrategy())
        elif strategy_mode == "HyDE":
            st.session_state.rag_engine.set_strategy(HyDERetrievalStrategy())
        elif strategy_mode == "Self-RAG":
            st.session_state.rag_engine.set_strategy(SelfRAGStrategy())


# --- 3. MAIN TABS ---
# Préparation des données modèles pour le chat
installed_models_list = LLMProvider.list_models(cloud_enabled=st.session_state.cloud_enabled)


def format_model_label(m):
    icon = "☁️" if m.get("type") in ["cloud", "api"] else "💻"
    return f"{icon} {get_friendly_name_from_tag(m['model'])}"


display_to_tag = {format_model_label(m): m["model"] for m in installed_models_list}
tag_to_friendly = {
    m["model"]: get_friendly_name_from_tag(m["model"]) for m in installed_models_list
}
sorted_display_names = sorted(display_to_tag.keys())

tab_chat, tab_eval = st.tabs(["💬 Chat Interactif", "⚖️ EvalOps Dashboard"])

with tab_chat:
    # On passe k_retrieval au chat render
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
