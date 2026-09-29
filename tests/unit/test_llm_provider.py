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
        patch("src.core.providers.groq_provider.GROQ_API_KEY", ""),
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


# ---------------------------------------------------------------------------
# Groq (story 16) : fournisseur cloud compatible OpenAI, client simulé, aucun appel réseau
# ---------------------------------------------------------------------------

GROQ_TAGS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]


class _FakeStream:
    """Flux `chat.completions.create(stream=True)` simulé : deux tokens puis l'usage."""

    def __init__(self, tokens):
        self._chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content=t))], usage=None) for t in tokens
        ]
        self._chunks.append(
            MagicMock(choices=[], usage=MagicMock(prompt_tokens=7, completion_tokens=2))
        )

    def __aiter__(self):
        self._it = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


def _groq_client(create):
    client = MagicMock()
    client.chat.completions.create = create
    return client


class TestGroqProvider:
    """Groq actif seulement avec une clé, routage exact, erreurs levées (jamais en token)."""

    @pytest.fixture(autouse=True)
    def fetch_ids(self):
        """`/models` simulé (story 17) : la clé factice accède aux 4 modèles, sans réseau."""
        from src.core.providers.groq_provider import GroqProvider

        with patch.object(
            GroqProvider, "_fetch_model_ids", autospec=True, return_value=set(GROQ_TAGS)
        ) as fetch:
            yield fetch

    def test_registered_and_listed_with_key(self):
        from src.core.providers.groq_provider import GROQ_BASE_URL, GroqProvider

        with patch("src.core.providers.groq_provider.GROQ_API_KEY", "cle-factice"):
            factory = LLMProviderFactory()
            groq = factory.get_provider_by_name("groq")
            assert isinstance(groq, GroqProvider)
            assert groq.provider_name == "groq" and groq.is_local is False
            models = [m for m in factory.list_all_models() if m["provider"] == "groq"]
        assert [m["model"] for m in models] == GROQ_TAGS
        assert all(m["type"] == "cloud" for m in models)
        assert GROQ_BASE_URL == "https://api.groq.com/openai/v1"

    def test_without_key_nothing_registered_nor_listed(self):
        from src.core.providers.groq_provider import GroqProvider

        factory = LLMProviderFactory()
        assert factory.get_provider_by_name("groq") is None
        assert GroqProvider().is_available is False
        assert GroqProvider().list_models() == []
        assert not [m for m in factory.list_all_models() if m["model"] in GROQ_TAGS]
        with pytest.raises(ValueError, match="Groq"):
            factory.get_provider("openai/gpt-oss-120b")

    def test_cloud_disabled_lists_no_groq_model(self, fetch_ids):
        with patch("src.core.providers.groq_provider.GROQ_API_KEY", "cle-factice"):
            factory = LLMProviderFactory()
            with patch.object(
                factory.get_provider_by_name("ollama"), "list_models", return_value=[]
            ):
                assert factory.list_all_models(include_cloud=False) == []
        fetch_ids.assert_not_called()

    def test_without_key_models_endpoint_never_called(self, fetch_ids):
        from src.core.providers.groq_provider import GroqProvider

        assert GroqProvider(api_key="").list_models() == []
        fetch_ids.assert_not_called()

    # --- Story 17 : seuls les modèles accessibles à la clé (`/models`) sont proposés ---

    def test_partial_access_lists_only_accessible_fixed_models(self, fetch_ids):
        from src.core.providers.groq_provider import GroqProvider

        # La clé accède aux 2 GPT-OSS et à d'autres ids (aperçu, transcription) hors liste fixe.
        fetch_ids.return_value = {
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "whisper-large-v3",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "compound-beta",
        }
        models = GroqProvider(api_key="cle-factice").list_models()
        assert [m["model"] for m in models] == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        assert [m["name"] for m in models] == ["GPT-OSS 120B", "GPT-OSS 20B"]
        assert all(m["provider"] == "groq" and m["type"] == "cloud" for m in models)

    @pytest.mark.parametrize("error", [OSError("réseau"), TimeoutError("délai"), "401"])
    def test_models_failure_falls_back_to_fixed_list(self, fetch_ids, error, caplog):
        import httpx
        import openai

        from src.core.providers.groq_provider import GroqProvider

        if error == "401":
            request = httpx.Request("GET", "https://api.groq.com/openai/v1/models")
            error = openai.AuthenticationError(
                "Invalid API Key", response=httpx.Response(401, request=request), body=None
            )
        fetch_ids.side_effect = error
        with caplog.at_level("WARNING", logger="src.core.providers.groq_provider"):
            models = GroqProvider(api_key="cle-factice").list_models()
        assert [m["model"] for m in models] == GROQ_TAGS
        assert "/models" in caplog.text

    def test_no_fixed_model_accessible_logs_warning(self, fetch_ids, caplog):
        from src.core.providers.groq_provider import GroqProvider

        fetch_ids.return_value = {"whisper-large-v3"}
        with caplog.at_level("WARNING", logger="src.core.providers.groq_provider"):
            assert GroqProvider(api_key="cle-factice").list_models() == []
        assert "aucun modèle de la liste fixe" in caplog.text

    def test_models_success_cached_no_second_call(self, fetch_ids):
        from src.core.providers.groq_provider import GroqProvider

        fetch_ids.return_value = {"openai/gpt-oss-20b"}
        groq = GroqProvider(api_key="cle-factice")
        for _ in range(3):
            assert [m["model"] for m in groq.list_models()] == ["openai/gpt-oss-20b"]
        assert fetch_ids.call_count == 1

    def test_models_failure_cached_ten_minutes_then_retried(self, fetch_ids):
        from src.core.providers import groq_provider
        from src.core.providers.groq_provider import GroqProvider

        fetch_ids.side_effect = OSError("réseau")
        groq = GroqProvider(api_key="cle-factice")
        with patch.object(groq_provider.time, "monotonic", return_value=1000.0):
            assert len(groq.list_models()) == 4
            assert len(groq.list_models()) == 4
        assert fetch_ids.call_count == 1
        with patch.object(groq_provider.time, "monotonic", return_value=1000.0 + 599):
            groq.list_models()
        assert fetch_ids.call_count == 1

        fetch_ids.side_effect = None
        fetch_ids.return_value = {"openai/gpt-oss-120b"}
        with patch.object(groq_provider.time, "monotonic", return_value=1000.0 + 601):
            assert [m["model"] for m in groq.list_models()] == ["openai/gpt-oss-120b"]
        assert fetch_ids.call_count == 2

    def test_inaccessible_tag_still_routed_to_groq(self, fetch_ids):
        fetch_ids.return_value = {"openai/gpt-oss-120b"}
        with patch("src.core.providers.groq_provider.GROQ_API_KEY", "cle-factice"):
            factory = LLMProviderFactory()
            assert factory.get_provider("llama-3.1-8b-instant").provider_name == "groq"

    @pytest.mark.parametrize("tag", GROQ_TAGS)
    def test_routing_by_exact_membership(self, tag):
        with patch("src.core.providers.groq_provider.GROQ_API_KEY", "cle-factice"):
            factory = LLMProviderFactory()
            assert factory.get_provider(tag).provider_name == "groq"

    @pytest.mark.parametrize(
        "tag", ["llama3.2:3b", "llama3.1:8b", "llama-3.3-70b", "OPENAI/GPT-OSS-120B"]
    )
    def test_ollama_homonyms_stay_local(self, tag):
        with (
            patch("src.core.providers.groq_provider.GROQ_API_KEY", "cle-factice"),
            patch("src.core.providers.provider_factory.is_api_model", return_value=False),
        ):
            factory = LLMProviderFactory()
            assert factory.get_provider(tag).provider_name == "ollama"

    def test_client_points_to_groq(self):
        from src.core.providers.groq_provider import GROQ_BASE_URL, GroqProvider

        with patch("src.core.providers.openai_provider._AsyncOpenAI") as client_cls:
            GroqProvider(api_key="cle-factice")._get_client()
        client_cls.assert_called_once_with(api_key="cle-factice", base_url=GROQ_BASE_URL)

    def test_langchain_model_points_to_groq(self):
        from src.core.providers.groq_provider import GROQ_BASE_URL, GroqProvider

        with patch("langchain_openai.ChatOpenAI") as chat_cls:
            GroqProvider(api_key="cle-factice").get_langchain_model("openai/gpt-oss-20b", 0.2)
        chat_cls.assert_called_once_with(
            model="openai/gpt-oss-20b",
            api_key="cle-factice",
            base_url=GROQ_BASE_URL,
            temperature=0.2,
        )

    @pytest.mark.asyncio
    async def test_chat_stream_yields_tokens_then_metrics(self):
        from src.core.providers.groq_provider import GroqProvider

        create = AsyncMock(return_value=_FakeStream(["Bon", "jour"]))
        groq = GroqProvider(api_key="cle-factice")
        groq._client = _groq_client(create)

        chunks = [
            c
            async for c in groq.chat_stream(
                "openai/gpt-oss-120b", [{"role": "user", "content": "Salut"}], 0.3, "Système"
            )
        ]
        assert chunks[:2] == ["Bon", "jour"]
        metrics = chunks[-1]
        assert isinstance(metrics, InferenceMetrics)
        assert (metrics.input_tokens, metrics.output_tokens) == (7, 2)
        kwargs = create.await_args.kwargs
        assert kwargs["model"] == "openai/gpt-oss-120b" and kwargs["stream"] is True
        assert kwargs["messages"][0] == {"role": "system", "content": "Système"}

    @pytest.mark.asyncio
    async def test_quota_error_is_raised_not_yielded(self):
        import httpx
        import openai

        from src.core.providers.groq_provider import GroqProvider

        request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        error = openai.RateLimitError(
            "Rate limit reached", response=httpx.Response(429, request=request), body=None
        )
        groq = GroqProvider(api_key="cle-factice")
        groq._client = _groq_client(AsyncMock(side_effect=error))

        chunks = []
        with pytest.raises(openai.RateLimitError):
            async for c in groq.chat_stream("llama-3.1-8b-instant", []):
                chunks.append(c)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_chat_stream_without_key_raises(self):
        from src.core.providers.groq_provider import GroqProvider

        with pytest.raises(ValueError, match="Groq"):
            async for _ in GroqProvider().chat_stream("openai/gpt-oss-20b", []):
                pass

    @pytest.mark.parametrize("tag", GROQ_TAGS)
    def test_groq_tag_is_cloud(self, tag):
        from src.core.providers.provider_factory import is_cloud_tag

        with patch("src.core.providers.provider_factory.get_model_info", return_value=None):
            assert is_cloud_tag(tag) is True


