import asyncio
import re
import time

import pandas as pd
import streamlit as st

from src.core.inference_service import InferenceCallbacks, InferenceService

# --- Imports Core ---
from src.core.llm_provider import LLMProvider
from src.core.models_db import get_model_card  # Pour le tableau (Card UX)
from src.core.models_db import (
    get_all_friendly_names,
    get_all_languages,
    get_friendly_name_from_tag,
    get_model_info,
)
from src.core.resource_manager import ResourceManager

# --- Configuration de la Page ---
st.set_page_config(page_title="Inférence & Arena", page_icon="🧠", layout="wide")

# --- CSS Custom ---
st.markdown(
    """
<style>
    [data-testid="stMetricValue"] { font-size: 24px; }
    .stTextArea textarea { font-family: monospace; }
</style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 1. SIDEBAR & CONFIGURATION GLOBALE
# ==========================================
with st.sidebar:
    st.header("⚙️ Configuration")

    # Global Cloud Toggle (Persistant)
    if "cloud_enabled" not in st.session_state:
        st.session_state.cloud_enabled = True

    cloud_enabled = st.toggle(
        "Activer Cloud (Mistral)",
        value=st.session_state.cloud_enabled,
        help="Si désactivé, seuls les modèles locaux (Ollama) seront accessibles.",
    )
    st.session_state.cloud_enabled = cloud_enabled

    st.divider()

    if not cloud_enabled:
        st.caption("🔒 Mode Local Strict")
    else:
        st.caption("☁️ Mode Hybride")

# ==========================================
# 2. CHARGEMENT CENTRALISÉ DES MODÈLES
# ==========================================
# On charge la liste UNE SEULE FOIS pour toute la page, en appliquant le filtre Cloud/Local
installed_models_list = LLMProvider.list_models(cloud_enabled=cloud_enabled)


def format_model_label(model_data):
    """Helper pour l'affichage avec icônes dans les SelectBox"""
    tag = model_data["model"]
    # Détection sécurisée du type
    is_cloud = model_data.get("type") == "cloud"
    friendly = get_friendly_name_from_tag(tag)
    icon = "☁️" if is_cloud else "💻"
    return f"{icon} {friendly}"


# Maps pour les sélecteurs (Label Joli -> Tag Technique)
display_to_tag = {format_model_label(m): m["model"] for m in installed_models_list}
# Map inverse pour retrouver le nom "friendly" depuis un tag (utile pour l'Arena)
tag_to_friendly = {
    m["model"]: get_friendly_name_from_tag(m["model"]) for m in installed_models_list
}

sorted_display_names = sorted(display_to_tag.keys())

st.title("🧠 Inférence & Model Arena")
st.caption("Benchmark technique et fonctionnel des SLM.")

# --- DATA: CAS D'USAGE ---
USE_CASES = {
    "🇬🇧 Traduction Technique": {
        "system": 'Tu es un expert en traduction technique. Traduis le texte suivant en Anglais, Espagnol et Allemand. Sois précis sur la terminologie informatique. Réponds au format JSON : {"en": "...", "es": "...", "de": "..."}.',
        "user": "L'architecture 'Local First' permet de réduire la latence réseau et d'améliorer la confidentialité des données en traitant les inférences directement sur le CPU de l'utilisateur, sans appel API vers le cloud.",
    },
    "📄 Extraction Structurée (JSON)": {
        "system": "Tu es un extracteur de données strict. Extrais les entités du texte (Date, Montant, Vendeur, Articles). Réponds UNIQUEMENT avec un JSON valide. Pas de texte avant ni après.",
        "user": "FACTURE N° 2024-001\nDate : 12 décembre 2024\nVendeur : Wavestone Tech\n\nArticles :\n- 1x Audit Green IT (500€)\n- 3x Licences Copilot (90€)\n\nTotal TTC : 590€",
    },
    "💻 Assistant Coding (Python)": {
        "system": "Tu es un Tech Lead Python expérimenté. Génère du code propre, typé (Type Hints) et documenté (Docstrings). Inclus une gestion d'erreur robuste.",
        "user": "Écris une fonction Python asynchrone qui interroge une API REST avec la librairie 'httpx', gère les retries en cas d'erreur 500, et retourne le résultat en dictionnaire.",
    },
    "🧮 Raisonnement (Chain of Thought)": {
        "system": "Tu es un expert en logique. Pour répondre, tu dois IMPÉRATIVEMENT utiliser la méthode 'Chain of Thought' : explique ton raisonnement étape par étape avant de donner la réponse finale.",
        "user": "J'ai 3 pommes. Hier j'en ai mangé une. Aujourd'hui j'en achète deux autres, mais j'en fais tomber une dans la boue que je jette. Combien de pommes puis-je manger maintenant ?",
    },
    "📝 Résumé Exécutif": {
        "system": "Tu es un assistant de direction. Fais un résumé concis (bullet points) du texte fourni, en te concentrant sur les décisions clés et les actions à entreprendre.",
        "user": "Compte rendu de réunion - Projet Alpha.\nLa réunion a débuté à 10h. L'équipe a convenu que le budget initial était insuffisant. Marc doit revoir le fichier Excel d'ici mardi. Sophie a soulevé un risque de sécurité sur l'API, il faut auditer le module d'auth. La deadline du projet est repoussée de 2 semaines pour permettre ces ajustements. Le client a validé le nouveau design.",
    },
}

# --- SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "lab_result" not in st.session_state:
    st.session_state.lab_result = None
if "lab_metrics" not in st.session_state:
    st.session_state.lab_metrics = None

# --- TABS ---
tab_chat, tab_lab, tab_arena, tab_manager = st.tabs(
    ["💬 Chat Libre", "🧪 Labo de Tests", "⚔️ Arena", "⚙️ Gestion Modèles"]
)

# ==========================================
# ONGLET 1 : CHAT LIBRE
# ==========================================
with tab_chat:
    col_chat_params, col_chat_main = st.columns([1, 3])

    with col_chat_params:
        st.subheader("Paramètres")
        # Utilisation de la liste filtrée globale
        selected_display = st.selectbox(
            "Modèle actif", sorted_display_names, key="chat_model_select"
        )
        selected_tag = display_to_tag.get(selected_display)

        temp = st.slider("Température", 0.0, 1.0, 0.7, key="chat_temp")

        st.info("Ce mode conserve l'historique.")
        if st.button("🗑️ Nouvelle conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    with col_chat_main:
        # Historique
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if "thought" in msg and msg["thought"]:
                    with st.expander("💭 Raisonnement (CoT)", expanded=False):
                        st.markdown(msg["thought"])
                st.markdown(msg["content"])

        # Input
        if prompt := st.chat_input("Discutez avec le modèle..."):
            st.session_state.messages.append({"role": "user", "content": prompt})

            with st.chat_message("assistant"):
                msg_container = st.empty()
                state = {"current_text": ""}

                async def on_token(token: str):
                    state["current_text"] += token
                    msg_container.markdown(state["current_text"] + "▌")

                callbacks = InferenceCallbacks(on_token=on_token)

                result = asyncio.run(
                    InferenceService.run_inference(
                        model_tag=selected_tag,
                        messages=st.session_state.messages,
                        temperature=temp,
                        callbacks=callbacks,
                    )
                )

                msg_container.empty()
                if result.thought:
                    # Correction SIM117 : Fusion des with
                    with msg_container.container(), st.expander("💭 Raisonnement", expanded=False):
                        st.markdown(result.thought)
                    st.markdown(result.clean_text)
                else:
                    msg_container.markdown(result.clean_text)

                st.session_state.messages.append(
                    {"role": "assistant", "content": result.clean_text, "thought": result.thought}
                )
                st.rerun()

# ==========================================
# ONGLET 2 : LABO DE TESTS
# ==========================================
with tab_lab:
    col_lab_config, col_lab_run, col_lab_metrics = st.columns([1, 2, 1])

    with col_lab_config:
        st.subheader("1. Scénario")
        lab_model_display = st.selectbox(
            "Modèle de Test", sorted_display_names, key="lab_model_select"
        )
        lab_model_tag = display_to_tag.get(lab_model_display)
        # Nom friendly sans l'icône pour lookup infos
        lab_model_friendly = tag_to_friendly.get(lab_model_tag, "Inconnu")

        selected_use_case = st.selectbox("Cas d'Usage", list(USE_CASES.keys()))
        default_sys = USE_CASES[selected_use_case]["system"]
        default_user = USE_CASES[selected_use_case]["user"]

        lab_temp = st.slider(
            "Température",
            0.0,
            1.0,
            0.2,
            key="lab_temp",
            help="Basse pour extraction/code, Haute pour créativité",
        )

    with col_lab_run:
        st.subheader("2. Entrées & Sorties")
        with st.expander("🛠️ Prompt Système", expanded=True):
            system_prompt = st.text_area("Instruction Système", value=default_sys, height=100)
        user_prompt = st.text_area("Prompt Utilisateur", value=default_user, height=150)

        if st.button("🚀 Lancer le Test (One-Shot)", use_container_width=True):
            if lab_model_tag:
                placeholder = st.empty()
                state = {"current_text": ""}

                async def on_token(token: str):
                    state["current_text"] += token
                    placeholder.markdown(state["current_text"] + "▌")

                callbacks = InferenceCallbacks(on_token=on_token)
                messages = [{"role": "user", "content": user_prompt}]

                with st.spinner("Inférence en cours..."):
                    result = asyncio.run(
                        InferenceService.run_inference(
                            model_tag=lab_model_tag,
                            messages=messages,
                            temperature=lab_temp,
                            system_prompt=system_prompt,
                            callbacks=callbacks,
                        )
                    )

                placeholder.empty()
                if result.thought:
                    # Correction SIM117 : Fusion des with
                    with placeholder.container(), st.expander("💭 Raisonnement", expanded=True):
                        st.markdown(result.thought)
                    st.markdown(result.clean_text)
                else:
                    placeholder.markdown(result.clean_text)

                st.session_state.lab_result = result.raw_text
                st.session_state.lab_metrics = result.metrics
            else:
                st.warning("Sélectionnez un modèle.")

    with col_lab_metrics:
        st.subheader("3. Audit")
        m = st.session_state.lab_metrics
        if m:
            info = get_model_info(lab_model_friendly)
            size_gb = info["size_gb"] if info else "?"

            st.markdown("#### ⚡ Performance")
            st.metric(
                "Débit (t/s)",
                f"{m.tokens_per_second}",
                delta="Fluide" if m.tokens_per_second > 20 else "Lent",
            )
            st.metric("Latence Totale", f"{m.total_duration_s} s")

            st.markdown("#### 💻 Technique")
            st.text(f"Load Time: {m.load_duration_s}s")
            st.text(f"In Tokens: {m.input_tokens}")
            st.text(f"Out Tokens: {m.output_tokens}")
            st.metric("RAM Modèle", size_gb)

            st.markdown("#### 🌱 Impact")
            st.progress(0.1, text="Calcul CodeCarbon...")
        else:
            st.info("Lancez un test pour voir les métriques.")

# ==========================================
# ONGLET 3 : ARENA
# ==========================================
with tab_arena:
    st.subheader("⚔️ Benchmark Comparatif")
    st.caption("Comparaison séquentielle et notation par un Juge IA.")

    col_arena_models, col_arena_judge, col_arena_prompt = st.columns([1, 1, 2])

    with col_arena_models:
        st.markdown("##### 1. Les Combattants")
        # On utilise les noms d'affichage (avec icônes) pour la sélection
        selected_arena_displays = st.multiselect(
            "Modèles à évaluer", options=sorted_display_names, help="Choisissez au moins 2 modèles."
        )
        # Conversion inverse pour récupérer les tags
        selected_arena_tags = [display_to_tag[d] for d in selected_arena_displays]
        selected_arena_friendlies = [tag_to_friendly[t] for t in selected_arena_tags]

    with col_arena_judge:
        st.markdown("##### 2. Le Juge")
        # Par défaut Mistral Large si dispo
        judge_options = sorted_display_names
        default_judge_idx = 0
        for i, name in enumerate(judge_options):
            if "mistral" in name.lower() and "large" in name.lower():
                default_judge_idx = i
                break

        judge_display = st.selectbox("Modèle Evaluateur", judge_options, index=default_judge_idx)
        judge_tag = display_to_tag.get(judge_display)

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
                    ram_check = ResourceManager.check_resources(tag)

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
                    grading_prompt = f"""Agis comme un juge impartial. Question: "{arena_prompt}". Réponse: "{result.clean_text}".
                    Donne UNIQUEMENT une note sur 100 (nombre entier) basée sur l'exactitude et la clarté."""

                    judge_resp = asyncio.run(
                        InferenceService.run_inference(
                            model_tag=judge_tag,
                            messages=[{"role": "user", "content": grading_prompt}],
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

# ==========================================
# ONGLET 4 : GESTIONNAIRE DE MODÈLES (UX V2)
# ==========================================
with tab_manager:
    st.markdown("### 📦 Bibliothèque de Modèles")

    # 1. Filtres avancés
    col_filter_lang, col_filter_cap, col_kpi = st.columns([2, 2, 1])

    with col_filter_lang:
        # Filtre Langue (AND Logic)
        all_langs = get_all_languages()
        selected_langs = st.multiselect(
            "🌍 Langues requises (ET)",
            all_langs,
            help="Affiche uniquement les modèles qui parlent TOUTES les langues sélectionnées.",
        )

    with col_filter_cap:
        # KPI simple
        if st.button("🔄 Rafraîchir les métadonnées"):
            st.rerun()

    with col_kpi:
        st.metric("Modèles affichés", len(installed_models_list))

    # 2. Préparation des données
    if installed_models_list:
        table_data = []

        for m in installed_models_list:
            # Récupération carte d'identité
            # NOTE: On utilise directement la fonction importée en haut du fichier,
            # sans la réimporter ici (Correction Ruff F811)
            card = get_model_card(m["model"], ollama_info=m)

            # Récupération infos fusionnées via ModelsDB
            info = get_model_info(card["name"]) or {}

            # Logique de Filtrage (Langues)
            model_langs = info.get("langs", [])
            # Correction Ruff SIM102 + SIM114 : Fusion des conditions
            if selected_langs and (
                not model_langs or not set(selected_langs).issubset(set(model_langs))
            ):
                continue

            # --- CORRECTION ARROW & CO2 ---

            # 1. Gestion CO2
            co2_raw = card["metrics"]["co2"]
            bench_stats = info.get("benchmark_stats", {})
            co2_kg = bench_stats.get("co2_emissions_kg")

            if co2_kg is not None and isinstance(co2_kg, int | float):  # Correction Ruff UP038
                co2_g = co2_kg * 1000
                # Correction Ruff SIM108 (Ternary)
                co2_display = "< 0.01 g" if co2_g < 0.01 else f"{co2_g:.2f} g"
            else:
                co2_display = "—"

            # 2. Gestion Sécurisée des Numériques (Contexte)
            raw_ctx = info.get("ctx", card["metrics"]["ctx"])
            ctx_val = None

            if isinstance(raw_ctx, int | float) or (isinstance(raw_ctx, str) and raw_ctx.isdigit()):
                ctx_val = int(raw_ctx)

            # 3. Construction de la ligne
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

        # 3. Affichage Tableau
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
                    "Statut": st.column_config.TextColumn(
                        "État",
                        width="small",
                        help="🛡️ Validé : Benchmark complet effectué\n🆕 Nouveau : Juste installé",
                    ),
                    "Nom": st.column_config.TextColumn(
                        "Modèle", width="medium", help="Nom technique ou commercial du modèle."
                    ),
                    "Éditeur": st.column_config.TextColumn(
                        "Éditeur",
                        width="small",
                        help="Créateur du modèle (Meta, Mistral, Google...)",
                    ),
                    "CO2 (Ref)": st.column_config.TextColumn(
                        "Impact CO2",
                        help="Estimation de l'empreinte carbone pour générer une réponse standard (~500 tokens). Exprimé en grammes (g).",
                        width="small",
                    ),
                    "Vitesse": st.column_config.TextColumn(
                        "Latence", help="Temps total (secondes) pour la génération de référence."
                    ),
                    "RAM": st.column_config.TextColumn(
                        "RAM Run", help="Pic de mémoire vive consommée durant l'inférence."
                    ),
                    "Contexte": st.column_config.NumberColumn(
                        "Ctx (tk)", help="Fenêtre de contexte maximale.", format="%d"
                    ),
                    "Params": st.column_config.TextColumn(
                        "Params Tot.", help="Nombre total de paramètres (Milliards)."
                    ),
                    "Actifs": st.column_config.TextColumn(
                        "Params Act.", help="Nombre de paramètres activés par token (MoE)."
                    ),
                    "Langues": st.column_config.ListColumn(
                        "Langues",
                        help="Langues officiellement supportées ou vérifiées.",
                        width="medium",
                    ),
                    "Description": st.column_config.TextColumn(
                        "Description",
                        width="large",
                        help="Détails sur les capacités et cas d'usage.",
                    ),
                    "Link": st.column_config.LinkColumn(
                        "Doc", display_text="Fiche", help="Lien vers la documentation officielle."
                    ),
                    "Taille": st.column_config.TextColumn(
                        "Disk", help="Espace disque occupé par le fichier modèle."
                    ),
                },
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Aucun modèle ne correspond à vos critères de filtrage.")

    else:
        st.warning("Aucun modèle détecté.")

    # --- SECTION TÉLÉCHARGEMENT ---
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
        # Correction SIM102 : Fusion des conditions
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
