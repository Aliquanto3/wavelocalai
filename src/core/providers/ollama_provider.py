# src/core/providers/ollama_provider.py
"""
Provider Ollama pour les modèles locaux.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

import ollama
from langchain_ollama import ChatOllama

from src.core.interfaces import ILLMProvider
from src.core.metrics import InferenceMetrics, MetricsCalculator

logger = logging.getLogger(__name__)


class OllamaProvider(ILLMProvider):
    """
    Provider pour les modèles locaux via Ollama.
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        """
        Initialise le provider Ollama.

        Args:
            base_url: URL du serveur Ollama
        """
        self._base_url = base_url

    def _create_async_client(self):
        """
        Crée un nouveau client async à chaque appel.
        Évite les problèmes d'event loop fermée entre les requêtes.
        """
        from ollama import AsyncClient as OllamaAsyncClient

        return OllamaAsyncClient(host=self._base_url)

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def is_local(self) -> bool:
        return True

    def list_models(self) -> list[dict[str, Any]]:
        """Liste les modèles installés localement via Ollama."""
        models = []
        try:
            ollama_resp = ollama.list()
            raw_models = (
                ollama_resp.models
                if hasattr(ollama_resp, "models")
                else ollama_resp.get("models", [])
            )

            for m in raw_models:
                model_dict = (
                    m.model_dump()
                    if hasattr(m, "model_dump")
                    else (m.__dict__ if hasattr(m, "__dict__") else dict(m))
                )
                model_dict["type"] = "local"
                if "model" not in model_dict and "name" in model_dict:
                    model_dict["model"] = model_dict["name"]
                models.append(model_dict)

        except Exception as e:
            logger.error(f"Erreur Ollama list: {e}")

        return models

    async def chat_stream(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str | InferenceMetrics, None]:
        """Génère une réponse en streaming via Ollama."""

        final_messages = messages.copy()
        if system_prompt:
            final_messages.insert(0, {"role": "system", "content": system_prompt})

        timer = MetricsCalculator()
        full_text = ""
        eval_count = 0
        prompt_eval_count = 0
        load_duration = 0

        # Créer un nouveau client pour chaque requête (évite "Event loop is closed")
        client = self._create_async_client()

        try:
            timer.start()
            stream = await client.chat(
                model=model_name,
                messages=final_messages,
                stream=True,
                options={"temperature": temperature},
            )

            async for chunk in stream:
                if isinstance(chunk, dict):
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        full_text += content
                        yield content

                    # Métriques finales
                    if chunk.get("done"):
                        eval_count = chunk.get("eval_count", len(full_text) // 4)
                        prompt_eval_count = chunk.get("prompt_eval_count", 0)
                        load_duration = chunk.get("load_duration", 0)
                else:
                    # Format objet Pydantic
                    content = getattr(chunk, "message", None)
                    if content and hasattr(content, "content"):
                        text = content.content
                        if text:
                            full_text += text
                            yield text

                    if getattr(chunk, "done", False):
                        eval_count = getattr(chunk, "eval_count", len(full_text) // 4)
                        prompt_eval_count = getattr(chunk, "prompt_eval_count", 0)
                        load_duration = getattr(chunk, "load_duration", 0)

            timer.stop()

            # Calcul des métriques
            duration = timer.duration
            tokens_per_second = eval_count / duration if duration > 0 else 0

            yield InferenceMetrics(
                model_name=model_name,
                input_tokens=prompt_eval_count,
                output_tokens=eval_count,
                total_duration_s=round(duration, 2),
                load_duration_s=round(load_duration / 1e9, 2) if load_duration else 0,
                tokens_per_second=round(tokens_per_second, 1),
                carbon_g=0.0,
            )

        except Exception as e:
            logger.error(f"Ollama Error: {e}")
            raise e

    def get_langchain_model(
        self, model_name: str, temperature: float = 0.7, **kwargs
    ) -> ChatOllama:
        """Retourne un modèle LangChain Ollama."""
        return ChatOllama(
            model=model_name,
            temperature=temperature,
            base_url=self._base_url,
            keep_alive="5m",
            **kwargs,
        )

    def pull_model(self, model_name: str) -> Any:
        """Télécharge un modèle via Ollama."""
        try:
            return ollama.pull(model_name, stream=True)
        except Exception as e:
            logger.error(f"Erreur pull {model_name}: {e}")
            raise e

    def health_check(self) -> bool:
        """Vérifie si Ollama est accessible."""
        try:
            ollama.list()
            return True
        except Exception:
            return False
