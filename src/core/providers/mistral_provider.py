# src/core/providers/mistral_provider.py
"""Provider Mistral AI pour les modèles cloud."""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from src.core.config import MISTRAL_API_KEY
from src.core.models_db import get_cloud_models_from_db
from src.core.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)

try:
    from mistralai import Mistral

    MISTRAL_AVAILABLE = True
except ImportError:
    Mistral = None
    MISTRAL_AVAILABLE = False


class MistralProvider(BaseProvider):
    """Provider pour les modèles Mistral AI (cloud)."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or MISTRAL_API_KEY

    def _create_client(self) -> "Mistral":
        """Crée un nouveau client Mistral (pour appels sync)."""
        if not MISTRAL_AVAILABLE or not self._api_key:
            raise ValueError("Provider Mistral non disponible")
        return Mistral(api_key=self._api_key)

    def _create_async_client(self) -> "Mistral":
        """
        Crée un nouveau client Mistral pour chaque appel async.

        Évite le problème 'Event loop is closed' causé par la réutilisation
        d'un client httpx persistant entre plusieurs asyncio.run().
        """
        if not MISTRAL_AVAILABLE or not self._api_key:
            raise ValueError("Provider Mistral non disponible")
        return Mistral(api_key=self._api_key)

    @property
    def provider_name(self) -> str:
        return "mistral"

    @property
    def is_local(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        return MISTRAL_AVAILABLE and bool(self._api_key)

    async def _stream_implementation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        metadata: dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """Implémentation streaming Mistral avec capture des métriques."""
        # Nouveau client à chaque appel pour éviter "Event loop is closed"
        client = self._create_async_client()

        stream = await client.chat.stream_async(
            model=model_name,
            messages=messages,
            temperature=temperature,
        )

        async for chunk in stream:
            if chunk.data.choices and chunk.data.choices[0].delta.content:
                content = chunk.data.choices[0].delta.content
                if content:
                    yield content

            # Capture des métriques d'usage (présentes sur le dernier chunk)
            if hasattr(chunk.data, "usage") and chunk.data.usage:
                metadata["input_tokens"] = getattr(chunk.data.usage, "prompt_tokens", 0)
                metadata["output_tokens"] = getattr(chunk.data.usage, "completion_tokens", 0)

    def list_models(self) -> list[dict[str, Any]]:
        if not self.is_available:
            return []
        return get_cloud_models_from_db(editor_filter="Mistral AI")

    def get_langchain_model(self, model_name: str, temperature: float = 0.7, **kwargs) -> Any:
        if not self.is_available:
            raise ValueError("Provider Mistral non disponible")
        from langchain_mistralai import ChatMistralAI

        return ChatMistralAI(
            model=model_name, api_key=self._api_key, temperature=temperature, **kwargs
        )

    def health_check(self) -> bool:
        if not self.is_available:
            return False
        try:
            client = self._create_client()
            client.models.list()
            return True
        except Exception:
            return False
