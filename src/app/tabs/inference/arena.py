"""
Onglet « Arène » de l'Arène des modèles : plusieurs modèles sur la même question, notés par
un modèle juge. Matrice note / débit (taille = CO₂, couleur par modèle), légendes, libellés
directs et tableau.
"""

import asyncio
import math
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.app.charts import (
    THEME_GRAY_TOKEN,
    THEME_SURFACE_TOKEN,
    THEME_TEXT_TOKEN,
    bubble_sizes,
    palette_size,
    remember_entity_slots,
    size_legend_text,
    slot_color,
    slot_symbol,
    stacked_labels,
    zero_based_range,
)
from src.app.formatting import (
    NBSP,
    PLOTLY_SEPARATORS,
    co2_in_unit,
    common_co2_unit,
    format_co2,
    format_duration,
    format_throughput,
    format_unit,
    mg_to_grams,
    pluralize,
)
from src.app.states import (
    LOADING_HINT,
    LOADING_LABEL,
    NOT_EVALUATED,
    THROUGHPUT_HELP,
    inference_failure_label,
    render_error,
    render_no_models,
)
from src.app.ui import (
    ModelMenu,
    badge_markdown,
    is_cloud_model,
    judge_help,
    judge_self_caption,
    judge_warnings,
    origin_label,
    render_badge,
    weak_judge_text,
)
from src.core.green_monitor import CarbonCalculator
from src.core.inference_service import InferenceService
from src.core.llm_provider import LLMProvider
from src.core.model_defaults import ARENA_MIN_MODELS
from src.core.models_db import get_friendly_name_from_tag, get_model_info
from src.core.utils import extract_params_billions as _extract_params_billions

# Diamètre minimal de l'étoile du vainqueur (px) : visible même s'il a le moins de CO₂.
WINNER_MIN_PX = 25.0

# Lancement désactivé sous ARENA_MIN_MODELS modèles : légende qui nomme le prérequis.
MIN_MODELS_CAPTION = f"Choisissez au moins {ARENA_MIN_MODELS} modèles."

# Statut d'une ligne de résultats.
STATUS_SCORED = "scored"
STATUS_NOT_EVALUATED = "not_evaluated"
STATUS_FAILED = "failed"

# Nombre signé, entier ou décimal (« -5 », « 8,5 ») : un candidat invalide annule la note.
_NUM = r"-?\d+(?:[.,]\d+)?"
# Note explicitement rapportée à 100 : « 85/100 », « 85 / 100 », « 85 sur 100 ».
_OVER_100 = re.compile(rf"(?<![\d.,])({_NUM})\s*(?:/|sur)\s*100(?![\d.,]*\d)")
# « sur 100 » ou « /100 » sans note devant (« Note sur 100 : 72 ») : échelle, pas une note.
_SCALE = re.compile(r"(?:/|\bsur)\s*100(?![\d.,]*\d)")
# Note étiquetée : « note : 85 », « Note finale = 85 », « score 85 ».
_LABELLED = re.compile(
    rf"\b(?:note|score)(?:\s+(?:globale|finale|attribuée))?\s*[:=]?\s*({_NUM})", re.I
)
# Réponse réduite au nombre (« 85 », « **85** », « 85. »).
_WHOLE = re.compile(rf"[\s*_`\"'«»]*({_NUM})[\s*_`\"'«».!]*")


def _as_score(raw: str) -> int | None:
    """Entier de 0 à 100, sinon None (négatif, décimal, hors échelle)."""
    return int(raw) if raw.isdigit() and 0 <= int(raw) <= 100 else None


def parse_judge_score(text: str | None) -> int | None:
    """
    Note du juge, seulement si elle est explicite : « N/100 » (ou « N sur 100 »), « note : N »,
    ou une réponse réduite au nombre. Un seul entier de 0 à 100 doit en ressortir ; sinon None
    (« non évalué ») : jamais un nombre isolé du texte (« enfant de 10 ans »), jamais un
    négatif, jamais 0 par défaut.
    """
    if not text:
        return None
    candidates = _OVER_100.findall(text)
    rest = _SCALE.sub(" ", _OVER_100.sub(" ", text))
    candidates += _LABELLED.findall(rest)
    whole = _WHOLE.fullmatch(text)
    if whole:
        candidates.append(whole.group(1))
    if not candidates:
        return None
    scores = {_as_score(raw) for raw in candidates}
    if None in scores or len(scores) != 1:
        return None
    (score,) = scores
    return score


