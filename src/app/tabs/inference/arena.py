import asyncio
import re

import pandas as pd
import streamlit as st

from src.core.inference_service import InferenceService
from src.core.models_db import get_model_info
from src.core.resource_manager import ResourceManager


def render_arena_tab(sorted_display_names: list, display_to_tag: dict, tag_to_friendly: dict):
    st.subheader("⚔️ Benchmark Comparatif")
    st.caption("Comparaison séquentielle et notation par un Juge IA.")

    col_arena_models, col_arena_judge, col_arena_prompt = st.columns([1, 1, 2])

    with col_arena_models:
        st.markdown("##### 1. Les Combattants")
        selected_arena_displays = st.multiselect(
            "Modèles à évaluer", options=sorted_display_names, help="Choisissez au moins 2 modèles."
        )
        selected_arena_tags = [display_to_tag[d] for d in selected_arena_displays]
        selected_arena_friendlies = [tag_to_friendly[t] for t in selected_arena_tags]

    with col_arena_judge:
        st.markdown("##### 2. Le Juge")
        judge_options = sorted_display_names
        default_judge_idx = 0
        for i, name in enumerate(judge_options):
            if "mistral" in name.lower() and "large" in name.lower():
                default_judge_idx = i
                break

        judge_display = st.selectbox("Modèle Evaluateur", judge_options, index=default_judge_idx)
        judge_tag = display_to_tag.get(judge_display)

        # NOUVEAU : Prompt éditable
        default_judge_prompt = """Agis comme un juge impartial.
Question: "{prompt}".
Réponse Modèle: "{response}".

Tu as une tâche : Noter la qualité de la réponse sur 100.
Sois sévère mais juste.
Format de réponse attendu : Uniquement le chiffre (ex: 85)."""

        with st.expander("⚖️ Prompt du Juge", expanded=False):
            judge_system_template = st.text_area(
                "Template de notation", value=default_judge_prompt, height=150
            )

    with col_arena_prompt:
        st.markdown("##### 3. L'Épreuve")
        arena_prompt = st.text_area(
            "Prompt du Benchmark", "Explique le concept de Green IT en 3 points clés.", height=100
        )
        run_benchmark_btn = st.button(
            "🚀 Lancer le Benchmark", type="primary", disabled=not selected_arena_tags
        )

    if run_benchmark_btn and selected_arena_tags and arena_prompt:
        st.divider()

        results_data = []
        model_responses = {}
        progress_placeholder = st.empty()
        prog_bar = st.progress(0.0)
        total_steps = len(selected_arena_tags)

        for i, tag in enumerate(selected_arena_tags):
            friendly_name = selected_arena_friendlies[i]
            progress_placeholder.info(
                f"⏳ [{i+1}/{total_steps}] **{friendly_name}** entre dans l'arène..."
            )

            try:
                # Check RAM (Si local)
                if "mistral" not in tag:
                    ResourceManager.check_resources(tag)

                result = asyncio.run(
                    InferenceService.run_inference(
                        model_tag=tag,
                        messages=[{"role": "user", "content": arena_prompt}],
                        temperature=0.1,
                    )
                )
                m = result.metrics

                info = get_model_info(friendly_name)
                size_gb_str = info["size_gb"] if info else "N/A"

                # Notation Juge
                progress_placeholder.info(f"⚖️ Le Juge délibère sur {friendly_name}...")
                score = 0
                if judge_tag:
                    # NOUVEAU : Injection des variables dans le template
                    formatted_prompt = judge_system_template.replace(
                        "{prompt}", arena_prompt
                    ).replace("{response}", result.clean_text)

                    judge_resp = asyncio.run(
                        InferenceService.run_inference(
                            model_tag=judge_tag,
                            messages=[{"role": "user", "content": formatted_prompt}],
                            temperature=0.0,
                        )
                    )
                    match = re.search(r"\d+", judge_resp.clean_text)
                    if match:
                        score = max(0, min(100, int(match.group())))

                results_data.append(
                    {
                        "Modèle": friendly_name,
                        "Note": score,
                        "Débit (t/s)": round(m.tokens_per_second, 1),
                        "Latence (s)": round(m.total_duration_s, 2),
                        "RAM Modèle": size_gb_str,
                    }
                )

                model_responses[friendly_name] = {
                    "text": result.clean_text,
                    "thought": result.thought,
                    "score": score,
                }

            except Exception as e:
                st.error(f"Crash de {friendly_name}: {e}")

            prog_bar.progress((i + 1) / total_steps)

        prog_bar.empty()
        progress_placeholder.success("✅ Tournoi terminé !")

        st.divider()
        if results_data:
            st.dataframe(
                pd.DataFrame(results_data),
                column_config={
                    "Note": st.column_config.ProgressColumn("Score", min_value=0, max_value=100)
                },
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("📝 Réponses Détaillées")
        for name, data in sorted(
            model_responses.items(), key=lambda x: x[1]["score"], reverse=True
        ):
            with st.expander(f"⭐ {data['score']}/100 - {name}", expanded=False):
                if data["thought"]:
                    st.info(f"**CoT:** {data['thought']}")
                st.markdown(data["text"])
