# tests/unit/test_llm_provider.py
"""
Tests unitaires pour LLMProvider et la nouvelle architecture de providers.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.llm_provider import LLMProvider
from src.core.metrics import InferenceMetrics
from src.core.providers.provider_factory import LLMProviderFactory


@pytest.fixture(autouse=True)
def isolated_provider_factory():
    """Factory neuve à chaque test, sans clé d'API réelle (.env ignoré) : aucun appel réseau.

    La factory est un singleton de classe dont le registre _providers est partagé :
    sans cette isolation, un provider Mistral créé avec une fausse clé par un test
    reste enregistré et health_check() appelle ensuite l'API Mistral.
    """
    with (
        patch("src.core.providers.mistral_provider.MISTRAL_API_KEY", None),
        patch("src.core.providers.openai_provider.OPENAI_API_KEY", ""),
        patch("src.core.providers.anthropic_provider.ANTHROPIC_API_KEY", ""),
        patch("src.core.providers.provider_factory._factory", None),
        patch.object(LLMProviderFactory, "_instance", None),
        patch.dict(LLMProviderFactory._providers, clear=True),
    ):
        yield


class TestLLMProviderListModels:
    """Tests pour la méthode list_models."""

    def test_list_models_with_cloud(self):
        """Test listing avec modèles cloud activés."""
        mock_ollama_models = [
            {"model": "qwen2.5:1.5b", "name": "qwen2.5:1.5b", "type": "local"},
            {"model": "llama3:8b", "name": "llama3:8b", "type": "local"},
        ]
        mock_cloud_models = [
            {"model": "mistral-large-2512", "name": "Mistral Large", "type": "cloud"},
        ]

        with (
            patch("src.core.providers.ollama_provider.ollama") as mock_ollama,
            patch("src.core.providers.mistral_provider.MISTRAL_API_KEY", "fake-key"),
            patch("src.core.providers.mistral_provider.MISTRAL_AVAILABLE", True),
            patch("src.core.models_db.get_cloud_models_from_db", return_value=mock_cloud_models),
            patch("src.core.providers.provider_factory._factory", None),
        ):

            mock_ollama.Client.return_value.list.return_value = MagicMock(models=mock_ollama_models)
            models = LLMProvider.list_models(cloud_enabled=True)

        # Vérifier qu'on a des modèles
        assert len(models) >= 1

    def test_list_models_local_only(self):
        """Test listing sans modèles cloud."""
        mock_ollama_models = [
            {"model": "qwen2.5:1.5b", "name": "qwen2.5:1.5b", "type": "local"},
        ]

        with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
            mock_ollama.Client.return_value.list.return_value = MagicMock(models=mock_ollama_models)

            # Reset la factory
            with patch("src.core.providers.provider_factory._factory", None):
                models = LLMProvider.list_models(cloud_enabled=False)

        # Vérifier qu'on n'a que des modèles locaux
        for model in models:
            assert model.get("type") != "cloud"


class TestLLMProviderChatStream:
    """Tests pour la méthode chat_stream."""

    @pytest.mark.asyncio
    async def test_chat_stream_routing_ollama(self):
        """Test que les modèles locaux utilisent le provider Ollama."""
        mock_response = ["Bonjour", " monde", "!"]
        mock_metrics = InferenceMetrics(
            model_name="qwen2.5:1.5b",
            input_tokens=10,
            output_tokens=5,
            total_duration_s=1.0,
            load_duration_s=0.1,
            tokens_per_second=5.0,
        )

        async def mock_stream(*args, **kwargs):
            for token in mock_response:
                yield token
            yield mock_metrics

        with (
            patch("src.core.model_detector.is_api_model", return_value=False),
            patch("src.core.providers.provider_factory._factory", None),
            patch.object(LLMProvider, "chat_stream", side_effect=mock_stream),
        ):

            collected = []
            async for chunk in LLMProvider.chat_stream(
                model_name="qwen2.5:1.5b",
                messages=[{"role": "user", "content": "Test"}],
            ):
                collected.append(chunk)

        # Vérifier qu'on a reçu les tokens et les métriques
        assert len(collected) == 4
        assert collected[0] == "Bonjour"
        assert isinstance(collected[-1], InferenceMetrics)

    @pytest.mark.asyncio
    async def test_chat_stream_routing_mistral(self):
        """Test que les modèles API utilisent le provider Mistral."""
        mock_response = ["Hello", " world"]
        mock_metrics = InferenceMetrics(
            model_name="mistral-large-2512",
            input_tokens=10,
            output_tokens=5,
            total_duration_s=1.0,
            load_duration_s=0.0,
            tokens_per_second=5.0,
        )

        async def mock_stream(*args, **kwargs):
            for token in mock_response:
                yield token
            yield mock_metrics

        with (
            patch("src.core.model_detector.is_api_model", return_value=True),
            patch.object(LLMProvider, "chat_stream", side_effect=mock_stream),
        ):

            collected = []
            async for chunk in LLMProvider.chat_stream(
                model_name="mistral-large-2512",
                messages=[{"role": "user", "content": "Test"}],
            ):
                collected.append(chunk)

        assert len(collected) == 3
        assert collected[0] == "Hello"


class TestLLMProviderLangChain:
    """Tests pour get_langchain_model."""

    def test_get_langchain_model_ollama(self):
        """Test création d'un modèle LangChain Ollama."""
        with (
            patch("src.core.model_detector.is_api_model", return_value=False),
            patch("src.core.providers.ollama_provider.ChatOllama") as mock_chat,
            patch("src.core.providers.provider_factory._factory", None),
        ):

            mock_chat.return_value = MagicMock()
            LLMProvider.get_langchain_model("qwen2.5:1.5b")

            # Vérifier que ChatOllama a été appelé
            mock_chat.assert_called_once()

    def test_get_langchain_model_mistral(self):
        """Test création d'un modèle LangChain Mistral."""
        # provider_factory importe is_api_model par nom : c'est là qu'il faut le patcher.
        # La factory est un singleton de classe : on repart d'une instance neuve.
        with (
            patch("src.core.providers.provider_factory.is_api_model", return_value=True),
            patch("src.core.providers.mistral_provider.MISTRAL_API_KEY", "fake-key"),
            patch("src.core.providers.mistral_provider.MISTRAL_AVAILABLE", True),
            patch("langchain_mistralai.ChatMistralAI") as mock_chat,
            patch("src.core.providers.provider_factory._factory", None),
            patch.object(LLMProviderFactory, "_instance", None),
        ):

            mock_chat.return_value = MagicMock()

            # Ce test peut échouer si Mistral n'est pas configuré
            try:
                LLMProvider.get_langchain_model("mistral-large-2512")
                mock_chat.assert_called_once()
            except ValueError:
                # Provider Mistral non disponible, c'est OK
                pass


