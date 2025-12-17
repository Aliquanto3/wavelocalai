"""
RAG Eval Tab - Sprint 3 (Dashboard Décisionnel)
Changements :
- Intégration de la bibliothèque Altair pour les graphiques.
- Création d'un "Podium" pour les 3 meilleurs modèles.
- Matrice de Décision : Graphique Qualité (Y) vs CO2 (X).
- Séparation des données brutes (pour calculs) et formatées (pour affichage).
"""

import asyncio
import time

import altair as alt
import pandas as pd
import streamlit as st

# --- SSOT GreenOps ---
from src.core.green_monitor import CarbonCalculator
from src.core.llm_provider import LLMProvider
from src.core.metrics import InferenceMetrics
from src.core.models_db import extract_thought, get_model_info
from src.core.utils import extract_params_billions as _extract_params_billions


def render_rag_eval_tab(
    rag_engine, eval_engine, display_to_tag, tag_to_friendly, sorted_display_names
):

    # EN-TÊTE
    c_title, c_badge = st.columns([3, 1])
    with c_title:
        st.subheader("⚖️ Dashboard d'Évaluation (LLM-as-a-Judge)")
        st.caption("Benchmark comparatif : Qualité vs Impact Environnemental.")
    with c_badge:
        # Petit badge informatif
        st.info(
            "💡 **GreenOps** : Le but est de trouver le modèle le plus léger possible qui maintient une qualité acceptable."
        )

    if not eval_engine:
        st.error("⚠️ Le moteur d'évaluation (Ragas) n'est pas installé.")
        return

    st.divider()

    # 1. CONFIGURATION DU BENCHMARK
    col_conf, col_run = st.columns([1, 2])

    with col_conf:
        st.markdown("#### 1. Candidats")
        candidate_displays = st.multiselect(
            "Sélectionner les modèles à tester",
            sorted_display_names,
            default=[sorted_display_names[0]] if sorted_display_names else None,
            label_visibility="collapsed",
        )
        candidate_tags = [display_to_tag[d] for d in candidate_displays]

        st.markdown("#### 2. Juge")
        # Auto-select a smart model as judge
        default_judge_idx = 0
        for i, d in enumerate(sorted_display_names):
            if "mistral" in d.lower() or "gpt" in d.lower() or "large" in d.lower():
                default_judge_idx = i

        judge_display = st.selectbox("Modèle Juge", sorted_display_names, index=default_judge_idx)
        judge_tag = display_to_tag.get(judge_display)

    with col_run:
        st.markdown("#### 3. Question de Référence")
        query = st.text_area(
            "Entrez une question complexe nécessitant le contexte documentaire",
            "Quels sont les risques principaux mentionnés dans le document ?",
            height=100,
        )

        run_btn = st.button("🚀 Lancer le Benchmark", type="primary", use_container_width=True)

    # 2. LOGIQUE D'EXÉCUTION
    if run_btn:
        if not candidate_tags or not judge_tag:
            st.error("Veuillez sélectionner au moins un candidat et un juge.")
            st.stop()

        # A. Retrieval Commun (Pour équité)
        with st.spinner("🔍 Récupération du contexte commun..."):
            try:
                retrieved_docs = rag_engine.search(query, k=3)
                contexts = [doc.page_content for doc in retrieved_docs]
                if not contexts:
                    st.warning("⚠️ Aucun document trouvé. L'évaluation risque d'être faussée.")
            except Exception as e:
                st.error(f"Erreur Retrieval : {e}")
                st.stop()

        # B. Boucle d'évaluation
        results_raw = []  # Pour les graphiques (floats)
        detailed_responses = {}

        prog_container = st.status("📊 Benchmark en cours...", expanded=True)
        total_steps = len(candidate_tags)
        prog_bar = prog_container.progress(0.0)

        # Helper Async
        async def _stream_and_capture(model_tag, prompt_text):
            txt = ""
            metrics = None
            stream = LLMProvider.chat_stream(
                model_tag, [{"role": "user", "content": prompt_text}], temperature=0.1
            )
            async for chunk in stream:
                if isinstance(chunk, str):
                    txt += chunk
                elif isinstance(chunk, InferenceMetrics):
                    metrics = chunk
            return txt, metrics

        for i, c_tag in enumerate(candidate_tags):
            c_friendly = tag_to_friendly[c_tag]
            prog_container.write(f"▶️ Test de **{c_friendly}**...")

            try:
                # Génération
                context_block = "\n".join(contexts)
                prompt_rag = f"Contexte:\n{context_block}\n\nQuestion: {query}"

                t0 = time.perf_counter()
                full_resp, metrics_obj = asyncio.run(_stream_and_capture(c_tag, prompt_rag))
                d_gen = time.perf_counter() - t0

                thought, clean_answer = extract_thought(full_resp)

                # Calcul Carbone (SSOT)
                carbon_mg = 0.0
                info = get_model_info(c_friendly) or {}
                ram_gb = 0.0

                if metrics_obj:
                    ram_gb = metrics_obj.model_size_gb or 0.0
                    if info.get("type") == "api" and metrics_obj.output_tokens > 0:
                        p = _extract_params_billions(
                            info.get("params_act") or info.get("params_tot", "0")
                        )
                        carbon_mg = (
                            CarbonCalculator.compute_mistral_impact_g(p, metrics_obj.output_tokens)
                            * 1000
                        )
                    else:
                        carbon_mg = (
                            CarbonCalculator.compute_local_theoretical_g(metrics_obj.output_tokens)
                            * 1000
                        )

                # Notation Juge
                prog_container.write("   ⚖️ Le juge délibère...")
                eval_result = eval_engine.evaluate_single_turn(
                    query=query,
                    response=clean_answer,
                    retrieved_contexts=contexts,
                    judge_tag=judge_tag,
                    embedding_model=rag_engine.embedding_model,
                )

                # Stockage Brut
                results_raw.append(
                    {
                        "Modèle": c_friendly,
                        "Score": eval_result.global_score,  # Float 0-1
                        "CO2_mg": carbon_mg,  # Float
                        "Latence_s": d_gen,  # Float
                        "Fidélité": eval_result.faithfulness,
                        "Pertinence": eval_result.answer_relevancy,
                        "RAM_GB": ram_gb,
                    }
                )

                detailed_responses[c_friendly] = {"text": clean_answer, "thought": thought}

            except Exception as e:
                st.error(f"Erreur sur {c_friendly}: {e}")

            prog_bar.progress((i + 1) / total_steps)

        prog_container.update(label="✅ Benchmark Terminé !", state="complete", expanded=False)

        # 3. VISUALISATION & PODIUM
        if results_raw:
            df = pd.DataFrame(results_raw)

            st.divider()

            # A. PODIUM (Top 3 Scores)
            st.markdown("### 🏆 Le Podium Qualité")
            df_sorted = df.sort_values("Score", ascending=False).reset_index(drop=True)

            cols_podium = st.columns(3)
            medals = ["🥇", "🥈", "🥉"]

            for i in range(min(3, len(df_sorted))):
                row = df_sorted.iloc[i]
                with cols_podium[i], st.container(border=True):
                    st.markdown(f"#### {medals[i]} {row['Modèle']}")
                    s_percent = row["Score"] * 100
                    st.metric("Score Global", f"{s_percent:.0f}/100")
                    st.caption(f"Coût : {row['CO2_mg']:.2f} mgCO₂")

            st.divider()

            # B. MATRICE DE DÉCISION (Altair Chart)
            # Axe X : Impact CO2 (On veut le plus bas possible -> à gauche)
            # Axe Y : Qualité (On veut le plus haut possible -> en haut)
            # Le "Sweet Spot" est en haut à gauche.

            st.markdown("### 🎯 Matrice de Décision : Qualité vs Impact")
            st.caption(
                "Le modèle idéal se situe en **haut à gauche** (Haute Qualité, Faible Impact)."
            )

            chart = (
                alt.Chart(df)
                .mark_circle(size=150)
                .encode(
                    x=alt.X("CO2_mg", title="Impact CO₂ (mg) - Plus bas est mieux"),
                    y=alt.Y(
                        "Score",
                        title="Qualité Globale (0-1) - Plus haut est mieux",
                        scale=alt.Scale(domain=[0, 1]),
                    ),
                    color="Modèle",
                    tooltip=[
                        "Modèle",
                        alt.Tooltip("Score", format=".2%"),
                        alt.Tooltip("CO2_mg", format=".2f"),
                        "Latence_s",
                    ],
                )
                .interactive()
            )

            st.altair_chart(chart, use_container_width=True)

            # C. TABLEAU DÉTAILLÉ
            st.markdown("### 📝 Données Détaillées")

            # Formatage pour l'affichage tableau uniquement
            df_display = df.copy()
            df_display["Score Global"] = (df_display["Score"] * 100).map("{:.0f}".format)

            st.dataframe(
                df_display,
                column_config={
                    "Modèle": st.column_config.TextColumn("Modèle", width="medium"),
                    "Score Global": st.column_config.ProgressColumn(
                        "Qualité", format="%s%%", min_value=0, max_value=100
                    ),
                    "CO2_mg": st.column_config.NumberColumn("CO₂ (mg)", format="%.2f"),
                    "Latence_s": st.column_config.NumberColumn("Latence", format="%.2f s"),
                    "RAM_GB": st.column_config.NumberColumn("RAM", format="%.1f GB"),
                    # On cache les colonnes brutes intermédiaires si besoin
                    "Score": None,
                },
                hide_index=True,
                use_container_width=True,
            )

            # D. RÉPONSES TEXTUELLES
            st.markdown("### 🔍 Analyse des Réponses")
            with st.expander("📄 Voir le Contexte Documentaire utilisé", expanded=False):
                for k, ctx in enumerate(contexts):
                    st.text(f"--- Chunk {k+1} ---\n{ctx[:300]}...")

            for name, data in detailed_responses.items():
                with st.expander(f"Réponse de {name}"):
                    if data["thought"]:
                        st.info(f"💭 **Pensée:**\n{data['thought']}")
                    st.markdown(data["text"])

        else:
            st.warning("Aucun résultat n'a été généré.")
