import streamlit as st
import pandas as pd
import time
import asyncio
from src.core.llm_provider import LLMProvider
from src.core.metrics import InferenceMetrics
from src.core.models_db import MODELS_DB, get_model_info, get_all_friendly_names, get_all_languages, get_friendly_name_from_tag, extract_thought

st.set_page_config(page_title="Inférence & Arena", page_icon="🧠", layout="wide")

# --- CSS Custom pour les métriques ---
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 24px; }
    .stTextArea textarea { font-family: monospace; }
</style>
""", unsafe_allow_html=True)

st.title("🧠 Inférence & Model Arena")
st.caption("Benchmark technique et fonctionnel des SLM.")

# --- DATA: BIBLIOTHÈQUE DE CAS D'USAGE (PROMPTS) ---
USE_CASES = {
    "🇬🇧 Traduction Technique": {
        "system": "Tu es un expert en traduction technique. Traduis le texte suivant en Anglais, Espagnol et Allemand. Sois précis sur la terminologie informatique. Réponds au format JSON : {\"en\": \"...\", \"es\": \"...\", \"de\": \"...\"}.",
        "user": "L'architecture 'Local First' permet de réduire la latence réseau et d'améliorer la confidentialité des données en traitant les inférences directement sur le CPU de l'utilisateur, sans appel API vers le cloud."
    },
    "📄 Extraction Structurée (JSON)": {
        "system": "Tu es un extracteur de données strict. Extrais les entités du texte (Date, Montant, Vendeur, Articles). Réponds UNIQUEMENT avec un JSON valide. Pas de texte avant ni après.",
        "user": "FACTURE N° 2024-001\nDate : 12 décembre 2024\nVendeur : Wavestone Tech\n\nArticles :\n- 1x Audit Green IT (500€)\n- 3x Licences Copilot (90€)\n\nTotal TTC : 590€"
    },
    "💻 Assistant Coding (Python)": {
        "system": "Tu es un Tech Lead Python expérimenté. Génère du code propre, typé (Type Hints) et documenté (Docstrings). Inclus une gestion d'erreur robuste.",
        "user": "Écris une fonction Python asynchrone qui interroge une API REST avec la librairie 'httpx', gère les retries en cas d'erreur 500, et retourne le résultat en dictionnaire."
    },
    "🧮 Raisonnement (Chain of Thought)": {
        "system": "Tu es un expert en logique. Pour répondre, tu dois IMPÉRATIVEMENT utiliser la méthode 'Chain of Thought' : explique ton raisonnement étape par étape avant de donner la réponse finale.",
        "user": "J'ai 3 pommes. Hier j'en ai mangé une. Aujourd'hui j'en achète deux autres, mais j'en fais tomber une dans la boue que je jette. Combien de pommes puis-je manger maintenant ?"
    },
    "📝 Résumé Exécutif": {
        "system": "Tu es un assistant de direction. Fais un résumé concis (bullet points) du texte fourni, en te concentrant sur les décisions clés et les actions à entreprendre.",
        "user": "Compte rendu de réunion - Projet Alpha.\nLa réunion a débuté à 10h. L'équipe a convenu que le budget initial était insuffisant. Marc doit revoir le fichier Excel d'ici mardi. Sophie a soulevé un risque de sécurité sur l'API, il faut auditer le module d'auth. La deadline du projet est repoussée de 2 semaines pour permettre ces ajustements. Le client a validé le nouveau design."
    }
}

# --- SESSION STATE ---
if "messages" not in st.session_state: st.session_state.messages = []
if "lab_result" not in st.session_state: st.session_state.lab_result = None
if "lab_metrics" not in st.session_state: st.session_state.lab_metrics = None

# --- LAYOUT PRINCIPAL ---
tab_chat, tab_lab, tab_manager = st.tabs(["💬 Chat Libre (Historique)", "🧪 Labo de Tests (One-Shot)", "⚙️ Gestion des Modèles"])

# ==========================================
# ONGLET 1 : CHAT LIBRE (Stateful)
# ==========================================
with tab_chat:
    col_chat_params, col_chat_main = st.columns([1, 3])
    
    with col_chat_params:
        st.subheader("Paramètres")
        # Sélection Modèle
        installed = LLMProvider.list_models()
        model_map = {get_friendly_name_from_tag(m['model']): m['model'] for m in installed} if installed else {}
        selected_friendly = st.selectbox("Modèle actif", sorted(model_map.keys()), key="chat_model_select")
        selected_tag = model_map.get(selected_friendly)
        
        temp = st.slider("Température", 0.0, 1.0, 0.7, key="chat_temp")
        
        st.info("Ce mode conserve l'historique de la conversation.")
        if st.button("🗑️ Nouvelle conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    with col_chat_main:
        # Affichage Historique (Mise à jour pour supporter le champ 'thought')
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                # Si le message contient une pensée enregistrée, on l'affiche d'abord
                if "thought" in msg and msg["thought"]:
                    with st.expander("💭 Raisonnement (CoT)", expanded=False):
                        st.markdown(msg["thought"])
                st.markdown(msg["content"])

        # Input
        if prompt := st.chat_input("Discutez avec le modèle..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                msg_container = st.empty()
                
                # --- DÉBUT REMPLACEMENT ---
                if selected_tag:
                    # 1. Définition de la logique asynchrone qui RETOURNE le texte final
                    async def run_chat():
                        current_text = "" # Variable locale à la fonction async
                        
                        # Appel du générateur async
                        stream = LLMProvider.chat_stream(
                            selected_tag, 
                            st.session_state.messages, 
                            temperature=temp
                        )
                        
                        async for item in stream:
                            if isinstance(item, str):
                                current_text += item
                                msg_container.markdown(current_text + "▌")
                            elif isinstance(item, InferenceMetrics):
                                st.session_state.last_metrics = item
                        
                        return current_text

                    # 2. Exécution et récupération du résultat
                    import asyncio
                    full_text = asyncio.run(run_chat())
                    # --- FIN REMPLACEMENT ---

                    # 3. Nettoyage et Extraction de la Pensée
                    msg_container.empty()
                    thought, clean_text = extract_thought(full_text)
                    
                    # 4. Affichage structuré
                    if thought:
                        with msg_container.container():
                            with st.expander("💭 Raisonnement (Chain of Thought)", expanded=True):
                                st.markdown(thought)
                            st.markdown(clean_text)
                    else:
                        msg_container.markdown(full_text)
                        clean_text = full_text # Fallback

                    # 5. Sauvegarde Historique
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": clean_text,
                        "thought": thought
                    })
                    
                    # Force le rafraîchissement pour afficher les métriques
                    st.rerun()
                else:
                    st.error("Sélectionnez un modèle.")

# ==========================================
# ONGLET 2 : LABO DE TESTS (Stateless)
# ==========================================
with tab_lab:
    col_lab_config, col_lab_run, col_lab_metrics = st.columns([1, 2, 1])

    # --- A. CONFIGURATION ---
    with col_lab_config:
        st.subheader("1. Scénario")
        
        # Choix du modèle (Indépendant du Chat)
        lab_model_friendly = st.selectbox("Modèle de Test", sorted(model_map.keys()), key="lab_model_select")
        lab_model_tag = model_map.get(lab_model_friendly)
        
        # Choix du Use Case
        selected_use_case = st.selectbox("Cas d'Usage", list(USE_CASES.keys()))
        
        # Récupération des defaults
        default_sys = USE_CASES[selected_use_case]["system"]
        default_user = USE_CASES[selected_use_case]["user"]

        # Paramètres d'exécution
        lab_temp = st.slider("Température", 0.0, 1.0, 0.2, key="lab_temp", help="Basse pour extraction/code, Haute pour créativité")

    # --- B. EXÉCUTION ---
    with col_lab_run:
        st.subheader("2. Entrées & Sorties")
        
        # Prompt Système Éditable
        with st.expander("🛠️ Prompt Système (Configuration du comportement)", expanded=True):
            system_prompt = st.text_area("Instruction Système", value=default_sys, height=100)
            
        # Prompt Utilisateur Éditable (One Shot)
        user_prompt = st.text_area("Prompt Utilisateur (Entrée)", value=default_user, height=150)
        
        if st.button("🚀 Lancer le Test (One-Shot)", use_container_width=True):
            if lab_model_tag:
                with st.spinner("Inférence en cours..."):
                    # On construit un historique éphémère (Stateless)
                    messages = [{"role": "user", "content": user_prompt}]
                    
                    # --- DÉBUT MODIFICATION ASYNC (Labo de Tests) ---
                    placeholder = st.empty()
                    
                    async def run_lab_test():
                        current_text = ""
                        current_metrics = None
                        
                        # Appel Backend Asynchrone
                        stream = LLMProvider.chat_stream(
                            model_name=lab_model_tag,
                            messages=messages,
                            temperature=lab_temp,
                            system_prompt=system_prompt
                        )
                        
                        # Consommation du stream
                        async for item in stream:
                            if isinstance(item, str):
                                current_text += item
                                # Mise à jour UI en temps réel
                                placeholder.markdown(current_text + "▌")
                            elif isinstance(item, InferenceMetrics):
                                current_metrics = item
                        
                        return current_text, current_metrics

                    # Exécution via la boucle d'événements
                    import asyncio
                    full_resp, metrics = asyncio.run(run_lab_test())
                    # --- FIN MODIFICATION ASYNC ---
                    
                    # 2. Nettoyage et Extraction
                    placeholder.empty()
                    thought, clean_text = extract_thought(full_resp)
                    
                    # 3. Affichage structuré final
                    if thought:
                        with placeholder.container():
                            with st.expander("💭 Raisonnement", expanded=True):
                                st.markdown(thought)
                            st.markdown(clean_text)
                    else:
                        placeholder.markdown(full_resp)
                    
                    # Sauvegarde dans le Session State pour les métriques à droite
                    st.session_state.lab_result = full_resp 
                    st.session_state.lab_metrics = metrics
            else:
                st.warning("Aucun modèle sélectionné.")

    # --- C. MÉTRIQUES ---
    with col_lab_metrics:
        st.subheader("3. Audit")
        
        m = st.session_state.lab_metrics
        if m:
            # Récupération taille modèle
            info = get_model_info(lab_model_friendly)
            size_gb = info['size_gb'] if info else "?"

            # Vitesse
            st.markdown("#### ⚡ Performance")
            st.metric("Débit (t/s)", f"{m.tokens_per_second}", delta="Fluide" if m.tokens_per_second > 20 else "Lent")
            st.metric("Latence Totale", f"{m.total_duration_s} s")
            
            # Technique
            st.markdown("#### 💻 Technique")
            st.text(f"Load Time: {m.load_duration_s}s")
            st.text(f"In Tokens: {m.input_tokens}")
            st.text(f"Out Tokens: {m.output_tokens}")
            st.metric("RAM Modèle", size_gb)
            
            # Green IT
            st.markdown("#### 🌱 Impact")
            st.caption("Estimation énergétique")
            st.progress(0.1, text="Calcul CodeCarbon...") # Placeholder
        else:
            st.info("Lancez un test pour voir les métriques.")
            st.markdown("""
            > **Note :** Les tests 'One-Shot' ne gardent pas de mémoire. Chaque clic sur 'Lancer' repart d'une feuille blanche.
            """)

# ==========================================
# ONGLET 3 : GESTIONNAIRE DE MODÈLES (MANAGER)
# ==========================================
with tab_manager:
    st.markdown("### 📦 Modèles Installés & Documentation")
    
    col_refresh, col_filter = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Rafraîchir la liste"):
            st.rerun()
            
    # Filtres
    with col_filter:
        all_langs = get_all_languages()
        selected_langs = st.multiselect("🌍 Filtrer par langue supportée (ET logique)", all_langs)

    installed_models = LLMProvider.list_models()
    
    if installed_models:
        table_data = []
        for m in installed_models:
            tag = m['model']
            friendly_name = get_friendly_name_from_tag(tag)
            
            info = get_model_info(friendly_name)
            
            # --- RÉCUPÉRATION DES STATS DE BENCHMARK (Même si 'info' est None) ---
            benchmark_stats = info.get("benchmark_stats", {}) if info else {}
            
            row = {
                "Nom": friendly_name,
                "Éditeur": "Inconnu",
                "Taille": f"{round(m.get('size', 0) / (1024**3), 2)} GB",
                
                # --- NOUVELLES COLONNES DE BENCHMARK ---
                "RAM (GB)": benchmark_stats.get('ram_usage_gb', None),
                "Vitesse (s)": benchmark_stats.get('speed_s', None),
                "CO2 (kg)": benchmark_stats.get('co2_emissions_kg', None),
                "Max Contexte (tk)": benchmark_stats.get('tested_ctx', info.get('ctx', 'N/A') if info else 'N/A'),
                
                "Total Params": "N/A", # Remplacement de 'Params Tot.'
                "Actifs": "N/A",       # Remplacement de 'Params Act.'
                "Contexte": "N/A",
                "Langues": [],
                "Description": "Modèle téléchargé manuellement.",
                "Documentation": None
            }
            
            if info:
                # Ici on ne garde que la logique de filtrage et de remplissage de base
                if selected_langs:
                    model_langs = set(info.get("langs", []))
                    if not set(selected_langs).issubset(model_langs):
                        continue

                # Remplissage des champs de documentation
                row["Éditeur"] = info.get("editor", "N/A")
                row["Total Params"] = info.get("params_tot", "N/A") # Clé mise à jour
                row["Actifs"] = info.get("params_act", "N/A")       # Clé mise à jour
                row["Langues"] = info.get("langs", [])
                row["Description"] = info.get("desc", "")
                row["Documentation"] = info.get("link", None)
            
            elif selected_langs:
                continue

            table_data.append(row)

        if table_data:
            df = pd.DataFrame(table_data)
            # Définition de l'ordre des colonnes (les métriques d'abord)
            column_order = [
                "Nom", "Éditeur", "Taille", 
                "RAM (GB)", "Max Contexte (tk)", 
                "Vitesse (s)", "CO2 (kg)", 
                "Total Params", "Actifs", 
                "Langues", "Description", "Documentation"
            ]
            
            st.dataframe(
                df,
                use_container_width=True,
                column_order=column_order,
                column_config={
                    # --- NOUVELLES CONFIGURATIONS DE BENCHMARK ---
                    "RAM (GB)": st.column_config.NumberColumn(
                        "RAM Modèle (GB)",
                        help="RAM utilisée au Max Valid Context (GB).",
                        format="%.2f", 
                        width="small" # Réduire la largeur pour gagner de la place
                    ),
                    "Max Contexte (tk)": st.column_config.NumberColumn(
                        "Max Contexte (tk)",
                        help="Taille maximale du contexte validé (tokens).",
                        format="%d",
                        width="small"
                    ),
                    "Vitesse (s)": st.column_config.NumberColumn(
                        "Vitesse (s)",
                        help="Durée totale du test au Max Valid Context (s). Plus bas = Mieux.",
                        format="%.2f",
                        width="small"
                    ),
                    "CO2 (kg)": st.column_config.NumberColumn(
                        "CO2 (kg)",
                        help="Émissions cumulées pour l'audit complet du contexte (kg CO2).",
                        format="%.3g", 
                        width="small"
                    ),
                    
                    # --- CONFIGURATIONS DESCRIPTIVES ---
                    "Total Params": st.column_config.TextColumn("Total Params", width="small"),
                    "Actifs": st.column_config.TextColumn("Actifs", width="small"),
                    "Langues": st.column_config.ListColumn("Langues", width="medium"),
                    "Description": st.column_config.TextColumn("Description", width="large"),
                    "Documentation": st.column_config.LinkColumn("Lien Doc", display_text="Voir Fiche"),
                    "Taille": st.column_config.TextColumn("Disk (GB)", help="Espace disque occupé", width="small")
                },
                hide_index=True
            )
        else:
            st.warning("Aucun modèle ne correspond aux filtres.")
    else:
        st.info("Aucun modèle local trouvé.")
        
    st.markdown("---")
    st.markdown("### ⬇️ Télécharger un nouveau modèle")
    
    col_select, col_info = st.columns([1, 1])
    with col_select:
        suggestions = sorted(get_all_friendly_names(local_only=True))
        options = ["✨ Sélectionner une suggestion..."] + suggestions + ["🛠️ Autre (Saisie Manuelle)"]
        choice = st.selectbox("Catalogue Wavestone", options)
        
        target_model_tag = ""
        if choice == "🛠️ Autre (Saisie Manuelle)":
            target_model_tag = st.text_input("Tag Ollama", "")
            st.caption("[Ollama Library](https://ollama.com/library)")
        elif choice != "✨ Sélectionner une suggestion...":
            info = get_model_info(choice)
            if info: target_model_tag = info["ollama_tag"]
            
    with col_info:
        if choice not in ["✨ Sélectionner une suggestion...", "🛠️ Autre (Saisie Manuelle)"]:
            info = get_model_info(choice)
            if info:
                st.info(f"**{info['desc']}**")
                st.markdown(f"**Contexte:** `{info['ctx']}` | **Params:** `{info['params_tot']}`")
                
    st.write("")
    if st.button("⬇️ Lancer le téléchargement"):
        if target_model_tag:
            status = st.status(f"Téléchargement de {target_model_tag}...", expanded=True)
            pbar = status.progress(0, text="Connexion...")
            try:
                for progress in LLMProvider.pull_model(target_model_tag):
                    if progress.get('total'):
                        p = progress['completed'] / progress['total']
                        pbar.progress(p, text=f"{progress['status']} - {int(p*100)}%")
                    else:
                        pbar.progress(0.5, text=progress['status'])
                pbar.progress(1.0, text="Terminé !")
                status.update(label="✅ Succès !", state="complete", expanded=False)
                time.sleep(1)
                st.rerun()
            except Exception as e:
                status.update(label="❌ Erreur", state="error")
                st.error(str(e))