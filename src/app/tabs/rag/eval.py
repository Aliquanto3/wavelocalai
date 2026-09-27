"""
Onglet « Évaluation de la qualité » de l'Assistant documentaire.

- Graphiques Altair, podium des 3 meilleurs modèles.
- Matrice qualité (Y) selon le CO₂ (X).
- Données brutes pour les calculs, valeurs formatées fr-FR pour l'affichage.
"""

import asyncio
import time

import altair as alt
import pandas as pd
import streamlit as st

from src.app.formatting import (
    MISSING,
    NBSP,
    NNBSP,
    co2_in_unit,
    common_co2_unit,
    format_co2,
    format_number,
    mg_to_grams,
    pluralize,
)
from src.app.states import NOT_EVALUATED, render_error, render_no_models
from src.app.ui import (
    ModelMenu,
    is_cloud_model,
    judge_help,
    judge_self_caption,
    judge_warnings,
    origin_label,
    render_badge,
    weak_judge_text,
)

# --- SSOT carbone ---
from src.core.green_monitor import CarbonCalculator
from src.core.llm_provider import LLMProvider
from src.core.metrics import InferenceMetrics
from src.core.models_db import extract_thought, get_friendly_name_from_tag, get_model_info
from src.core.utils import extract_params_billions as _extract_params_billions

# Locale Vega (fr-FR) passée dans la spécification : aucune locale chargée depuis un CDN.
VEGA_LOCALE = {
    "number": {
        "decimal": ",",
        "thousands": NNBSP,
        "grouping": [3],
        "currency": ["", f"{NBSP}€"],
    }
}


def _format_ratio(value) -> str:
    """Score Ragas (0-1) sur /100 : 0.85 → « 85/100 »."""
    text = format_number(None if value is None else value * 100, 0)
    return text if text == MISSING else f"{text}/100"


def _is_scored(value) -> bool:
    """Score présent et fini (None ou NaN = « non évalué »)."""
    return value is not None and value == value


def _to_100(series: pd.Series) -> pd.Series:
    """Scores 0-1 → /100 arrondis ; « non évalué » reste vide (jamais 0)."""
    return pd.to_numeric(series, errors="coerce").mul(100).round()


