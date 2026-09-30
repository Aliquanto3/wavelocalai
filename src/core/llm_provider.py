# src/core/llm_provider.py
"""
Gestionnaire unifié des LLM (Façade).

Ce module maintient la compatibilité avec l'API existante tout en déléguant
aux providers spécifiques via la factory.
"""

import logging
import math
from collections.abc import AsyncGenerator
from typing import Any

from src.core.metrics import InferenceMetrics, ReasoningChunk
from src.core.model_detector import is_api_model
from src.core.providers.provider_factory import get_provider_factory, is_cloud_tag

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
    ) -> AsyncGenerator[str | ReasoningChunk | InferenceMetrics, None]:
        """
        Génère une réponse en streaming.

        Args:
            model_name: Tag du modèle
            messages: Historique de conversation
            temperature: Créativité du modèle
            system_prompt: Instruction système optionnelle

        Yields:
            str: Tokens générés
            ReasoningChunk: Raisonnement du modèle (Ollama), à part de la réponse
            InferenceMetrics: Métriques finales

        Raises:
            ValueError: Fournisseur indisponible pour ce modèle.
            Exception: Erreur du fournisseur (Ollama arrêté, réseau…). Une erreur n'est jamais
                renvoyée comme un token : l'appelant l'affiche comme une erreur.
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

        except Exception as e:
            logger.error(f"Chat stream error for {model_name}: {e}")
            raise

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

    @staticmethod
    def _ollama_provider():
        """Provider Ollama de la factory (hôte utilisé pour la génération), ou None."""
        return get_provider_factory().get_provider_by_name("ollama")

    @staticmethod
    def ollama_available(timeout: float = 2.0) -> bool:
        """
        Vérifie qu'Ollama répond, en local et avec un délai court.

        N'interroge aucun fournisseur cloud (contrairement à health_check, qui en appelle
        certains réellement) : sert à l'état « Système » de l'application.
        """
        provider = LLMProvider._ollama_provider()
        if provider is None or not hasattr(provider, "health_check"):
            return False
        try:
            return bool(provider.health_check(timeout=timeout))
        except Exception:
            return False

    @staticmethod
    def is_model_loaded(model_name: str, timeout: float = 2.0) -> bool | None:
        """
        Indique si un modèle local est déjà en mémoire dans Ollama.

        Returns:
            True (chargé), False (pas encore chargé : le premier appel sera plus long) ou
            None (modèle cloud, ou état inconnu). Ne lève jamais d'exception.
        """
        if not model_name or LLMProvider._is_mistral_api_model(model_name):
            return None
        try:
            provider = get_provider_factory().get_provider(model_name)
        except Exception:
            return None
        if getattr(provider, "provider_name", None) != "ollama":
            return None
        try:
            return provider.is_model_loaded(model_name, timeout=timeout)
        except Exception:
            return None

    @staticmethod
    def loaded_model_size_gb(model_name: str, timeout: float = 2.0) -> float | None:
        """
        Taille chargée (Go) d'un modèle local en mémoire dans Ollama (`ollama ps`), lue juste
        après une génération pour le badge mémoire.

        Returns:
            La taille en Go, ou None : modèle cloud (tag distant servi par Ollama, fournisseur
            autre qu'Ollama), modèle absent de `ps`, Ollama injoignable ou taille nulle.
            Jamais d'estimation ; ne lève jamais d'exception.
        """
        try:
            if not model_name or LLMProvider._is_mistral_api_model(model_name):
                return None
            if is_cloud_tag(model_name) is True:
                return None
            provider = get_provider_factory().get_provider(model_name)
            if getattr(provider, "provider_name", None) != "ollama" or not hasattr(
                provider, "loaded_model_size_gb"
            ):
                return None
            size = provider.loaded_model_size_gb(model_name, timeout=timeout)
        except Exception:
            return None
        if isinstance(size, bool) or not isinstance(size, (int, float)):
            return None
        return size if math.isfinite(size) and size > 0 else None

    @staticmethod
    def loaded_models_ram_gb(timeout: float = 2.0) -> float:
        """
        Mémoire vive (Go) occupée par les modèles déjà chargés dans Ollama : rajoutée à la
        mémoire disponible pour qu'un modèle résident ne soit pas déclassé par les choix par
        défaut. 0.0 si Ollama est absent, injoignable ou sur un autre hôte ; ne lève jamais
        d'exception.
        """
        try:
            provider = LLMProvider._ollama_provider()
            if provider is None or not hasattr(provider, "loaded_models_ram_gb"):
                return 0.0
            return float(provider.loaded_models_ram_gb(timeout=timeout))
        except Exception:
            return 0.0
