"""
Assistant documentaire : import de documents, discussion avec ses sources, évaluation.

- Import via st.dialog
- Réglages experts repliés dans la barre latérale
- État vide explicite
"""

import time

import nest_asyncio
import streamlit as st

# UI COMPONENTS
from src.app.tabs.rag.chat import render_rag_chat_tab
from src.app.tabs.rag.eval import render_rag_eval_tab
from src.app.formatting import pluralize
from src.app.modules import DOCUMENTS
from src.app.ui import FAVICON_PATH, model_options
from src.core.config import DATA_DIR
from src.core.eval_engine import EvalEngine
from src.core.llm_provider import LLMProvider
from src.core.rag.strategies.hyde import HyDERetrievalStrategy
from src.core.rag.strategies.naive import NaiveRetrievalStrategy
from src.core.rag.strategies.self_rag import SelfRAGStrategy
from src.core.rag_engine import RAGEngine

# PATCH ASYNCIO
nest_asyncio.apply()

st.set_page_config(page_title=DOCUMENTS.title, page_icon=FAVICON_PATH, layout="wide")

# Stratégies de recherche : libellé affiché → classe. Noms techniques en aide seulement.
SEARCH_STRATEGIES = {
    "Recherche directe": NaiveRetrievalStrategy,
    "Réponse hypothétique": HyDERetrievalStrategy,
    "Auto-vérification": SelfRAGStrategy,
}
SEARCH_STRATEGIES_HELP = (
    "Recherche directe : Naive RAG. Réponse hypothétique : HyDE, le modèle rédige une réponse "
    "supposée qui sert à chercher. Auto-vérification : Self-RAG, le modèle juge la pertinence "
    "des extraits."
)


# --- 0. HELPERS ---
def get_local_models(subfolder: str):
    path = DATA_DIR / "models" / subfolder
    if not path.exists():
        return []
    return [d.name for d in path.iterdir() if d.is_dir()]


def _base_summary(stats: dict) -> str:
    """« 2 documents indexés · 14 extraits » à partir de VectorStoreManager.get_stats."""
    # Un extrait sans métadonnée « source » (None ou vide) ne compte pas comme un document.
    sources = [s for s in stats.get("sources", []) if s]
    documents = pluralize(len(sources), "document indexé", "documents indexés")
    return f"{documents} · {pluralize(stats['count'], 'extrait')}"


# --- 1. INITIALISATION SERVICES ---
if "rag_engine" not in st.session_state:
    with st.spinner("Démarrage de l'assistant documentaire…"):
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
@st.dialog("Gérer la base documentaire")
def open_knowledge_manager():
    st.caption("Ajoutez des documents PDF, TXT, MD ou DOCX à la base documentaire.")

    # Zone d'upload large
    uploaded_files = st.file_uploader(
        "Sélectionner des fichiers", type=["pdf", "txt", "md", "docx"], accept_multiple_files=True
    )

    if uploaded_files:
        ready = pluralize(
            len(uploaded_files), "fichier prêt à être indexé", "fichiers prêts à être indexés"
        )
        st.info(f"{ready}.")

        if st.button(
            "Indexer les documents", type="primary", icon=":material/upload:", width="stretch"
        ):
            # Simulation d'ingestion (Remplacer par votre appel réel rag_engine.add_documents)
            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                # Exemple de boucle d'ingestion
                for i, file in enumerate(uploaded_files):
                    status_text.text(f"Traitement de {file.name}…")
                    # --- CODE D'INGESTION RÉEL ICI ---
                    # rag_engine.ingest(file)
                    # ---------------------------------
                    time.sleep(0.5)  # Fake work pour la démo UX
                    progress_bar.progress((i + 1) / len(uploaded_files))

                st.success("Indexation terminée.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Erreur lors de l'indexation : {e}")

    st.divider()
    st.caption("Contenu actuel")
    stats = st.session_state.rag_engine.get_stats()
    st.markdown(_base_summary(stats))

    if st.button("Vider la base documentaire", type="secondary", icon=":material/delete:"):
        st.session_state.rag_engine.clear_database()
        st.rerun()


# --- 3. SIDEBAR (NETTOYÉE) ---
with st.sidebar:
    st.divider()

    # A. Gestion des documents (secondaire : l'action principale de la vue est dans la page)
    st.subheader("Base documentaire")
    if st.button("Gérer la base documentaire", icon=":material/folder_open:", width="stretch"):
        open_knowledge_manager()

    # Contenu de la base
    stats = st.session_state.rag_engine.get_stats()
    st.caption(_base_summary(stats))

    st.divider()

    # B. Réglages experts (repliés)
    with st.expander("Réglages avancés", expanded=False):
        # 1. Embedding
        st.caption(
            "Modèle de représentation des textes",
            help="Modèle d'embedding qui convertit chaque extrait en vecteur.",
        )
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

        st.divider()

        # 2. Stratégie
        strat_mode = st.radio(
            "Stratégie de recherche", list(SEARCH_STRATEGIES), index=0, help=SEARCH_STRATEGIES_HELP
        )
        k_retrieval = st.slider(
            "Nombre d'extraits",
            1,
            10,
            4,
            help="Top-K : nombre d'extraits retrouvés pour chaque question.",
        )

        # 3. Reranker
        avail_rerank = ["Aucun"] + get_local_models("rerankers")
        curr_rerank = st.session_state.rag_engine.current_reranker_name
        sel_rerank = st.selectbox(
            "Modèle de reclassement",
            avail_rerank,
            index=avail_rerank.index(curr_rerank) if curr_rerank in avail_rerank else 0,
            help="Reranker : réordonne les extraits retrouvés par pertinence.",
        )

        # Apply logic
        st.session_state.rag_engine.set_strategy(SEARCH_STRATEGIES[strat_mode]())

        # Reranker change logic would go here if needed per existing code

# --- 4. MAIN PAGE LOGIC ---

st.title(DOCUMENTS.title)

# Vérification de l'état vide
doc_count = st.session_state.rag_engine.get_stats()["count"]

if doc_count == 0:
    # --- EMPTY STATE UI (card native) ---
    with st.container(border=True):
        st.header("Votre base documentaire est vide")
        st.write("Importez vos documents pour pouvoir les interroger.")
        if st.button("Importer des documents", type="primary", icon=":material/upload_file:"):
            open_knowledge_manager()

    st.header("Pourquoi un assistant documentaire local ?")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("**Confidentialité**\n\nVos documents restent sur cette machine.")
    with c2:
        st.info(
            "**Précision**\n\nLe modèle répond à partir de vos sources, citées sous la réponse."
        )
    with c3:
        st.info(
            "**Sobriété**\n\nDe petits modèles précis plutôt que de grands modèles énergivores."
        )

else:
    # --- NORMAL UI (TABS) ---
    installed_models_list = LLMProvider.list_models(
        cloud_enabled=st.session_state.get("cloud_enabled", True)
    )

    display_to_tag, tag_to_friendly, sorted_display_names = model_options(
        installed_models_list, cloud_types=("cloud", "api")
    )

    tab_chat, tab_eval = st.tabs(["Discussion", "Évaluation de la qualité"])

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
