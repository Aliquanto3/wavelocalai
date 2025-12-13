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
        """Test récupération normale de la liste."""
        # Mock de la réponse Ollama
        mock_response = {
            "models": [
                {"model": "qwen2.5:1.5b", "size": 1500000000},
                {"model": "llama3:8b", "size": 8000000000},
            ]
        }

        with patch("src.core.llm_provider.ollama.list", return_value=mock_response):
            models = LLMProvider.list_models()

        assert len(models) == 2
        assert models[0]["model"] == "qwen2.5:1.5b"

    def test_list_models_empty(self):
        """Test quand aucun modèle installé."""
        mock_response = {"models": []}

        with patch("src.core.llm_provider.ollama.list", return_value=mock_response):
            models = LLMProvider.list_models()

        assert models == []

    def test_list_models_connection_error(self):
        """Test gestion erreur de connexion Ollama."""
        with patch(
            "src.core.llm_provider.ollama.list", side_effect=Exception("Connection refused")
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

            # Consomme le stream
            events = list(stream)

            assert len(events) == 2
            assert events[0]["status"] == "downloading"
            assert events[1]["status"] == "done"

    def test_pull_model_error(self):
        """Test gestion d'erreur lors du pull."""
        with patch("src.core.llm_provider.ollama.pull", side_effect=Exception("Model not found")):
            with pytest.raises(Exception, match="Model not found"):
                LLMProvider.pull_model("fake-model")


@pytest.mark.asyncio
class TestLLMProviderChatStream:
    """Tests de la méthode chat_stream (async)."""

    async def test_chat_stream_basic(self):
        """Test stream basique."""

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

        with patch("src.core.llm_provider.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value
            mock_instance.chat = AsyncMock(return_value=fake_stream())

            messages = [{"role": "user", "content": "Test"}]

            full_text = ""
            metrics = None

            stream = LLMProvider.chat_stream("test-model", messages)

            async for item in stream:
                if isinstance(item, str):
                    full_text += item
                elif isinstance(item, InferenceMetrics):
                    metrics = item

            assert full_text == "Hello World"
            assert metrics is not None
            assert metrics.output_tokens == 2

    async def test_chat_stream_with_system_prompt(self):
        """Test que le system prompt est inséré."""

        async def fake_stream():
            yield {"message": {"content": "OK"}}
            yield {"done": True, "eval_count": 1, "eval_duration": 1, "prompt_eval_count": 1}

        with patch("src.core.llm_provider.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value
            mock_instance.chat = AsyncMock(return_value=fake_stream())

            messages = [{"role": "user", "content": "Test"}]
            system_prompt = "Tu es un assistant strict."

            stream = LLMProvider.chat_stream("test-model", messages, system_prompt=system_prompt)

            # Consomme le stream
            async for _ in stream:
                pass

            # Vérifie que chat() a été appelé
            mock_instance.chat.assert_called_once()
            call_args = mock_instance.chat.call_args

            # Le premier message devrait être le system prompt
            sent_messages = call_args.kwargs["messages"]
            assert sent_messages[0]["role"] == "system"
            assert sent_messages[0]["content"] == system_prompt

    @pytest.mark.asyncio
    async def test_chat_stream_error_handling(self):
        """Test gestion d'erreur dans le stream."""

        async def fake_stream_with_error():
            yield {"message": {"content": "Start"}}
            raise Exception("Network error")

        with patch("src.core.llm_provider.AsyncClient") as mock_client:
            mock_instance = mock_client.return_value
            mock_instance.chat = AsyncMock(return_value=fake_stream_with_error())

            messages = [{"role": "user", "content": "Test"}]
            stream = LLMProvider.chat_stream("test-model", messages)

            # ✅ CORRECTION : L'exception est relancée, donc on la capture
            with pytest.raises(Exception, match="Network error"):
                async for item in stream:
                    pass
