import streamlit as st
import os
import time
import tempfile
import pandas as pd
from src.core.rag_engine import RAGEngine
from src.core.llm_provider import LLMProvider
from src.core.models_db import MODELS_DB, get_friendly_name_from_tag, extract_thought

st.set_page_config(page_title="RAG Knowledge Base", page_icon="📚", layout="wide")

st.title("📚 RAG Knowledge Base")
st.caption("Interrogez vos documents locaux avec traçabilité complète.")

# --- 1. INITIALISATION ---
if "rag_engine" not in st.session_state:
    with st.spinner("🚀 Démarrage du moteur vectoriel (Embeddings)..."):
        # C'est souvent ici que ça prend du temps la première fois (téléchargement modèle embedding)
        st.session_state.rag_engine = RAGEngine()

if "rag_messages" not in st.session_state:
    st.session_state.rag_messages = []

# --- 2. SIDEBAR : GESTION DES DOCS ---
with st.sidebar:
    st.header("🗄️ Base Documentaire")
    
    # A. État de la base (Introspection)
    stats = st.session_state.rag_engine.get_stats()
    st.metric("Chunks Vectorisés", stats['count'])
    
    with st.expander("Voir les sources indexées", expanded=False):
        if stats['sources']:
            for src in stats['sources']:
                st.text(f"📄 {src}")
        else:
            st.caption("Aucun document en base.")

    st.markdown("---")

    # B. Ingestion
    st.subheader("Ajouter des documents")
    uploaded_files = st.file_uploader(
        "Upload PDF/TXT", 
        type=["pdf", "txt", "md"], 
        accept_multiple_files=True
    )
    
    if uploaded_files:
        if st.button(f"⚡ Indexer {len(uploaded_files)} fichier(s)"):
            progress_bar = st.progress(0, text="Démarrage...")
            start_ingest = time.perf_counter()
            
            # --- DÉBUT MODIFICATION ASYNC ---
            async def process_uploads():
                for i, uploaded_file in enumerate(uploaded_files):
                    # Fichier temporaire
                    suffix = f".{uploaded_file.name.split('.')[-1]}"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                        tmp_file.write(uploaded_file.getbuffer())
                        tmp_path = tmp_file.name
                    
                    try:
                        # Appel de la nouvelle méthode asynchrone (non-bloquante)
                        # Cela permet à Streamlit de continuer à rafraîchir la barre de progression
                        await st.session_state.rag_engine.ingest_file_async(tmp_path, uploaded_file.name)
                    except Exception as e:
                        st.error(f"Erreur sur {uploaded_file.name} : {e}")
                    finally:
                        # Nettoyage
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                    
                    # Mise à jour de la barre
                    progress_bar.progress((i + 1) / len(uploaded_files), text=f"Indexation de {uploaded_file.name}...")

            import asyncio
            asyncio.run(process_uploads())
            # --- FIN MODIFICATION ASYNC ---
            
            duration = time.perf_counter() - start_ingest
            st.success(f"Indexation terminée en {duration:.2f}s !")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    
    # C. Paramètres & Modèle
    k_retrieval = st.slider("Nombre de sources (k)", 1, 10, 3)
    
    st.markdown("### 🧠 Modèle")
    installed = LLMProvider.list_models()
    
    # Mapping Friendly Names
    model_map = {get_friendly_name_from_tag(m['model']): m['model'] for m in installed} if installed else {}
    
    # Tri Alphabétique
    sorted_names = sorted(model_map.keys())
    
    selected_friendly = st.selectbox("Sélectionner un LLM", sorted_names)
    selected_tag = model_map.get(selected_friendly)

    st.markdown("---")
    if st.button("🗑️ PURGER LA BASE", type="primary"):
        st.session_state.rag_engine.clear_database()
        st.toast("Base vectorielle effacée.", icon="🧹")
        time.sleep(1)
        st.rerun()

# --- 3. INTERFACE CHAT AVEC OBSERVABILITÉ ---
col_chat, col_debug = st.columns([2, 1])

