"""
Onglet « Gestion des modèles » de l'Arène des modèles : modèles installés, filtres par
capacité, installation depuis le catalogue ou par tag Ollama.
"""

import contextlib
import time

import pandas as pd
import streamlit as st

from src.app.formatting import pluralize
from src.core.llm_provider import LLMProvider
from src.core.models_db import (
    get_all_friendly_names,
    get_model_card,
    get_model_info,
)


# --- 1. HELPERS DE PARSING (Pour le tri) ---
def _parse_params_to_float(val: str | int | float) -> float:
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


def _parse_size_to_float(val: str) -> float:
    if not val or not isinstance(val, str):
        return 0.0
    try:
        return float(val.lower().replace("gb", "").replace("mb", "").strip())
    except Exception:
        return 0.0


# Options du sélecteur d'installation et des filtres : valeurs comparées par égalité,
# définies une seule fois.
CATALOG_PLACEHOLDER = "Choisir dans le catalogue…"
MANUAL_TAG_OPTION = "Autre (tag Ollama saisi à la main)"

FILTER_ALL = "Tout"
FILTER_REASONING = "Raisonnement"
FILTER_TOOLS = "Outils"
FILTER_FAST = "Rapide"
FILTER_CLOUD = "Cloud"


# --- 2. MODAL DE TÉLÉCHARGEMENT ---
@st.dialog("Ajouter un modèle")
def open_download_modal(installed_names: list):
    st.caption("Téléchargez des modèles depuis la bibliothèque Ollama ou le catalogue Wavestone.")

    col_sel, col_info = st.columns([2, 1])

    with col_sel:
        # 1. Récupération catalogue complet
        all_suggestions = sorted(get_all_friendly_names(local_only=True))

        # 2. Filtrage : On retire ceux déjà installés
        # On normalise en minuscule pour éviter les doublons de casse
        installed_set = {n.lower() for n in installed_names}
        filtered_suggestions = [s for s in all_suggestions if s.lower() not in installed_set]

        # 3. Construction du menu avec l'ordre demandé
        options = [CATALOG_PLACEHOLDER, MANUAL_TAG_OPTION] + filtered_suggestions

        choice = st.selectbox("Modèle", options, label_visibility="collapsed")

        target_tag = ""
        if choice == MANUAL_TAG_OPTION:
            target_tag = st.text_input(
                "Tag Ollama (par exemple llama3:8b)", help="Liste des tags : ollama.com/library"
            )
        elif choice != CATALOG_PLACEHOLDER:
            info = get_model_info(choice)
            if info:
                target_tag = info["ollama_tag"]

    with col_info:
        if choice not in [CATALOG_PLACEHOLDER, MANUAL_TAG_OPTION]:
            info = get_model_info(choice)
            if info:
                st.info(
                    f"**Caractéristiques**\n\nContexte : {info.get('ctx', '?')}\n"
                    f"Paramètres : {info.get('params_tot', '?')}"
                )

    st.divider()

    # Bouton d'action
    if st.button(
        "Ajouter le modèle",
        type="primary",
        icon=":material/download:",
        width="stretch",
        disabled=not target_tag,
    ):
        status_box = st.status(f"Ajout de **{target_tag}**…", expanded=True)
        pbar = status_box.progress(0, text="Connexion…")

        try:
            for progress in LLMProvider.pull_model(target_tag):
                if progress.get("total"):
                    p = progress["completed"] / progress["total"]
                    pbar.progress(p, text=f"{progress['status']} ({int(p*100)}%)")
                else:
                    pbar.progress(0.5, text=progress["status"])

            pbar.progress(1.0, text="Terminé")
            status_box.update(label="Modèle ajouté", state="complete")
            time.sleep(1)
            st.rerun()

        except Exception as e:
            status_box.update(label="Échec de l'ajout", state="error")
            st.error(f"Le modèle n'a pas pu être ajouté : {e}")


