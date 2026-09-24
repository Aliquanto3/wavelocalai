# tests/unit/test_provider_factory.py
"""Tests de la factory de providers."""

import pytest

from src.core.providers.provider_factory import LLMProviderFactory, get_provider_factory


class TestProviderFactory:
    """Vérifie le singleton et la logique de sélection."""

    def test_singleton_behavior(self) -> None:
        """La factory doit être un singleton unique."""
        f1 = get_provider_factory()
        f2 = get_provider_factory()
        assert f1 is f2

    @pytest.mark.parametrize(
        "tag, expected_name",
        [
            ("gpt-4o", "openai"),
            ("claude-3-5-sonnet", "anthropic"),
            ("qwen2.5:1.5b", "ollama"),
            ("mistral-large-2512", "mistral"),
        ],
    )
    def test_get_provider_routing(self, tag: str, expected_name: str) -> None:
        """Vérifie que le tag du modèle route vers le bon provider."""
        factory = get_provider_factory()
        # On ne teste que si le provider est chargé (dépend de vos clés API en test)
        if expected_name in factory.available_providers:
            provider = factory.get_provider(tag)
            assert provider.provider_name == expected_name
