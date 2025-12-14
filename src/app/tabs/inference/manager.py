import time

import pandas as pd
import streamlit as st

from src.core.llm_provider import LLMProvider
from src.core.models_db import (
    get_all_friendly_names,
    get_all_languages,
    get_model_card,
    get_model_info,
)


def render_manager_tab(installed_models_list: list):
    st.markdown("### 📦 Bibliothèque de Modèles")

    # 1. Filtres avancés
    col_filter_lang, col_filter_cap, col_kpi = st.columns([2, 2, 1])

    with col_filter_lang:
        all_langs = get_all_languages()
        selected_langs = st.multiselect(
            "🌍 Langues requises (ET)",
            all_langs,
            help="Affiche uniquement les modèles qui parlent TOUTES les langues sélectionnées.",
        )

    with col_filter_cap:
        if st.button("🔄 Rafraîchir les métadonnées"):
            st.rerun()

    with col_kpi:
        st.metric("Modèles affichés", len(installed_models_list))

    # 2. Préparation des données
    if installed_models_list:
        table_data = []

        for m in installed_models_list:
            card = get_model_card(m["model"], ollama_info=m)
            info = get_model_info(card["name"]) or {}
            model_langs = info.get("langs", [])

            if selected_langs and (
                not model_langs or not set(selected_langs).issubset(set(model_langs))
            ):
                continue

            # Gestion CO2
            bench_stats = info.get("benchmark_stats", {})
            co2_kg = bench_stats.get("co2_emissions_kg")

            if co2_kg is not None and isinstance(co2_kg, int | float):
                co2_g = co2_kg * 1000
                co2_display = "< 0.01 g" if co2_g < 0.01 else f"{co2_g:.2f} g"
            else:
                co2_display = "—"

            raw_ctx = info.get("ctx", card["metrics"]["ctx"])
            ctx_val = None
            if isinstance(raw_ctx, int | float) or (isinstance(raw_ctx, str) and raw_ctx.isdigit()):
                ctx_val = int(raw_ctx)

            row = {
                "Type": "☁️ Cloud" if card["is_cloud"] else "💻 Local",
                "Statut": f"{card['status_icon']} {card['status_text']}",
                "Nom": card["name"],
                "Éditeur": card["editor"],
                "CO2 (Ref)": co2_display,
                "Vitesse": card["metrics"]["speed"],
                "RAM": card["metrics"]["ram"],
                "Contexte": ctx_val,
                "Params": info.get("params_tot", card["specs"]["params"]),
                "Actifs": info.get("params_act", "—"),
                "Langues": model_langs if model_langs else [],
                "Description": info.get("desc", card["description"]),
                "Link": info.get("link"),
                "Taille": card["size_str"],
            }
            table_data.append(row)

        if table_data:
            st.dataframe(
                pd.DataFrame(table_data),
                column_order=[
                    "Type",
                    "Statut",
                    "Nom",
                    "Éditeur",
                    "CO2 (Ref)",
                    "Vitesse",
                    "RAM",
                    "Contexte",
                    "Params",
                    "Actifs",
                    "Langues",
                    "Description",
                    "Link",
                ],
                column_config={
                    "Type": st.column_config.TextColumn(
                        "Type",
                        width="small",
                        help="💻 = Tourne sur votre machine\n☁️ = Appel API externe",
                    ),
                    "Statut": st.column_config.TextColumn("État", width="small"),
                    "Nom": st.column_config.TextColumn("Modèle", width="medium"),
                    "Éditeur": st.column_config.TextColumn("Éditeur", width="small"),
                    "CO2 (Ref)": st.column_config.TextColumn("Impact CO2", width="small"),
                    "Vitesse": st.column_config.TextColumn("Latence"),
                    "RAM": st.column_config.TextColumn("RAM Run"),
                    "Contexte": st.column_config.NumberColumn("Ctx (tk)", format="%d"),
                    "Params": st.column_config.TextColumn("Params Tot."),
                    "Actifs": st.column_config.TextColumn("Params Act."),
                    "Langues": st.column_config.ListColumn("Langues", width="medium"),
                    "Description": st.column_config.TextColumn("Description", width="large"),
                    "Link": st.column_config.LinkColumn("Doc", display_text="Fiche"),
                    "Taille": st.column_config.TextColumn("Disk"),
                },
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Aucun modèle ne correspond à vos critères de filtrage.")
    else:
        st.warning("Aucun modèle détecté.")

    st.markdown("---")
    st.markdown("### ⬇️ Télécharger un nouveau modèle")

    col_select, col_info = st.columns([1, 1])
    with col_select:
        suggestions = sorted(get_all_friendly_names(local_only=True))
        options = (
            ["✨ Sélectionner une suggestion..."] + suggestions + ["🛠️ Autre (Saisie Manuelle)"]
        )
        choice = st.selectbox("Catalogue Wavestone", options)

        target_model_tag = ""
        if choice == "🛠️ Autre (Saisie Manuelle)":
            target_model_tag = st.text_input("Tag Ollama", "")
            st.caption("[Ollama Library](https://ollama.com/library)")
        elif choice != "✨ Sélectionner une suggestion...":
            info = get_model_info(choice)
            if info:
                target_model_tag = info["ollama_tag"]

    with col_info:
        if choice not in ["✨ Sélectionner une suggestion...", "🛠️ Autre (Saisie Manuelle)"] and (
            info := get_model_info(choice)
        ):
            st.info(f"**{info.get('desc', '')}**")
            st.markdown(
                f"**Contexte:** `{info.get('ctx', '?')}` | **Params:** `{info.get('params_tot', '?')}`"
            )

    st.write("")
    if st.button("⬇️ Lancer le téléchargement") and target_model_tag:
        status = st.status(f"Téléchargement de {target_model_tag}...", expanded=True)
        pbar = status.progress(0, text="Connexion...")
        try:
            for progress in LLMProvider.pull_model(target_model_tag):
                if progress.get("total"):
                    p = progress["completed"] / progress["total"]
                    pbar.progress(p, text=f"{progress['status']} - {int(p*100)}%")
                else:
                    pbar.progress(0.5, text=progress["status"])
            pbar.progress(1.0, text="Terminé !")
            status.update(label="✅ Succès !", state="complete", expanded=False)
            time.sleep(1)
            st.rerun()
        except Exception as e:
            status.update(label="❌ Erreur", state="error")
            st.error(str(e))
