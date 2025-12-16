import asyncio
import time

import pandas as pd
import streamlit as st

from src.core.llm_provider import LLMProvider
from src.core.metrics import InferenceMetrics  # ✅ Import essentiel
from src.core.models_db import extract_thought, get_model_info


def render_rag_eval_tab(
    rag_engine, eval_engine, display_to_tag, tag_to_friendly, sorted_display_names
):
    st.subheader("🎯 LLM-as-a-Judge : Benchmark Comparatif")
    st.caption(
        "Comparez les performances (Vitesse, RAM, CO2) et la pertinence de plusieurs modèles sur une même question RAG."
    )

    if not eval_engine:
        st.error("Le moteur d'évaluation n'est pas disponible (pip install ragas).")
        return

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
            "Quels sont les objectifs principaux du projet ?",
            height=100,
        )

        if st.button("🚀 Lancer le Benchmark", type="primary"):
            if not candidate_tags or not judge_tag:
                st.error("Sélectionnez au moins un candidat et un juge.")
                st.stop()

            # 1. Retrieval Commun (Pour être équitable, tous les modèles ont le même contexte)
            with st.spinner("🔍 Récupération du contexte (RAG Common)..."):
                try:
                    retrieved_docs = rag_engine.search(query, k=3)
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

            # Fonction helper pour capturer les métriques du stream
            async def _stream_and_capture(model_tag: str, prompt_text: str):
                txt = ""
                captured_metrics = None

                stream = LLMProvider.chat_stream(
                    model_tag,
                    [{"role": "user", "content": prompt_text}],
                    temperature=0.1,
                )
                async for chunk in stream:
                    if isinstance(chunk, str):
                        txt += chunk
                    elif isinstance(chunk, InferenceMetrics):
                        captured_metrics = chunk

                return txt, captured_metrics

            for i, c_tag in enumerate(candidate_tags):
                c_friendly = tag_to_friendly[c_tag]
                prog_container.write(f"▶️ [{i+1}/{total_steps}] Évaluation de **{c_friendly}**...")

                try:
                    # --- PRÉPARATION DU PROMPT RAG ---
                    # ✅ CORRECTION 1 : Construction de la variable prompt_rag manquante
                    context_block = "\n".join(contexts)
                    prompt_rag = (
                        f"Tu es un assistant expert. Utilise le contexte suivant pour répondre à la question.\n\n"
                        f"Contexte:\n{context_block}\n\n"
                        f"Question: {query}"
                    )

                    # --- CHRONO GÉNÉRATION ---
                    t_gen_start = time.perf_counter()
                    prog_container.write("   🎤 Génération...")

                    full_resp, metrics_obj = asyncio.run(_stream_and_capture(c_tag, prompt_rag))

                    d_gen = time.perf_counter() - t_gen_start
                    prog_container.write(f"   ✅ Généré en {d_gen:.2f}s")

                    thought, clean_answer = extract_thought(full_resp)
                    out_tokens = len(full_resp) // 4

                    # --- CHRONO NOTATION ---
                    t_eval_start = time.perf_counter()
                    prog_container.write("   ⚖️ Notation par le Juge...")

                    # On récupère l'embedding actif depuis le RAGEngine
                    active_embedding_model = rag_engine.embedding_model

                    eval_result = eval_engine.evaluate_single_turn(
                        query=query,
                        response=clean_answer,
                        retrieved_contexts=contexts,
                        judge_tag=judge_tag,
                        embedding_model=active_embedding_model,
                    )
                    d_eval = time.perf_counter() - t_eval_start
                    prog_container.write(f"   ✅ Noté en {d_eval:.2f}s")

                    # --- RÉCUPÉRATION DES MÉTRIQUES ---
                    # Récupération des vraies valeurs mesurées par LLMProvider
                    real_ram = metrics_obj.model_size_gb if metrics_obj else None
                    real_co2 = metrics_obj.carbon_g if metrics_obj else None

                    # Fallback sur les valeurs statiques (JSON) si pas de mesure live (ex: API Cloud)
                    if real_ram is None or real_ram == 0:
                        info = get_model_info(c_friendly) or {}
                        bench_stats = info.get("benchmark_stats", {})
                        real_ram = bench_stats.get("ram_usage_gb")

                    results_data.append(
                        {
                            "Modèle": c_friendly,
                            "Score Global": f"{eval_result.global_score * 100:.0f}/100",
                            "Fidélité": eval_result.faithfulness,
                            "Pertinence": eval_result.answer_relevancy,
                            "Durée (s)": round(
                                d_gen, 2
                            ),  # ✅ CORRECTION 2 : Utilisation de d_gen au lieu de duration
                            "Out Tokens": out_tokens,
                            "RAM (Go)": real_ram,
                            "CO2 (g)": real_co2,
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

            prog_container.update(label="✅ Benchmark Terminé !", state="complete", expanded=False)

            st.divider()
            st.subheader("🏆 Tableau Comparatif")

            if results_data:
                df = pd.DataFrame(results_data)
                # ✅ CORRECTION 3 : Alignement des clés de config avec les données
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
                            "Fidélité", help="Respect du contexte documentaire (0-1)", format="%.2f"
                        ),
                        "Durée (s)": st.column_config.NumberColumn("Latence", format="%.2f s"),
                        "RAM (Go)": st.column_config.NumberColumn("RAM (Go)", format="%.1f GB"),
                        "CO2 (g)": st.column_config.NumberColumn(
                            "CO2 (g)", format="%.6f g", help="Impact carbone mesuré (CodeCarbon)."
                        ),
                    },
                    use_container_width=True,
                    hide_index=True,
                )

                st.subheader("📝 Analyse des Réponses & Sources")
                with st.expander("📄 Voir les Contextes utilisés (Communs à tous)", expanded=False):
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
