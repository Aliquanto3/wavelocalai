# src/core/providers/provider_factory.py
"""
Factory pour la gestion centralisée des providers LLM.
"""

import logging
from typing import Any

from src.core.interfaces import ILLMProvider
from src.core.model_detector import is_api_model
from src.core.providers.mistral_provider import MistralProvider
from src.core.providers.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """
    Factory singleton pour gérer les providers LLM.

    Permet d'obtenir le bon provider en fonction du modèle demandé
    et de lister tous les modèles disponibles.
    """

    _instance = None
    _providers: dict[str, ILLMProvider] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_providers()
        return cls._instance

    def _initialize_providers(self):
        """Initialise les providers disponibles."""
        # Provider Ollama (toujours disponible)
        self._providers["ollama"] = OllamaProvider()

        # Provider Mistral (si configuré)
        mistral = MistralProvider()
        if mistral.is_available:
            self._providers["mistral"] = mistral
            logger.info("✅ Provider Mistral initialisé")
        else:
            logger.debug("ℹ️ Provider Mistral non disponible (clé API manquante)")

        # Provider OpenAI (si configuré)
        from src.core.providers.openai_provider import OpenAIProvider

        openai_provider = OpenAIProvider()
        if openai_provider.is_available:
            self._providers["openai"] = openai_provider
            logger.info("✅ Provider OpenAI initialisé")
        else:
            logger.debug("ℹ️ Provider OpenAI non disponible (clé API manquante)")

        # Provider Anthropic (si configuré)
        from src.core.providers.anthropic_provider import AnthropicProvider

        anthropic_provider = AnthropicProvider()
        if anthropic_provider.is_available:
            self._providers["anthropic"] = anthropic_provider
            logger.info("✅ Provider Anthropic initialisé")
        else:
            logger.debug("ℹ️ Provider Anthropic non disponible (clé API manquante)")

    def get_provider(self, model_tag: str) -> ILLMProvider:
        """
        Retourne le provider approprié pour un modèle donné.

        Args:
            model_tag: Tag du modèle (ex: "qwen2.5:1.5b", "gpt-4o", "claude-3-5-sonnet")

        Returns:
            ILLMProvider correspondant

        Raises:
            ValueError: Si aucun provider ne peut gérer ce modèle
        """
        # Détection par préfixe du modèle
        model_lower = model_tag.lower()

        # OpenAI
        if model_lower.startswith("gpt-") or model_lower.startswith("o1-"):
            if "openai" in self._providers:
                return self._providers["openai"]
            raise ValueError(f"Modèle OpenAI {model_tag} demandé mais provider non disponible")

        # Anthropic
        if model_lower.startswith("claude-"):
            if "anthropic" in self._providers:
                return self._providers["anthropic"]
            raise ValueError(f"Modèle Anthropic {model_tag} demandé mais provider non disponible")

        # Mistral API (vérifier via models.json)
        if is_api_model(model_tag):
            if "mistral" in self._providers:
                return self._providers["mistral"]
            raise ValueError(f"Modèle API {model_tag} demandé mais provider Mistral non disponible")

        # Par défaut, utiliser Ollama pour les modèles locaux
        return self._providers["ollama"]

    def get_provider_by_name(self, provider_name: str) -> ILLMProvider | None:
        """
        Retourne un provider par son nom.

        Args:
            provider_name: Nom du provider ('ollama', 'mistral', etc.)

        Returns:
            ILLMProvider ou None si non trouvé
        """
        return self._providers.get(provider_name)

    def list_all_models(self, include_cloud: bool = True) -> list[dict[str, Any]]:
        """
        Liste tous les modèles de tous les providers.

        Args:
            include_cloud: Inclure les modèles cloud (Mistral, etc.)

        Returns:
            Liste consolidée de tous les modèles disponibles
        """
        all_models = []

        for provider_name, provider in self._providers.items():
            if not include_cloud and not provider.is_local:
                continue

            try:
                models = provider.list_models()
                # Ajouter le nom du provider à chaque modèle
                for model in models:
                    model["provider"] = provider_name
                all_models.extend(models)
            except Exception as e:
                logger.warning(f"Erreur listing modèles {provider_name}: {e}")

        return all_models

    def register_provider(self, name: str, provider: ILLMProvider):
        """
        Enregistre un nouveau provider.

        Args:
            name: Nom unique du provider
            provider: Instance du provider
        """
        self._providers[name] = provider
        logger.info(f"✅ Provider '{name}' enregistré")

    def health_check_all(self) -> dict[str, bool]:
        """
        Vérifie l'état de tous les providers.

        Returns:
            Dict {provider_name: is_healthy}
        """
        return {name: provider.health_check() for name, provider in self._providers.items()}

    @property
    def available_providers(self) -> list[str]:
        """Liste des noms de providers disponibles."""
        return list(self._providers.keys())


# Instance singleton globale
_factory: LLMProviderFactory | None = None


def get_provider_factory() -> LLMProviderFactory:
    """Retourne l'instance singleton de la factory."""
    global _factory
    if _factory is None:
        _factory = LLMProviderFactory()
    return _factory
