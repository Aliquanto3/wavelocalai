"""
Onglet « Discussion » de l'Assistant documentaire.

- Sources dans un expander replié sous chaque réponse.
- Métadonnées (badge Local ou Cloud, modèle, durée, mémoire, CO₂) sous chaque réponse.
- Métadonnées conservées dans l'historique.
"""

import asyncio
import time

import streamlit as st

from src.app.formatting import (
    format_co2,
    format_duration,
    format_gb,
    format_number,
    mg_to_grams,
    pluralize,
)
from src.app.states import (
    LOADING_HINT,
    LOADING_LABEL,
    generation_failure_advice,
    render_error,
    render_no_models,
)
from src.app.ui import ModelMenu, badge_markdown, is_cloud_model, render_badge

# --- SSOT carbone ---
from src.core.green_monitor import CarbonCalculator
from src.core.llm_provider import LLMProvider
from src.core.metrics import InferenceMetrics
from src.core.models_db import extract_thought, get_friendly_name_from_tag, get_model_info
from src.core.utils import extract_params_billions as _extract_params_billions


def render_rag_chat_tab(
    rag_engine,
    display_to_tag,
    tag_to_friendly,
    sorted_display_names,
    k_retrieval,
    menu: ModelMenu | None = None,
):

    if not sorted_display_names:
        render_no_models()
        return

    # 1. SÉLECTEUR DE MODÈLE (Haut de page, discret)
    c_sel, c_space = st.columns([1, 2])
    with c_sel:
        selected_display = st.selectbox(
            "Modèle actif",
            sorted_display_names,
            key="rag_chat_select",
            label_visibility="collapsed",
        )
        selected_tag = display_to_tag.get(selected_display)
        friendly_name = tag_to_friendly.get(selected_tag)
        # Badge du modèle choisi, dérivé de son fournisseur réel.
        selected_is_cloud = is_cloud_model(selected_tag, menu)
        render_badge(selected_is_cloud)

    st.divider()

    # 2. HISTORIQUE DE CONVERSATION
    # On utilise enumerate pour garantir des clés uniques aux widgets (boutons)
    for i, msg in enumerate(st.session_state.rag_messages):
        with st.chat_message(msg["role"]):
            # A. Affichage Pensée (CoT)
            if msg.get("thought"):
                with st.expander("Raisonnement", expanded=False):
                    st.markdown(msg["thought"])

            # B. Contenu Principal
            st.markdown(msg["content"])

            # C. Zone Métadonnées (Uniquement pour l'assistant)
            if msg["role"] == "assistant":
                # Ligne de séparation discrète
                st.divider()

                # C1. Sources (Expander)
                if msg.get("sources"):
                    sources_label = pluralize(
                        len(msg["sources"]), "source utilisée", "sources utilisées"
                    )
                    with st.expander(sources_label, expanded=False):
                        for idx, doc in enumerate(msg["sources"]):
                            # Score brut du reranker (logit, parfois négatif) : ni une
                            # probabilité ni une pertinence ; « — » sans reranker.
                            score = doc.metadata.get("rerank_score")
                            src_name = doc.metadata.get("source", "Document inconnu")
                            st.caption(
                                f"**Source {idx + 1}** : {src_name} "
                                f"(score de reclassement : {format_number(score, 2)})"
                            )
                            st.text(doc.page_content[:400] + "…")

                # C2. Métriques & Actions (Badges)
                c_meta1, c_meta2 = st.columns([3, 1])
                with c_meta1:
                    # Badge Local ou Cloud et nom du modèle qui a répondu, puis mesures.
                    badges = []
                    if "is_cloud" in msg:
                        badges.append(badge_markdown(msg["is_cloud"]))
                    if msg.get("model_name"):
                        badges.append(msg["model_name"])
                    if "metrics" in msg:
                        m = msg["metrics"]
                        badges.append(format_duration(m.get("total_time", 0)))
                        if "ram_gb" in m:
                            badges.append(format_gb(m["ram_gb"]))
                        if "carbon_mg" in m:
                            badges.append(format_co2(mg_to_grams(m["carbon_mg"])))

                    if badges:
                        st.caption(" · ".join(badges))

                with c_meta2:
                    # Bouton de téléchargement avec CLÉ UNIQUE
                    st.download_button(
                        "Télécharger",
                        msg["content"],
                        file_name=f"rag_response_{i}.md",
                        key=f"dl_rag_{i}",
                        icon=":material/download:",
                        help="Télécharger la réponse en Markdown",
                    )

    # 3. INPUT UTILISATEUR
    if prompt := st.chat_input("Posez une question à vos documents"):
        # Ajout message user
        st.session_state.rag_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 4. RÉPONSE ASSISTANT
        with st.chat_message("assistant"):
            resp_container = st.empty()
            # Premier chargement, testé avant la recherche : HyDE et Self-RAG appellent déjà
            # le modèle pendant la recherche.
            loading = LLMProvider.is_model_loaded(selected_tag) is False
            status_box = st.status(
                LOADING_LABEL if loading else "Recherche dans vos documents…", expanded=True
            )
            if loading:
                status_box.write(LOADING_HINT)

            t_start_pipeline = time.perf_counter()

            # A. Pipeline RAG (Retrieval) : un échec de recherche (base, embeddings) n'est
            # pas un échec du modèle.
            try:
                # Feedback dynamique sur la stratégie
                strat_name = rag_engine.strategy.__class__.__name__
                if "HyDE" in strat_name:
                    status_box.write("Rédaction d'une réponse hypothétique pour la recherche…")
                elif "SelfRAG" in strat_name:
                    status_box.write("Vérification de la pertinence des extraits…")
                else:
                    status_box.write("Recherche des extraits les plus proches…")

                t_ret = time.perf_counter()
                retrieved = rag_engine.search(prompt, k=k_retrieval)
                d_ret = time.perf_counter() - t_ret
                found = pluralize(len(retrieved), "extrait trouvé", "extraits trouvés")
                status_box.write(f"{found} ({format_duration(d_ret)})")
            except Exception as e:
                status_box.update(label="Recherche impossible", state="error", expanded=False)
                render_error(
                    "La recherche dans vos documents a échoué. Réessayez ; si l'erreur persiste, "
                    "choisissez « Recherche directe » dans les réglages ou réimportez vos "
                    "documents.",
                    f"{type(e).__name__}: {e}",
                )
                return

            try:
                # B. Préparation Prompt
                context_text = "\n\n".join([doc.page_content for doc in retrieved])
                sys_prompt = (
                    f"Tu es un assistant expert. Utilise ce contexte pour répondre:\n{context_text}"
                )
                payload = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt},
                ]

                # C. Génération (Streaming)
                status_box.write(f"Génération avec {friendly_name}…")

                async def run_gen():
                    full_txt = ""
                    captured_metrics = None
                    stream = LLMProvider.chat_stream(selected_tag, payload, temperature=0.1)
                    async for chunk in stream:
                        if isinstance(chunk, str):
                            if not full_txt:
                                status_box.update(label="Génération en cours…")
                            full_txt += chunk
                            resp_container.markdown(full_txt + "▌")
                        elif isinstance(chunk, InferenceMetrics):
                            captured_metrics = chunk
                    return full_txt, captured_metrics

                full_resp, metrics_obj = asyncio.run(run_gen())

                # Fin du process
                total_duration = time.perf_counter() - t_start_pipeline
                status_box.update(label="Terminé", state="complete", expanded=False)

                # D. Traitement Post-Génération
                thought, clean = extract_thought(full_resp)

                # Affichage Final
                resp_container.empty()
                if thought:
                    with st.expander("Raisonnement", expanded=True):
                        st.markdown(thought)
                st.markdown(clean)

                # E. Calculs carbone (SSOT)
                carbon_mg = 0.0
                ram_gb = 0.0
                if metrics_obj:
                    # Nom du catalogue (pas le nom affiché, qui peut porter le tag).
                    info = get_model_info(get_friendly_name_from_tag(selected_tag)) or {}

                    # 1. RAM
                    ram_gb = metrics_obj.model_size_gb or 0.0

                    # 2. Carbone
                    if info.get("type") == "api" and metrics_obj.output_tokens > 0:
                        raw_params = info.get("params_act") or info.get("params_tot", "0")
                        active_params = _extract_params_billions(raw_params)
                        carbon_mg = (
                            CarbonCalculator.compute_mistral_impact_g(
                                active_params, metrics_obj.output_tokens
                            )
                            * 1000
                        )
                    else:
                        carbon_mg = (
                            CarbonCalculator.compute_local_theoretical_g(metrics_obj.output_tokens)
                            * 1000
                        )

                # F. Sauvegarde Persistante
                msg_data = {
                    "role": "assistant",
                    "content": clean,
                    "thought": thought,
                    "sources": retrieved,  # On garde les objets Document
                    # Modèle qui a répondu et son fournisseur réel (badge de l'historique).
                    "model_tag": selected_tag,
                    "model_name": friendly_name,
                    "is_cloud": selected_is_cloud,
                    "metrics": {
                        "total_time": total_duration,
                        "ram_gb": ram_gb,
                        "carbon_mg": carbon_mg,
                    },
                }
                st.session_state.rag_messages.append(msg_data)

                # Rerun pour afficher proprement les badges (optionnel, mais propre)
                st.rerun()

            except Exception as e:
                # Erreur du fournisseur (Ollama arrêté, modèle absent…) : jamais affichée comme
                # une réponse ; la question reste dans l'historique.
                status_box.update(label="Erreur", state="error", expanded=False)
                resp_container.empty()
                render_error(
                    "La réponse n'a pas pu être générée. "
                    + generation_failure_advice(selected_tag),
                    f"{type(e).__name__}: {e}",
                )
