# src/core/providers/anthropic_provider.py
"""Provider Anthropic pour les modèles Claude."""

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.core.config import ANTHROPIC_API_KEY
from src.core.models_db import get_cloud_models_from_db
from src.core.providers.base_provider import BaseProvider

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

try:
    from anthropic import AsyncAnthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class AnthropicProvider(BaseProvider):
    """Provider pour les modèles Anthropic Claude."""

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialise le provider Anthropic.

        Args:
            api_key: Clé API optionnelle.
        """
        self._api_key = api_key or ANTHROPIC_API_KEY
        self._client: AsyncAnthropic | None = None

    def _get_client(self) -> "AsyncAnthropic":
        """
        Initialise ou retourne le client asynchrone Anthropic.

        Returns:
            Le client AsyncAnthropic.

        Raises:
            ImportError: Si le package anthropic n'est pas installé.
            ValueError: Si la clé API n'est pas configurée.
        """
        if self._client is None:
            if not ANTHROPIC_AVAILABLE:
                raise ImportError("Package 'anthropic' manquant.")
            if not self._api_key:
                raise ValueError("Clé API Anthropic non configurée.")
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    @property
    def provider_name(self) -> str:
        """Returns: 'anthropic'."""
        return "anthropic"

    @property
    def is_local(self) -> bool:
        """Returns: False."""
        return False

    @property
    def is_available(self) -> bool:
        """Returns: True si configuré."""
        return ANTHROPIC_AVAILABLE and bool(self._api_key)

    async def _stream_implementation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        metadata: dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """
        Gère le flux de réponse Anthropic et capture l'usage.

        Args:
            model_name: Tag du modèle Claude.
            messages: Liste des messages (excluant le système).
            temperature: Température.
            metadata: Métadonnées incluant '_system_prompt'.

        Yields:
            Tokens textuels.
        """
        client = self._get_client()
        system = metadata.get("_system_prompt", "You are a helpful assistant.")

        async with client.messages.stream(
            model=model_name,
            max_tokens=4096,
            system=system,
            messages=messages,
            temperature=temperature,
        ) as stream:
            async for text in stream.text_stream:
                yield text

            final_message = await stream.get_final_message()
            if final_message.usage:
                metadata["input_tokens"] = final_message.usage.input_tokens
                metadata["output_tokens"] = final_message.usage.output_tokens

    def list_models(self) -> list[dict[str, Any]]:
        if not self.is_available:
            return []
        return get_cloud_models_from_db(editor_filter="Anthropic")

    def get_langchain_model(self, model_name: str, temperature: float = 0.7, **kwargs: Any) -> Any:
        """
        Retourne l'objet ChatAnthropic.

        Args:
            model_name: Tag du modèle.
            temperature: Température.
            **kwargs: Paramètres additionnels.

        Returns:
            Instance de ChatAnthropic.
        """
        if not self.is_available:
            raise ValueError("Provider Anthropic non disponible")
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_name, api_key=self._api_key, temperature=temperature, **kwargs
        )

    def health_check(self) -> bool:
        """Vérifie la validité de la connexion."""
        if not self.is_available:
            return False
        try:
            # Listing des modèles comme alternative moins coûteuse qu'un message
            import anthropic

            client = anthropic.Anthropic(api_key=self._api_key)
            # Anthropic n'a pas de client.models.list() universel simple,
            # on garde un petit message mais sur le modèle le moins cher.
            client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception as e:
            logger.error(f"Anthropic Health Check failed: {e}")
            return False
