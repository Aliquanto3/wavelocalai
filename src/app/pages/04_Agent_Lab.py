import nest_asyncio
import streamlit as st

from src.core.agent_engine import AgentEngine
from src.core.crew_engine import CrewFactory
from src.core.llm_provider import LLMProvider
from src.core.models_db import extract_thought, get_friendly_name_from_tag, get_model_info
from src.core.resource_manager import ResourceManager

# Patch pour les boucles d'événements imbriquées (CrewAI + Streamlit)
nest_asyncio.apply()

st.set_page_config(page_title="Agent Lab", page_icon="🧪", layout="wide")
# ... le reste du fichier reste IDENTIQUE, juste l'entête change ...
# (Copie le reste du contenu du fichier original ou de la version précédente)
st.title("🧪 Agent Lab : Orchestration")
st.caption("Environnement d'exécution pour Agents Autonomes (LangGraph) et Équipes (CrewAI).")

# --- SESSION ---
if "agent_messages" not in st.session_state:
    st.session_state.agent_messages = []

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuration")

    # 1. LISTING ET TRI
    installed = LLMProvider.list_models()
    # Logique de tri (Verified vs Experimental)
    verified_models = []
    experimental_models = []

    for m in installed:
        friendly = get_friendly_name_from_tag(m.get("model"))  # .get car dict désormais
        info = get_model_info(friendly)
        if info and "tools" in info.get("capabilities", []):
            verified_models.append(friendly)
        else:
            experimental_models.append(friendly)

    all_choices = sorted(verified_models) + sorted(experimental_models)

    def format_func(option):
        return f"✅ {option}" if option in verified_models else f"⚠️ {option}"

    selected_friendly = st.selectbox("Cerveau (LLM)", all_choices, format_func=format_func)

    # Récupération Tag
    info = get_model_info(selected_friendly)
    selected_tag = info["ollama_tag"] if info else None
    if not selected_tag:  # Fallback manuel
        for m in installed:
            if get_friendly_name_from_tag(m.get("model")) == selected_friendly:
                selected_tag = m.get("model")
                break

    st.divider()

    # 2. SÉLECTION DU MODE
    agent_mode = st.radio(
        "Architecture",
        ["Solo (LangGraph)", "Crew (Multi-Agent)"],
        captions=["Rapide • Tâches simples", "Puissant • Recherche & Synthèse"],
    )

    st.info(
        """
        **Outils disponibles :**
        1. 🕒 **Time :** Heure système.
        2. 🧮 **Calculator :** Calculs sécurisés.
        3. 🏢 **Wavestone Search :** Base interne simulée.
"""
    )

    if st.button("🗑️ Reset Mémoire"):
        st.session_state.agent_messages = []
        st.rerun()

# --- LOGIQUE D'AFFICHAGE ---

# MODE A : LANGGRAPH (Chat interactif)
if agent_mode == "Solo (LangGraph)":
    # Affichage historique
    for msg in st.session_state.agent_messages:
        with st.chat_message(msg["role"]):
            if msg.get("type") == "tool_log":
                with st.status(f"🛠️ {msg['tool']}", state="complete"):
                    st.write(f"Args: `{msg['args']}`")
                    st.write(f"Result: {msg['content']}")
            elif msg.get("thought"):
                with st.expander("💭 Pensée", expanded=False):
                    st.markdown(msg["thought"])
            st.markdown(msg["content"])

    if prompt := st.chat_input("Votre instruction pour l'agent..."):
        if not selected_tag:
            st.stop()

        # Pre-Flight Check RAM (1 Agent)
        check = ResourceManager.check_resources(selected_tag, n_instances=1)
        if not check.allowed:
            st.error(f"⚠️ {check.message}")
            st.stop()

        st.session_state.agent_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            container = st.container()
            engine = AgentEngine(selected_tag)

            full_resp = ""
            thought = None

            try:
                stream = engine.run_stream(prompt, st.session_state.agent_messages)

                for event in stream:
                    ev_type = event["type"]

                    if ev_type == "tool_call":
                        with container.status(f"🔨 Outil : {event['tool']}", expanded=True):
                            st.write(f"Args : `{event['args']}`")
                        st.session_state.agent_messages.append(
                            {
                                "role": "assistant",
                                "type": "tool_log",
                                "tool": event["tool"],
                                "args": event["args"],
                                "content": "...",
                            }
                        )

                    elif ev_type == "tool_result":
                        if (
                            st.session_state.agent_messages
                            and st.session_state.agent_messages[-1].get("type") == "tool_log"
                        ):
                            st.session_state.agent_messages[-1]["content"] = event["content"]

                    elif ev_type == "final_answer":
                        thought, clean = extract_thought(event["content"])
                        full_resp = clean
                        if thought:
                            with container.expander("💭 Pensée", expanded=True):
                                st.markdown(thought)
                        container.markdown(full_resp)

                    elif ev_type == "error":
                        container.error(event["content"])

                if full_resp:
                    st.session_state.agent_messages.append(
                        {"role": "assistant", "content": full_resp, "thought": thought}
                    )

            except Exception as e:
                container.error(f"Crash Agent : {e}")

# MODE B : CREWAI (Execution One-Shot)
else:
    st.subheader("👥 L'Équipe d'Audit (CrewAI)")
    st.markdown(
        """
    Cette équipe est composée de :
    * 🕵️‍♂️ **Senior Researcher :** Cherche les faits et utilise les outils.
    * 📝 **Briefing Manager :** Synthétise les trouvailles.
    """
    )

    crew_topic = st.text_input("Sujet de la mission", "La politique Green IT chez Wavestone")

    if st.button("🚀 Lancer la Mission"):
        if not selected_tag:
            st.stop()

        # Pre-Flight Check RAM (2 Agents !!)
        check = ResourceManager.check_resources(selected_tag, n_instances=2)
        if not check.allowed:
            st.error("⛔ **Ressources Insuffisantes pour le Multi-Agent**")
            st.error(f"{check.message}")
            st.warning(
                "Conseil : Utilisez un modèle plus petit (ex: Qwen 1.5B) ou passez en mode Solo."
            )
            st.stop()
        else:
            st.success(f"✅ Pre-Flight Check OK : {check.ram_available_gb:.1f} GB dispo.")

        with st.status("👨‍✈️ Orchestration de l'équipe...", expanded=True) as status:
            try:
                status.write("1. Recrutement des agents...")
                crew = CrewFactory.create_audit_crew(selected_tag)

                status.write(f"2. Briefing sur : '{crew_topic}'...")
                # Note: kickoff prend un dict d'inputs
                result = crew.kickoff(inputs={"topic": crew_topic})

                status.update(label="✅ Mission Accomplie !", state="complete", expanded=False)

                st.markdown("### 📝 Rapport Final")
                # CrewAI retourne parfois un objet CrewOutput, on prend le str
                final_text = str(result)
                st.markdown(final_text)

                with st.expander("Voir les métriques d'exécution"):
                    # CrewAI fournit des stats d'usage basiques
                    st.json(
                        result.token_usage if hasattr(result, "token_usage") else "Non disponible"
                    )

            except Exception as e:
                status.update(label="❌ Échec Mission", state="error")
                st.error(f"Erreur CrewAI : {e}")
