"""
Tests unitaires des états vrais (story 5) : erreurs levées par chat_stream, état d'Ollama sur
l'hôte réellement utilisé, modèle en mémoire, détection de l'accélérateur, note du juge de
l'Arène et classement. Ollama et NVML sont simulés : aucun réseau.

Usage: python -m pytest tests/unit/test_failure_states.py -v
"""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.core import accelerator
from src.core.llm_provider import LLMProvider
from src.core.providers.ollama_provider import OllamaProvider
from src.core.providers.provider_factory import LLMProviderFactory


@pytest.fixture(autouse=True)
def isolated_provider_factory():
    """Factory neuve, sans clé d'API réelle : aucun fournisseur cloud, aucun appel réseau."""
    with (
        patch("src.core.providers.mistral_provider.MISTRAL_API_KEY", None),
        patch("src.core.providers.openai_provider.OPENAI_API_KEY", ""),
        patch("src.core.providers.anthropic_provider.ANTHROPIC_API_KEY", ""),
        patch("src.core.providers.provider_factory._factory", None),
        patch.object(LLMProviderFactory, "_instance", None),
        patch.dict(LLMProviderFactory._providers, clear=True),
    ):
        yield


# ---------------------------------------------------------------------------
# chat_stream : une erreur n'est jamais un token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_raises_when_provider_unavailable():
    """Fournisseur indisponible : ValueError levée, pas de texte « Erreur : … »."""
    factory = MagicMock()
    factory.get_provider.side_effect = ValueError("Modèle OpenAI gpt-4o demandé")
    with patch("src.core.llm_provider.get_provider_factory", return_value=factory):
        chunks = []
        with pytest.raises(ValueError, match="gpt-4o"):
            async for chunk in LLMProvider.chat_stream("gpt-4o", [{"role": "user"}]):
                chunks.append(chunk)
    assert chunks == []


@pytest.mark.asyncio
async def test_chat_stream_propagates_provider_errors():
    async def failing(**kwargs):
        raise ConnectionError("Connection refused")
        yield  # pragma: no cover

    provider = MagicMock()
    provider.chat_stream = failing
    factory = MagicMock()
    factory.get_provider.return_value = provider
    with (
        patch("src.core.llm_provider.get_provider_factory", return_value=factory),
        pytest.raises(ConnectionError),
    ):
        async for _ in LLMProvider.chat_stream("qwen2.5:1.5b", [{"role": "user"}]):
            pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "cls_name"),
    [
        ("src.core.providers.openai_provider", "OpenAIProvider"),
        ("src.core.providers.anthropic_provider", "AnthropicProvider"),
        ("src.core.providers.mistral_provider", "MistralProvider"),
    ],
)
async def test_cloud_provider_unavailable_raises(module, cls_name):
    """Fournisseur cloud sans clé : ValueError, jamais un token « Erreur : … »."""
    import importlib

    provider_cls = getattr(importlib.import_module(module), cls_name)
    provider = provider_cls.__new__(provider_cls)
    with (
        patch.object(provider_cls, "is_available", new=property(lambda self: False)),
        pytest.raises(ValueError, match="non disponible"),
    ):
        async for _ in provider.chat_stream("model", [{"role": "user", "content": "Q"}]):
            pass


# ---------------------------------------------------------------------------
# État d'Ollama : hôte réellement utilisé, délai court
# ---------------------------------------------------------------------------


def test_health_check_uses_base_url_and_short_timeout():
    provider = OllamaProvider(base_url="http://127.0.0.1:11999")
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        assert provider.health_check() is True
    mock_ollama.Client.assert_called_once_with(host="http://127.0.0.1:11999", timeout=2.0)
    mock_ollama.Client.return_value.list.assert_called_once()
    # Jamais le client par défaut (hôte OLLAMA_HOST, sans délai).
    mock_ollama.list.assert_not_called()


def test_list_and_pull_use_base_url():
    """Liste et téléchargement visent le même hôte que la génération et la santé."""
    provider = OllamaProvider(base_url="http://127.0.0.1:11999")
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.list.return_value = SimpleNamespace(
            models=[{"model": "qwen2.5:1.5b"}]
        )
        assert [m["model"] for m in provider.list_models()] == ["qwen2.5:1.5b"]
        provider.pull_model("gemma3:1b")
    hosts = {c.kwargs["host"] for c in mock_ollama.Client.call_args_list}
    assert hosts == {"http://127.0.0.1:11999"}
    mock_ollama.Client.return_value.pull.assert_called_once_with("gemma3:1b", stream=True)
    mock_ollama.list.assert_not_called()
    mock_ollama.pull.assert_not_called()