with col_chat:
    # Affichage historique
    for msg in st.session_state.rag_messages:
        with st.chat_message(msg["role"]):
            if "thought" in msg and msg["thought"]:
                with st.expander("💭 Raisonnement RAG", expanded=False):
                    st.markdown(msg["thought"])
            st.markdown(msg["content"])

    # Input
    if prompt := st.chat_input("Votre question sur les documents..."):
        st.session_state.rag_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # --- PROCESSUS RAG DÉTAILLÉ ---
        with st.chat_message("assistant"):
            response_container = st.empty()
            full_response = ""
            
            # Conteneur de Status (Step-by-step)
            with st.status("🚀 Exécution du Pipeline RAG...", expanded=True) as status:
                
                # ÉTAPE 1 : Retrieval
                t0 = time.perf_counter()
                status.write("🔍 1. Vectorisation & Recherche (Retrieval)...")
                try:
                    retrieved_docs = st.session_state.rag_engine.search(prompt, k=k_retrieval)
                    t1 = time.perf_counter()
                    retrieval_time = t1 - t0
                    status.write(f"   ✅ Trouvé {len(retrieved_docs)} sources en {retrieval_time:.4f}s")
                except Exception as e:
                    status.update(label="❌ Erreur Retrieval", state="error")
                    st.error(str(e))
                    st.stop()

                # ÉTAPE 2 : Construction Prompt (Ajout du timer demandé)
                t_ctx_start = time.perf_counter()
                status.write("📝 2. Assemblage du Contexte...")
                
                context_text = "\n\n".join([doc.page_content for doc in retrieved_docs])
                system_prompt = f"""Tu es un assistant expert. Réponds à la question en utilisant UNIQUEMENT le contexte ci-dessous.
                Si la réponse n'y est pas, dis "Je ne sais pas".
                
                CONTEXTE :
                {context_text}"""
                
                rag_payload = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
                
                t_ctx_end = time.perf_counter()
                ctx_time = t_ctx_end - t_ctx_start
                status.write(f"   ✅ Assemblé en {ctx_time:.5f}s") # Affichage de la durée d'assemblage
                
                # ÉTAPE 3 : Génération (Inférence) avec TTFT
                status.write(f"🧠 3. Génération avec {selected_friendly}...")
                t2 = time.perf_counter()
                
                try:
                    # --- DÉBUT REMPLACEMENT ASYNC (CORRIGÉ) ---
                    async def run_rag_gen():
                        # Initialisation des variables locales à la fonction
                        current_response = ""
                        current_ttft = 0.0
                        first_token_seen = False
                        
                        # Appel asynchrone
                        stream = LLMProvider.chat_stream(selected_tag, rag_payload, temperature=0.1)
                        
                        async for chunk in stream:
                             # Détection du TTFT (Time To First Token)
                             if not first_token_seen:
                                current_ttft = time.perf_counter() - t2
                                first_token_seen = True
                                status.write(f"   ⏱️ Premier token après {current_ttft:.2f}s (Chargement Modèle)")
                             
                             if isinstance(chunk, str):
                                current_response += chunk
                                response_container.markdown(current_response + "▌")
                        
                        # On retourne les valeurs finales vers le script principal
                        return current_response, current_ttft

                    import asyncio
                    # Exécution et récupération des résultats
                    full_response, ttft = asyncio.run(run_rag_gen())
                    # --- FIN REMPLACEMENT ASYNC ---
                    
                    t3 = time.perf_counter()
                    gen_time = t3 - t2
                    
                    # Estimation débit (Tokens/s) - Approx 1 mot = 1.3 tokens ou via len/4
                    est_tokens = len(full_response) / 4 
                    tps = est_tokens / (gen_time - ttft) if (gen_time - ttft) > 0 else 0
                    
                    response_container.markdown(full_response)
                    status.write(f"   ⚡ Débit génération : ~{tps:.1f} tokens/s")
                    
                    # Finalisation Status
                    total_time = t3 - t0
                    status.update(label=f"✅ Réponse en {total_time:.2f}s (TTFT: {ttft:.2f}s)", state="complete", expanded=False)
                    
                    # Sauvegarde Historique
                    st.session_state.rag_messages.append({"role": "assistant", "content": full_response})
                    st.session_state.last_rag_debug = {
                        "retrieval_time": retrieval_time,
                        "gen_time": gen_time,
                        "ttft": ttft,
                        "sources": retrieved_docs
                    }

                    # --- NOUVEL AFFICHAGE ---
                    response_container.empty() # On efface le stream brut
                    
                    thought, clean_text = extract_thought(full_response)
                    
                    if thought:
                        with response_container.container():
                            with st.expander("💭 Analyse du Contexte", expanded=True):
                                st.markdown(thought)
                            st.markdown(clean_text)
                    else:
                        response_container.markdown(full_response)
                        clean_text = full_response

                    # Mise à jour status
                    status.write(f"   ⚡ Débit génération : ~{tps:.1f} tokens/s")
                    total_time = t3 - t0
                    status.update(label=f"✅ Réponse en {total_time:.2f}s", state="complete", expanded=False)
                    
                    # Sauvegarde Historique Enrichie
                    st.session_state.rag_messages.append({
                        "role": "assistant", 
                        "content": clean_text,
                        "thought": thought
                    })
                    
                except Exception as e:
                    status.update(label="❌ Erreur Inférence", state="error")
                    st.error(f"Erreur LLM : {e}")

# --- 4. PANNEAU DE DROITE (DEBUG & SOURCES) ---
with col_debug:
    st.subheader("🔍 Analyse Technique")
    
    if "last_rag_debug" in st.session_state:
        debug = st.session_state.last_rag_debug
        
        # Métriques Rapides
        c1, c2 = st.columns(2)
        c1.metric("Retrieval", f"{debug['retrieval_time']:.3f}s")
        c2.metric("Inférence", f"{debug['gen_time']:.2f}s")
        
        st.markdown("---")
        st.markdown("### 📄 Sources Utilisées")
        
        sources = debug.get("sources", [])
        if sources:
            for i, doc in enumerate(sources):
                source_name = doc.metadata.get('source', 'Inconnu')
                with st.expander(f"Source {i+1} : {source_name}", expanded=False):
                    st.caption(f"Score pertinence: (N/A avec Chroma standard)") 
                    st.info(doc.page_content)
        else:
            st.warning("Aucune source trouvée pour cette question.")
    else:
        st.info("Lancez une requête pour voir les détails d'exécution.")