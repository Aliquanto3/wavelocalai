# src/core/llm_provider.py
"""
Gestionnaire unifié des LLM (Façade).

Ce module maintient la compatibilité avec l'API existante tout en déléguant
aux providers spécifiques via la factory.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from src.core.metrics import InferenceMetrics
from src.core.model_detector import is_api_model
from src.core.providers.provider_factory import get_provider_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMProvider:
    """
    Façade unifiée pour l'accès aux LLM.

    Maintient la compatibilité avec l'API existante tout en utilisant
    la nouvelle architecture basée sur les providers.

    Note: Cette classe est conservée pour la rétrocompatibilité.
    Pour les nouveaux développements, préférez utiliser directement
    la factory via get_provider_factory().
    """

    @staticmethod
    def _is_mistral_api_model(model_tag: str) -> bool:
        """Vérifie si un modèle est de type API Mistral."""
        return is_api_model(model_tag)

    @staticmethod
    def list_models(cloud_enabled: bool = True) -> list[dict[str, Any]]:
        """
        Liste tous les modèles disponibles.

        Args:
            cloud_enabled: Inclure les modèles cloud (Mistral)

        Returns:
            Liste des modèles avec leurs métadonnées
        """
        factory = get_provider_factory()
        return factory.list_all_models(include_cloud=cloud_enabled)

    @staticmethod
    def pull_model(model_name: str) -> Any:
        """
        Télécharge un modèle via Ollama.

        Args:
            model_name: Nom du modèle à télécharger

        Raises:
            ValueError: Si tentative de télécharger un modèle cloud
        """
        if LLMProvider._is_mistral_api_model(model_name):
            raise ValueError("Impossible de télécharger un modèle API Cloud.")

        factory = get_provider_factory()
        ollama_provider = factory.get_provider_by_name("ollama")

        if ollama_provider and hasattr(ollama_provider, "pull_model"):
            return ollama_provider.pull_model(model_name)

        raise ValueError("Provider Ollama non disponible")

    @staticmethod
    async def chat_stream(
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str | InferenceMetrics, None]:
        """
        Génère une réponse en streaming.

        Args:
            model_name: Tag du modèle
            messages: Historique de conversation
            temperature: Créativité du modèle
            system_prompt: Instruction système optionnelle

        Yields:
            str: Tokens générés
            InferenceMetrics: Métriques finales
        """
        factory = get_provider_factory()

        try:
            provider = factory.get_provider(model_name)
            async for chunk in provider.chat_stream(
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                system_prompt=system_prompt,
            ):
                yield chunk

        except ValueError as e:
            # Provider non disponible
            logger.error(f"Provider error: {e}")
            yield f"❌ Erreur : {e}"

        except Exception as e:
            logger.error(f"Chat stream error for {model_name}: {e}")
            raise e

    @staticmethod
    def get_langchain_model(model_name: str, temperature: float = 0.7, **kwargs) -> Any:
        """
        Retourne un modèle LangChain prêt à l'emploi.

        Args:
            model_name: Tag du modèle
            temperature: Température d'inférence
            **kwargs: Arguments additionnels

        Returns:
            Instance de BaseChatModel (LangChain)
        """
        factory = get_provider_factory()
        provider = factory.get_provider(model_name)
        return provider.get_langchain_model(
            model_name=model_name, temperature=temperature, **kwargs
        )

    @staticmethod
    def health_check() -> dict[str, bool]:
        """
        Vérifie l'état de tous les providers.

        Returns:
            Dict {provider_name: is_healthy}
        """
        factory = get_provider_factory()
        return factory.health_check_all()
