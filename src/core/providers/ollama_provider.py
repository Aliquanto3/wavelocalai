# src/core/providers/ollama_provider.py
"""Provider Ollama pour les modèles locaux."""

import logging
from collections.abc import AsyncGenerator
from typing import Any

import ollama
from langchain_ollama import ChatOllama

from src.core.providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)


class OllamaProvider(BaseProvider):
    """Provider pour les modèles locaux via Ollama."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self._base_url = base_url

    def pull_model(self, model_name: str) -> Any:
        """
        Télécharge un modèle via la bibliothèque ollama.

        Args:
            model_name: Nom du modèle (tag)

        Returns:
            Réponse du téléchargement
        """
        try:
            return ollama.pull(model_name, stream=True)
        except Exception as e:
            logger.error(f"Erreur lors du pull du modèle {model_name}: {e}")
            raise ValueError(f"Échec du téléchargement Ollama: {e}") from e

    def _create_async_client(self):
        from ollama import AsyncClient as OllamaAsyncClient

        return OllamaAsyncClient(host=self._base_url)

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def is_local(self) -> bool:
        return True

    @property
    def is_available(self) -> bool:
        return True  # Toujours disponible si Ollama tourne

    async def _stream_implementation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float,
        metadata: dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """Implémentation streaming Ollama avec paramètres anti-répétition."""
        client = self._create_async_client()

        # Options optimisées pour éviter les boucles de répétition sur petits SLM
        options = {
            "temperature": temperature,
            "repeat_penalty": 1.2,  # Pénalise les tokens déjà générés
            "repeat_last_n": 64,  # Fenêtre de contexte pour la pénalité
            "top_k": 40,  # Limite aux 40 tokens les plus probables
            "top_p": 0.9,  # Nucleus sampling
        }

        stream = await client.chat(
            model=model_name,
            messages=messages,
            stream=True,
            options=options,
        )

        async for chunk in stream:
            if isinstance(chunk, dict):
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content
                if chunk.get("done"):
                    metadata["output_tokens"] = chunk.get("eval_count", 0)
                    metadata["input_tokens"] = chunk.get("prompt_eval_count", 0)
                    metadata["load_duration"] = chunk.get("load_duration", 0) / 1e9
            else:
                content = getattr(chunk, "message", None)
                if content and hasattr(content, "content") and content.content:
                    yield content.content
                if getattr(chunk, "done", False):
                    metadata["output_tokens"] = getattr(chunk, "eval_count", 0)
                    metadata["input_tokens"] = getattr(chunk, "prompt_eval_count", 0)
                    metadata["load_duration"] = getattr(chunk, "load_duration", 0) / 1e9

    def list_models(self) -> list[dict[str, Any]]:
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

    def get_langchain_model(self, model_name: str, temperature: float = 0.7, **kwargs) -> Any:
        return ChatOllama(model=model_name, temperature=temperature, **kwargs)

    def health_check(self) -> bool:
        try:
            ollama.list()
            return True
        except Exception:
            return False