def _num(value) -> float | None:
    """Valeur numérique finie, ou None (absente ou NaN d'un tableau pandas)."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def rank_results(results_data: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Classement : notes numériques d'abord (décroissantes, puis débit), puis les « non évalué »
    (par débit), enfin les échecs, qui n'ont pas de place au classement.

    Returns:
        (notés, non évalués, échecs)
    """

    def speed(row):
        return _num(row.get("Débit (t/s)")) or 0.0

    scored = [r for r in results_data if r["status"] == STATUS_SCORED]
    not_evaluated = [r for r in results_data if r["status"] == STATUS_NOT_EVALUATED]
    failed = [r for r in results_data if r["status"] == STATUS_FAILED]
    scored.sort(key=lambda r: (-r["Note"], -speed(r)))
    not_evaluated.sort(key=lambda r: -speed(r))
    return scored, not_evaluated, failed


def _note_label(row: dict) -> str:
    if row["status"] == STATUS_SCORED:
        return f"{row['Note']}/100"
    if row["status"] == STATUS_NOT_EVALUATED:
        return NOT_EVALUATED
    return "—"


def _status_label(row: dict) -> str:
    if row["status"] == STATUS_SCORED:
        return "Classé"
    if row["status"] == STATUS_NOT_EVALUATED:
        return f"{NOT_EVALUATED.capitalize()} : {row['reason']}"
    return row["reason"]


def co2_unit_of(rows: list[dict]) -> str:
    """Unité de CO₂ commune à toutes les lignes d'une comparaison (EXPERIENCE.md)."""
    return common_co2_unit(mg_to_grams(r.get("CO2 (mg)")) for r in rows)


def _co2_label(row: dict, unit: str) -> str:
    """CO₂ d'une ligne dans l'unité de la comparaison : « 7,6 mgCO₂ »."""
    return format_co2(mg_to_grams(row.get("CO2 (mg)")), unit)


def _timings_label(row: dict) -> str:
    """« Chargement 8 s · Durée totale 10 s » ; sans chargement pour un modèle cloud."""
    parts = []
    if _num(row.get("Chargement (s)")) is not None:
        parts.append(f"Chargement {format_duration(row['Chargement (s)'])}")
    if _num(row.get("Durée totale (s)")) is not None:
        parts.append(f"Durée totale {format_duration(row['Durée totale (s)'])}")
    return " · ".join(parts)


def _execution_label(row) -> str:
    """« Local », « Cloud » ou « Origine inconnue » : fournisseur réel du modèle de la ligne
    (colonne de tableau, où un badge ne peut pas s'afficher)."""
    return origin_label(row.get("is_cloud"))


