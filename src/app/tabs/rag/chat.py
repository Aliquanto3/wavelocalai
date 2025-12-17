"""
RAG Chat Tab - Sprint 2 (UX & GreenOps Inline)
Changements :
- Suppression de la colonne latérale de debug.
- Intégration des sources dans un expander sous la réponse.
- Affichage des métriques (Temps, CO2, RAM) en "Badges" sous le message.
- Persistance complète des métadonnées dans l'historique.
"""

import asyncio
import time

import streamlit as st

# --- SSOT GreenOps ---
from src.core.green_monitor import CarbonCalculator
from src.core.llm_provider import LLMProvider
from src.core.metrics import InferenceMetrics
from src.core.models_db import extract_thought, get_model_info
from src.core.utils import extract_params_billions as _extract_params_billions


def render_rag_chat_tab(
    rag_engine, display_to_tag, tag_to_friendly, sorted_display_names, k_retrieval
):

    # 1. SÉLECTEUR DE MODÈLE (Haut de page, discret)
    c_sel, c_space = st.columns([1, 2])
    with c_sel:
        selected_display = st.selectbox(
            "🤖 Modèle Actif",
            sorted_display_names,
            key="rag_chat_select",
            label_visibility="collapsed",
        )
        selected_tag = display_to_tag.get(selected_display)
        friendly_name = tag_to_friendly.get(selected_tag)

    st.divider()

    # 2. HISTORIQUE DE CONVERSATION
    # On utilise enumerate pour garantir des clés uniques aux widgets (boutons)
    for i, msg in enumerate(st.session_state.rag_messages):
        with st.chat_message(msg["role"]):
            # A. Affichage Pensée (CoT)
            if msg.get("thought"):
                with st.expander("💭 Raisonnement", expanded=False):
                    st.markdown(msg["thought"])

            # B. Contenu Principal
            st.markdown(msg["content"])

            # C. Zone Métadonnées (Uniquement pour l'assistant)
            if msg["role"] == "assistant":
                # Ligne de séparation discrète
                st.markdown("---")

                # C1. Sources (Expander)
                if msg.get("sources"):
                    with st.expander(f"📚 {len(msg['sources'])} Sources utilisées", expanded=False):
                        for idx, doc in enumerate(msg["sources"]):
                            score = doc.metadata.get("score", 0)
                            src_name = doc.metadata.get("source", "Doc inconnu")
                            st.caption(f"**Source {idx+1}** : {src_name} (Pertinence: {score:.2f})")
                            st.text(doc.page_content[:400] + "...")

                # C2. Métriques & Actions (Badges)
                c_meta1, c_meta2 = st.columns([3, 1])
                with c_meta1:
                    # Construction des badges
                    badges = []
                    if "metrics" in msg:
                        m = msg["metrics"]
                        badges.append(f"⏱️ {m.get('total_time', 0):.1f}s")
                        if "ram_gb" in m:
                            badges.append(f"💾 {m['ram_gb']:.1f} GB")
                        if "carbon_mg" in m:
                            badges.append(f"🌱 {m['carbon_mg']:.2f} mgCO₂")

                    if badges:
                        st.caption(" | ".join(badges))

                with c_meta2:
                    # Bouton de téléchargement avec CLÉ UNIQUE
                    st.download_button(
                        "📥 MD",
                        msg["content"],
                        file_name=f"rag_response_{i}.md",
                        key=f"dl_rag_{i}",
                        help="Télécharger la réponse",
                    )

    # 3. INPUT UTILISATEUR
    if prompt := st.chat_input("Posez une question à vos documents..."):
        # Ajout message user
        st.session_state.rag_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 4. RÉPONSE ASSISTANT
        with st.chat_message("assistant"):
            resp_container = st.empty()
            status_box = st.status("🚀 Recherche & Réflexion...", expanded=True)

            t_start_pipeline = time.perf_counter()

            try:
                # A. Pipeline RAG (Retrieval)
                # Feedback dynamique sur la stratégie
                strat_name = rag_engine.strategy.__class__.__name__
                if "HyDE" in strat_name:
                    status_box.write("🔮 HyDE : Génération hypothétique...")
                elif "SelfRAG" in strat_name:
                    status_box.write("⚖️ Self-RAG : Analyse critique...")
                else:
                    status_box.write("🔍 Naive RAG : Recherche vectorielle...")

                t_ret = time.perf_counter()
                retrieved = rag_engine.search(prompt, k=k_retrieval)
                d_ret = time.perf_counter() - t_ret
                status_box.write(f"✅ {len(retrieved)} documents trouvés ({d_ret:.2f}s)")

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
                status_box.write(f"🧠 Génération avec {friendly_name}...")

                async def run_gen():
                    full_txt = ""
                    captured_metrics = None
                    stream = LLMProvider.chat_stream(selected_tag, payload, temperature=0.1)
                    async for chunk in stream:
                        if isinstance(chunk, str):
                            full_txt += chunk
                            resp_container.markdown(full_txt + "▌")
                        elif isinstance(chunk, InferenceMetrics):
                            captured_metrics = chunk
                    return full_txt, captured_metrics

                full_resp, metrics_obj = asyncio.run(run_gen())

                # Fin du process
                total_duration = time.perf_counter() - t_start_pipeline
                status_box.update(label="✅ Terminé", state="complete", expanded=False)

                # D. Traitement Post-Génération
                thought, clean = extract_thought(full_resp)

                # Affichage Final
                resp_container.empty()
                if thought:
                    with st.expander("💭 CoT", expanded=True):
                        st.markdown(thought)
                st.markdown(clean)

                # E. Calculs GreenOps (SSOT)
                carbon_mg = 0.0
                ram_gb = 0.0
                if metrics_obj:
                    info = get_model_info(friendly_name) or {}

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
                status_box.update(label="❌ Erreur", state="error")
                st.error(f"Erreur Pipeline : {e}")
