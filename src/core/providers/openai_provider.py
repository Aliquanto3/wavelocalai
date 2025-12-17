from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openai import AsyncOpenAI

from src.core.interfaces import ILLMProvider
from src.core.metrics import InferenceMetrics, MetricsCalculator

logger = logging.getLogger(__name__)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Import conditionnel pour le runtime
try:
    from openai import AsyncOpenAI as _AsyncOpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    _AsyncOpenAI = None
    OPENAI_AVAILABLE = False


class OpenAIProvider(ILLMProvider):
    """
    Provider pour les modèles OpenAI (GPT-4, GPT-3.5, etc.).
    """

    # Modèles disponibles avec leurs métadonnées
    AVAILABLE_MODELS = {
        "gpt-4o": {"name": "GPT-4o", "params": "?", "context": 128000},
        "gpt-4o-mini": {"name": "GPT-4o Mini", "params": "?", "context": 128000},
        "gpt-4-turbo": {"name": "GPT-4 Turbo", "params": "?", "context": 128000},
        "gpt-4": {"name": "GPT-4", "params": "?", "context": 8192},
        "gpt-3.5-turbo": {"name": "GPT-3.5 Turbo", "params": "?", "context": 16385},
    }

    def __init__(self, api_key: str | None = None):
        """
        Initialise le provider OpenAI.

        Args:
            api_key: Clé API OpenAI (utilise OPENAI_API_KEY par défaut)
        """
        self._api_key = api_key or OPENAI_API_KEY
        self._client = None

    def _get_client(self) -> AsyncOpenAI:
        """Lazy initialization du client."""
        if self._client is None:
            if not OPENAI_AVAILABLE:
                raise ImportError("openai package not installed. Run: pip install openai")
            if not self._api_key:
                raise ValueError("OpenAI API key not configured")
            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def is_local(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        """Vérifie si le provider est configuré et disponible."""
        return OPENAI_AVAILABLE and bool(self._api_key)

    def list_models(self) -> list[dict[str, Any]]:
        """Liste les modèles OpenAI disponibles."""
        if not self.is_available:
            return []

        models = []
        for model_id, info in self.AVAILABLE_MODELS.items():
            models.append(
                {
                    "model": model_id,
                    "name": info["name"],
                    "type": "cloud",
                    "provider": "openai",
                    "params": info["params"],
                    "context_length": info["context"],
                }
            )

        return models

    async def chat_stream(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str | InferenceMetrics, None]:
        """Génère une réponse en streaming via l'API OpenAI."""

        if not self.is_available:
            yield "❌ Erreur : Provider OpenAI non disponible (clé API manquante ou SDK non installé)."
            return

        final_messages = []
        if system_prompt:
            final_messages.append({"role": "system", "content": system_prompt})
        final_messages.extend(messages)

        timer = MetricsCalculator()
        full_text = ""
        prompt_tokens = 0
        completion_tokens = 0

        try:
            client = self._get_client()
            timer.start()

            stream = await client.chat.completions.create(
                model=model_name,
                messages=final_messages,
                temperature=temperature,
                stream=True,
                stream_options={"include_usage": True},
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_text += content
                    yield content

                # Récupérer l'usage si disponible
                if hasattr(chunk, "usage") and chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens or 0
                    completion_tokens = chunk.usage.completion_tokens or 0

            timer.stop()

            # Estimation si usage non disponible
            if completion_tokens == 0:
                completion_tokens = len(full_text) // 4

            duration = timer.duration
            tokens_per_second = completion_tokens / duration if duration > 0 else 0

            yield InferenceMetrics(
                model_name=model_name,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                total_duration_s=round(duration, 2),
                load_duration_s=0,
                tokens_per_second=round(tokens_per_second, 1),
                carbon_g=0.0,
            )

        except Exception as e:
            logger.error(f"OpenAI Error: {e}")
            raise e

    def get_langchain_model(self, model_name: str, temperature: float = 0.7, **kwargs) -> Any:
        """Retourne un modèle LangChain OpenAI."""
        if not self.is_available:
            raise ValueError("Provider OpenAI non disponible (clé API manquante)")

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name, api_key=self._api_key, temperature=temperature, **kwargs
        )

    def health_check(self) -> bool:
        """Vérifie si l'API OpenAI est accessible."""
        if not self.is_available:
            return False
        try:
            # Test simple : lister les modèles
            import openai

            client = openai.OpenAI(api_key=self._api_key)
            client.models.list()
            return True
        except Exception:
            return False