def _render_results_table(ranked: list[dict], unit: str) -> None:
    """Tableau de tous les modèles, échecs compris : chaque ligne dit son statut et si le
    modèle est local ou cloud. CO₂ dans l'unité commune `unit` ; chargement et durée totale
    à part du débit."""
    df = pd.DataFrame(
        {
            "Modèle": [r["Modèle"] for r in ranked],
            "Exécution": [_execution_label(r) for r in ranked],
            "Note": [_note_label(r) for r in ranked],
            "Débit": [r.get("Débit (t/s)") for r in ranked],
            "Chargement": [r.get("Chargement (s)") for r in ranked],
            "Durée totale": [r.get("Durée totale (s)") for r in ranked],
            "CO₂": [co2_in_unit(mg_to_grams(r.get("CO2 (mg)")), unit) for r in ranked],
            "Statut": [_status_label(r) for r in ranked],
        }
    )
    st.dataframe(
        df,
        column_config={
            "Modèle": st.column_config.TextColumn("Modèle", width="medium"),
            "Exécution": st.column_config.TextColumn(
                "Exécution",
                help="Local : le modèle tourne sur cette machine. Cloud : les données envoyées "
                "au modèle quittent la machine.",
            ),
            "Note": st.column_config.TextColumn(
                "Note (/100)", help="« non évalué » : le juge n'a pas pu noter la réponse."
            ),
            "Débit": st.column_config.NumberColumn(
                "Débit (tokens/s)", format="localized", help=THROUGHPUT_HELP
            ),
            "Chargement": st.column_config.NumberColumn(
                "Chargement (s)",
                format="localized",
                help="Chargement du modèle en mémoire (vide pour un modèle cloud).",
            ),
            "Durée totale": st.column_config.NumberColumn("Durée totale (s)", format="localized"),
            "CO₂": st.column_config.NumberColumn(f"CO₂ ({unit})", format="localized"),
            "Statut": st.column_config.TextColumn("Statut", width="large"),
        },
        hide_index=True,
        width="stretch",
    )


def _hover_text(row, unit: str) -> str:
    timings = _timings_label(row)
    return (
        f"<b>{row['Modèle']}</b><br>Note : {row['Note']}/100"
        f"<br>Débit : {format_throughput(row['Débit (t/s)'], bool(row.get('Débit estimé')))}"
        f"<br>CO₂ : {_co2_label(row, unit)}" + (f"<br>{timings}" if timings else "")
    )


# Écart horizontal entre le bord d'un point et son étiquette (px).
_LABEL_OFFSET_PX = 28


def _quality_matrix(df: pd.DataFrame, slots: dict[str, int], unit: str) -> go.Figure:
    """
    Matrice qualité (note /100) selon le débit, une trace par modèle noté (`df`, classé).

    - Axes depuis 0 : jamais resserrés sur les seules valeurs (5,8 à 6 tokens/s).
    - Couleur et forme liées au modèle (`slots`, par tag), étoile pour le vainqueur.
    - Taille du point = CO₂ (surface proportionnelle), légende de taille sous le graphique ;
      l'étoile du vainqueur garde au moins WINNER_MIN_PX.
    - Nom complet et CO₂ en étiquette directe, reliée à son point, du côté intérieur du cadre
      et empilée sans chevauchement quand les points sont proches ; légende des modèles dès
      2 séries.
    """
    n_colors = palette_size()
    x_range = zero_based_range(df["Débit (t/s)"])
    sizes = bubble_sizes(df["CO2 (mg)"])
    sizes[0] = max(sizes[0], WINNER_MIN_PX)
    points = [(_num(row["Débit (t/s)"]), _num(row["Note"])) for _, row in df.iterrows()]
    labels = stacked_labels(points, x_range[1])
    fig = go.Figure()
    for i, row in df.iterrows():
        slot = slots.get(row.get("tag"), i)
        x, y = points[i]
        fig.add_trace(
            go.Scatter(
                x=[x],
                y=[y],
                mode="markers",
                name=row["Modèle"],
                marker={
                    "size": sizes[i],
                    "symbol": "star" if i == 0 else slot_symbol(slot, n_colors),
                    "color": slot_color(slot, n_colors),
                    "opacity": 0.9,
                    # Anneau de 2 px couleur du fond : points superposés distincts.
                    "line": {"width": 2, "color": THEME_SURFACE_TOKEN},
                },
                cliponaxis=False,
                hoverinfo="text",
                hovertext=[_hover_text(row, unit)],
            )
        )
        label = labels[i]
        if label is None:
            continue
        # Étiquette en couleur de texte du thème (jamais la couleur de la série), reliée au
        # point par un trait gris qui part du bord du point.
        offset = sizes[i] / 2 + _LABEL_OFFSET_PX
        fig.add_annotation(
            x=x,
            y=y,
            text=f"<b>{row['Modèle']}</b><br>{_co2_label(row, unit)}",
            ax=-offset if label.side == "left" else offset,
            axref="pixel",
            ay=label.y,
            ayref="y",
            xanchor="right" if label.side == "left" else "left",
            yanchor="middle",
            align="right" if label.side == "left" else "left",
            font={"color": THEME_TEXT_TOKEN},
            showarrow=True,
            arrowhead=0,
            arrowwidth=1,
            arrowcolor=THEME_GRAY_TOKEN,
            standoff=sizes[i] / 2,
        )

    fig.update_layout(
        title="Note du juge selon le débit (taille du point = CO₂)",
        height=460,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        showlegend=len(df) >= 2,
        # Légende horizontale sous le graphique : toute la largeur de la colonne au tracé.
        legend={
            "title": {"text": "Modèle"},
            "itemsizing": "constant",
            "orientation": "h",
            "xref": "container",
            "x": 0,
            "xanchor": "left",
            "yref": "container",
            "y": 0,
            "yanchor": "bottom",
        },
        separators=PLOTLY_SEPARATORS,
    )
    fig.update_xaxes(title="Débit (tokens/s)", range=x_range, showgrid=True, zeroline=True)
    # Échelle /100 seulement, sans graduation au-delà ; marge pour les points à 0 et 100.
    fig.update_yaxes(
        title="Note du juge (/100)", range=[-6, 106], tickvals=[0, 20, 40, 60, 80, 100]
    )
    return fig


