from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic

from src.core.interfaces import ILLMProvider
from src.core.metrics import InferenceMetrics, MetricsCalculator

logger = logging.getLogger(__name__)

# Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Import conditionnel pour le runtime
try:
    from anthropic import AsyncAnthropic as _AsyncAnthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    _AsyncAnthropic = None
    ANTHROPIC_AVAILABLE = False


class AnthropicProvider(ILLMProvider):
    """
    Provider pour les modèles Anthropic (Claude).
    """

    # Modèles disponibles avec leurs métadonnées
    AVAILABLE_MODELS = {
        "claude-opus-5-5": {"name": "Claude Opus 5.5", "params": "?", "context": 1000000},
        "claude-sonnet-5-5": {"name": "Claude Sonnet 5.5", "params": "?", "context": 1000000},
        "claude-haiku-5-5": {"name": "Claude Haiku 5.5", "params": "?", "context": 1000000},
        "claude-fable-5-1": {"name": "Claude Fable 5.1", "params": "?", "context": 1000000},
    }

    def __init__(self, api_key: str | None = None):
        """
        Initialise le provider Anthropic.

        Args:
            api_key: Clé API Anthropic (utilise ANTHROPIC_API_KEY par défaut)
        """
        self._api_key = api_key or ANTHROPIC_API_KEY
        self._client = None

    def _get_client(self) -> AsyncAnthropic:
        """Lazy initialization du client."""
        if self._client is None:
            if not ANTHROPIC_AVAILABLE:
                raise ImportError("anthropic package not installed. Run: pip install anthropic")
            if not self._api_key:
                raise ValueError("Anthropic API key not configured")
            self._client = _AsyncAnthropic(api_key=self._api_key)
        return self._client

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def is_local(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        """Vérifie si le provider est configuré et disponible."""
        return ANTHROPIC_AVAILABLE and bool(self._api_key)

    def list_models(self) -> list[dict[str, Any]]:
        """Liste les modèles Anthropic disponibles."""
        if not self.is_available:
            return []

        models = []
        for model_id, info in self.AVAILABLE_MODELS.items():
            models.append(
                {
                    "model": model_id,
                    "name": info["name"],
                    "type": "cloud",
                    "provider": "anthropic",
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
        """Génère une réponse en streaming via l'API Anthropic."""

        if not self.is_available:
            # Une erreur n'est jamais renvoyée comme un token : l'appelant l'affiche.
            raise ValueError(
                "Provider Anthropic non disponible (clé API manquante ou SDK non installé)."
            )

        # Anthropic reçoit le system à part : on y réunit `system_prompt` et le contenu des
        # messages system (contexte RAG compris) ; le défaut ne sert que s'il n'y en a aucun.
        system_parts = [system_prompt] if system_prompt else []
        system_parts += [m.get("content") for m in messages if m.get("role") == "system"]
        system = (
            "\n\n".join(p for p in system_parts if isinstance(p, str) and p)
            or "You are a helpful assistant."
        )

        filtered_messages = [m for m in messages if m.get("role") != "system"]

        timer = MetricsCalculator()
        full_text = ""
        input_tokens = 0
        output_tokens = 0

        try:
            client = self._get_client()
            timer.start()

            # `temperature` est ignorée : le SDK 1.x ne l'accepte plus et les modèles
            # Claude actuels refusent les paramètres d'échantillonnage (erreur 400).
            async with client.messages.stream(
                model=model_name,
                max_tokens=4096,
                system=system,
                messages=filtered_messages,
            ) as stream:
                async for text in stream.text_stream:
                    full_text += text
                    yield text

                # Récupérer les métriques finales
                final_message = await stream.get_final_message()
                if final_message.usage:
                    input_tokens = final_message.usage.input_tokens
                    output_tokens = final_message.usage.output_tokens

            timer.stop()

            # Estimation si usage non disponible
            if output_tokens == 0:
                output_tokens = len(full_text) // 4

            duration = timer.duration
            tokens_per_second = output_tokens / duration if duration > 0 else 0

            yield InferenceMetrics(
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_duration_s=round(duration, 2),
                load_duration_s=0,
                tokens_per_second=round(tokens_per_second, 1),
                carbon_g=0.0,
            )

        except Exception as e:
            logger.error(f"Anthropic Error: {e}")
            raise e

    def get_langchain_model(self, model_name: str, temperature: float = 0.7, **kwargs) -> Any:
        """Retourne un modèle LangChain Anthropic."""
        if not self.is_available:
            raise ValueError("Provider Anthropic non disponible (clé API manquante)")

        from langchain_anthropic import ChatAnthropic

        # `temperature` reste dans la signature publique mais n'est pas transmise : les
        # modèles Claude actuels refusent les paramètres d'échantillonnage (erreur 400).
        return ChatAnthropic(model=model_name, api_key=self._api_key, **kwargs)

    def health_check(self) -> bool:
        """Vérifie si l'API Anthropic est accessible."""
        if not self.is_available:
            return False
        try:
            # Test simple avec un message minimal
            import anthropic

            client = anthropic.Anthropic(api_key=self._api_key)
            client.messages.create(
                model="claude-haiku-5-5",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return True
        except Exception:
            return False