# --- 3. RENDU PRINCIPAL ---
def render_manager_tab(installed_models_list: list):

    # -- Prépation de la liste des noms installés pour le filtrage --
    installed_friendly_names = []

    # EN-TÊTE ACTIONNABLE
    c_title, c_add, c_refresh = st.columns([3, 1, 0.8])
    with c_title:
        st.header("Modèles disponibles")
        count = pluralize(
            len(installed_models_list), "modèle prêt à l'emploi", "modèles prêts à l'emploi"
        )
        st.caption(f"{count}.")
    with c_refresh:
        if st.button("Rafraîchir", icon=":material/refresh:", help="Rafraîchir la liste"):
            st.rerun()

    st.divider()

    # FILTRES RAPIDES (PILLS)
    filter_options = [FILTER_ALL, FILTER_REASONING, FILTER_TOOLS, FILTER_FAST, FILTER_CLOUD]
    try:
        selection = st.pills(
            "Filtrer par capacité", filter_options, default=FILTER_ALL, selection_mode="single"
        )
    except AttributeError:
        selection = st.radio("Filtre", filter_options, horizontal=True)

    # PRÉPARATION DES DONNÉES
    if installed_models_list:
        table_data = []
        for m in installed_models_list:
            card = get_model_card(m["model"], ollama_info=m)
            # On stocke le nom friendly pour le passer au modal plus tard
            installed_friendly_names.append(card["name"])

            info = get_model_info(card["name"]) or {}
            stats = info.get("benchmark_stats", {})

            # --- LOGIQUE DE FILTRAGE ---
            keep = True
            is_cloud = card["is_cloud"]

            if (
                selection == FILTER_CLOUD
                and not is_cloud
                or (
                    selection == FILTER_REASONING
                    and stats.get("quality_scores", {}).get("reasoning_avg", 0) < 0.6
                )
                or (
                    selection == FILTER_TOOLS
                    and stats.get("tool_capability", {}).get("success_rate", 0) < 0.8
                )
                or selection == FILTER_FAST
                and stats.get("avg_ttft_ms", 9999) > 800
                or selection != FILTER_ALL
                and selection != FILTER_CLOUD
                and is_cloud
            ):
                keep = False

            if not keep:
                continue

            # --- PREP VALEURS ---
            speed = stats.get("avg_tokens_per_second", 0.0)
            if speed == 0 and not is_cloud:
                with contextlib.suppress(ValueError):
                    speed = float(card["metrics"]["speed"].split(" ")[0])

            ram = stats.get("ram_usage_at_max_ctx_gb", 0.0)
            if ram == 0:
                ram = _parse_size_to_float(card.get("size_str", ""))

            co2_kg = stats.get("avg_co2_per_1k_tokens", 0)
            co2_mg = co2_kg * 1_000_000 if co2_kg else None

            caps = []
            if stats.get("tool_capability", {}).get("success_rate", 0) > 0.9:
                caps.append("Outils")
            if stats.get("quality_scores", {}).get("reasoning_avg", 0) > 0.7:
                caps.append("Raisonnement")
            if is_cloud:
                caps.append("Cloud")

            row = {
                "Nom": card["name"],
                "Format": "Cloud" if is_cloud else "Local",
                "Vitesse": speed,
                # Valeur inconnue (0) → absente (None), affichée vide plutôt que « 0,0 ».
                "RAM": ram or None,
                "CO2": co2_mg,
                "Params": _parse_params_to_float(
                    info.get("params_act") or info.get("params_tot", "0")
                )
                or None,
                "Contexte": int(info.get("ctx", 0)) if str(info.get("ctx", "0")).isdigit() else 0,
                "Capacités": " · ".join(caps),
                "Tag": m["model"],
            }
            table_data.append(row)

        # AFFICHAGE DU TABLEAU
        if table_data:
            df = pd.DataFrame(table_data)
            df = df.sort_values(by="Vitesse", ascending=False)

            st.dataframe(
                df,
                column_order=["Nom", "Format", "Vitesse", "RAM", "CO2", "Params", "Capacités"],
                column_config={
                    "Nom": st.column_config.TextColumn(
                        "Modèle", width="medium", help="Nom usuel du modèle."
                    ),
                    "Format": st.column_config.TextColumn(
                        "Type",
                        width="small",
                        help="Cloud : modèle distant (Mistral, OpenAI), joint par Internet.\n"
                        "Local : modèle qui tourne sur cette machine (Ollama).",
                    ),
                    "Vitesse": st.column_config.ProgressColumn(
                        "Débit (tokens/s)",
                        # Entier : aucun séparateur décimal à localiser.
                        format="%.0f",
                        min_value=0,
                        max_value=100,
                        help="Tokens générés par seconde. Plus la barre est pleine, plus la "
                        "génération est rapide.",
                    ),
                    # Colonnes numériques (tri numérique) au format de la locale du
                    # navigateur : virgule décimale sur un poste en français.
                    "RAM": st.column_config.NumberColumn(
                        "Mémoire (Go)",
                        format="localized",
                        help="Mémoire vive (ou vidéo) occupée par le modèle une fois chargé.",
                    ),
                    "CO2": st.column_config.NumberColumn(
                        "CO₂ (mg pour 1 000 tokens)",
                        format="localized",
                        help="Estimation de l'impact carbone pour 1 000 tokens générés.",
                    ),
                    "Params": st.column_config.NumberColumn(
                        "Paramètres (milliards)",
                        format="localized",
                        help="Nombre de paramètres, en milliards.",
                    ),
                    "Capacités": st.column_config.TextColumn(
                        "Capacités",
                        help="Outils : sait appeler des outils (function calling).\n"
                        "Raisonnement : bon en raisonnement logique.\nCloud : modèle distant.",
                    ),
                },
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("Aucun modèle ne correspond à ce filtre.")
    else:
        st.warning("Aucun modèle détecté.")

    # BOUTON D'AJOUT (En dessous du titre mais logique définie ici pour utiliser installed_names)
    with c_add:
        if st.button("Ajouter un modèle", type="primary", icon=":material/add:", width="stretch"):
            # On passe la liste des noms installés au modal pour filtrage
            open_download_modal(installed_friendly_names)