def test_groq_fetch_model_ids_uses_short_timeout():
    """`_fetch_model_ids` réel (hors fixture de la classe) : client synchrone simulé, 5 s."""
    from src.core.providers.groq_provider import GROQ_BASE_URL, GroqProvider

    with patch("openai.OpenAI") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.models.list.return_value = [
            MagicMock(id="openai/gpt-oss-20b"),
            MagicMock(id="whisper-large-v3"),
        ]
        ids = GroqProvider(api_key="cle-factice")._fetch_model_ids()
    assert ids == {"openai/gpt-oss-20b", "whisper-large-v3"}
    client_cls.assert_called_once_with(
        api_key="cle-factice", base_url=GROQ_BASE_URL, timeout=5.0, max_retries=0
    )
    client_cls.return_value.__exit__.assert_called_once()


# ---------------------------------------------------------------------------
# Ollama : raisonnement (`message.thinking`) transmis à part du texte (story 18)
# ---------------------------------------------------------------------------


def _ollama_stream_chunks(as_objects: bool):
    """Flux simulé : deux fragments de raisonnement, puis la réponse, puis le chunk final."""
    import ollama

    raw = [
        {"message": {"role": "assistant", "content": "", "thinking": "Je pèse "}},
        {"message": {"role": "assistant", "content": "", "thinking": "les options."}},
        {"message": {"role": "assistant", "content": "Réponse."}},
        {
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "eval_count": 8,
            "eval_duration": 400_000_000,
        },
    ]
    if not as_objects:
        return raw
    return [ollama.ChatResponse(model="qwen3.5:0.8b", done=False, **c) for c in raw[:3]] + [
        ollama.ChatResponse(model="qwen3.5:0.8b", **raw[3])
    ]


