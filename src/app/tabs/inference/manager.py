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


def _parse_params_to_float(val: str | int | float) -> float:
    """Convertit '7B', '350M' en float (Milliards) pour le tri."""
    if isinstance(val, (int, float)):
        return float(val)
    if not val or not isinstance(val, str):
        return 0.0
    s = val.upper().strip().replace(" ", "")
    try:
        if "X" in s and "B" in s:  # Ex: 8x7B
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
    """Convertit '1.5 GB' en 1.5 (float)."""
    if not val or not isinstance(val, str):
        return 0.0
    try:
        return float(val.lower().replace("gb", "").replace("mb", "").strip())
    except Exception:
        return 0.0


def render_manager_tab(installed_models_list: list):
    st.markdown("### 📦 Bibliothèque de Modèles")

    # 1. Filtres
    col_filter_lang, col_filter_cap, col_refresh, col_kpi = st.columns([2, 2, 1, 1])

    with col_filter_lang:
        all_langs = get_all_languages()
        selected_langs = st.multiselect(
            "🌍 Langues requises (ET)",
            all_langs,
            help="Affiche uniquement les modèles validés pour TOUTES ces langues.",
        )

    with col_filter_cap:
        cap_options = {
            "🛠️ Tools": "tools_validated",
            "{} JSON": "json_validated",
            "🧠 Raisonnement": "reasoning_high",
            "⚡ Rapide (<800ms)": "fast_ux",
        }
        selected_caps = st.multiselect(
            "✨ Capacités requises",
            options=list(cap_options.keys()),
            help="Filtre sur les capacités techniques validées.",
        )

    with col_refresh:
        st.write("")
        if st.button("🔄 Rafraîchir", use_container_width=True):
            st.rerun()

    with col_kpi:
        st.write("")
        st.metric("Total", len(installed_models_list), label_visibility="collapsed")

    # 2. Préparation des données
    if installed_models_list:
        table_data = []

        for m in installed_models_list:
            card = get_model_card(m["model"], ollama_info=m)
            info = get_model_info(card["name"]) or {}
            stats = info.get("benchmark_stats", {})
            model_langs = info.get("langs", [])

            # --- FILTRAGE ---
            if selected_langs and (
                not model_langs or not set(selected_langs).issubset(set(model_langs))
            ):
                continue

            keep_model = True
            for cap_label in selected_caps:
                key = cap_options[cap_label]
                if (
                    (
                        key == "tools_validated"
                        and stats.get("tool_capability", {}).get("success_rate", 0) < 0.9
                    )
                    or (
                        key == "json_validated"
                        and stats.get("json_capability", {}).get("schema_compliance_rate", 0) < 0.9
                    )
                    or (
                        key == "reasoning_high"
                        and stats.get("quality_scores", {}).get("reasoning_avg", 0) < 0.6
                    )
                    or key == "fast_ux"
                    and stats.get("avg_ttft_ms", 9999) > 800
                ):
                    keep_model = False
            if not keep_model:
                continue

            # --- NORMALISATION (TYPES NUMÉRIQUES POUR TRI) ---

            # Vitesse (Float)
            speed_val = stats.get("avg_tokens_per_second", 0.0)
            if speed_val == 0.0:
                # Tentative de parsing du statique "35 t/s" si benchmark manquant
                try:
                    speed_val = float(card["metrics"]["speed"].split(" ")[0])
                except Exception:
                    speed_val = 0.0

            # TTFT (Float sec)
            ttft_ms = stats.get("avg_ttft_ms", 0)
            ttft_s = ttft_ms / 1000.0 if ttft_ms else None

            # RAM (Float)
            # Priorité : Benchmark > Taille Disque > 0
            ram_val = stats.get("ram_usage_at_max_ctx_gb", 0.0)
            if ram_val == 0.0:
                ram_val = _parse_size_to_float(card.get("size_str", ""))

            # Params (Float)
            raw_pt = info.get("params_tot", card["specs"]["params"])
            raw_pa = info.get("params_act", "—")
            val_pt = _parse_params_to_float(raw_pt)
            val_pa = _parse_params_to_float(raw_pa)

            # Taille Disque (Float)
            disk_val = _parse_size_to_float(card.get("size_str", ""))

            # Caps (String + Count pour pré-tri)
            caps_icons = []
            if stats.get("tool_capability", {}).get("success_rate", 0) > 0.9:
                caps_icons.append("🛠️")
            if stats.get("json_capability", {}).get("schema_compliance_rate", 0) > 0.9:
                caps_icons.append("{}")
            if stats.get("quality_scores", {}).get("reasoning_avg", 0) > 0.7:
                caps_icons.append("🧠")

            # UX
            ux_rating = stats.get("ux_rating", "")
            ux_emoji = ux_rating.split(" ")[0] if ux_rating else ""

            # CO2
            co2_kg = stats.get("avg_co2_per_1k_tokens", 0)
            co2_mg = co2_kg * 1_000_000 if co2_kg else None

            # Nettoyage Licence (Remplacement des erreurs par un emoji)
            raw_lic = stats.get("detected_license", "—")
            if raw_lic in ["Erreur lecture", "Non détectée", "Erreur", "N/A"]:
                lic_display = "❓"
            else:
                lic_display = raw_lic

            row = {
                "Type": "☁️ API" if card["is_cloud"] else "💻 Local",
                "Nom": card["name"],
                "Licence": lic_display,
                "UX": ux_emoji,
                "Vitesse": speed_val,
                "TTFT": ttft_s,
                "Efficience": stats.get("efficiency_grade", "—"),
                "CO2": co2_mg,
                "Caps": " ".join(caps_icons),
                "RAM": ram_val,
                "Contexte": int(info.get("ctx", 0)) if str(info.get("ctx", "0")).isdigit() else 0,
                "Params Tot.": val_pt,
                "Params Act.": val_pa,
                "Disque": disk_val,
                "Langues": model_langs,
                "Link": info.get("link"),
                # Métriques cachées pour le pré-tri par défaut
                "_count_caps": len(caps_icons),
                "_count_langs": len(model_langs),
            }
            table_data.append(row)

        if table_data:
            df = pd.DataFrame(table_data)

            # PRÉ-TRI PAR DÉFAUT : Par Capacités puis par Nombre de Langues (Descendant)
            df = df.sort_values(by=["_count_caps", "_count_langs"], ascending=False)

            st.dataframe(
                df,
                column_order=[
                    "Type",
                    "Nom",
                    "Licence",
                    "UX",
                    "Vitesse",
                    "TTFT",
                    "Efficience",
                    "CO2",
                    "Caps",
                    "RAM",
                    "Contexte",
                    "Params Tot.",
                    "Params Act.",
                    "Disque",
                    "Langues",
                    "Link",
                ],
                column_config={
                    "Type": st.column_config.TextColumn("Type", width="small"),
                    "Nom": st.column_config.TextColumn("Modèle", width="medium"),
                    "Licence": st.column_config.TextColumn(
                        "Licence",
                        width="small",
                        help="Licence détectée automatiquement. Cliquez sur 'Lien' pour vérifier les conditions d'usage.",
                    ),
                    "UX": st.column_config.TextColumn(
                        "UX",
                        width="small",
                        help="Note de fluidité ressentie (basée sur le TTFT).\n⚡ Instantané (<300ms)\n🚀 Rapide (<800ms)\n🐢 Acceptable (<1.5s)",
                    ),
                    "Vitesse": st.column_config.NumberColumn(
                        "Vit. (t/s)",
                        format="%.1f t/s",
                        help="Débit de génération (Tokens/seconde). Valeur plus haute = génération plus rapide.",
                    ),
                    "TTFT": st.column_config.NumberColumn(
                        "Latence",
                        format="%.2f s",
                        help="Time To First Token : Temps d'attente avant le début de la réponse.",
                    ),
                    "Efficience": st.column_config.TextColumn(
                        "RSE",
                        width="small",
                        help="Grade (🟢/🟡/🔴) calculé selon le ratio : Qualité du Raisonnement / Coût Carbone.",
                    ),
                    "CO2": st.column_config.NumberColumn(
                        "CO₂ (mg)",
                        format="%.1f mg",
                        help="Impact carbone pour 1000 tokens générés (milligrammes).",
                    ),
                    "Caps": st.column_config.TextColumn(
                        "Caps.",
                        width="small",
                        help="Capacités validées :\n🛠️ = Tool Calling fiable\n{} = JSON Schema respecté\n🧠 = Raisonnement logique > 70%",
                    ),
                    "RAM": st.column_config.NumberColumn(
                        "RAM",
                        format="%.1f GB",
                        help="Mémoire vive réelle consommée. Si 0 (erreur de sonde), affiche la taille disque.",
                    ),
                    "Contexte": st.column_config.NumberColumn(
                        "Ctx (tk)",
                        format="%d",
                        help="Fenêtre de contexte maximale (mémoire à court terme du modèle).",
                    ),
                    "Params Tot.": st.column_config.NumberColumn(
                        "P. Tot",
                        format="%.1f B",
                        help="Nombre total de paramètres (Milliards). Indique la 'culture générale' du modèle.",
                    ),
                    "Params Act.": st.column_config.NumberColumn(
                        "P. Act",
                        format="%.1f B",
                        help="Paramètres actifs par token (pour les modèles MoE). Indique le coût d'inférence réel.",
                    ),
                    "Disque": st.column_config.NumberColumn(
                        "Disque",
                        format="%.1f GB",
                        help="Espace de stockage occupé sur le disque dur.",
                    ),
                    "Langues": st.column_config.ListColumn(
                        "Langues",
                        help="Liste des langues validées par le benchmark (Compréhension ou Génération).",
                    ),
                    "Link": st.column_config.LinkColumn("Lien", display_text="🔗"),
                },
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Aucun modèle ne correspond à vos critères.")
    else:
        st.warning("Aucun modèle détecté en local.")

    # ... (Reste du code de téléchargement inchangé) ...
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
