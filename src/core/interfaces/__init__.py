# src/core/interfaces/i_llm_provider.py
"""
Interface abstraite pour les providers LLM.
Permet l'ajout de nouveaux providers (OpenAI, Anthropic, etc.) sans modifier le code existant.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from src.core.metrics import InferenceMetrics


class ILLMProvider(ABC):
    """
    Interface abstraite définissant le contrat pour tous les providers LLM.

    Chaque provider (Ollama, Mistral, OpenAI, etc.) doit implémenter cette interface.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Nom du provider (ex: 'ollama', 'mistral', 'openai')."""
        pass

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """True si le provider est local (pas d'appel API externe)."""
        pass

    @abstractmethod
    def list_models(self) -> list[dict[str, Any]]:
        """
        Liste les modèles disponibles pour ce provider.

        Returns:
            Liste de dicts avec au minimum les clés:
            - 'model': str (tag/identifiant du modèle)
            - 'name': str (nom d'affichage)
            - 'type': str ('local' ou 'cloud')
        """
        pass

    @abstractmethod
    async def chat_stream(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str | InferenceMetrics, None]:
        """
        Génère une réponse en streaming.

        Args:
            model_name: Identifiant du modèle
            messages: Historique de conversation [{"role": "user/assistant", "content": "..."}]
            temperature: Créativité (0.0 = déterministe, 1.0 = créatif)
            system_prompt: Instruction système optionnelle

        Yields:
            str: Tokens générés
            InferenceMetrics: Métriques finales (dernier yield)
        """
        pass

    @abstractmethod
    def get_langchain_model(self, model_name: str, temperature: float = 0.7, **kwargs) -> Any:
        """
        Retourne un modèle compatible LangChain.

        Args:
            model_name: Identifiant du modèle
            temperature: Température d'inférence
            **kwargs: Arguments additionnels spécifiques au provider

        Returns:
            Instance de BaseChatModel (LangChain)
        """
        pass

    def supports_model(self, model_tag: str) -> bool:
        """
        Vérifie si ce provider supporte un modèle donné.

        Args:
            model_tag: Tag du modèle à vérifier

        Returns:
            True si le provider peut gérer ce modèle
        """
        # Implémentation par défaut : vérifier dans la liste des modèles
        try:
            models = self.list_models()
            return any(m.get("model") == model_tag for m in models)
        except Exception:
            return False

    def health_check(self) -> bool:
        """
        Vérifie si le provider est disponible et fonctionnel.
        Returns:
            True si le provider est accessible
        """
        try:
            self.list_models()
            return True
        except Exception:
            return False
