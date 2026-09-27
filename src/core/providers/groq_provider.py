"""
Provider Groq : API compatible OpenAI (https://api.groq.com/openai/v1), clé `GROQ_API_KEY`.

Réutilise le SDK `openai` (et `langchain_openai`) avec une URL de base propre : aucune
dépendance supplémentaire. Actif seulement si la clé est configurée ; ses modèles ne sont
listés que si le cloud est autorisé (LLMProviderFactory.list_all_models).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from src.core.providers import openai_provider
from src.core.providers.openai_provider import OpenAIProvider

if TYPE_CHECKING:
    from openai import AsyncOpenAI

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Modèles de chat en production chez Groq (documentation publique, vérifiée le 27/09/2026) :
# ni aperçu (preview), ni transcription. Un tag est routé vers Groq par appartenance exacte à
# cette liste (un tag Ollama comme `llama3.2:3b` reste local).
GROQ_MODELS: dict[str, dict[str, Any]] = {
    "openai/gpt-oss-120b": {"name": "GPT-OSS 120B", "params": "?", "context": 131072},
    "openai/gpt-oss-20b": {"name": "GPT-OSS 20B", "params": "?", "context": 131072},
    "llama-3.3-70b-versatile": {
        "name": "Llama 3.3 70B Versatile",
        "params": "?",
        "context": 131072,
    },
    "llama-3.1-8b-instant": {"name": "Llama 3.1 8B Instant", "params": "?", "context": 131072},
}


def is_groq_model(model_tag: str | None) -> bool:
    """Tag servi par Groq : appartenance exacte à `GROQ_MODELS`."""
    return bool(model_tag) and model_tag in GROQ_MODELS


class GroqProvider(OpenAIProvider):
    """Provider Groq, sur le modèle d'OpenAIProvider (même SDK, URL de base Groq). Le
    `chat_stream` hérité lève les erreurs de Groq (quota 429, clé invalide), jamais renvoyées
    comme un token."""

    DISPLAY_NAME = "Groq"
    AVAILABLE_MODELS = GROQ_MODELS

    def __init__(self, api_key: str | None = None):
        """
        Args:
            api_key: Clé API Groq (utilise GROQ_API_KEY par défaut)
        """
        self._api_key = api_key or GROQ_API_KEY
        self._client = None

    def _get_client(self) -> AsyncOpenAI:
        """Client `AsyncOpenAI` pointé sur Groq, créé au premier appel."""
        if self._client is None:
            if not openai_provider.OPENAI_AVAILABLE:
                raise ImportError("openai package not installed. Run: pip install openai")
            if not self._api_key:
                raise ValueError("Groq API key not configured")
            self._client = openai_provider._AsyncOpenAI(
                api_key=self._api_key, base_url=GROQ_BASE_URL
            )
        return self._client

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def is_available(self) -> bool:
        """Vérifie si le provider est configuré et disponible."""
        return openai_provider.OPENAI_AVAILABLE and bool(self._api_key)

    def list_models(self) -> list[dict[str, Any]]:
        """Liste les modèles Groq proposés (vide sans clé)."""
        models = super().list_models()
        for model in models:
            model["provider"] = self.provider_name
        return models

    def get_langchain_model(self, model_name: str, temperature: float = 0.7, **kwargs) -> Any:
        """Retourne un modèle LangChain `ChatOpenAI` pointé sur Groq."""
        if not self.is_available:
            raise ValueError("Provider Groq non disponible (clé API manquante)")

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            api_key=self._api_key,
            base_url=GROQ_BASE_URL,
            temperature=temperature,
            **kwargs,
        )

    def health_check(self) -> bool:
        """Vérifie si l'API Groq est accessible."""
        if not self.is_available:
            return False
        try:
            import openai

            client = openai.OpenAI(api_key=self._api_key, base_url=GROQ_BASE_URL)
            client.models.list()
            return True
        except Exception:
            return False
