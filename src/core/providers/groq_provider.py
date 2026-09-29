"""
Provider Groq : API compatible OpenAI (https://api.groq.com/openai/v1), clé `GROQ_API_KEY`.

Réutilise le SDK `openai` (et `langchain_openai`) avec une URL de base propre : aucune
dépendance supplémentaire. Actif seulement si la clé est configurée ; ses modèles ne sont
listés que si le cloud est autorisé (LLMProviderFactory.list_all_models).
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any

from src.core.providers import openai_provider
from src.core.providers.openai_provider import OpenAIProvider

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Appel `/models` : délai court, résultat gardé (succès pour la vie du provider, échec
# 10 minutes) pour ne jamais le relancer à chaque rerun de Streamlit.
MODELS_TIMEOUT_S = 5.0
MODELS_FAILURE_TTL_S = 600.0

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
        # Ids renvoyés par `/models` (None : pas encore obtenus ou échec) et instant de l'échec.
        self._accessible_ids: frozenset[str] | None = None
        self._failed_at: float | None = None

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

    def _fetch_model_ids(self) -> set[str]:
        """Ids des modèles accessibles à la clé (`GET /models`), délai borné à 5 s."""
        import openai

        # Aucun nouvel essai du SDK : le délai reste de 5 s, le client est fermé ensuite.
        with openai.OpenAI(
            api_key=self._api_key,
            base_url=GROQ_BASE_URL,
            timeout=MODELS_TIMEOUT_S,
            max_retries=0,
        ) as client:
            return {model.id for model in client.models.list()}

    def _accessible_model_ids(self) -> frozenset[str] | None:
        """Ids accessibles à la clé, gardés en mémoire ; None si `/models` a échoué (échec
        gardé 10 minutes avant un nouvel essai)."""
        if self._accessible_ids is not None:
            return self._accessible_ids
        now = time.monotonic()
        if self._failed_at is not None and now - self._failed_at < MODELS_FAILURE_TTL_S:
            return None
        try:
            self._accessible_ids = frozenset(self._fetch_model_ids())
            self._failed_at = None
        except Exception as e:
            logger.warning(f"Groq /models indisponible, liste fixe proposée : {e}")
            self._failed_at = now
        return self._accessible_ids

    def list_models(self) -> list[dict[str, Any]]:
        """Liste les modèles Groq proposés (vide sans clé) : ceux de la liste fixe accessibles
        à la clé d'après `/models`, ou toute la liste fixe si `/models` échoue."""
        models = super().list_models()
        if not models:
            return models
        accessible = self._accessible_model_ids()
        if accessible is not None:
            models = [m for m in models if m["model"] in accessible]
            if not models:
                logger.warning("Groq : aucun modèle de la liste fixe accessible à cette clé")
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
