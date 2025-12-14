"""
Tests unitaires pour LLMProvider.
Usage: pytest tests/unit/test_llm_provider.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.llm_provider import LLMProvider
from src.core.metrics import InferenceMetrics


class TestLLMProviderListModels:
    """Tests de la méthode list_models."""

    def test_list_models_success(self):
        """Test récupération normale de la liste unifiée."""
        # Mock de la réponse Ollama
        mock_ollama_response = {
            "models": [
                {"model": "qwen2.5:1.5b", "size": 1500000000},
                {"model": "llama3:8b", "size": 8000000000},
            ]
        }

        # On mocke ollama.list ET on s'assure que MISTRAL_API_KEY est None pour ce test
        with (
            patch("src.core.llm_provider.ollama.list", return_value=mock_ollama_response),
            patch("src.core.llm_provider.MISTRAL_API_KEY", None),
        ):
            models = LLMProvider.list_models()

        # On vérifie qu'on a bien les modèles locaux + le tag "type": "local"
        assert len(models) == 2
        assert models[0]["model"] == "qwen2.5:1.5b"
        assert models[0]["type"] == "local"

    def test_list_models_with_cloud(self):
        """Test récupération avec des modèles Cloud simulés."""
        mock_ollama_response = {"models": []}

        # On simule une clé API présente
        with (
            patch("src.core.llm_provider.ollama.list", return_value=mock_ollama_response),
            patch("src.core.llm_provider.MISTRAL_API_KEY", "fake_key"),
        ):
            models = LLMProvider.list_models()

        # On devrait avoir les modèles cloud par défaut définis dans le code
        assert len(models) >= 3
        assert any(m["model"] == "mistral-large-latest" and m["type"] == "cloud" for m in models)

    def test_list_models_connection_error(self):
        """Test gestion erreur de connexion Ollama (ne doit pas crasher le Cloud)."""
        with (
            patch("src.core.llm_provider.ollama.list", side_effect=Exception("Connection refused")),
            patch("src.core.llm_provider.MISTRAL_API_KEY", None),
        ):
            models = LLMProvider.list_models()

        assert models == []


class TestLLMProviderPullModel:
    """Tests de la méthode pull_model."""

    def test_pull_model_success(self):
        """Test téléchargement réussi."""

        def fake_pull_stream(model_name, stream=True):
            yield {"status": "downloading", "completed": 500, "total": 1000}
            yield {"status": "done"}

        with patch("src.core.llm_provider.ollama.pull", side_effect=fake_pull_stream):
            stream = LLMProvider.pull_model("test-model")
            events = list(stream)

            assert len(events) == 2
            assert events[0]["status"] == "downloading"

    def test_pull_model_cloud_error(self):
        """Test interdiction de télécharger un modèle Cloud."""
        with pytest.raises(ValueError, match="Impossible de télécharger"):
            LLMProvider.pull_model("mistral-large-latest")


@pytest.mark.asyncio
class TestLLMProviderChatStream:
    """Tests de la méthode chat_stream (async)."""

    async def test_chat_stream_basic_ollama(self):
        """Test stream basique vers Ollama."""

        async def fake_stream():
            yield {"message": {"content": "Hello"}}
            yield {"message": {"content": " World"}}
            yield {
                "done": True,
                "eval_count": 2,
                "eval_duration": 1000000000,
                "prompt_eval_count": 5,
                "load_duration": 500000000,
            }

        # NOTE IMPORTANTE : On mocke 'OllamaAsyncClient' et non plus 'AsyncClient'
        with patch("src.core.llm_provider.OllamaAsyncClient") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.chat = AsyncMock(return_value=fake_stream())

            messages = [{"role": "user", "content": "Test"}]
            full_text = ""
            metrics = None

            # On appelle le chat_stream global qui va router vers _stream_ollama
            stream = LLMProvider.chat_stream("test-model", messages)

            async for item in stream:
                if isinstance(item, str):
                    full_text += item
                elif isinstance(item, InferenceMetrics):
                    metrics = item

            assert full_text == "Hello World"
            assert metrics is not None
            assert metrics.output_tokens == 2
            assert metrics.model_name == "test-model"

    async def test_chat_stream_with_system_prompt(self):
        """Test que le system prompt est inséré (Routing Ollama)."""

        async def fake_stream():
            yield {"message": {"content": "OK"}}
            yield {"done": True}

        with patch("src.core.llm_provider.OllamaAsyncClient") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.chat = AsyncMock(return_value=fake_stream())

            messages = [{"role": "user", "content": "Test"}]
            system_prompt = "Tu es un assistant strict."

            stream = LLMProvider.chat_stream("test-model", messages, system_prompt=system_prompt)

            async for _ in stream:
                pass

            # Vérification des appels
            mock_instance.chat.assert_called_once()
            call_args = mock_instance.chat.call_args
            sent_messages = call_args.kwargs["messages"]

            # Le premier message doit être le system prompt
            assert sent_messages[0]["role"] == "system"
            assert sent_messages[0]["content"] == system_prompt

    @pytest.mark.asyncio
    async def test_chat_stream_error_handling(self):
        """Test gestion d'erreur dans le stream."""

        async def fake_stream_with_error():
            yield {"message": {"content": "Start"}}
            raise Exception("Ollama is down")

        with patch("src.core.llm_provider.OllamaAsyncClient") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.chat = AsyncMock(return_value=fake_stream_with_error())

            messages = [{"role": "user", "content": "Test"}]
            stream = LLMProvider.chat_stream("test-model", messages)

            with pytest.raises(Exception, match="Ollama is down"):
                async for _ in stream:
                    pass