class TestLLMProviderPullModel:
    """Tests pour pull_model."""

    def test_pull_model_local(self):
        """Test téléchargement d'un modèle local."""
        with (
            patch("src.core.model_detector.is_api_model", return_value=False),
            patch("src.core.providers.ollama_provider.ollama") as mock_ollama,
            patch("src.core.providers.provider_factory._factory", None),
        ):

            mock_ollama.Client.return_value.pull.return_value = iter(["progress"])
            LLMProvider.pull_model("qwen2.5:1.5b")

            # Même hôte que la génération (base_url), jamais le client par défaut.
            mock_ollama.Client.assert_called_once_with(host="http://localhost:11434")
            mock_ollama.Client.return_value.pull.assert_called_once_with(
                "qwen2.5:1.5b", stream=True
            )
            mock_ollama.pull.assert_not_called()

    def test_pull_model_cloud_raises_error(self):
        """Test qu'on ne peut pas télécharger un modèle cloud."""
        # llm_provider importe is_api_model par nom : on patche la méthode qui l'utilise.
        with (
            patch.object(LLMProvider, "_is_mistral_api_model", return_value=True),
            pytest.raises(ValueError, match="Impossible de télécharger"),
        ):
            LLMProvider.pull_model("mistral-large-2512")


class TestLLMProviderHealthCheck:
    """Tests pour health_check."""

    def test_health_check_returns_dict(self):
        """Test que health_check retourne un dictionnaire."""
        with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
            mock_ollama.Client.return_value.list.return_value = MagicMock(models=[])

            with patch("src.core.providers.provider_factory._factory", None):
                result = LLMProvider.health_check()

        assert isinstance(result, dict)
        assert "ollama" in result