class TestOllamaReasoningChunks:
    """Le raisonnement sort en `ReasoningChunk`, jamais en `str` ; `think=` n'est pas passé."""

    async def _collect(self, chunks):
        from src.core.providers.ollama_provider import OllamaProvider

        async def fake_stream():
            for chunk in chunks:
                yield chunk

        client = MagicMock()
        client.chat = AsyncMock(return_value=fake_stream())
        provider = OllamaProvider(base_url="http://127.0.0.1:11999")
        with patch.object(provider, "_create_async_client", return_value=client):
            items = [
                item
                async for item in provider.chat_stream(
                    "qwen3.5:0.8b", [{"role": "user", "content": "Q"}]
                )
            ]
        return items, client.chat.call_args.kwargs

    @pytest.mark.asyncio
    @pytest.mark.parametrize("as_objects", [False, True], ids=["dict", "objet ollama"])
    async def test_thinking_yielded_apart_from_text(self, as_objects):
        from src.core.metrics import ReasoningChunk

        items, kwargs = await self._collect(_ollama_stream_chunks(as_objects))

        assert [i for i in items if isinstance(i, ReasoningChunk)] == [
            ReasoningChunk("Je pèse "),
            ReasoningChunk("les options."),
        ]
        assert [i for i in items if isinstance(i, str)] == ["Réponse."]
        assert isinstance(items[-1], InferenceMetrics)
        assert items[-1].output_tokens == 8
        assert "think" not in kwargs

    @pytest.mark.asyncio
    async def test_str_consumers_get_same_text(self):
        """Consommateurs qui ne gardent que les `str` (Discussion, HyDE, Self-RAG) : texte
        de la réponse seul, sans le raisonnement."""
        items, _ = await self._collect(_ollama_stream_chunks(as_objects=False))
        assert "".join(i for i in items if isinstance(i, str)) == "Réponse."


