# src/core/providers/openai_provider.py
"""Provider OpenAI pour les modèles GPT."""

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.core.config import OPENAI_API_KEY
from src.core.models_db import get_cloud_models_from_db
from src.core.providers.base_provider import BaseProvider

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI  # type: ignore

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class OpenAIProvider(BaseProvider):
    """Provider pour les modèles OpenAI (GPT-4, GPT-3.5, etc.)."""

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialise le provider OpenAI.

        Args:
            api_key: Clé API optionnelle (sinon utilise OPENAI_API_KEY).
        """
        self._api_key = api_key or OPENAI_API_KEY
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> "AsyncOpenAI":
        """
        Initialise ou retourne le client asynchrone OpenAI.

        Returns:
            Le client AsyncOpenAI.

        Raises:
            ImportError: Si le package openai n'est pas installé.
            ValueError: Si la clé API n'est pas configurée.
        """
        if self._client is None:
            if not OPENAI_AVAILABLE:
                raise ImportError("Package 'openai' manquant. Installez-le : pip install openai")
            if not self._api_key:
                raise ValueError("Clé API OpenAI non configurée dans .env")
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    @property
    def provider_name(self) -> str:
        """Returns: 'openai'."""
        return "openai"

    @property
    def is_local(self) -> bool:
        """Returns: False (Cloud provider)."""
        return False

    @property
    def is_available(self) -> bool:
        """Returns: True si le package est installé et la clé configurée."""
        return OPENAI_AVAILABLE and bool(self._api_key)

    async def _stream_implementation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        metadata: dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """
        Gère le streaming des tokens et capture la consommation.

        Args:
            model_name: Identifiant du modèle OpenAI.
            messages: Historique de conversation.
            temperature: Niveau de créativité.
            metadata: Dictionnaire pour stocker les métriques d'inférence.

        Yields:
            Les fragments de texte générés.
        """
        client = self._get_client()

        stream = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

            if hasattr(chunk, "usage") and chunk.usage:
                metadata["input_tokens"] = chunk.usage.prompt_tokens or 0
                metadata["output_tokens"] = chunk.usage.completion_tokens or 0

    def list_models(self) -> list[dict[str, Any]]:
        if not self.is_available:
            return []
        return get_cloud_models_from_db(editor_filter="OpenAI")

    def get_langchain_model(self, model_name: str, temperature: float = 0.7, **kwargs: Any) -> Any:
        """
        Retourne l'objet ChatOpenAI compatible LangChain.

        Args:
            model_name: Nom du modèle.
            temperature: Température d'inférence.
            **kwargs: Paramètres supplémentaires.

        Returns:
            Instance de ChatOpenAI.
        """
        if not self.is_available:
            raise ValueError("Provider OpenAI non disponible")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name, api_key=self._api_key, temperature=temperature, **kwargs
        )

    def health_check(self) -> bool:
        """Vérifie la validité de la clé via une requête légère de listing."""
        if not self.is_available:
            return False
        try:
            import openai

            client = openai.OpenAI(api_key=self._api_key)
            client.models.list()
            return True
        except Exception as e:
            logger.error(f"OpenAI Health Check failed: {e}")
            return False