def test_health_check_false_when_ollama_down():
    provider = OllamaProvider()
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.list.side_effect = ConnectionError("refused")
        assert provider.health_check() is False


@pytest.mark.parametrize(
    ("ps_models", "tag", "expected"),
    [
        ([{"model": "qwen2.5:1.5b", "size_vram": 1}], "qwen2.5:1.5b", True),
        ([SimpleNamespace(model="qwen2.5:1.5b", name="qwen2.5:1.5b")], "qwen2.5:1.5b", True),
        ([{"model": "llama3:latest"}], "llama3", True),
        ([{"model": "gemma3:1b"}], "qwen2.5:1.5b", False),
        ([], "qwen2.5:1.5b", False),
    ],
)
def test_is_model_loaded_reads_ps(ps_models, tag, expected):
    provider = OllamaProvider()
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.ps.return_value = SimpleNamespace(models=ps_models)
        assert provider.is_model_loaded(tag) is expected


def test_is_model_loaded_unknown_when_ps_fails():
    """`ps()` en échec : None (ni indicateur ni erreur), jamais d'exception."""
    provider = OllamaProvider()
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.ps.side_effect = ConnectionError("refused")
        assert provider.is_model_loaded("qwen2.5:1.5b") is None


def test_ollama_available_queries_ollama_only():
    """État « Système » : seul Ollama est interrogé, jamais un fournisseur cloud."""
    cloud = MagicMock()
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        LLMProviderFactory()._providers["anthropic"] = cloud
        assert LLMProvider.ollama_available() is True
        mock_ollama.Client.return_value.list.side_effect = ConnectionError("refused")
        assert LLMProvider.ollama_available() is False
    cloud.health_check.assert_not_called()


def test_is_model_loaded_none_for_cloud_models():
    """Modèle cloud (fournisseur présent ou non) : None, sans appeler `ollama ps`."""
    openai = MagicMock(provider_name="openai")
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        assert LLMProvider.is_model_loaded("gpt-4o") is None  # fournisseur absent
        LLMProviderFactory()._providers["openai"] = openai
        assert LLMProvider.is_model_loaded("gpt-4o") is None
        assert LLMProvider.is_model_loaded("") is None
    mock_ollama.Client.return_value.ps.assert_not_called()
    openai.is_model_loaded.assert_not_called()


def test_is_model_loaded_for_local_model():
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.ps.return_value = {"models": [{"name": "qwen2.5:1.5b"}]}
        assert LLMProvider.is_model_loaded("qwen2.5:1.5b") is True
        assert LLMProvider.is_model_loaded("gemma3:1b") is False


GIB = 1024**3


@pytest.mark.parametrize(
    ("ps_models", "tag", "expected"),
    [
        ([{"model": "qwen2.5:1.5b", "size": int(2.5 * GIB)}], "qwen2.5:1.5b", 2.5),
        (
            [SimpleNamespace(model="llama3:latest", name="llama3:latest", size=GIB)],
            "llama3",
            1.0,
        ),
        ([{"model": "gemma3:1b", "size": GIB}], "qwen2.5:1.5b", None),  # tag absent
        ([{"model": "qwen2.5:1.5b", "size": 0}], "qwen2.5:1.5b", None),  # taille nulle
        ([{"model": "qwen2.5:1.5b", "size": -5}], "qwen2.5:1.5b", None),
        ([{"model": "qwen2.5:1.5b"}], "qwen2.5:1.5b", None),  # taille absente
        ([], "qwen2.5:1.5b", None),
    ],
)
def test_loaded_model_size_reads_ps(ps_models, tag, expected):
    """Taille chargée d'un modèle (`ollama ps`, champ `size`) en Go ; None sinon, jamais 0."""
    provider = OllamaProvider()
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.ps.return_value = SimpleNamespace(models=ps_models)
        size = provider.loaded_model_size_gb(tag)
    assert size == (pytest.approx(expected) if expected is not None else None)


def test_loaded_model_size_unknown_when_ps_fails():
    provider = OllamaProvider()
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.ps.side_effect = ConnectionError("refused")
        assert provider.loaded_model_size_gb("qwen2.5:1.5b") is None