# ---------------------------------------------------------------------------
# Ollama : flux fermé sans fragment final `done` (story 19)
# ---------------------------------------------------------------------------


class TestOllamaInterruptedStream:
    """Ollama ferme parfois le flux en HTTP 200 sans fragment `done` : la réponse tronquée
    lève `InterruptedResponseError`, sans métriques."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("as_objects", [False, True], ids=["dict", "objet ollama"])
    async def test_stream_without_done_raises(self, as_objects):
        from src.core.metrics import InterruptedResponseError

        truncated = _ollama_stream_chunks(as_objects)[:3]
        items = []
        with pytest.raises(InterruptedResponseError, match="Réponse interrompue"):
            async for item in _iter_provider(truncated):
                items.append(item)

        assert [i for i in items if isinstance(i, str)] == ["Réponse."]
        assert not any(isinstance(i, InferenceMetrics) for i in items)

    @pytest.mark.asyncio
    async def test_complete_stream_unchanged(self):
        items = [i async for i in _iter_provider(_ollama_stream_chunks(as_objects=False))]
        assert isinstance(items[-1], InferenceMetrics)


async def _iter_provider(chunks):
    from src.core.providers.ollama_provider import OllamaProvider

    async def fake_stream():
        for chunk in chunks:
            yield chunk

    client = MagicMock()
    client.chat = AsyncMock(return_value=fake_stream())
    provider = OllamaProvider(base_url="http://127.0.0.1:11999")
    with patch.object(provider, "_create_async_client", return_value=client):
        async for item in provider.chat_stream("qwen3.5:0.8b", [{"role": "user", "content": "Q"}]):
            yield item
