"""
Routage du LLM de CrewAI par tag (hôte Ollama, Mistral cloud), sans réseau.

Usage: python -m pytest tests/unit/test_crew_engine_llm.py -q
"""

from types import SimpleNamespace

import pytest

from src.core import crew_engine
from src.core.crew_engine import CrewFactory

LOCAL_TAG = "qwen2.5:1.5b"


def test_ollama_llm_uses_ipv4_loopback_by_default():
    """L'hôte vient du provider Ollama : `localhost` y est déjà visé en 127.0.0.1."""
    llm = CrewFactory._get_native_llm(LOCAL_TAG)

    assert "127.0.0.1:11434" in llm.base_url
    assert "localhost" not in llm.base_url


def test_ollama_llm_follows_provider_host(monkeypatch):
    provider = SimpleNamespace(base_url="http://gpu-box:11500")
    factory = SimpleNamespace(get_provider_by_name=lambda name: provider)
    monkeypatch.setattr(crew_engine, "get_provider_factory", lambda: factory)

    llm = CrewFactory._get_native_llm(LOCAL_TAG)

    assert "gpu-box:11500" in llm.base_url


def test_ollama_base_url_falls_back_to_provider_default(monkeypatch):
    """Fabrique sans provider Ollama : hôte par défaut d'un OllamaProvider neuf."""
    factory = SimpleNamespace(get_provider_by_name=lambda name: None)
    monkeypatch.setattr(crew_engine, "get_provider_factory", lambda: factory)

    assert crew_engine._ollama_base_url() == "http://127.0.0.1:11434"
