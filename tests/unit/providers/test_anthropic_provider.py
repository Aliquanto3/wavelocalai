# tests/unit/providers/test_anthropic_provider.py
"""Tests unitaires pour le provider Anthropic Claude."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.providers.anthropic_provider import AnthropicProvider


class TestAnthropicProvider:
    """Suite de tests pour AnthropicProvider."""

    @pytest.mark.asyncio
    async def test_stream_implementation_context_manager(self) -> None:
        provider = AnthropicProvider(api_key="sk-ant-test")
        metadata = {"_system_prompt": "Test system"}

        mock_stream = AsyncMock()
        # Correction : Simulation d'un itérateur asynchrone correct
        mock_stream.text_stream.__aiter__.return_value = ["Cla", "ude"]

        # Pour que "async for" fonctionne sur un Mock, il faut parfois itérer manuellement
        # ou utiliser un helper si la version de Python/Mock est ancienne.
        # Ici, nous forçons le comportement de l'itérateur.
        mock_stream.__aenter__.return_value = mock_stream

        final_msg = MagicMock()
        final_msg.usage.input_tokens = 20
        final_msg.usage.output_tokens = 10
        mock_stream.get_final_message = AsyncMock(return_value=final_msg)

        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_stream
        provider._client = mock_client

        collected = []
        async for chunk in provider._stream_implementation("claude-3", [], 0.7, metadata):
            collected.append(chunk)

        assert collected == ["Cla", "ude"]

    def test_get_langchain_model_initialization(self) -> None:
        """Vérifie l'instanciation de ChatAnthropic."""
        with patch("langchain_anthropic.ChatAnthropic") as mock_langchain:
            provider = AnthropicProvider(api_key="sk-ant")
            provider.get_langchain_model("claude-3-5-sonnet-20241022", temperature=0.1)

            mock_langchain.assert_called_once_with(
                model="claude-3-5-sonnet-20241022",
                api_key="sk-ant",  # pragma: allowlist secret
                temperature=0.1,
            )
