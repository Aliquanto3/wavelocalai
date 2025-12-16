"""
Inference Arena Tab - Sprint 3 (Gamification & Podium)
Mise à jour UX : Graphique Bubble Chart (Taille = CO2) + Labels enrichis.
"""

import asyncio
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.core.green_monitor import CarbonCalculator
from src.core.inference_service import InferenceService
from src.core.models_db import get_model_info


# --- HELPER PARSING ---
def _extract_params_billions(val: str | int | float) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if not val or not isinstance(val, str):
        return 0.0
    s = val.upper().strip().replace(" ", "")
    try:
        if "X" in s and "B" in s:
            parts = s.replace("B", "").split("X")
            return float(parts[0]) * float(parts[1])
        if s.endswith("B"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1000.0
        if s.isdigit():
            return float(s)
    except Exception:
        pass
    return 0.0


def _render_podium(results_data):
    """Affiche le vainqueur et les graphiques comparatifs (Bubble Chart)."""
    if not results_data:
        return

    # Tri : Score (desc) > Vitesse (desc)
    df = pd.DataFrame(results_data)
    df = df.sort_values(by=["Note", "Débit (t/s)"], ascending=[False, False]).reset_index(drop=True)
    winner = df.iloc[0]
    runner_up = df.iloc[1] if len(df) > 1 else None

    st.markdown("### 🏆 Le Verdict")

    col_winner, col_chart = st.columns([1, 2])

    # --- CARTE DU VAINQUEUR ---
    with col_winner, st.container(border=True):
        st.markdown(
            "<div style='text-align: center; font-size: 1.2rem;'>🥇 Vainqueur</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<h2 style='text-align: center; color: #F59E0B;'>{winner['Modèle']}</h2>",
            unsafe_allow_html=True,
        )

        st.divider()

        c1, c2 = st.columns(2)
        c1.metric("Score Juge", f"{winner['Note']}/100")
        c2.metric("Vitesse", f"{winner['Débit (t/s)']} t/s")

        # Comparaison (Reason to Win)
        if runner_up is not None:
            diff_score = winner["Note"] - runner_up["Note"]
            diff_speed = winner["Débit (t/s)"] - runner_up["Débit (t/s)"]

            reason = ""
            if diff_score > 5:
                reason = f"Plus intelligent (+{diff_score} pts)"
            elif diff_speed > 5:
                reason = f"Plus rapide (+{diff_speed:.1f} t/s)"
            elif winner["CO2 (mg)"] < runner_up["CO2 (mg)"]:
                reason = "Plus écologique"
            else:
                reason = "Meilleur équilibre"

            st.info(f"**Pourquoi ?** {reason}")

        # Badge GreenOps
        co2 = winner["CO2 (mg)"]
        color = "green" if co2 < 10 else ("orange" if co2 < 50 else "red")
        st.caption(f"🌍 Impact : :{color}[{co2:.2f} mgCO₂]")

    # --- GRAPHIQUE BUBBLE CHART (Plotly) ---
    with col_chart:
        fig = go.Figure()

        for i, row in df.iterrows():
            is_winner = i == 0

            # 1. COULEUR : Distinction Vainqueur (Or) vs Autres (Gris/Bleuté)
            color = "#F59E0B" if is_winner else "#60A5FA"
            symbol = "star" if is_winner else "circle"

            # 2. TAILLE (Bubble Logic) : Proportionnelle au CO2
            # On clope la taille min/max pour garder le graphique lisible
            # Exemple : Un modèle léger (10mg) = 15px, un lourd (100mg) = 45px
            co2_val = row["CO2 (mg)"]
            size = max(15, min(50, co2_val / 2))

            # Si c'est le vainqueur, on force une taille minimale pour qu'il se voie
            if is_winner:
                size = max(size, 25)

            # 3. LABEL DIRECT : Nom + CO2
            label = f"<b>{row['Modèle']}</b><br>🌱 {co2_val:.1f} mg"

            fig.add_trace(
                go.Scatter(
                    x=[row["Débit (t/s)"]],
                    y=[row["Note"]],
                    mode="markers+text",
                    text=[label],
                    textposition="top center",
                    marker={
                        "size": size,  # Ligne 126
                        "color": color,
                        "symbol": symbol,
                        "line": {"width": 1, "color": "white"},  # Ligne 129 corrigée
                        "opacity": 0.9,
                    },  # Ligne 131
                    name=row["Modèle"],
                    hoverinfo="text",
                    hovertext=f"<b>{row['Modèle']}</b><br>Score: {row['Note']}/100<br>Vitesse: {row['Débit (t/s)']} t/s<br>CO2: {co2_val} mg",
                )
            )

        fig.update_layout(
            title="Matrice Performance vs Impact (Taille du point = CO₂)",
            xaxis_title="Vitesse (Tokens/sec)",
            yaxis_title="Qualité (Note Juge /100)",
            yaxis={"range": [0, 110]},  # Marge en haut pour les labels
            xaxis={"showgrid": True},
            height=380,
            margin={"l": 20, "r": 20, "t": 40, "b": 20},
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)


def render_arena_tab(sorted_display_names: list, display_to_tag: dict, tag_to_friendly: dict):

    # --- 1. CONFIGURATION ---
    col_conf, col_prompt = st.columns([1, 2])

    with col_conf:
        st.subheader("1. Les Combattants")
        selected_arena_displays = st.multiselect(
            "Sélectionner Modèles",
            options=sorted_display_names,
            default=sorted_display_names[:2] if len(sorted_display_names) >= 2 else None,
            label_visibility="collapsed",
        )
        selected_arena_tags = [display_to_tag[d] for d in selected_arena_displays]
        selected_arena_friendlies = [tag_to_friendly[t] for t in selected_arena_tags]

        with st.expander("⚖️ Options du Juge (Arbitre)", expanded=False):
            judge_options = sorted_display_names
            def_idx = 0
            for i, n in enumerate(judge_options):
                if "mistral" in n.lower() or "llama" in n.lower():
                    def_idx = i
                    break

            judge_display = st.selectbox("Modèle Arbitre", judge_options, index=def_idx)
            judge_tag = display_to_tag.get(judge_display)

            default_judge_prompt = """Agis comme un juge impartial.
Question: "{prompt}".
Réponse Modèle: "{response}".

Note la qualité de la réponse sur 100.
Critères : Précision, Concision, Respect des consignes.
Format : Uniquement le chiffre (ex: 85)."""
            judge_sys = st.text_area("Critères de notation", value=default_judge_prompt, height=150)

    with col_prompt:
        st.subheader("2. Le Défi")
        arena_prompt = st.text_area(
            "Votre challenge",
            value="Explique le concept de 'Dette Technique' à un enfant de 10 ans avec une métaphore filée.",
            height=100,
            label_visibility="collapsed",
        )

        btn_col1, btn_col2 = st.columns([1, 3])
        with btn_col1:
            start_btn = st.button(
                "⚔️ FIGHT !",
                type="primary",
                use_container_width=True,
                disabled=not selected_arena_tags,
            )
        with btn_col2:
            if not selected_arena_tags:
                st.caption("👈 Sélectionnez au moins 2 modèles.")

    # --- 3. EXÉCUTION ---
    if start_btn and selected_arena_tags and arena_prompt:
        st.divider()

        results_data = []
        model_responses = {}

        status_box = st.status("🏟️ Ouverture de l'arène...", expanded=True)
        prog_bar = status_box.progress(0.0)

        total_steps = len(selected_arena_tags)

        for i, tag in enumerate(selected_arena_tags):
            friendly_name = selected_arena_friendlies[i]
            status_box.write(f"🥊 **{friendly_name}** entre sur le ring...")

            try:
                # 1. INFERENCE
                result = asyncio.run(
                    InferenceService.run_inference(
                        model_tag=tag,
                        messages=[{"role": "user", "content": arena_prompt}],
                        temperature=0.1,
                    )
                )
                m = result.metrics

                # 2. CALCUL GREENOPS
                info = get_model_info(friendly_name) or {}
                raw_params = info.get("params_act") or info.get("params_tot", "0")
                p = _extract_params_billions(raw_params)

                impact_mg = 0.0
                if info.get("type") == "api" and m.output_tokens > 0:
                    impact_mg = CarbonCalculator.compute_mistral_impact_g(p, m.output_tokens) * 1000
                else:
                    impact_mg = CarbonCalculator.compute_local_theoretical_g(m.output_tokens) * 1000

                # 3. NOTATION JUGE
                score = 0
                if judge_tag:
                    status_box.write(f"   ⚖️ Le juge délibère pour {friendly_name}...")
                    eval_p = judge_sys.replace("{prompt}", arena_prompt).replace(
                        "{response}", result.clean_text
                    )
                    eval_res = asyncio.run(
                        InferenceService.run_inference(
                            model_tag=judge_tag,
                            messages=[{"role": "user", "content": eval_p}],
                            temperature=0.0,
                        )
                    )
                    match = re.search(r"\d+", eval_res.clean_text)
                    if match:
                        score = max(0, min(100, int(match.group())))

                results_data.append(
                    {
                        "Modèle": friendly_name,
                        "Note": score,
                        "Débit (t/s)": round(m.tokens_per_second, 1),
                        "CO2 (mg)": round(impact_mg, 2),
                    }
                )

                model_responses[friendly_name] = {
                    "text": result.clean_text,
                    "thought": result.thought,
                    "score": score,
                }

            except Exception as e:
                status_box.error(f"❌ KO {friendly_name}: {e}")

            prog_bar.progress((i + 1) / total_steps)

        status_box.update(label="✅ Combat terminé !", state="complete", expanded=False)

        # --- 4. RÉSULTATS ---
        if results_data:
            _render_podium(results_data)

            st.divider()
            st.subheader("📝 Détails des Copies")

            if len(model_responses) == 2:
                c1, c2 = st.columns(2)
                sorted_items = sorted(
                    model_responses.items(), key=lambda x: x[1]["score"], reverse=True
                )
                for idx, (name, data) in enumerate(sorted_items):
                    with c1 if idx == 0 else c2, st.container(border=True):
                        st.markdown(f"**{name}** (Note: {data['score']})")
                        st.caption(data["text"])
            else:
                for name, data in sorted(
                    model_responses.items(), key=lambda x: x[1]["score"], reverse=True
                ):
                    with st.expander(f"{name} - {data['score']}/100"):
                        st.markdown(data["text"])