def _render_podium(results_data):
    """Affiche le vainqueur, la matrice note / débit et le tableau.

    Seuls les modèles notés montent sur le podium ; « non évalué » et échecs apparaissent
    dans le tableau, jamais avec 0/100.
    """
    scored, not_evaluated, failed = rank_results(results_data)
    if not scored and not not_evaluated:
        return
    # Une seule unité de CO₂ pour toute la comparaison (tableau, vainqueur, graphique).
    unit = co2_unit_of(results_data)

    st.header("Verdict")

    if not scored:
        st.info(
            "Le juge n'a pu noter aucune réponse : pas de vainqueur. Comparez le débit et le "
            "CO₂ dans le tableau."
        )
        _render_results_table(not_evaluated + failed, unit)
        return

    df = pd.DataFrame(scored).reset_index(drop=True)
    winner = df.iloc[0]
    runner_up = df.iloc[1] if len(df) > 1 else None

    col_winner, col_chart = st.columns([1, 2])

    # --- CARTE DU VAINQUEUR ---
    with col_winner, st.container(border=True):
        st.markdown("Vainqueur", text_alignment="center")
        st.subheader(winner["Modèle"], anchor=False, text_alignment="center")
        render_badge(winner.get("is_cloud"))

        st.divider()

        c1, c2 = st.columns(2)
        c1.metric("Note du juge", f"{winner['Note']}/100")
        c2.metric(
            "Débit",
            format_throughput(winner["Débit (t/s)"], bool(winner.get("Débit estimé"))),
            help=THROUGHPUT_HELP,
        )

        # Comparaison (Reason to Win)
        if runner_up is not None:
            diff_score = winner["Note"] - runner_up["Note"]
            diff_speed = (_num(winner["Débit (t/s)"]) or 0.0) - (
                _num(runner_up["Débit (t/s)"]) or 0.0
            )

            reason = ""
            if diff_score > 5:
                reason = f"Meilleure note (+{diff_score} points)"
            elif diff_speed > 5:
                reason = f"Plus rapide (+{format_unit(diff_speed, 'tokens/s')})"
            elif (
                _num(winner["CO2 (mg)"]) is not None
                and _num(runner_up["CO2 (mg)"]) is not None
                and winner["CO2 (mg)"] < runner_up["CO2 (mg)"]
            ):
                reason = "Moins de CO₂"
            else:
                reason = "Meilleur équilibre"

            st.info(f"**Pourquoi ?** {reason}")

        # CO₂ (texte, sans code couleur par seuil), chargement et durée totale à part.
        st.caption(f"CO₂ : {_co2_label(winner, unit)}")
        timings = _timings_label(winner)
        if timings:
            st.caption(timings)

    # --- MATRICE QUALITÉ / DÉBIT (Plotly) ---
    # Couleur par modèle (tag), dans l'ordre stable de la sélection (results_data, échecs
    # compris), registre commun à l'évaluation de la qualité : ni le classement ni les modèles
    # écartés ne la changent.
    slots = remember_entity_slots(r["tag"] for r in results_data if r.get("tag"))
    with col_chart:
        st.plotly_chart(_quality_matrix(df, slots, unit), width="stretch")
        st.caption(
            f"{size_legend_text((mg_to_grams(v) for v in df['CO2 (mg)']), unit)} "
            f"Étoile : vainqueur, au moins {WINNER_MIN_PX:.0f}{NBSP}px quel que soit son CO₂. "
            "Valeurs exactes dans le tableau ci-dessous."
        )

    _render_results_table(scored + not_evaluated + failed, unit)


