from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.core.providers.mistral_provider import MistralProvider


class TestMistralProvider:
    """Suite de tests corrigée pour MistralProvider."""

    @patch("src.core.providers.mistral_provider.MISTRAL_API_KEY", "fake-key")
    @patch("src.core.providers.mistral_provider.MISTRAL_AVAILABLE", True)
    def test_availability_logic(self) -> None:
        provider = MistralProvider()
        assert provider.is_available is True

    @patch("langchain_mistralai.ChatMistralAI")
    def test_get_langchain_model(self, mock_chat: MagicMock) -> None:
        provider = MistralProvider(api_key="mistral-key")

        # ✅ CORRECT : On patch la classe, pas l'instance
        with patch(
            "src.core.providers.mistral_provider.MistralProvider.is_available",
            new_callable=PropertyMock,
        ) as mock_avail:
            mock_avail.return_value = True
            provider.get_langchain_model("mistral-large-latest", temperature=0.2)
            mock_chat.assert_called_once()

    @patch("src.core.providers.mistral_provider.get_cloud_models_from_db")
    def test_list_models_from_db(self, mock_get_db: MagicMock) -> None:
        mock_get_db.return_value = [
            {"name": "Mistral Large", "model": "mistral-large-2512", "type": "cloud", "size": 0}
        ]
        provider = MistralProvider()

        with patch(
            "src.core.providers.mistral_provider.MistralProvider.is_available",
            new_callable=PropertyMock,
        ) as mock_avail:
            mock_avail.return_value = True

            # Test list_models() brut
            models = provider.list_models()
            mock_get_db.assert_called_once_with(editor_filter="Mistral AI")
            assert len(models) == 1
            assert models[0]["name"] == "Mistral Large"

            # Test list_models_with_provider() — clé provider ajoutée
            models_with_provider = provider.list_models_with_provider()
            assert models_with_provider[0]["provider"] == "mistral"
