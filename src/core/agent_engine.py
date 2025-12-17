"""
Agent Engine - Moteur d'agent autonome basé sur LangGraph.

Modifications principales :
- Support de la sélection dynamique d'outils
- Support des modèles API (Mistral) en plus d'Ollama
- Détection du type de modèle via models.json (SOURCE DE VÉRITÉ)
"""

import logging
import os
from collections.abc import Generator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from src.core.agent_tools import AVAILABLE_TOOLS, get_tools_by_names
from src.core.model_detector import is_api_model
from src.core.models_db import MODELS_DB, get_model_info

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentEngine:
    """
    Moteur d'agent autonome basé sur LangGraph.
    Capable d'utiliser des outils sélectionnés pour répondre.
    Supporte les modèles locaux (Ollama) et API (Mistral).
    """

    def __init__(self, model_name: str, enabled_tools: list[str] = None):
        """
        Initialise l'agent avec un modèle et une liste d'outils.

        Args:
            model_name: Tag du modèle (ex: "qwen2.5:1.5b", "mistral-large-2512")
            enabled_tools: Liste des noms d'outils à activer (None = tous)
                          Ex: ["calculator", "send_email", "system_monitor"]
        """
        self.model_name = model_name

        # 1. Sélection des outils
        if enabled_tools is None:
            # Par défaut, tous les outils sont activés
            self.tools = AVAILABLE_TOOLS
            logger.info(f"Agent initialisé avec TOUS les outils ({len(AVAILABLE_TOOLS)})")
        else:
            # Filtrage des outils par nom
            self.tools = get_tools_by_names(enabled_tools)
            logger.info(f"Agent initialisé avec {len(self.tools)} outil(s): {enabled_tools}")

        # 2. Détection du type de modèle via models.json et initialisation du LLM
        self.llm = self._initialize_llm(model_name)

        # 3. Création du graphe d'agent (Prebuilt ReAct Agent)
        self.agent_executor = create_react_agent(self.llm, self.tools)

    def _initialize_llm(self, model_tag: str):
        # Utiliser le détecteur central
        if is_api_model(model_tag):
            return self._initialize_mistral_api(model_tag)
        else:
            return self._initialize_ollama(model_tag)

    def _initialize_mistral_api(self, model_tag: str):
        """
        Initialise un modèle Mistral via l'API.

        Args:
            model_tag: Tag du modèle
            model_info: Informations du modèle depuis models.json

        Returns:
            ChatMistralAI: Instance du modèle API
        """
        try:
            from langchain_mistralai import ChatMistralAI

            api_key = os.getenv("MISTRAL_API_KEY")
            if not api_key:
                raise ValueError(
                    f"MISTRAL_API_KEY manquante dans .env pour utiliser le modèle API '{model_tag}'. "
                    f"Ajoutez votre clé Mistral dans le fichier .env"
                )

            logger.info(f"🌐 Initialisation du modèle API Mistral : {model_tag} ")

            return ChatMistralAI(
                model=model_tag,
                mistral_api_key=api_key,
                temperature=0.0,  # Zéro créativité pour la rigueur des appels d'outils
            )

        except ImportError as e:
            raise ImportError(
                "Le package 'langchain-mistralai' est requis pour les modèles Mistral API. "
                "Installez-le avec : pip install langchain-mistralai"
            ) from e

        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du modèle API {model_tag} : {e}")
            raise

    def _initialize_ollama(self, model_tag: str):
        """
        Initialise un modèle local via Ollama.

        Args:
            model_tag: Tag du modèle

        Returns:
            ChatOllama: Instance du modèle local
        """
        logger.info(f"🏠 Initialisation du modèle local Ollama : {model_tag}")

        return ChatOllama(
            model=model_tag,
            temperature=0.0,  # Zéro créativité pour la rigueur des appels d'outils
        )

    def run_stream(
        self,
        user_query: str,
        chat_history: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> Generator[dict, None, None]:
        """
        Exécute l'agent et stream les événements (pensées, appels d'outils, réponse finale).

        Args:
            user_query: Question de l'utilisateur
            chat_history: Historique de conversation (optionnel)
            system_prompt: Instructions système personnalisées (optionnel)

        Yields:
            dict: Événements avec structure {"type": ..., "content": ..., etc.}
        """
        if chat_history is None:
            chat_history = []

        # Valeur par défaut si non fournie
        default_system = (
            "Tu es un assistant utile capable d'utiliser des outils. "
            "Si tu utilises un outil, base ta réponse finale sur son résultat. "
            "Réponds dans la même langue que l'utilisateur."
        )
        final_system_prompt = system_prompt if system_prompt else default_system

        # Construction des messages LangChain
        lc_messages = [SystemMessage(content=final_system_prompt)]

        for msg in chat_history:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))

        lc_messages.append(HumanMessage(content=user_query))

        try:
            # Stream des événements du graphe
            stream = self.agent_executor.stream({"messages": lc_messages}, stream_mode="values")

            seen_messages = set()

            for event in stream:
                messages = event.get("messages", [])
                if not messages:
                    continue

                last_message = messages[-1]
                msg_id = id(last_message)

                if msg_id in seen_messages:
                    continue
                seen_messages.add(msg_id)

                # A. Appel d'outil (Tool Call)
                if isinstance(last_message, AIMessage) and last_message.tool_calls:
                    for tool_call in last_message.tool_calls:
                        yield {
                            "type": "tool_call",
                            "tool": tool_call["name"],
                            "args": tool_call["args"],
                        }

                # B. Résultat d'outil (Tool Message)
                elif hasattr(last_message, "tool_call_id"):
                    yield {"type": "tool_result", "content": last_message.content}

                # C. Réponse Finale (AIMessage sans tool_calls)
                elif isinstance(last_message, AIMessage) and not last_message.tool_calls:
                    yield {"type": "final_answer", "content": last_message.content}

        except Exception as e:
            logger.error(f"Erreur Agent: {e}")
            yield {"type": "error", "content": f"Erreur critique de l'agent : {str(e)}"}


