import asyncio
import logging
import os
import tempfile
import time

import nest_asyncio
import pandas as pd
import streamlit as st

from src.core.eval_engine import EvalEngine
from src.core.llm_provider import LLMProvider
from src.core.models_db import extract_thought, get_friendly_name_from_tag, get_model_info
from src.core.rag_engine import RAGEngine

# --- PATCH ASYNCIO (CRITIQUE POUR RAGAS) ---
nest_asyncio.apply()

st.set_page_config(page_title="RAG Knowledge & Eval", page_icon="📚", layout="wide")

# --- CSS CUSTOM ---
st.markdown(
    """
<style>
    [data-testid="stMetricValue"] { font-size: 20px; }
</style>
""",
    unsafe_allow_html=True,
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

if "rag_messages" not in st.session_state:
    st.session_state.rag_messages = []

# --- 2. SIDEBAR : GESTION COMMUNE & CONFIG ---
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

        duration = time.perf_counter() - start_ingest
        st.success(f"Indexation terminée en {duration:.2f}s !")
        time.sleep(1)
        st.rerun()

    st.markdown("---")
    k_retrieval = st.slider("Nombre de sources (k)", 1, 10, 3)

    if st.button("🗑️ PURGER LA BASE", type="primary"):
        st.session_state.rag_engine.clear_database()
        st.toast("Base effacée.", icon="🧹")
        time.sleep(1)
        st.rerun()

# --- HELPER : FORMATAGE LISTE MODÈLES ---
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


# --- 3. ONGLETS PRINCIPAUX ---
tab_chat, tab_eval = st.tabs(["💬 Chat RAG", "⚖️ Évaluation (EvalOps)"])

# ==============================================================================
# ONGLET 1 : CHAT CLASSIQUE
# ==============================================================================
with tab_chat:
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
                    retrieved = st.session_state.rag_engine.search(prompt, k=k_retrieval)
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

# ==============================================================================
# ONGLET 2 : EVAL OPS (BENCHMARK MULTI-MODÈLES)
# ==============================================================================
with tab_eval:
    st.subheader("🎯 LLM-as-a-Judge : Benchmark Comparatif")
    st.caption(
        "Comparez les performances (Vitesse, RAM, CO2) et la pertinence de plusieurs modèles sur une même question RAG."
    )

    if "eval_engine" not in st.session_state:
        st.error("Le moteur d'évaluation n'est pas disponible (pip install ragas).")

    else:
        col_conf, col_run = st.columns([1, 2])

        with col_conf:
            st.markdown("#### 1. Configuration")

            candidate_displays = st.multiselect(
                "🤖 Modèles Candidats (Élèves)",
                sorted_display_names,
                default=[sorted_display_names[0]] if sorted_display_names else None,
                help="Sélectionnez un ou plusieurs modèles à comparer.",
            )
            candidate_tags = [display_to_tag[d] for d in candidate_displays]

            st.markdown("---")

            st.markdown("#### ⚖️ Modèle Juge")

            default_judge_idx = 0
            for i, d in enumerate(sorted_display_names):
                if "mistral" in d.lower() or "gpt" in d.lower() or "large" in d.lower():
                    default_judge_idx = i

            judge_display = st.selectbox(
                "Sélectionner le Juge",
                sorted_display_names,
                index=default_judge_idx,
                key="eval_judge",
                help="Utilisez un modèle performant pour noter les autres.",
            )
            judge_tag = display_to_tag.get(judge_display)

        with col_run:
            st.markdown("#### 2. Protocole de Test")

            query = st.text_area(
                "Question de référence",
                "Quelle est la politique de confidentialité du projet WaveLocalAI ?",
                height=100,
            )

            if st.button("🚀 Lancer le Benchmark", type="primary"):
                if not candidate_tags or not judge_tag:
                    st.error("Sélectionnez au moins un candidat et un juge.")
                    st.stop()

                with st.spinner("🔍 Récupération du contexte (RAG Common)..."):
                    try:
                        retrieved_docs = st.session_state.rag_engine.search(query, k=3)
                        contexts = [doc.page_content for doc in retrieved_docs]
                        if not contexts:
                            st.error("❌ Aucun document trouvé pour cette question.")
                            st.stop()
                    except Exception as e:
                        st.error(f"Erreur Retrieval : {e}")
                        st.stop()

                results_data = []
                detailed_responses = {}

                prog_container = st.status("📊 Exécution du Benchmark...", expanded=True)
                total_steps = len(candidate_tags)
                prog_bar = prog_container.progress(0.0)

                async def _stream_to_text(model_tag: str, prompt_text: str) -> str:
                    txt = ""
                    stream = LLMProvider.chat_stream(
                        model_tag,
                        [{"role": "user", "content": prompt_text}],
                        temperature=0.1,
                    )
                    async for chunk in stream:
                        if isinstance(chunk, str):
                            txt += chunk
                    return txt

                for i, c_tag in enumerate(candidate_tags):
                    c_friendly = tag_to_friendly[c_tag]
                    prog_container.write(
                        f"▶️ [{i+1}/{total_steps}] Évaluation de **{c_friendly}**..."
                    )

                    try:
                        prog_container.write("   🎤 Génération...")
                        t_start = time.perf_counter()

                        prompt_rag = (
                            f"Contexte:\n{chr(10).join(contexts)}\n\nQuestion: {query}\nRéponse:"
                        )

                        full_resp = asyncio.run(_stream_to_text(c_tag, prompt_rag))

                        duration = time.perf_counter() - t_start

                        thought, clean_answer = extract_thought(full_resp)

                        out_tokens = len(full_resp) // 4

                        prog_container.write("   ⚖️ Notation par le Juge...")
                        eval_result = st.session_state.eval_engine.evaluate_single_turn(
                            query=query,
                            response=clean_answer,
                            retrieved_contexts=contexts,
                            judge_tag=judge_tag,
                        )

                        info = get_model_info(c_friendly) or {}
                        bench_stats = info.get("benchmark_stats", {})

                        # Fix Arrow : Récupération propre avec type float ou None (pas de "N/A" string)
                        ref_ram_raw = bench_stats.get("ram_usage_gb")
                        ref_ram = float(ref_ram_raw) if ref_ram_raw is not None else None

                        # Fix CO2 : Conversion kg -> g
                        ref_co2_kg = bench_stats.get("co2_emissions_kg")
                        ref_co2_g = (ref_co2_kg * 1000) if ref_co2_kg is not None else None

                        results_data.append(
                            {
                                "Modèle": c_friendly,
                                "Score Global": f"{eval_result.global_score * 100:.0f}/100",
                                "Fidélité": eval_result.faithfulness,
                                "Pertinence": eval_result.answer_relevancy,
                                "Durée (s)": round(duration, 2),
                                "Out Tokens": out_tokens,
                                "RAM (Ref GB)": ref_ram,  # Float ou None
                                "CO2 (Ref g)": ref_co2_g,  # Float (g) ou None
                            }
                        )

                        detailed_responses[c_friendly] = {
                            "text": clean_answer,
                            "thought": thought,
                            "score": eval_result.global_score,
                        }

                    except Exception as e:
                        st.error(f"Erreur sur {c_friendly}: {e}")

                    prog_bar.progress((i + 1) / total_steps)

                prog_container.update(
                    label="✅ Benchmark Terminé !", state="complete", expanded=False
                )

                st.divider()
                st.subheader("🏆 Tableau Comparatif")

                if results_data:
                    df = pd.DataFrame(results_data)

                    st.dataframe(
                        df,
                        column_config={
                            "Score Global": st.column_config.ProgressColumn(
                                "Qualité Globale",
                                help="Moyenne Fidélité + Pertinence",
                                format="%s",
                                min_value=0,
                                max_value=100,
                            ),
                            "Fidélité": st.column_config.NumberColumn(
                                "Fidélité",
                                help="Respect du contexte documentaire (0-1)",
                                format="%.2f",
                            ),
                            "Durée (s)": st.column_config.NumberColumn("Latence", format="%.2f s"),
                            "RAM (Ref GB)": st.column_config.NumberColumn(
                                "RAM (Ref)", format="%.1f GB"
                            ),
                            "CO2 (Ref g)": st.column_config.NumberColumn(
                                "CO2 (Ref)",
                                format="%.4f g",
                                help="Impact carbone de référence pour une requête standard.",
                            ),
                        },
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.subheader("📝 Analyse des Réponses & Sources")

                    with st.expander(
                        "📄 Voir les Contextes utilisés (Communs à tous)", expanded=False
                    ):
                        for k, ctx in enumerate(contexts):
                            st.info(f"**Chunk {k+1}** : {ctx[:300]}...")

                    for name, data in sorted(
                        detailed_responses.items(), key=lambda x: x[1]["score"], reverse=True
                    ):
                        score_txt = f"{data['score']*100:.0f}/100"
                        with st.expander(f"🤖 {name} (Note: {score_txt})", expanded=False):
                            if data["thought"]:
                                st.markdown("#### 💭 Raisonnement (Chain of Thought)")
                                st.info(data["thought"])

                            st.markdown("#### 🎤 Réponse")
                            st.markdown(data["text"])

                else:
                    st.warning("Aucun résultat généré.")
