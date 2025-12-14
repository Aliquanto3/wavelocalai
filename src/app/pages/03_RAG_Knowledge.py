import asyncio
import logging
import os
import tempfile
import time

import nest_asyncio
import streamlit as st

# IMPORT DES NOUVEAUX TABS
from src.app.tabs.rag.chat import render_rag_chat_tab
from src.app.tabs.rag.eval import render_rag_eval_tab
from src.core.eval_engine import EvalEngine
from src.core.llm_provider import LLMProvider
from src.core.models_db import get_friendly_name_from_tag
from src.core.rag_engine import RAGEngine

# PATCH ASYNCIO
nest_asyncio.apply()

st.set_page_config(page_title="RAG Knowledge & Eval", page_icon="📚", layout="wide")
st.markdown(
    """<style>[data-testid="stMetricValue"] { font-size: 20px; }</style>""", unsafe_allow_html=True
)

st.title("📚 RAG Knowledge Base")
st.caption("Interrogation documentaire et Benchmark de Qualité (EvalOps).")

# --- 1. INITIALISATION SERVICES ---
if "rag_engine" not in st.session_state:
    with st.spinner("🚀 Démarrage du moteur vectoriel..."):
        st.session_state.rag_engine = RAGEngine()

if "eval_engine" not in st.session_state:
    try:
        st.session_state.eval_engine = EvalEngine()
    except Exception as e:
        logging.warning(f"⚠️ Moteur d'évaluation non chargé (Manque Ragas ?) : {e}")
        st.session_state.eval_engine = None

if "rag_messages" not in st.session_state:
    st.session_state.rag_messages = []

# --- 2. SIDEBAR COMMUNE ---
with st.sidebar:
    st.header("⚙️ Configuration")
    if "rag_cloud_enabled" not in st.session_state:
        st.session_state.rag_cloud_enabled = True

    cloud_enabled = st.toggle(
        "Activer Cloud (Mistral)",
        value=st.session_state.rag_cloud_enabled,
        help="Active l'accès aux modèles via API (Mistral, etc).",
    )
    st.session_state.rag_cloud_enabled = cloud_enabled
    st.divider()
    st.header("🗄️ Base Documentaire")

    stats = st.session_state.rag_engine.get_stats()
    st.metric("Chunks Vectorisés", stats["count"])

    with st.expander("Voir les sources", expanded=False):
        if stats["sources"]:
            for src in stats["sources"]:
                st.text(f"📄 {src}")
        else:
            st.caption("Base vide.")

    st.markdown("---")
    st.subheader("Ajouter des documents")
    uploaded_files = st.file_uploader(
        "Upload PDF/TXT", type=["pdf", "txt", "md"], accept_multiple_files=True
    )

    if uploaded_files and st.button(f"⚡ Indexer {len(uploaded_files)} fichier(s)"):
        progress_bar = st.progress(0, text="Démarrage...")
        start_ingest = time.perf_counter()

        async def process_uploads():
            for i, uploaded_file in enumerate(uploaded_files):
                suffix = f".{uploaded_file.name.split('.')[-1]}"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                    tmp_file.write(uploaded_file.getbuffer())
                    tmp_path = tmp_file.name
                try:
                    await st.session_state.rag_engine.ingest_file_async(
                        tmp_path, uploaded_file.name
                    )
                except Exception as e:
                    st.error(f"Erreur sur {uploaded_file.name} : {e}")
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                progress_bar.progress((i + 1) / len(uploaded_files))

        asyncio.run(process_uploads())
        st.success(f"Indexation terminée en {time.perf_counter() - start_ingest:.2f}s !")
        time.sleep(1)
        st.rerun()

    st.markdown("---")
    k_retrieval = st.slider("Nombre de sources (k)", 1, 10, 3)

    if st.button("🗑️ PURGER LA BASE", type="primary"):
        st.session_state.rag_engine.clear_database()
        st.toast("Base effacée.", icon="🧹")
        time.sleep(1)
        st.rerun()

# --- PREPARATION DATA ---
installed_models_list = LLMProvider.list_models(cloud_enabled=st.session_state.rag_cloud_enabled)


def format_model_label(model_data):
    tag = model_data["model"]
    is_cloud = model_data.get("type") == "cloud" or model_data.get("type") == "api"
    friendly = get_friendly_name_from_tag(tag)
    icon = "☁️" if is_cloud else "💻"
    return f"{icon} {friendly}"


display_to_tag = {format_model_label(m): m["model"] for m in installed_models_list}
tag_to_friendly = {
    m["model"]: get_friendly_name_from_tag(m["model"]) for m in installed_models_list
}
sorted_display_names = sorted(display_to_tag.keys())

# --- 3. ONGLETS ---
tab_chat, tab_eval = st.tabs(["💬 Chat RAG", "⚖️ Évaluation (EvalOps)"])

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