def test_llm_provider_loaded_model_size():
    """Modèle local : taille lue dans `ps` ; modèle cloud ou tag vide : None, sans `ps`."""
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.ps.return_value = {
            "models": [{"name": "qwen2.5:1.5b", "size": int(2.5 * GIB)}]
        }
        assert LLMProvider.loaded_model_size_gb("qwen2.5:1.5b") == pytest.approx(2.5)
        assert LLMProvider.loaded_model_size_gb("gemma3:1b") is None
        mock_ollama.Client.return_value.ps.side_effect = ConnectionError("refused")
        assert LLMProvider.loaded_model_size_gb("qwen2.5:1.5b") is None

    openai = MagicMock(provider_name="openai")
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        LLMProviderFactory()._providers["openai"] = openai
        assert LLMProvider.loaded_model_size_gb("gpt-4o") is None
        assert LLMProvider.loaded_model_size_gb("") is None
    mock_ollama.Client.return_value.ps.assert_not_called()
    openai.loaded_model_size_gb.assert_not_called()


def test_llm_provider_loaded_model_size_none_for_remote_tag():
    """Tag distant servi par Ollama (`glm-4.6:cloud`) : modèle cloud, None sans `ps`, même
    si `ps` le liste avec une taille."""
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.ps.return_value = {
            "models": [{"name": "glm-4.6:cloud", "size": GIB}]
        }
        assert LLMProvider.loaded_model_size_gb("glm-4.6:cloud") is None
    mock_ollama.Client.return_value.ps.assert_not_called()


def test_llm_provider_loaded_model_size_never_raises():
    with patch.object(
        LLMProvider, "_is_mistral_api_model", side_effect=RuntimeError("détecteur en échec")
    ):
        assert LLMProvider.loaded_model_size_gb("qwen2.5:1.5b") is None


# ---------------------------------------------------------------------------
# Accélérateur : NVML, puis Apple Silicon, sinon aucun
# ---------------------------------------------------------------------------


def _fake_pynvml(count=1, name=b"NVIDIA GeForce RTX 3060", init_error=None):
    fake = MagicMock()
    if init_error:
        fake.nvmlInit.side_effect = init_error
    fake.nvmlDeviceGetCount.return_value = count
    fake.nvmlDeviceGetName.return_value = name
    return fake


def test_nvidia_gpu_detected():
    fake = _fake_pynvml()
    with patch.dict(sys.modules, {"pynvml": fake}):
        info = accelerator.detect_accelerator()
    assert info == accelerator.AcceleratorInfo("nvidia", "NVIDIA GeForce RTX 3060")
    fake.nvmlShutdown.assert_called_once()


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ([b"NVIDIA A100", b"NVIDIA A100"], "2 × NVIDIA A100"),
        (["NVIDIA RTX 4090", "NVIDIA RTX 3060"], "NVIDIA RTX 4090 + NVIDIA RTX 3060"),
    ],
)
def test_several_nvidia_gpus(names, expected):
    """Plusieurs GPU NVIDIA : leur nombre ou leurs noms, pas seulement le premier."""
    fake = _fake_pynvml(count=len(names))
    fake.nvmlDeviceGetName.side_effect = names
    with patch.dict(sys.modules, {"pynvml": fake}):
        info = accelerator.detect_accelerator()
    assert info == accelerator.AcceleratorInfo("nvidia", expected)


def test_nvml_without_gpu_is_none():
    with (
        patch.dict(sys.modules, {"pynvml": _fake_pynvml(count=0)}),
        patch.object(accelerator, "is_apple_silicon", return_value=False),
    ):
        assert accelerator.detect_accelerator() == accelerator.NO_ACCELERATOR


def test_nvml_failure_is_none():
    """Pilote absent (NVMLError à l'initialisation) : « aucun », sans exception."""
    with (
        patch.dict(sys.modules, {"pynvml": _fake_pynvml(init_error=OSError("no driver"))}),
        patch.object(accelerator, "is_apple_silicon", return_value=False),
    ):
        info = accelerator.detect_accelerator()
    assert not info.detected


def test_apple_silicon_detected_without_nvml():
    with (
        patch.object(accelerator, "detect_nvidia_gpu", return_value=None),
        patch("src.core.accelerator.platform.system", return_value="Darwin"),
        patch("src.core.accelerator.platform.machine", return_value="arm64"),
    ):
        info = accelerator.detect_accelerator()
    assert info.kind == "apple"


def test_intel_mac_is_none():
    with (
        patch.object(accelerator, "detect_nvidia_gpu", return_value=None),
        patch("src.core.accelerator.platform.system", return_value="Darwin"),
        patch("src.core.accelerator.platform.machine", return_value="x86_64"),
    ):
        assert accelerator.detect_accelerator() == accelerator.NO_ACCELERATOR