def render_rag_eval_tab(
    rag_engine,
    eval_engine,
    display_to_tag,
    tag_to_friendly,
    sorted_display_names,
    menu: ModelMenu | None = None,
):
    judge_default = menu.judge_default if menu else None

    # EN-TÊTE
    c_title, c_badge = st.columns([3, 1])
    with c_title:
        st.header("Évaluation de la qualité")
        st.caption(
            "Qualité des réponses et impact environnemental, modèle par modèle.",
            help="Évaluation par un modèle juge (LLM-as-a-judge), métriques Ragas.",
        )
    with c_badge:
        # Petit badge informatif
        st.info("**Sobriété** : trouver le modèle le plus léger qui garde une qualité acceptable.")

    if not eval_engine:
        st.error(
            "Le moteur d'évaluation n'est pas installé : installez les dépendances de "
            "requirements.txt, puis rechargez la page."
        )
        return

    if not sorted_display_names:
        render_no_models()
        return

    st.divider()

    # 1. CONFIGURATION DU BENCHMARK
    col_conf, col_run = st.columns([1, 2])

    with col_conf:
        st.subheader("Modèles évalués")
        # Par défaut : le modèle proposé en premier, sauf le juge (il ne note pas sa propre
        # réponse) quand un autre modèle est disponible.
        default_candidates = [d for d in sorted_display_names if d != judge_default][:1] or [
            sorted_display_names[0]
        ]
        candidate_displays = st.multiselect(
            "Modèles évalués",
            sorted_display_names,
            default=default_candidates,
            label_visibility="collapsed",
        )
        candidate_tags = [display_to_tag[d] for d in candidate_displays]

        st.subheader("Juge")
        # Par défaut : le plus gros modèle local qui tient en mémoire (model_defaults).
        default_judge_idx = (
            sorted_display_names.index(judge_default)
            if judge_default in sorted_display_names
            else 0
        )
        judge_display = st.selectbox(
            "Modèle juge",
            sorted_display_names,
            index=default_judge_idx,
            help=judge_help(menu),
        )
        judge_tag = display_to_tag.get(judge_display)
        # Le juge lit la question, les extraits et les réponses : son badge dit où ils partent.
        render_badge(is_cloud_model(judge_tag, menu))
        for warning in judge_warnings(menu, judge_display):
            st.warning(warning)
        self_caption = judge_self_caption(tag_to_friendly, judge_tag, candidate_tags)
        if self_caption:
            st.caption(self_caption)
        weak_text = weak_judge_text(menu, judge_display)

    with col_run:
        st.subheader("Question de référence")
        query = st.text_area(
            "Question qui demande le contenu de vos documents",
            "Quels sont les risques principaux mentionnés dans le document ?",
            height=100,
        )

        run_btn = st.button("Lancer l'évaluation", type="primary", width="stretch")

    # 2. LOGIQUE D'EXÉCUTION
    if run_btn:
        if not candidate_tags or not judge_tag:
            st.error("Choisissez au moins un modèle à évaluer et un juge.")
            st.stop()

        # A. Retrieval Commun (Pour équité)
        with st.spinner("Recherche des extraits communs à tous les modèles…"):
            try:
                retrieved_docs = rag_engine.search(query, k=3)
                contexts = [doc.page_content for doc in retrieved_docs]
                if not contexts:
                    st.warning("Aucun extrait trouvé : l'évaluation risque d'être faussée.")
            except Exception as e:
                st.error(f"La recherche dans vos documents a échoué : {e}")
                st.stop()

        # B. Boucle d'évaluation
        results_raw = []  # Pour les graphiques (floats)
        detailed_responses = {}
        failures = []  # (modèle, détail technique)

        prog_container = st.status("Évaluation en cours…", expanded=True)
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
            c_is_cloud = is_cloud_model(c_tag, menu)
            prog_container.write(f"Réponse de **{c_friendly}**…")

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
                # Nom du catalogue (pas le nom affiché, qui peut porter le tag).
                info = get_model_info(get_friendly_name_from_tag(c_tag)) or {}
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
                prog_container.write("Notation par le juge…")
                eval_result = eval_engine.evaluate_single_turn(
                    query=query,
                    response=clean_answer,
                    retrieved_contexts=contexts,
                    judge_tag=judge_tag,
                    embedding_model=rag_engine.embedding_model,
                )

                # Stockage Brut ; score None = « non évalué » (jamais converti en 0)
                results_raw.append(
                    {
                        "Modèle": c_friendly,
                        "is_cloud": c_is_cloud,  # Fournisseur réel (badge, tableau)
                        "Score": eval_result.global_score,  # Float 0-1 ou None
                        "CO2_mg": carbon_mg,  # Float
                        "Latence_s": d_gen,  # Float
                        "Fidélité": eval_result.faithfulness,
                        "Pertinence": eval_result.answer_relevancy,
                        "RAM_GB": ram_gb,
                        "Raison": eval_result.reason,
                        "Détail": eval_result.detail,
                    }
                )

                detailed_responses[c_friendly] = {
                    "text": clean_answer,
                    "thought": thought,
                    "is_cloud": c_is_cloud,
                }

            except Exception as e:
                prog_container.write(
                    f"**{c_friendly}** : la réponse n'a pas pu être générée. Les autres continuent."
                )
                failures.append((c_friendly, f"{type(e).__name__}: {e}"))

            prog_bar.progress((i + 1) / total_steps)

        if results_raw:
            done_label = "Évaluation terminée"
            if failures:
                done_label += (
                    f" · {pluralize(len(failures), 'modèle en échec', 'modèles en échec')}"
                )
            prog_container.update(label=done_label, state="complete", expanded=False)
        else:
            prog_container.update(label="Évaluation échouée", state="error", expanded=False)

        if failures:
            names = ", ".join(name for name, _ in failures)
            render_error(
                f"Réponse impossible pour : {names}. Vérifiez qu'Ollama est démarré et que le "
                "modèle est installé.",
                "\n".join(f"{name} : {detail}" for name, detail in failures),
            )

        # 3. VISUALISATION & PODIUM
        if results_raw:
            df = pd.DataFrame(results_raw)

            st.divider()

            # A. PODIUM (Top 3 Scores) : modèles notés seulement ; « non évalué » ensuite.
            scored_mask = df["Score"].map(_is_scored).astype(bool)
            df_scored = df[scored_mask].sort_values("Score", ascending=False)
            df_unscored = df[~scored_mask]

            # Une seule unité de CO₂ pour le podium, le graphique et le tableau (EXPERIENCE.md).
            co2_unit = common_co2_unit(mg_to_grams(v) for v in df["CO2_mg"])

            st.subheader("Podium de la qualité")
            # Les notes viennent du juge : ses limites accompagnent le podium.
            for caption in (weak_text, self_caption):
                if caption:
                    st.caption(caption)
            if df_scored.empty:
                st.info(
                    "Aucune réponse n'a pu être notée : pas de podium. La raison est indiquée "
                    "dans le tableau ci-dessous."
                )
            else:
                df_podium = df_scored.reset_index(drop=True)
                cols_podium = st.columns(3)
                for i in range(min(3, len(df_podium))):
                    row = df_podium.iloc[i]
                    with cols_podium[i], st.container(border=True):
                        st.markdown(f"**{i + 1}. {row['Modèle']}**")
                        render_badge(row["is_cloud"])
                        st.metric("Note globale", _format_ratio(row["Score"]))
                        st.caption(f"CO₂ : {format_co2(mg_to_grams(row['CO2_mg']), co2_unit)}")

            for _, row in df_unscored.iterrows():
                st.caption(
                    f"**{row['Modèle']}** : {NOT_EVALUATED}",
                    help=row["Raison"] or "Le juge n'a pas pu noter cette réponse.",
                )

            st.divider()

            # B. MATRICE DE DÉCISION (Altair Chart)
            # Axe X : Impact CO2 (On veut le plus bas possible -> à gauche)
            # Axe Y : Qualité (On veut le plus haut possible -> en haut)
            # Le "Sweet Spot" est en haut à gauche.
            # Seuls les modèles notés sont tracés : « non évalué » n'a pas de place sur l'axe.
            if not df_scored.empty:
                st.subheader("Qualité selon le CO₂")
                st.caption(
                    "Le modèle idéal se situe en **haut à gauche** : qualité haute, CO₂ faible."
                )

                # Note sur /100 pour l'axe et l'infobulle (une seule échelle, EXPERIENCE.md).
                df_chart = df_scored.assign(
                    Note=df_scored["Score"].astype(float) * 100,
                    CO2=[co2_in_unit(mg_to_grams(v), co2_unit) for v in df_scored["CO2_mg"]],
                )

                chart = (
                    alt.Chart(df_chart[["Modèle", "Note", "CO2", "Latence_s"]])
                    .mark_circle(size=150)
                    .encode(
                        x=alt.X("CO2", title=f"CO₂ ({co2_unit}), plus bas est mieux"),
                        y=alt.Y(
                            "Note",
                            title="Note globale (/100), plus haut est mieux",
                            scale=alt.Scale(domain=[0, 100]),
                        ),
                        color="Modèle",
                        tooltip=[
                            "Modèle",
                            alt.Tooltip("Note", title="Note (/100)", format=".0f"),
                            # Trois chiffres significatifs, sans zéros finaux.
                            alt.Tooltip("CO2", title=f"CO₂ ({co2_unit})", format=".3~r"),
                            alt.Tooltip("Latence_s", title="Durée (s)", format=".2f"),
                        ],
                    )
                    .interactive()
                    # Virgule décimale et espace fine des milliers (locale Vega, sans CDN).
                    .configure(locale=VEGA_LOCALE)
                )

                st.altair_chart(chart, width="stretch")

            # C. TABLEAU DÉTAILLÉ
            st.subheader("Données détaillées")

            # Valeurs numériques (tri numérique), scores sur /100 ; affichage au format de la
            # locale du navigateur (virgule décimale sur un poste en français).
            # Notés d'abord ; une note vide = « non évalué », raison dans la colonne Statut.
            df_table = pd.concat([df_scored, df_unscored])
            df_display = pd.DataFrame(
                {
                    "Modèle": df_table["Modèle"],
                    "Exécution": [origin_label(v) for v in df_table["is_cloud"]],
                    "Note": _to_100(df_table["Score"]),
                    "Fidélité": _to_100(df_table["Fidélité"]),
                    "Pertinence": _to_100(df_table["Pertinence"]),
                    "CO₂": [co2_in_unit(mg_to_grams(v), co2_unit) for v in df_table["CO2_mg"]],
                    "Durée": df_table["Latence_s"],
                    "Mémoire": df_table["RAM_GB"],
                    "Statut": [
                        (
                            "Évalué"
                            if _is_scored(score)
                            else f"{NOT_EVALUATED.capitalize()} : {reason or 'raison inconnue'}"
                        )
                        for score, reason in zip(df_table["Score"], df_table["Raison"], strict=True)
                    ],
                }
            )

            st.dataframe(
                df_display,
                column_config={
                    "Modèle": st.column_config.TextColumn("Modèle", width="medium"),
                    "Exécution": st.column_config.TextColumn(
                        "Exécution",
                        help="Local : le modèle tourne sur cette machine. Cloud : les données "
                        "envoyées au modèle quittent la machine.",
                    ),
                    "Note": st.column_config.ProgressColumn(
                        "Note (/100)", format="%.0f", min_value=0, max_value=100
                    ),
                    "Fidélité": st.column_config.NumberColumn(
                        "Fidélité (/100)",
                        format="localized",
                        help="Faithfulness (Ragas) : la réponse s'appuie sur les extraits.",
                    ),
                    "Pertinence": st.column_config.NumberColumn(
                        "Pertinence (/100)",
                        format="localized",
                        help="Answer relevancy (Ragas) : la réponse traite la question posée.",
                    ),
                    "CO₂": st.column_config.NumberColumn(f"CO₂ ({co2_unit})", format="localized"),
                    "Durée": st.column_config.NumberColumn("Durée (s)", format="localized"),
                    "Mémoire": st.column_config.NumberColumn("Mémoire (Go)", format="localized"),
                    "Statut": st.column_config.TextColumn(
                        "Statut",
                        width="large",
                        help="« Non évalué » : Ragas ou le juge n'a pas pu noter la réponse.",
                    ),
                },
                hide_index=True,
                width="stretch",
            )

            # Texte des exceptions de l'évaluation : replié, hors du tableau.
            eval_details = [
                f"{name} : {detail}"
                for name, detail in zip(df_table["Modèle"], df_table["Détail"], strict=True)
                if isinstance(detail, str) and detail
            ]
            if eval_details:
                with st.expander("Détails techniques", expanded=False):
                    st.code("\n".join(eval_details), language=None)

            # D. RÉPONSES TEXTUELLES
            st.subheader("Réponses des modèles")
            with st.expander("Extraits fournis aux modèles", expanded=False):
                for k, ctx in enumerate(contexts):
                    st.text(f"--- Extrait {k + 1} ---\n{ctx[:300]}…")

            for name, data in detailed_responses.items():
                with st.expander(f"Réponse de {name}"):
                    render_badge(data["is_cloud"])
                    if data["thought"]:
                        st.info(f"**Raisonnement :**\n{data['thought']}")
                    st.markdown(data["text"])

        elif not failures:
            st.warning("Aucun résultat : aucun modèle n'a pu être évalué.")
