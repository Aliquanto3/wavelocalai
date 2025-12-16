"""
Inference Manager Tab - Sprint 1 (App Store Look & Onboarding)
Mise à jour UX : Filtres intelligents, Ordre menu, Tooltips techniques.
"""

import contextlib
import time

import pandas as pd
import streamlit as st

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


# --- 2. MODAL DE TÉLÉCHARGEMENT ---
@st.dialog("⬇️ Installer un nouveau Modèle")
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
        options = [
            "✨ Sélectionner dans le catalogue...",
            "🛠️ Autre (Tag Ollama Manuel)",
        ] + filtered_suggestions

        choice = st.selectbox("Modèle", options, label_visibility="collapsed")

        target_tag = ""
        if choice == "🛠️ Autre (Tag Ollama Manuel)":
            target_tag = st.text_input("Tag (ex: llama3:8b)", help="Voir ollama.com/library")
        elif choice != "✨ Sélectionner dans le catalogue...":
            info = get_model_info(choice)
            if info:
                target_tag = info["ollama_tag"]

    with col_info:
        if choice not in ["✨ Sélectionner dans le catalogue...", "🛠️ Autre (Tag Ollama Manuel)"]:
            info = get_model_info(choice)
            if info:
                st.info(
                    f"**Specs**\n\nCtx: {info.get('ctx','?')}\nParams: {info.get('params_tot','?')}"
                )

    st.divider()

    # Bouton d'action
    if st.button(
        "⬇️ Lancer l'installation", type="primary", use_container_width=True, disabled=not target_tag
    ):
        status_box = st.status(f"Installation de **{target_tag}**...", expanded=True)
        pbar = status_box.progress(0, text="Connexion...")

        try:
            for progress in LLMProvider.pull_model(target_tag):
                if progress.get("total"):
                    p = progress["completed"] / progress["total"]
                    pbar.progress(p, text=f"{progress['status']} ({int(p*100)}%)")
                else:
                    pbar.progress(0.5, text=progress["status"])

            pbar.progress(1.0, text="Terminé !")
            status_box.update(label="✅ Modèle installé avec succès !", state="complete")
            time.sleep(1)
            st.rerun()

        except Exception as e:
            status_box.update(label="❌ Échec", state="error")
            st.error(f"Erreur : {str(e)}")


# --- 3. RENDU PRINCIPAL ---
def render_manager_tab(installed_models_list: list):

    # -- Prépation de la liste des noms installés pour le filtrage --
    installed_friendly_names = []

    # EN-TÊTE ACTIONNABLE
    c_title, c_add, c_refresh = st.columns([3, 1, 0.5])
    with c_title:
        st.markdown("### 📦 Mes Modèles Locaux")
        st.caption(f"{len(installed_models_list)} modèles installés et prêts à l'emploi.")
    with c_refresh:
        if st.button("🔄", help="Rafraîchir la liste"):
            st.rerun()

    st.divider()

    # FILTRES RAPIDES (PILLS)
    filter_options = ["Tout", "🧠 Raisonnement", "🛠️ Tools", "⚡ Rapide", "☁️ Cloud"]
    try:
        selection = st.pills(
            "Filtrer par capacité", filter_options, default="Tout", selection_mode="single"
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
                selection == "☁️ Cloud"
                and not is_cloud
                or (
                    selection == "🧠 Raisonnement"
                    and stats.get("quality_scores", {}).get("reasoning_avg", 0) < 0.6
                )
                or (
                    selection == "🛠️ Tools"
                    and stats.get("tool_capability", {}).get("success_rate", 0) < 0.8
                )
                or selection == "⚡ Rapide"
                and stats.get("avg_ttft_ms", 9999) > 800
                or selection != "Tout"
                and selection != "☁️ Cloud"
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
                caps.append("🛠️")
            if stats.get("quality_scores", {}).get("reasoning_avg", 0) > 0.7:
                caps.append("🧠")
            if is_cloud:
                caps.append("☁️")

            row = {
                "Nom": card["name"],
                "Format": "API" if is_cloud else "Local",
                "Vitesse": speed,
                "RAM": ram,
                "CO2": co2_mg,
                "Params": _parse_params_to_float(
                    info.get("params_act") or info.get("params_tot", "0")
                ),
                "Contexte": int(info.get("ctx", 0)) if str(info.get("ctx", "0")).isdigit() else 0,
                "Capacités": " ".join(caps),
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
                        "Modèle", width="medium", help="Nom commercial du modèle (Friendly Name)."
                    ),
                    "Format": st.column_config.TextColumn(
                        "Type",
                        width="small",
                        help="API = Modèle distant (Mistral/OpenAI) via Internet.\nLocal = Modèle tournant sur votre machine (Ollama).",
                    ),
                    "Vitesse": st.column_config.ProgressColumn(
                        "Vitesse (t/s)",
                        format="%.1f t/s",
                        min_value=0,
                        max_value=100,
                        help="Tokens par seconde (Débit). Plus la barre est pleine, plus la génération est rapide.",
                    ),
                    "RAM": st.column_config.NumberColumn(
                        "RAM (GB)",
                        format="%.1f GB",
                        help="Mémoire vive (VRAM/RAM) occupée par le modèle une fois chargé.",
                    ),
                    "CO2": st.column_config.NumberColumn(
                        "CO₂ (mg/1k)",
                        format="%.1f mg",
                        help="Estimation de l'impact carbone pour 1000 tokens générés (ACV pour Cloud, Scope 2 pour Local).",
                    ),
                    "Params": st.column_config.NumberColumn(
                        "Params (B)",
                        format="%.1f B",
                        help="Nombre de paramètres (milliards). Indique la complexité et la 'culture' du modèle.",
                    ),
                    "Capacités": st.column_config.TextColumn(
                        "Badge",
                        help="🛠️ = Supporte les Outils/Function Calling.\n🧠 = Fort en raisonnement logique.\n☁️ = Modèle Cloud.",
                    ),
                },
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Aucun modèle ne correspond à ce filtre.")
    else:
        st.warning("Aucun modèle détecté.")

    # BOUTON D'AJOUT (En dessous du titre mais logique définie ici pour utiliser installed_names)
    with c_add:
        if st.button("➕ Ajouter un Modèle", type="primary", use_container_width=True):
            # On passe la liste des noms installés au modal pour filtrage
            open_download_modal(installed_friendly_names)
