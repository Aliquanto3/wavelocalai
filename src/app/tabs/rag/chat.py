import asyncio
import time

import streamlit as st

from src.core.llm_provider import LLMProvider

# ✅ Import nécessaire pour identifier le type de chunk
from src.core.metrics import InferenceMetrics
from src.core.models_db import extract_thought


def render_rag_chat_tab(
    rag_engine, display_to_tag, tag_to_friendly, sorted_display_names, k_retrieval
):
    col_chat_main, col_chat_debug = st.columns([2, 1])

    with col_chat_main:
        selected_display = st.selectbox(
            "Modèle Actif (Chat)", sorted_display_names, key="rag_chat_select"
        )
        selected_tag = display_to_tag.get(selected_display)
        friendly_name = tag_to_friendly.get(selected_tag)

        st.divider()

        for msg in st.session_state.rag_messages:
            with st.chat_message(msg["role"]):
                if "thought" in msg and msg["thought"]:
                    with st.expander("💭 Raisonnement", expanded=False):
                        st.markdown(msg["thought"])
                st.markdown(msg["content"])

        if prompt := st.chat_input("Posez une question à vos documents..."):
            st.session_state.rag_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                resp_container = st.empty()

                with st.status("🚀 Pipeline RAG en cours...", expanded=True) as status:
                    t_start_pipeline = time.perf_counter()

                    # 1. Feedback Stratégie
                    current_strategy = rag_engine.strategy.__class__.__name__
                    if "HyDE" in current_strategy:
                        status.write("🔮 **HyDE** : Génération d'une réponse hypothétique...")
                    elif "SelfRAG" in current_strategy:
                        status.write(
                            "⚖️ **Self-RAG** : Analyse critique et réécriture potentielle..."
                        )
                    else:
                        status.write("🔍 **Naive** : Recherche par similarité directe...")

                    # 2. Retrieval avec Chrono
                    t_retrieval_start = time.perf_counter()
                    retrieved = rag_engine.search(prompt, k=k_retrieval)
                    d_retrieval = time.perf_counter() - t_retrieval_start

                    # Feedback Reranker
                    if rag_engine.current_reranker_name:
                        status.write(
                            f"🎯 **Retrieval & Reranking** : {len(retrieved)} documents trouvés ({d_retrieval:.2f}s)"
                        )
                    else:
                        status.write(
                            f"🔍 **Retrieval (Naive)** : {len(retrieved)} documents trouvés ({d_retrieval:.2f}s)"
                        )

                    context_text = "\n\n".join([doc.page_content for doc in retrieved])
                    sys_prompt = f"Tu es un assistant expert. Utilise ce contexte pour répondre:\n{context_text}"
                    payload = [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt},
                    ]

                    status.write(f"🧠 Génération avec {friendly_name}...")

                    # --- GÉNÉRATION ASYNC AVEC CAPTURE MÉTRIQUES ---
                    async def run_gen():
                        full_txt = ""
                        first = False
                        ttft = 0.0
                        captured_metrics = None  # Variable pour stocker les métriques

                        stream = LLMProvider.chat_stream(selected_tag, payload, temperature=0.1)
                        async for chunk in stream:
                            # Détection du TTFT (Time To First Token) sur le premier chunk de texte
                            if not first and isinstance(chunk, str):
                                ttft = (
                                    time.perf_counter() - t_start_pipeline
                                )  # approx depuis début pipeline ou t2
                                first = True

                            if isinstance(chunk, str):
                                full_txt += chunk
                                resp_container.markdown(full_txt + "▌")
                            elif isinstance(chunk, InferenceMetrics):
                                captured_metrics = chunk

                        return full_txt, ttft, captured_metrics

                    full_resp, ttft_val, metrics_obj = asyncio.run(run_gen())

                    total_duration = time.perf_counter() - t_start_pipeline
                    status.update(
                        label=f"✅ Réponse terminée ({total_duration:.2f}s)",
                        state="complete",
                        expanded=False,
                    )

                    thought, clean = extract_thought(full_resp)

                    st.session_state.rag_messages.append(
                        {"role": "assistant", "content": clean, "thought": thought}
                    )

                    # Sauvegarde des infos de debug pour la colonne de droite
                    st.session_state.last_rag_debug = {
                        "sources": retrieved,
                        "ttft": ttft_val,
                        "total_time": total_duration,
                        "metrics": metrics_obj,  # On stocke l'objet complet
                    }

                    resp_container.empty()
                    if thought:
                        with resp_container.container():
                            with st.expander("💭 CoT", expanded=True):
                                st.markdown(thought)
                            st.markdown(clean)
                    else:
                        resp_container.markdown(clean)

    with col_chat_debug:
        st.markdown("### 🔍 Sources & Métriques")
        if "last_rag_debug" in st.session_state:
            d = st.session_state.last_rag_debug

            # 1. Métriques de Performance
            st.markdown("#### ⚡ Performance")

            # Ligne 1 : Temps
            c1, c2 = st.columns(2)
            c1.metric("⏱️ Temps Total", f"{d['total_time']:.2f}s")
            c2.metric("⚡ TTFT", f"{d['ttft']:.2f}s")

            # Ligne 2 : Ressources (si disponibles dans metrics)
            metrics = d.get("metrics")
            if metrics:
                c3, c4 = st.columns(2)
                ram_val = f"{metrics.model_size_gb:.1f} GB" if metrics.model_size_gb else "N/A"
                co2_val = f"{metrics.carbon_g:.4f} g" if metrics.carbon_g is not None else "0 g"

                c3.metric("💾 RAM Peak", ram_val)
                c4.metric("🌍 CO2", co2_val)

                c5, c6 = st.columns(2)
                c5.metric("🚀 Vitesse", f"{metrics.tokens_per_second:.1f} t/s")
                c6.metric("📝 Output", f"{metrics.output_tokens} tok")
            else:
                st.info("Métriques détaillées non disponibles pour ce run.")

            st.divider()

            # 2. Sources
            st.markdown(f"#### 📚 Sources ({len(d['sources'])})")
            for i, doc in enumerate(d["sources"]):
                source_name = doc.metadata.get("source", "Inconnu")
                score = doc.metadata.get("score", None)  # Si disponible
                score_label = f" (Sc: {score:.2f})" if score else ""

                with st.expander(f"{i+1}. {source_name}{score_label}"):
                    st.caption(f"Stratégie: {doc.metadata.get('strategy', 'Naive')}")
                    st.text(doc.page_content)
        else:
            st.info("Lancez une requête pour voir les détails.")
