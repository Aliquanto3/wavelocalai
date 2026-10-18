"""
Tests : modèles d'embedding exclus des sélecteurs, `is_api_model` sur les fournisseurs
cloud à préfixe, Ollama injoignable (pas de réinterrogation immédiate).
Usage: python -m pytest tests/unit/test_modeles_embedding_ollama_absent.py -v
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

import src.app.ui as ui
from src.core.model_defaults import is_embedding_model
from src.core.model_detector import is_api_model
from src.core.providers import ollama_provider
from src.core.providers.ollama_provider import OllamaProvider

# --- Point A : modèles d'embedding -------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ({"model": "nomic-embed-text:latest"}, True),
        ({"model": "mxbai-EMBED-large:335m"}, True),
        ({"name": "bge-m3-embedding"}, True),
        ({"model": "x:1b", "details": {"family": "nomic-bert"}}, True),
        ({"model": "qwen2.5:1.5b", "details": {"family": "qwen2"}}, False),
        ({"model": "qwen2.5:1.5b"}, False),
        ({"model": "gemma3:1b", "details": None}, False),
    ],
)
def test_is_embedding_model(model, expected):
    assert is_embedding_model(model) is expected


def test_model_menu_excludes_embedding_models(monkeypatch):
    monkeypatch.setattr(ui, "get_friendly_name_from_tag", lambda tag: tag)
    monkeypatch.setattr(ui, "available_memory_gb", lambda: 16.0)
    monkeypatch.setattr("src.core.model_defaults.load_versioned_catalog", lambda path=None: {})
    monkeypatch.setattr("src.core.model_defaults.MODELS_DB", {})
    monkeypatch.setattr(ui, "machine_benchmark", lambda: {})
    models = [
        {"model": "nomic-embed-text:latest", "type": "local", "size": 274_000_000},
        {"model": "qwen2.5:1.5b", "type": "local", "size": 986_000_000},
    ]

    menu = ui.model_menu(models)

    assert list(menu.display_to_tag.values()) == ["qwen2.5:1.5b"]
    assert all("embed" not in label.lower() for label in menu.labels)
    assert all("embed" not in label.lower() for label in menu.arena_defaults)


# --- Point B : is_api_model ------------------------------------------------------------


@pytest.mark.parametrize(
    "tag", ["claude-sonnet-5-5", "gpt-4o-mini", "o1-mini", "llama-3.1-8b-instant"]
)
def test_is_api_model_cloud_provider_without_warning(tag, caplog):
    with caplog.at_level(logging.WARNING, logger="src.core.model_detector"):
        assert is_api_model(tag) is True
    assert not caplog.records


@pytest.mark.parametrize("tag", ["gpt-oss:20b", "llama3.2:3b"])
def test_is_api_model_unknown_ollama_tag_stays_local(tag):
    assert is_api_model(tag) is False


def test_cloud_provider_name_keeps_provider_label():
    from src.app.states import _cloud_provider_name

    assert _cloud_provider_name("claude-sonnet-5-5") == "Anthropic"
    assert _cloud_provider_name("gpt-4o-mini") == "OpenAI"
    assert _cloud_provider_name("llama-3.1-8b-instant") == "Groq"
    assert _cloud_provider_name("qwen2.5:1.5b") is None


# --- Point C : Ollama injoignable ------------------------------------------------------


def test_ollama_down_is_not_requeried_immediately():
    provider = OllamaProvider()
    with patch.object(ollama_provider, "ollama") as mock_ollama:
        client = MagicMock()
        client.list.side_effect = ConnectionError("refused")
        mock_ollama.Client.return_value = client

        assert provider.list_models() == []
        assert provider.health_check() is False
        assert provider.list_models() == []

        # Une seule tentative (127.0.0.1 puis repli [::1]) : les suivantes sont court-circuitées.
        assert client.list.call_count == 2


def test_ollama_requeried_after_delay_and_recovers():
    provider = OllamaProvider()
    with patch.object(ollama_provider, "ollama") as mock_ollama:
        client = MagicMock()
        client.list.side_effect = ConnectionError("refused")
        mock_ollama.Client.return_value = client
        assert provider.health_check() is False

        provider._down_until = 0.0  # délai écoulé (horloge : test suivant)
        client.list.side_effect = None
        client.list.return_value = {"models": [{"model": "qwen2.5:1.5b"}]}

        assert provider.health_check() is True
        assert [m["model"] for m in provider.list_models()] == ["qwen2.5:1.5b"]


def test_list_all_models_keeps_cloud_when_ollama_down():
    from src.core.providers.provider_factory import LLMProviderFactory

    factory = LLMProviderFactory.__new__(LLMProviderFactory)
    cloud = MagicMock(is_local=False)
    cloud.list_models.return_value = [{"model": "claude-sonnet-5-5", "type": "cloud"}]
    local = OllamaProvider()
    factory._providers = {"ollama": local, "anthropic": cloud}
    with patch.object(ollama_provider, "ollama") as mock_ollama:
        mock_ollama.Client.return_value.list.side_effect = ConnectionError("refused")
        models = factory.list_all_models(include_cloud=True)

    assert [m["model"] for m in models] == ["claude-sonnet-5-5"]


def test_ollama_down_expires_with_clock():
    provider = OllamaProvider()
    with (
        patch.object(ollama_provider, "ollama") as mock_ollama,
        patch.object(ollama_provider.time, "monotonic", return_value=100.0) as clock,
    ):
        client = mock_ollama.Client.return_value
        client.list.side_effect = ConnectionError("refused")
        assert provider.health_check() is False
        calls = client.list.call_count

        clock.return_value = 100.0 + ollama_provider.DOWN_RETRY_S - 0.1
        assert provider.health_check() is False
        assert client.list.call_count == calls

        clock.return_value = 100.0 + ollama_provider.DOWN_RETRY_S
        client.list.side_effect = None
        client.list.return_value = {"models": []}
        assert provider.health_check() is True


@pytest.mark.parametrize(
    "error", [ollama_provider.httpx.ReadTimeout("busy"), ValueError("réponse illisible")]
)
def test_ollama_busy_or_other_error_not_memorized(error):
    """Un délai de lecture (Ollama occupé) ou une autre erreur ne masque pas les modèles
    locaux au rafraîchissement suivant."""
    provider = OllamaProvider()
    with patch.object(ollama_provider, "ollama") as mock_ollama:
        client = mock_ollama.Client.return_value
        client.list.side_effect = error
        assert provider.health_check() is False
        assert provider.list_models() == []

        client.list.side_effect = None
        client.list.return_value = {"models": [{"model": "qwen2.5:1.5b"}]}
        assert [m["model"] for m in provider.list_models()] == ["qwen2.5:1.5b"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:11434", ("http://127.0.0.1:11434", "http://[::1]:11434")),
        ("http://127.0.0.1:11999", ("http://127.0.0.1:11999", None)),
        ("http://gpu-box:11434", ("http://gpu-box:11434", None)),
        ("localhost:11434", ("localhost:11434", None)),
    ],
)
def test_localhost_targets_ipv4_first(url, expected):
    assert ollama_provider._ipv4_first(url) == expected


def test_localhost_falls_back_to_ipv6_and_keeps_it():
    """Ollama qui n'écoute qu'en IPv6 : 127.0.0.1 refusé, [::1] répond et est adopté."""
    provider = OllamaProvider()
    with patch.object(ollama_provider, "ollama") as mock_ollama:
        ok = MagicMock()
        ok.list.return_value = {"models": [{"model": "qwen2.5:1.5b"}]}
        refused = MagicMock()
        refused.list.side_effect = ConnectionError("refused")

        def client(host, **_kw):
            return ok if host.startswith("http://[::1]") else refused

        mock_ollama.Client.side_effect = client
        assert provider.health_check() is True
        assert provider._base_url == "http://[::1]:11434"
        assert [m["model"] for m in provider.list_models()] == ["qwen2.5:1.5b"]
        assert refused.list.call_count == 1


def test_localhost_both_refused_marks_down_and_keeps_ipv4():
    provider = OllamaProvider()
    with patch.object(ollama_provider, "ollama") as mock_ollama:
        mock_ollama.Client.return_value.list.side_effect = ConnectionError("refused")
        assert provider.health_check() is False
        assert mock_ollama.Client.return_value.list.call_count == 2
        assert provider._base_url == "http://127.0.0.1:11434"
        assert provider.list_models() == []
        assert mock_ollama.Client.return_value.list.call_count == 2
