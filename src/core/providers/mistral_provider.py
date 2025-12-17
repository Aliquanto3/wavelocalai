# src/core/providers/mistral_provider.py
"""
Provider Mistral AI pour les modèles cloud.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from src.core.config import MISTRAL_API_KEY
from src.core.interfaces import ILLMProvider
from src.core.metrics import InferenceMetrics, MetricsCalculator
from src.core.models_db import get_cloud_models_from_db

logger = logging.getLogger(__name__)

# Import conditionnel de Mistral
try:
    from mistralai import Mistral

    MISTRAL_AVAILABLE = True
except ImportError:
    Mistral = None
    MISTRAL_AVAILABLE = False


class MistralProvider(ILLMProvider):
    """
    Provider pour les modèles Mistral AI (cloud).
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialise le provider Mistral.

        Args:
            api_key: Clé API Mistral (utilise MISTRAL_API_KEY par défaut)
        """
        self._api_key = api_key or MISTRAL_API_KEY
        self._client = None

        if MISTRAL_AVAILABLE and self._api_key:
            self._client = Mistral(api_key=self._api_key)

    @property
    def provider_name(self) -> str:
        return "mistral"

    @property
    def is_local(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        """Vérifie si le provider est configuré et disponible."""
        return MISTRAL_AVAILABLE and bool(self._api_key)

    def list_models(self) -> list[dict[str, Any]]:
        """Liste les modèles Mistral configurés dans models.json."""
        if not self.is_available:
            return []
        return get_cloud_models_from_db()

    async def chat_stream(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str | InferenceMetrics, None]:
        """Génère une réponse en streaming via l'API Mistral."""

        if not self.is_available:
            yield "❌ Erreur : Provider Mistral non disponible (clé API manquante ou SDK non installé)."
            return

        final_messages = messages.copy()
        if system_prompt:
            final_messages.insert(0, {"role": "system", "content": system_prompt})

        timer = MetricsCalculator()
        full_text = ""

        try:
            timer.start()

            stream = await self._client.chat.stream_async(
                model=model_name,
                messages=final_messages,
                temperature=temperature,
            )

            async for chunk in stream:
                if chunk.data.choices and chunk.data.choices[0].delta.content:
                    content = chunk.data.choices[0].delta.content
                    if content:
                        full_text += content
                        yield content

            timer.stop()

            # Estimation des tokens (Mistral ne retourne pas toujours le compte exact)
            eval_count = len(full_text) // 4  # Approximation
            duration = timer.duration
            tokens_per_second = eval_count / duration if duration > 0 else 0

            yield InferenceMetrics(
                model_name=model_name,
                input_tokens=0,  # Non fourni par Mistral en streaming
                output_tokens=eval_count,
                total_duration_s=round(duration, 2),
                load_duration_s=0,
                tokens_per_second=round(tokens_per_second, 1),
                carbon_g=0.0,  # Sera calculé par le service appelant
            )

        except Exception as e:
            logger.error(f"Mistral Error: {e}")
            raise e

    def get_langchain_model(self, model_name: str, temperature: float = 0.7, **kwargs) -> Any:
        """Retourne un modèle LangChain Mistral."""
        if not self.is_available:
            raise ValueError("Provider Mistral non disponible (clé API manquante)")

        from langchain_mistralai import ChatMistralAI

        return ChatMistralAI(
            model=model_name, api_key=self._api_key, temperature=temperature, **kwargs
        )

    def health_check(self) -> bool:
        """Vérifie si l'API Mistral est accessible."""
        if not self.is_available:
            return False
        try:
            # Test simple : lister les modèles
            self._client.models.list()
            return True
        except Exception:
            return False