# ---------------------------------------------------------------------------
# Juge de l'Arène et classement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("85", 85),
        ("Note : 85/100", 85),
        ("85 / 100", 85),
        ("score 85 sur 100", 85),
        ("Note sur 100 : 72", 72),
        ("**85**", 85),
        ("85.", 85),
        ("Note : 85", 85),
        ("Note finale : 90. Clair pour un enfant de 10 ans.", 90),
        ("100/100", 100),
        ("Précision 30/40, total 85/100", 85),
        # Pas de note clairement identifiable : « non évalué », jamais 0 ni le premier entier.
        ("", None),
        (None, None),
        ("Très bonne réponse.", None),
        ("150", None),
        ("8.5", None),
        ("8/10", None),
        ("Critère 1 : 20, critère 2 : 30, total : 85", None),
        # Nombre isolé du texte, négatif : jamais une note.
        ("Adapté à un enfant de 10 ans", None),
        ("La réponse vaut 0.", None),
        ("-5", None),
        ("-5/100", None),
        ("Note : -5", None),
        ("Note : 8,5", None),
        ("70/100 ou 80/100", None),
    ],
)
def test_parse_judge_score(reply, expected):
    from src.app.tabs.inference.arena import parse_judge_score

    assert parse_judge_score(reply) == expected


def test_rank_results_orders_scores_then_not_evaluated_then_failures():
    from src.app.tabs.inference.arena import (
        STATUS_FAILED,
        STATUS_NOT_EVALUATED,
        STATUS_SCORED,
        rank_results,
    )

    rows = [
        {"Modèle": "F", "Note": None, "Débit (t/s)": None, "status": STATUS_FAILED},
        {"Modèle": "N-lent", "Note": None, "Débit (t/s)": 10.0, "status": STATUS_NOT_EVALUATED},
        {"Modèle": "S-70", "Note": 70, "Débit (t/s)": 50.0, "status": STATUS_SCORED},
        {"Modèle": "N-rapide", "Note": None, "Débit (t/s)": 40.0, "status": STATUS_NOT_EVALUATED},
        {"Modèle": "S-90-lent", "Note": 90, "Débit (t/s)": 5.0, "status": STATUS_SCORED},
        {"Modèle": "S-90-rapide", "Note": 90, "Débit (t/s)": 30.0, "status": STATUS_SCORED},
    ]
    scored, not_evaluated, failed = rank_results(rows)
    assert [r["Modèle"] for r in scored] == ["S-90-rapide", "S-90-lent", "S-70"]
    assert [r["Modèle"] for r in not_evaluated] == ["N-rapide", "N-lent"]
    assert [r["Modèle"] for r in failed] == ["F"]


# ---------------------------------------------------------------------------
# États de l'interface (src/app/states.py)
# ---------------------------------------------------------------------------


def test_unavailable_ollama_is_not_cached(monkeypatch):
    """« Indisponible » n'est jamais mis en cache : recharger la page suffit à le lever."""
    import streamlit as st

    from src.app import states

    st.cache_data.clear()
    answers = iter([False, True, False])
    monkeypatch.setattr(
        LLMProvider, "ollama_available", staticmethod(lambda timeout=2.0: next(answers))
    )
    try:
        assert states.ollama_available() is False
        assert states.ollama_available() is True
        # « Disponible » est mis en cache quelques secondes : pas de nouvel appel.
        assert states.ollama_available() is True
    finally:
        st.cache_data.clear()


def test_failure_advice_depends_on_provider():
    from src.app.states import generation_failure_advice

    # Tags Ollama préfixés `gpt-` (story 22) : conseil Ollama, pas OpenAI.
    for tag in ("qwen2.5:1.5b", "gpt-oss:20b", "gpt-oss:120b-cloud"):
        advice = generation_failure_advice(tag)
        assert "Ollama" in advice and "OpenAI" not in advice
    for tag, name in (
        ("gpt-4o", "OpenAI"),
        ("o1-mini", "OpenAI"),
        ("claude-3-5-sonnet", "Anthropic"),
        ("openai/gpt-oss-120b", "Groq"),
    ):
        advice = generation_failure_advice(tag)
        assert name in advice and "Ollama" not in advice and "Local" in advice


def test_timeout_message_mentions_loading():
    from src.app.states import LOADING_HINT, inference_error_message
    from src.core.inference_service import InferenceResult

    result = InferenceResult("", "", None, None, error="Timeout", timed_out=True, timeout_s=120)
    message = inference_error_message(result, "qwen2.5:1.5b")
    assert message.startswith("Délai dépassé (2\u00a0min)")
    assert "chargement" in message
    # Aucune durée promise pour le premier chargement.
    assert not any(ch.isdigit() for ch in LOADING_HINT)
