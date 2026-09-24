# src/core/providers/base_provider.py
"""
Classe de base pour tous les providers LLM.
Implémente le pattern Template Method pour factoriser la logique commune.
"""

import logging
from abc import abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from src.core.interfaces import ILLMProvider
from src.core.metrics import InferenceMetrics, MetricsCalculator

logger = logging.getLogger(__name__)


class BaseProvider(ILLMProvider):
    """
    Provider abstrait avec implémentation commune de chat_stream.

    Les sous-classes doivent implémenter :
    - _stream_implementation() : logique spécifique au provider
    - _extract_metrics() : extraction des métriques spécifiques
    - provider_name, is_local, is_available, list_models, get_langchain_model, health_check
    """

    async def chat_stream(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str | InferenceMetrics, None]:
        """
        Génère une réponse en streaming (implémentation commune).

        Template Method : délègue la partie spécifique à _stream_implementation.
        """
        if not self.is_available:
            yield f"❌ Erreur : Provider {self.provider_name} non disponible"
            return

        # Préparation des messages avec system prompt
        final_messages = self._prepare_messages(messages, system_prompt)

        timer = MetricsCalculator()
        full_text = ""
        stream_metadata: dict[str, Any] = {}

        try:
            timer.start()

            async for chunk in self._stream_implementation(
                model_name, final_messages, temperature, stream_metadata
            ):
                full_text += chunk
                yield chunk

            timer.stop()

            yield self._build_metrics(model_name, full_text, timer, stream_metadata)

        except Exception as e:
            logger.error(f"{self.provider_name} Error: {e}")
            raise

    def _prepare_messages(
        self, messages: list[dict[str, str]], system_prompt: str | None
    ) -> list[dict[str, str]]:
        """Prépare les messages avec le system prompt. Peut être surchargée."""
        final_messages = messages.copy()
        if system_prompt:
            final_messages.insert(0, {"role": "system", "content": system_prompt})
        return final_messages

    @abstractmethod
    async def _stream_implementation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        metadata: dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """
        Implémentation spécifique du streaming pour chaque provider.

        Args:
            model_name: Nom du modèle
            messages: Messages préparés
            temperature: Température de génération
            metadata: Dict pour stocker les métriques spécifiques (tokens, etc.)

        Yields:
            str: Chunks de texte générés
        """
        pass

    def _build_metrics(
        self,
        model_name: str,
        full_text: str,
        timer: MetricsCalculator,
        metadata: dict[str, Any],
    ) -> InferenceMetrics:
        """Construit les métriques finales. Peut être surchargée."""
        output_tokens = metadata.get("output_tokens", len(full_text) // 4)
        input_tokens = metadata.get("input_tokens", 0)
        load_duration = metadata.get("load_duration", 0)

        duration = timer.duration
        tokens_per_second = output_tokens / duration if duration > 0 else 0

        return InferenceMetrics(
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_duration_s=round(duration, 2),
            load_duration_s=round(load_duration, 2),
            tokens_per_second=round(tokens_per_second, 1),
            carbon_g=0.0,
        )

    def list_models_with_provider(self) -> list[dict[str, Any]]:
        """
        Liste les modèles en ajoutant systématiquement la clé 'provider'.

        Wrapper autour de list_models() pour garantir la cohérence
        de la structure retournée par tous les providers.

        Returns:
            Liste de modèles avec 'provider' garanti.
        """
        models = self.list_models()
        for model in models:
            model.setdefault("provider", self.provider_name)
        return models