def _write_loading_note(status_box, tag: str, friendly_name: str) -> None:
    """Premier chargement : l'étape le dit avant la génération (rien si `ps()` échoue)."""
    if LLMProvider.is_model_loaded(tag) is False:
        status_box.write(f"**{friendly_name}** : {LOADING_LABEL} {LOADING_HINT}")


def _judge(status_box, judge_tag, judge_name, judge_sys, prompt, answer):
    """Note du juge : (note ou None, raison si « non évalué », détail technique ou None)."""
    if not judge_tag:
        return None, "aucun modèle juge choisi.", None
    _write_loading_note(status_box, judge_tag, judge_name)
    eval_p = judge_sys.replace("{prompt}", prompt).replace("{response}", answer)
    eval_res = asyncio.run(
        InferenceService.run_inference(
            model_tag=judge_tag,
            messages=[{"role": "user", "content": eval_p}],
            temperature=0.0,
        )
    )
    if eval_res.error:
        reason = f"le juge n'a pas répondu ({inference_failure_label(eval_res).lower()})."
        return None, reason, eval_res.error
    score = parse_judge_score(eval_res.clean_text)
    if score is None:
        return None, "la réponse du juge ne contient pas de note lisible de 0 à 100.", None
    return score, None, None


def render_arena_tab(
    sorted_display_names: list,
    display_to_tag: dict,
    tag_to_friendly: dict,
    menu: ModelMenu | None = None,
):
    """
    Onglet « Arène ». `menu` (src/app/ui.py) porte les choix par défaut adaptés à la
    machine : libellés présélectionnés (petits modèles locaux qui tiennent en mémoire, hors
    juge), juge par défaut (plus gros modèle local fiable qui tient) et ce que la règle sait
    de chaque modèle (avertissements du juge).
    """
    preselected = menu.arena_defaults if menu else []
    judge_default = menu.judge_default if menu else None

    if not sorted_display_names:
        render_no_models(in_arena=True)
        return

    # --- 1. CONFIGURATION ---
    col_conf, col_prompt = st.columns([1, 2])

    with col_conf:
        st.header("Modèles")
        selected_arena_displays = st.multiselect(
            "Modèles à comparer",
            options=sorted_display_names,
            default=[d for d in (preselected or []) if d in sorted_display_names],
            label_visibility="collapsed",
        )
        selected_arena_tags = [display_to_tag[d] for d in selected_arena_displays]
        selected_arena_friendlies = [tag_to_friendly[t] for t in selected_arena_tags]

        with st.expander("Réglages du juge", expanded=False):
            judge_options = sorted_display_names
            def_idx = judge_options.index(judge_default) if judge_default in judge_options else 0
            judge_display = st.selectbox(
                "Modèle juge",
                judge_options,
                index=def_idx,
                help=judge_help(menu),
            )
            judge_tag = display_to_tag.get(judge_display)
            # Le juge lit la question et les réponses : son badge dit où elles partent.
            render_badge(is_cloud_model(judge_tag, menu))

            default_judge_prompt = """Agis comme un juge impartial.
Question: "{prompt}".
Réponse Modèle: "{response}".

Note la qualité de la réponse sur 100.
Critères : Précision, Concision, Respect des consignes.
Format : Uniquement le chiffre (ex: 85)."""
            judge_sys = st.text_area("Critères de notation", value=default_judge_prompt, height=150)

        # Hors de l'expander replié : les avertissements restent visibles.
        for warning in judge_warnings(menu, judge_display):
            st.warning(warning)
        self_caption = judge_self_caption(tag_to_friendly, judge_tag, selected_arena_tags)
        if self_caption:
            st.caption(self_caption)
        weak_text = weak_judge_text(menu, judge_display)

    with col_prompt:
        st.header("Question")
        arena_prompt = st.text_area(
            "Question posée aux modèles",
            value="Explique le concept de « dette technique » à un enfant de 10 ans avec une métaphore filée.",
            height=100,
            label_visibility="collapsed",
        )

        enough_models = len(selected_arena_tags) >= ARENA_MIN_MODELS
        btn_col1, btn_col2 = st.columns([1, 3])
        with btn_col1:
            start_btn = st.button(
                "Lancer la comparaison",
                type="primary",
                width="stretch",
                disabled=not enough_models,
            )
        with btn_col2:
            if not enough_models:
                st.caption(MIN_MODELS_CAPTION)

    # --- 3. EXÉCUTION ---
    if start_btn and enough_models and arena_prompt:
        st.divider()

        results_data = []
        model_responses = {}
        failure_details = []

        status_box = st.status("Comparaison en cours…", expanded=True)
        prog_bar = status_box.progress(0.0)

        total_steps = len(selected_arena_tags)
        judge_name = tag_to_friendly.get(judge_tag, judge_tag) if judge_tag else None

        for i, tag in enumerate(selected_arena_tags):
            friendly_name = selected_arena_friendlies[i]
            # Fournisseur réel, gardé dans chaque ligne de résultats (tableau, vainqueur).
            is_cloud = is_cloud_model(tag, menu)
            _write_loading_note(status_box, tag, friendly_name)
            status_box.write(f"Génération par **{friendly_name}**…")

            try:
                # 1. INFERENCE
                result = asyncio.run(
                    InferenceService.run_inference(
                        model_tag=tag,
                        messages=[{"role": "user", "content": arena_prompt}],
                        temperature=0.1,
                    )
                )

                # Échec (délai dépassé…) : la ligne du modèle le dit, les autres continuent.
                if result.error:
                    label = inference_failure_label(result)
                    status_box.write(f"**{friendly_name}** : {label}. Les autres continuent.")
                    results_data.append(
                        {
                            "Modèle": friendly_name,
                            "tag": tag,
                            "is_cloud": is_cloud,
                            "Note": None,
                            "Débit (t/s)": None,
                            "Chargement (s)": None,
                            "Durée totale (s)": None,
                            "CO2 (mg)": None,
                            "status": STATUS_FAILED,
                            "reason": label,
                        }
                    )
                    failure_details.append(f"{friendly_name} : {result.error}")
                    prog_bar.progress((i + 1) / total_steps)
                    continue

                m = result.metrics

                # 2. CALCUL GREENOPS
                # Nom du catalogue (pas le nom affiché, qui peut porter le tag).
                info = get_model_info(get_friendly_name_from_tag(tag)) or {}
                raw_params = info.get("params_act") or info.get("params_tot", "0")
                p = _extract_params_billions(raw_params)

                impact_mg = None
                if m is not None:
                    if info.get("type") == "api" and m.output_tokens > 0:
                        impact_mg = (
                            CarbonCalculator.compute_mistral_impact_g(p, m.output_tokens) * 1000
                        )
                    else:
                        impact_mg = (
                            CarbonCalculator.compute_local_theoretical_g(m.output_tokens) * 1000
                        )

                # 3. NOTATION JUGE (« non évalué » plutôt que 0 si le juge ne peut pas noter)
                if judge_tag:
                    status_box.write(f"Notation de {friendly_name} par le juge…")
                score, reason, judge_error = _judge(
                    status_box, judge_tag, judge_name, judge_sys, arena_prompt, result.clean_text
                )
                if judge_error:
                    failure_details.append(f"Juge ({friendly_name}) : {judge_error}")

                results_data.append(
                    {
                        "Modèle": friendly_name,
                        "tag": tag,
                        "is_cloud": is_cloud,
                        "Note": score,
                        # Débit = eval_count / eval_duration pour Ollama (D3).
                        "Débit (t/s)": None if m is None else round(m.tokens_per_second, 1),
                        "Débit estimé": m is not None and m.throughput_estimated,
                        # Chargement mesuré par Ollama seulement (vide pour le cloud).
                        "Chargement (s)": (
                            m.load_duration_s if m is not None and m.load_measured else None
                        ),
                        "Durée totale (s)": None if m is None else m.total_duration_s,
                        "CO2 (mg)": None if impact_mg is None else round(impact_mg, 2),
                        "status": STATUS_NOT_EVALUATED if score is None else STATUS_SCORED,
                        "reason": reason,
                    }
                )

                model_responses[friendly_name] = {
                    "text": result.clean_text,
                    "thought": result.thought,
                    "score": score,
                    "reason": reason,
                    "is_cloud": is_cloud,
                }

            except Exception as e:
                status_box.write(f"**{friendly_name}** : échec inattendu. Les autres continuent.")
                results_data.append(
                    {
                        "Modèle": friendly_name,
                        "tag": tag,
                        "is_cloud": is_cloud,
                        "Note": None,
                        "Débit (t/s)": None,
                        "Chargement (s)": None,
                        "Durée totale (s)": None,
                        "CO2 (mg)": None,
                        "status": STATUS_FAILED,
                        "reason": "Échec inattendu",
                    }
                )
                failure_details.append(f"{friendly_name} : {e}")

            prog_bar.progress((i + 1) / total_steps)

        n_failed = sum(1 for r in results_data if r["status"] == STATUS_FAILED)
        all_failed = n_failed == len(results_data)
        if all_failed:
            status_box.update(label="Comparaison échouée", state="error", expanded=False)
        else:
            label = "Comparaison terminée"
            if n_failed:
                label += f" · {pluralize(n_failed, 'modèle en échec', 'modèles en échec')}"
            status_box.update(label=label, state="complete", expanded=False)

        # --- 4. RÉSULTATS ---
        if all_failed:
            render_error(
                "Aucun modèle n'a répondu : pas de classement. Vérifiez qu'Ollama est démarré, "
                "puis relancez la comparaison avec une question plus courte ou des modèles "
                "plus petits.",
                "\n".join(failure_details),
            )
            return

        # La note du vainqueur et du podium vient du juge : ses limites l'accompagnent.
        for caption in (weak_text, self_caption):
            if caption:
                st.caption(caption)
        _render_podium(results_data)
        if failure_details:
            with st.expander("Détails techniques", expanded=False):
                st.code("\n".join(failure_details), language=None)

        st.divider()
        st.header("Réponses des modèles")

        # Notes numériques d'abord, puis « non évalué ».
        def _order(item):
            score = item[1]["score"]
            return (score is None, -(score or 0))

        sorted_items = sorted(model_responses.items(), key=_order)
        if len(model_responses) == 2:
            c1, c2 = st.columns(2)
            for idx, (name, data) in enumerate(sorted_items):
                with c1 if idx == 0 else c2, st.container(border=True):
                    note = NOT_EVALUATED if data["score"] is None else f"{data['score']}/100"
                    st.markdown(
                        f"**{name}** (note : {note}) {badge_markdown(data['is_cloud'])}",
                        help=data["reason"],
                    )
                    st.caption(data["text"])
        else:
            for name, data in sorted_items:
                note = NOT_EVALUATED if data["score"] is None else f"{data['score']}/100"
                with st.expander(f"{name} · {note}"):
                    render_badge(data["is_cloud"])
                    if data["reason"]:
                        st.caption(f"{NOT_EVALUATED.capitalize()} : {data['reason']}")
                    st.markdown(data["text"])