# ========================================
# UTILITAIRES POUR TESTS & DEBUGGING
# ========================================


def list_available_models():
    """Liste tous les modèles disponibles avec leur type."""
    if not MODELS_DB:
        print("❌ Base de données des modèles vide")
        return

    print(f"\n📋 {len(MODELS_DB)} modèles disponibles :\n")

    for model_name, info in MODELS_DB.items():
        model_type = info.get("type", "unknown")
        ollama_tag = info.get("ollama_tag", "N/A")
        icon = "🌐" if model_type == "api" else "🏠"

        print(f"{icon} {model_name:<40} | Tag: {ollama_tag:<25} | Type: {model_type}")


def test_model_detection(model_tag: str):
    """Teste la détection du type d'un modèle."""
    print(f"\n🔍 Test de détection pour : {model_tag}\n")

    info = get_model_info(model_tag)

    if info:
        print("✅ Modèle trouvé dans models.json")
        print(f"   Type : {info.get('type', 'N/A')}")
        print(f"   Éditeur : {info.get('editor', 'N/A')}")
        print(f"   Paramètres : {info.get('params_tot', 'N/A')}")
        print(f"   Capacités : {', '.join(info.get('capabilities', []))}")
    else:
        print("❌ Modèle non trouvé dans models.json")
        print("   Fallback : Utilisation d'Ollama par défaut")


if __name__ == "__main__":
    # Tests de base
    print("=" * 80)
    print("AGENT ENGINE - TESTS DE DÉTECTION DE MODÈLES")
    print("=" * 80)

    # Liste tous les modèles
    list_available_models()

    # Tests de détection
    print("\n" + "=" * 80)
    print("TESTS DE DÉTECTION")
    print("=" * 80)

    test_cases = [
        "qwen2.5:1.5b",  # Local
        "mistral-large-2512",  # API
        "devstral-2512",  # API
        "mistral:7b",  # Local (Mistral via Ollama)
        "model-inconnu",  # Non trouvé
    ]

    for model_tag in test_cases:
        test_model_detection(model_tag)
