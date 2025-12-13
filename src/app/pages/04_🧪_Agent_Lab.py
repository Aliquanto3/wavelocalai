import streamlit as st
import time
from src.core.llm_provider import LLMProvider
from src.core.agent_engine import AgentEngine
from src.core.models_db import MODELS_DB, get_friendly_name_from_tag, get_model_info, extract_thought

st.set_page_config(page_title="Agent Lab", page_icon="🤖", layout="wide")

st.title("🤖 Agent Lab (LangGraph)")
st.caption("Observez une IA utiliser des outils pour résoudre des tâches complexes.")

# --- SESSION ---
if "agent_messages" not in st.session_state: st.session_state.agent_messages = []

# --- SIDEBAR ---
with st.sidebar:
    st.header("Configuration de l'Agent")
    
    # 1. LISTING ET TRI INTELLIGENT
    installed = LLMProvider.list_models()
    
    verified_models = []
    experimental_models = []
    
    for m in installed:
        friendly = get_friendly_name_from_tag(m['model'])
        info = get_model_info(friendly)
        
        if info:
            # Cas A : Modèle connu dans la DB
            if "tools" in info.get("capabilities", []):
                verified_models.append(friendly)
            # Sinon (connu mais pas compatible), on l'ignore pour éviter le crash sûr
        else:
            # Cas B : Modèle manuel (Inconnu de la DB)
            # On l'accepte mais on le marque comme expérimental
            experimental_models.append(friendly)
    
    # Fusion des listes
    sorted_verified = sorted(verified_models)
    sorted_experimental = sorted(experimental_models)
    
    # On prépare les options avec des séparateurs visuels si besoin
    # Mais le plus simple est une liste unique avec des préfixes ou juste mélangée
    all_choices = sorted_verified + sorted_experimental
    
    if not all_choices:
        st.error("Aucun modèle trouvé.")
        st.stop()
        
    # Logique d'affichage dans le selectbox
    def format_func(option):
        if option in sorted_experimental:
            return f"⚠️ {option} (Non vérifié)"
        return f"✅ {option}"

    selected_friendly = st.selectbox(
        "Cerveau (LLM)", 
        all_choices, 
        format_func=format_func, # Affiche les emojis
        help="Les modèles ✅ sont validés pour les outils. Les modèles ⚠️ peuvent échouer (Erreur 400)."
    )
    
    # Récupération du tag technique
    info = get_model_info(selected_friendly)
    if info:
        selected_tag = info['ollama_tag']
    else:
        # Pour les modèles expérimentaux, le friendly name EST souvent le tag ou proche
        # On doit retrouver le tag original depuis la liste 'installed'
        # C'est un peu trickier car get_friendly_name_from_tag a transformé le nom
        # On refait une passe inverse rapide :
        for m in installed:
            if get_friendly_name_from_tag(m['model']) == selected_friendly:
                selected_tag = m['model']
                break

    st.markdown("---")
    st.info(
        """
        **Outils disponibles :**
        1. 🕒 **Time :** Heure actuelle système.
        2. 🧮 **Calculator :** Calculs mathématiques.
        3. 🏢 **Wavestone Search :** Base de connaissances interne.
        """
    )
    
    if st.button("🗑️ Reset Mémoire"):
        st.session_state.agent_messages = []
        st.rerun()

# --- CHAT INTERFACE ---
for msg in st.session_state.agent_messages:
    with st.chat_message(msg["role"]):
        # Affichage logs outils
        if msg.get("type") == "tool_log":
            with st.status(f"🛠️ Utilisation : {msg['tool']}", state="complete"):
                st.write(f"**Args :** `{msg['args']}`")
                st.write(f"**Résultat :** {msg['content']}")
        
        # Affichage pensée cachée (si sauvegardée)
        elif msg.get("thought"):
            with st.expander("💭 Raisonnement du modèle (Interne)", expanded=False):
                st.markdown(msg["thought"])
            st.markdown(msg["content"])
            
        else:
            st.markdown(msg["content"])

if prompt := st.chat_input("Ex: 'Quelle heure est-il et combien font 45 fois 12 ?'"):
    if not selected_tag:
        st.error("Veuillez sélectionner un modèle compatible.")
        st.stop()

    # 1. User Msg
    st.session_state.agent_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # 2. Agent Loop
    with st.chat_message("assistant"):
        container = st.container()
        engine = AgentEngine(selected_tag)
        
        full_response = ""
        thought_content = None
        
        # --- METRIQUES ---
        start_time = time.perf_counter()
        last_step_time = start_time
        
        # On itère sur le stream
        stream = engine.run_stream(prompt, st.session_state.agent_messages)
        
        try:
            for event in stream:
                current_time = time.perf_counter()
                step_duration = current_time - last_step_time
                last_step_time = current_time
                
                event_type = event["type"]
                
                if event_type == "tool_call":
                    with container.status(f"🔨 L'agent réfléchit... ({step_duration:.2f}s)", expanded=True) as status:
                        st.write(f"**Outil choisi :** `{event['tool']}`")
                        st.write(f"**Arguments :** `{event['args']}`")
                        status.update(label=f"🔨 Appel outil : {event['tool']}", state="running")
                        
                        # Log historique
                        st.session_state.agent_messages.append({
                            "role": "assistant",
                            "type": "tool_log",
                            "tool": event['tool'],
                            "args": event['args'],
                            "content": "..." 
                        })
                        
                elif event_type == "tool_result":
                    # Update historique précédent
                    if st.session_state.agent_messages and st.session_state.agent_messages[-1].get("type") == "tool_log":
                        st.session_state.agent_messages[-1]["content"] = event["content"]
                        container.info(f"✅ Résultat ({step_duration:.2f}s) : {event['content']}")

                elif event_type == "final_answer":
                    raw_content = event["content"]
                    
                    # Extraction du Raisonnement (<think>)
                    thought_content, clean_response = extract_thought(raw_content)
                    full_response = clean_response
                    
                    # Affichage
                    if thought_content:
                        with container.expander("💭 Raisonnement du modèle (Chain of Thought)", expanded=True):
                            st.markdown(thought_content)
                    
                    container.markdown(full_response)
                
                elif event_type == "error":
                    container.error(event["content"])

            # Fin exécution
            total_duration = time.perf_counter() - start_time
            container.caption(f"🏁 Tâche terminée en {total_duration:.2f}s")
            
            # Sauvegarde réponse finale
            if full_response:
                st.session_state.agent_messages.append({
                    "role": "assistant", 
                    "content": full_response,
                    "thought": thought_content # On sauvegarde la pensée aussi
                })
                
        except Exception as e:
            container.error(f"Erreur d'exécution : {e}")