# tests/unit/providers/test_ollama_provider.py
"""Tests unitaires pour le provider Ollama (Local)."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.providers.ollama_provider import OllamaProvider


class TestOllamaProvider:
    """Suite de tests pour OllamaProvider."""

    def test_provider_metadata(self) -> None:
        """Vérifie que le provider est correctement identifié comme local."""
        provider = OllamaProvider()
        assert provider.provider_name == "ollama"
        assert provider.is_local is True

    @patch("src.core.providers.ollama_provider.ollama.list")
    def test_list_models_parsing(self, mock_ollama_list: MagicMock) -> None:
        """
        Vérifie le parsing des modèles retournés par l'API Ollama.
        Gère les cas où la réponse est un objet avec un attribut .models.
        """
        # Simulation d'un retour d'objet Ollama
        mock_model = MagicMock()
        mock_model.model_dump.return_value = {"name": "qwen2.5:1.5b", "size": 1024**3}
        mock_ollama_list.return_value = MagicMock(models=[mock_model])

        provider = OllamaProvider()
        models = provider.list_models()

        assert len(models) == 1
        assert models[0]["model"] == "qwen2.5:1.5b"
        assert models[0]["type"] == "local"

    @patch("src.core.providers.ollama_provider.ollama.pull")
    def test_pull_model_execution(self, mock_ollama_pull: MagicMock) -> None:
        """Vérifie que la commande pull est correctement relayée."""
        provider = OllamaProvider()
        provider.pull_model("llama3")
        mock_ollama_pull.assert_called_once_with("llama3", stream=True)

    def test_health_check_success(self) -> None:
        """Vérifie le health check quand Ollama est disponible."""
        with patch("src.core.providers.ollama_provider.ollama.list") as mock_list:
            provider = OllamaProvider()
            assert provider.health_check() is True
            mock_list.assert_called_once()