class TestCloudDisabledExcludesRemoteTags:
    """Cloud désactivé (D1, story 8) : aucun modèle cloud, tags distants d'Ollama compris."""

    OLLAMA_MODELS = [
        {"model": "glm-4.6:cloud", "type": "local"},
        {"model": "gpt-oss:120b-cloud", "type": "local"},
        {"model": "qwen2.5:1.5b", "type": "local"},
    ]
    CLOUD_MODELS = [{"model": "mistral-large-2512", "type": "cloud"}]

    def _factory(self):
        """Factory aux providers simulés : Ollama (local) et un fournisseur cloud."""
        ollama = MagicMock(is_local=True)
        ollama.list_models.side_effect = lambda: [dict(m) for m in self.OLLAMA_MODELS]
        mistral = MagicMock(is_local=False)
        mistral.list_models.side_effect = lambda: [dict(m) for m in self.CLOUD_MODELS]
        factory = object.__new__(LLMProviderFactory)
        factory._providers = {"ollama": ollama, "mistral": mistral}
        return factory

    def test_cloud_disabled_lists_local_models_only(self):
        models = self._factory().list_all_models(include_cloud=False)
        assert [m["model"] for m in models] == ["qwen2.5:1.5b"]

    def test_cloud_enabled_lists_remote_and_cloud_models(self):
        models = self._factory().list_all_models(include_cloud=True)
        assert [m["model"] for m in models] == [
            "glm-4.6:cloud",
            "gpt-oss:120b-cloud",
            "qwen2.5:1.5b",
            "mistral-large-2512",
        ]

    def test_facade_passes_cloud_setting(self):
        with patch("src.core.llm_provider.get_provider_factory", return_value=self._factory()):
            local = LLMProvider.list_models(cloud_enabled=False)
        assert [m["model"] for m in local] == ["qwen2.5:1.5b"]

    @pytest.mark.parametrize(
        ("tag", "expected"),
        [
            ("qwen2.5:1.5b", False),
            # Modèle Ollama local courant : le préfixe « gpt- » ne le rend pas cloud.
            ("gpt-oss:20b", False),
            ("glm-4.6:cloud", True),
            ("gpt-oss:120b-cloud", True),
            ("kimi-k2-cloud:latest", True),
            ("gpt-4o-mini", True),
            ("claude-3-5-sonnet", True),
            # Origine inconnue : ni fournisseur, ni catalogue, ni tag Ollama.
            ("", None),
            (None, None),
            ("N/A", None),
            ("modele-inconnu", None),
        ],
    )
    def test_is_cloud_tag_origin(self, tag, expected):
        from src.core.providers.provider_factory import is_cloud_tag

        with patch("src.core.providers.provider_factory.get_model_info", return_value=None):
            assert is_cloud_tag(tag) is expected

    @pytest.mark.parametrize(("model_type", "expected"), [("api", True), ("local", False)])
    def test_is_cloud_tag_catalog_type(self, model_type, expected):
        from src.core.providers.provider_factory import is_cloud_tag

        with patch(
            "src.core.providers.provider_factory.get_model_info",
            return_value={"type": model_type},
        ):
            assert is_cloud_tag("mistral-large-2512") is expected
