from unittest.mock import MagicMock, patch

import pytest

from src.core.llm_provider import LLMProvider


class TestLLMProviderListModels:
    @patch("src.core.llm_provider.ollama.list")
    @patch("src.core.llm_provider.get_cloud_models_from_db")
    def test_list_models_with_cloud(self, mock_get_cloud, mock_ollama_list):
        """Teste la fusion des modèles locaux et cloud"""
        # Setup Local
        mock_model_local = MagicMock()
        mock_model_local.model_dump.return_value = {"name": "llama3:8b", "size": 100}
        mock_ollama_list.return_value = MagicMock(models=[mock_model_local])

        # Setup Cloud (DB)
        mock_get_cloud.return_value = [
            {"model": "mistral-large-latest", "type": "cloud", "source": "db"}
        ]

        # On patche la clé API pour activer le mode cloud
        with patch("src.core.llm_provider.MISTRAL_API_KEY", "fake_key"):
            models = LLMProvider.list_models(cloud_enabled=True)

            assert len(models) == 2
            # Vérif Local
            assert any(m["model"] == "llama3:8b" and m["type"] == "local" for m in models)
            # Vérif Cloud
            assert any(
                m["model"] == "mistral-large-latest" and m["type"] == "cloud" for m in models
            )

    @patch("src.core.llm_provider.ollama.list")
    def test_list_models_local_only(self, mock_ollama_list):
        """Teste le filtre cloud_enabled=False"""
        mock_model = MagicMock()
        mock_model.model_dump.return_value = {"name": "qwen:0.5b"}
        mock_ollama_list.return_value = MagicMock(models=[mock_model])

        # Même avec une clé API, si cloud_enabled=False, pas de cloud
        with patch("src.core.llm_provider.MISTRAL_API_KEY", "fake_key"):
            models = LLMProvider.list_models(cloud_enabled=False)
            assert len(models) == 1
            assert models[0]["type"] == "local"


class TestLLMProviderChatStream:
    @pytest.mark.asyncio
    async def test_chat_stream_routing_ollama(self):
        """Vérifie que les modèles standards vont vers Ollama"""

        # On définit un VRAI générateur asynchrone pour le test
        async def fake_ollama_stream(*args, **kwargs):
            yield "chunk_test"

        # On utilise side_effect pour injecter ce générateur
        with patch("src.core.llm_provider.LLMProvider._stream_ollama") as mock_stream:
            mock_stream.side_effect = fake_ollama_stream

            # Action
            gen = LLMProvider.chat_stream("llama3", [])

            # Consommation du générateur
            chunks = []
            async for c in gen:
                chunks.append(c)

            # Vérification
            mock_stream.assert_called_once()
            assert chunks == ["chunk_test"]

    @pytest.mark.asyncio
    async def test_chat_stream_routing_mistral(self):
        """Vérifie que les modèles 'mistral-' vont vers l'API"""

        # On définit un VRAI générateur asynchrone pour le test
        async def fake_mistral_stream(*args, **kwargs):
            yield "chunk_mistral"

        # On patche _is_mistral_api_model pour forcer le routing,
        # et on patche _stream_mistral avec notre générateur
        with (
            patch("src.core.llm_provider.LLMProvider._is_mistral_api_model", return_value=True),
            patch("src.core.llm_provider.LLMProvider._stream_mistral") as mock_stream,
            patch("src.core.llm_provider.MISTRAL_API_KEY", "ok"),
        ):

            mock_stream.side_effect = fake_mistral_stream

            # Action
            gen = LLMProvider.chat_stream("mistral-large", [])

            # Consommation
            chunks = []
            async for c in gen:
                chunks.append(c)

            # Vérification
            mock_stream.assert_called_once()
            assert chunks == ["chunk_mistral"]
