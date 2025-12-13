import logging
from typing import List, Dict, Any, Generator

from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.core.agent_tools import AVAILABLE_TOOLS

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentEngine:
    """
    Moteur d'agent autonome basé sur LangGraph.
    Capable d'utiliser des outils pour répondre.
    """
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        
        # 1. Initialisation du LLM avec support des outils
        # ChatOllama gère nativement le 'bind_tools' pour les modèles compatibles
        self.llm = ChatOllama(
            model=model_name,
            temperature=0.0, # Zéro créativité pour la rigueur des appels d'outils
        )
        
        # 2. Création du graphe d'agent (Prebuilt ReAct Agent)
        # LangGraph gère automatiquement la boucle : LLM -> Tool -> LLM
        self.agent_executor = create_react_agent(self.llm, AVAILABLE_TOOLS)

    from typing import Optional, List, Dict

    def run_stream(
    self,
    user_query: str,
    chat_history: Optional[List[Dict]] = None
) -> Generator[Dict, None, None]:
        """
        Exécute l'agent et stream les événements (pensées, appels d'outils, réponse finale).
        """
        if chat_history is None:
            chat_history = []

        # Conversion de l'historique simple en format LangChain
        lc_messages = [
            SystemMessage(content="Tu es un assistant utile capable d'utiliser des outils. Si tu utilises un outil, base ta réponse finale sur son résultat. Réponds dans la même langue que l'utilisateur.")
        ]
        
        for msg in chat_history:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
        
        lc_messages.append(HumanMessage(content=user_query))
        
        try:
            # Stream des événements du graphe
            # On demande à streamer les "values" pour voir l'évolution de l'état
            stream = self.agent_executor.stream(
                {"messages": lc_messages},
                stream_mode="values"
            )
            
            seen_messages = set()
            
            for event in stream:
                # LangGraph renvoie l'état complet des messages à chaque étape
                messages = event.get("messages", [])
                if not messages:
                    continue
                    
                last_message = messages[-1]
                msg_id = id(last_message)
                
                if msg_id in seen_messages:
                    continue
                seen_messages.add(msg_id)
                
                # Analyse du type de message pour le feedback UI
                
                # A. Appel d'outil (Tool Call)
                if isinstance(last_message, AIMessage) and last_message.tool_calls:
                    for tool_call in last_message.tool_calls:
                        yield {
                            "type": "tool_call",
                            "tool": tool_call["name"],
                            "args": tool_call["args"]
                        }
                        
                # B. Résultat d'outil (Tool Message)
                # Note: Dans la structure prebuilt, les ToolMessages suivent les AIMessages
                # On les capture s'ils sont le dernier message
                elif hasattr(last_message, "tool_call_id"): # C'est un ToolMessage
                    yield {
                        "type": "tool_result",
                        "content": last_message.content
                    }
                
                # C. Réponse Finale (AIMessage sans tool_calls)
                elif isinstance(last_message, AIMessage) and not last_message.tool_calls:
                    yield {
                        "type": "final_answer",
                        "content": last_message.content
                    }
                    
        except Exception as e:
            logger.error(f"Erreur Agent: {e}")
            yield {
                "type": "error",
                "content": f"Erreur critique de l'agent : {str(e)}"
            }