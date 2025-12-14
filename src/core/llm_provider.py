import logging
from collections.abc import AsyncGenerator
from typing import Any

import ollama
from ollama import AsyncClient as OllamaAsyncClient

try:
    from mistralai import Mistral
except ImportError:
    Mistral = None

from src.core.config import MISTRAL_API_KEY
from src.core.metrics import InferenceMetrics, MetricsCalculator
from src.core.models_db import MODELS_DB, get_cloud_models_from_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMProvider:
    """
    Gestionnaire unifié (Factory).
    """

    @staticmethod
    def _is_mistral_api_model(model_tag: str) -> bool:
        """
        Détecte si le modèle est une API Cloud via models.json.
        """
        # 1. Vérification propre via le JSON (Source of Truth)
        for info in MODELS_DB.values():
            if info.get("ollama_tag") == model_tag:
                return info.get("type") == "api"

        # 2. Fallback de sécurité
        known_cloud_prefixes = ("mistral-", "codestral-", "magistral-", "ministral-", "devstral-")
        return model_tag.startswith(known_cloud_prefixes)

    @staticmethod
    def list_models(cloud_enabled: bool = True) -> list[dict[str, Any]]:
        models = []

        # 1. Modèles Locaux (Via Ollama Runtime)
        try:
            ollama_resp = ollama.list()
            raw_models = (
                ollama_resp.models
                if hasattr(ollama_resp, "models")
                else ollama_resp.get("models", [])
            )

            for m in raw_models:
                # Normalisation Dict
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

        # 2. Modèles Cloud (Via JSON DB)
        if cloud_enabled and MISTRAL_API_KEY:
            cloud_models = get_cloud_models_from_db()
            models.extend(cloud_models)

        return models

    @staticmethod
    def pull_model(model_name: str) -> Any:
        if LLMProvider._is_mistral_api_model(model_name):
            raise ValueError("Impossible de télécharger un modèle API Cloud.")
        try:
            return ollama.pull(model_name, stream=True)
        except Exception as e:
            logger.error(f"Erreur pull {model_name}: {e}")
            raise e

    @staticmethod
    async def chat_stream(
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        system_prompt: str = None,
    ) -> AsyncGenerator[str | InferenceMetrics, None]:
        if LLMProvider._is_mistral_api_model(model_name):
            if not MISTRAL_API_KEY:
                yield "❌ Erreur : Clé API Mistral manquante."
                return
            async for chunk in LLMProvider._stream_mistral(
                model_name, messages, temperature, system_prompt
            ):
                yield chunk
        else:
            async for chunk in LLMProvider._stream_ollama(
                model_name, messages, temperature, system_prompt
            ):
                yield chunk

    @staticmethod
    async def _stream_ollama(model_name, messages, temperature, system_prompt):
        final_messages = messages.copy()
        if system_prompt:
            final_messages.insert(0, {"role": "system", "content": system_prompt})
        timer = MetricsCalculator()
        timer.start()
        full_text = ""
        eval_count = 0
        prompt_eval_count = 0
        load_duration = 0
        client = OllamaAsyncClient()
        try:
            stream = await client.chat(
                model=model_name,
                messages=final_messages,
                stream=True,
                options={"temperature": temperature},
            )
            async for chunk in stream:
                if "message" in chunk and "content" in chunk["message"]:
                    content = chunk["message"]["content"]
                    full_text += content
                    yield content
                if "done" in chunk and chunk["done"]:
                    eval_count = chunk.get("eval_count", 0)
                    prompt_eval_count = chunk.get("prompt_eval_count", 0)
                    load_duration = chunk.get("load_duration", 0)
            timer.stop()
            if eval_count == 0:
                eval_count = len(full_text) / 4
            duration = timer.duration
            tps = eval_count / duration if duration > 0 else 0
            yield InferenceMetrics(
                model_name=model_name,
                input_tokens=prompt_eval_count,
                output_tokens=int(eval_count),
                total_duration_s=round(duration, 2),
                load_duration_s=round(load_duration / 1e9, 2),
                tokens_per_second=round(tps, 1),
                model_size_gb=0,
            )
        except Exception as e:
            logger.error(f"Ollama Error: {e}")
            raise e

    @staticmethod
    async def _stream_mistral(model_name, messages, temperature, system_prompt):
        final_messages = messages.copy()
        if system_prompt:
            final_messages.insert(0, {"role": "system", "content": system_prompt})
        timer = MetricsCalculator()
        timer.start()
        full_text = ""
        try:
            client = Mistral(api_key=MISTRAL_API_KEY)
            stream_response = client.chat.stream(
                model=model_name, messages=final_messages, temperature=temperature
            )
            for chunk in stream_response:
                content = chunk.data.choices[0].delta.content
                if content:
                    full_text += content
                    yield content
            timer.stop()
            eval_count = len(full_text) / 4
            duration = timer.duration
            tps = eval_count / duration if duration > 0 else 0
            yield InferenceMetrics(
                model_name=model_name,
                input_tokens=0,
                output_tokens=int(eval_count),
                total_duration_s=round(duration, 2),
                load_duration_s=0,
                tokens_per_second=round(tps, 1),
                carbon_g=0.0,
            )
        except Exception as e:
            logger.error(f"Mistral API Error: {e}")
            raise e

    @staticmethod
    def get_langchain_model(model_name: str, temperature: float = 0.7, **kwargs):
        """
        Retourne un modèle LangChain prêt à l'emploi.
        Accepte **kwargs pour passer des paramètres spécifiques (ex: model_kwargs).
        """
        if LLMProvider._is_mistral_api_model(model_name):
            if not MISTRAL_API_KEY:
                raise ValueError("Clé API Mistral manquante.")
            from langchain_mistralai import ChatMistralAI

            # On passe kwargs (qui peut contenir model_kwargs)
            return ChatMistralAI(
                model=model_name, api_key=MISTRAL_API_KEY, temperature=temperature, **kwargs
            )

        from langchain_ollama import ChatOllama

        # Pour Ollama, on peut aussi passer kwargs si besoin (ex: format="json")
        return ChatOllama(model=model_name, temperature=temperature, keep_alive="5m", **kwargs)
