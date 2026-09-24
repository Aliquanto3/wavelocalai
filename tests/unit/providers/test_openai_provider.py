# tests/unit/providers/test_openai_provider.py
"""Tests unitaires pour le provider OpenAI."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.providers.openai_provider import OpenAIProvider


class TestOpenAIProvider:
    """Suite de tests pour OpenAIProvider."""

    @patch("src.core.providers.openai_provider.OPENAI_AVAILABLE", True)
    def test_availability_and_metadata(self) -> None:
        """Vérifie la configuration de base du provider."""
        provider = OpenAIProvider(api_key="sk-fake-key")
        assert provider.provider_name == "openai"
        assert provider.is_available is True
        assert provider.is_local is False

    @pytest.mark.asyncio
    @patch("openai.AsyncOpenAI")
    async def test_stream_implementation_usage_tracking(self, mock_async_openai: MagicMock) -> None:
        """
        Vérifie que le streaming capture correctement les tokens d'usage.

        Args:
            mock_async_openai: Mock du client officiel OpenAI.
        """
        provider = OpenAIProvider(api_key="sk-fake")
        metadata: dict = {}

        # Simulation d'un chunk avec usage
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock(delta=MagicMock(content="Hello"))]
        mock_chunk.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        # Configuration du mock stream
        mock_stream = MagicMock()
        mock_stream.__aiter__.return_value = [mock_chunk]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)
        provider._client = mock_client

        # Consommation du générateur
        tokens = [
            t
            async for t in provider._stream_implementation(
                "gpt-4o", [{"role": "user", "content": "hi"}], 0.7, metadata
            )
        ]

        assert tokens == ["Hello"]
        assert metadata["input_tokens"] == 10
        assert metadata["output_tokens"] == 5

    def test_health_check_failure(self) -> None:
        """Vérifie le comportement en cas d'échec API."""
        with patch("openai.OpenAI") as mock_sync_client:
            mock_sync_client.return_value.models.list.side_effect = Exception("Auth Error")
            provider = OpenAIProvider(api_key="wrong-key")
            assert provider.health_check() is False
