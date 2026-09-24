# tests/unit/test_llm_provider.py
"""Tests de la façade LLMProvider."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.llm_provider import LLMProvider


class TestLLMProviderFaçade:
    """Tests de haut niveau sur la façade unifiée."""

    @patch("src.core.llm_provider.get_provider_factory")
    def test_list_models_consolidation(self, mock_get_factory: MagicMock) -> None:
        """Vérifie que la façade agrège les résultats de la factory."""
        mock_factory = MagicMock()
        mock_factory.list_all_models.return_value = [{"model": "m1"}]
        mock_get_factory.return_value = mock_factory

        models = LLMProvider.list_models()
        assert len(models) == 1
        mock_factory.list_all_models.assert_called_once()

    @patch("src.core.llm_provider.is_api_model")
    @patch("src.core.llm_provider.get_provider_factory")
    def test_pull_model_delegation(
        self, mock_get_factory: MagicMock, mock_is_api: MagicMock
    ) -> None:
        """Vérifie que pull_model délègue bien à Ollama pour les modèles locaux."""
        mock_is_api.return_value = False
        mock_ollama = MagicMock()
        mock_factory = MagicMock()
        mock_factory.get_provider_by_name.return_value = mock_ollama
        mock_get_factory.return_value = mock_factory

        LLMProvider.pull_model("local-model")
        mock_ollama.pull_model.assert_called_once_with("local-model")
