import asyncio
import time

import streamlit as st

from src.core.llm_provider import LLMProvider
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

                with st.status("🚀 Pipeline RAG...", expanded=True) as status:
                    t0 = time.perf_counter()
                    status.write("🔍 Retrieval...")
                    retrieved = rag_engine.search(prompt, k=k_retrieval)
                    status.write(
                        f"   ✅ {len(retrieved)} docs trouvés ({time.perf_counter()-t0:.2f}s)"
                    )

                    context_text = "\n\n".join([doc.page_content for doc in retrieved])
                    sys_prompt = f"Tu es un assistant expert. Utilise ce contexte pour répondre:\n{context_text}"
                    payload = [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt},
                    ]

                    status.write(f"🧠 Génération avec {friendly_name}...")
                    t2 = time.perf_counter()

                    async def run_gen():
                        full_txt = ""
                        first = False
                        ttft = 0
                        stream = LLMProvider.chat_stream(selected_tag, payload, temperature=0.1)
                        async for chunk in stream:
                            if not first:
                                ttft = time.perf_counter() - t2
                                first = True
                            if isinstance(chunk, str):
                                full_txt += chunk
                                resp_container.markdown(full_txt + "▌")
                        return full_txt, ttft

                    full_resp, ttft_val = asyncio.run(run_gen())
                    status.update(label="✅ Réponse terminée", state="complete", expanded=False)
                    thought, clean = extract_thought(full_resp)

                    st.session_state.rag_messages.append(
                        {"role": "assistant", "content": clean, "thought": thought}
                    )

                    st.session_state.last_rag_debug = {
                        "sources": retrieved,
                        "ttft": ttft_val,
                        "total_time": time.perf_counter() - t0,
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
            st.metric("Temps Total", f"{d['total_time']:.2f}s", delta=f"TTFT: {d['ttft']:.2f}s")

            st.markdown("#### Sources")
            for i, doc in enumerate(d["sources"]):
                with st.expander(f"Source {i+1} : {doc.metadata.get('source', '?')}"):
                    st.caption(doc.page_content)
        else:
            st.info("Lancez une requête pour voir les détails.")
