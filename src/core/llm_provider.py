import logging
from collections.abc import AsyncGenerator
from typing import Any, Union

import ollama
from ollama import AsyncClient

from src.core.metrics import InferenceMetrics, MetricsCalculator

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMProvider:
    """
    Gestionnaire unifié pour les modèles de langage locaux (via Ollama).
    Version Async pour support Multi-Agents & UI non-bloquante.
    """

    @staticmethod
    def list_models() -> list[dict[str, Any]]:
        """Récupère la liste des modèles installés (Reste Synchrone)."""
        try:
            models_info = ollama.list()
            if "models" in models_info:
                return models_info["models"]
            return []
        except Exception as e:
            logger.error(f"Erreur Ollama list: {e}")
            return []

    @staticmethod
    def pull_model(model_name: str) -> Any:
        """Télécharge un modèle avec suivi (Reste Synchrone pour l'instant)."""
        # Note : Ollama python lib ne supporte pas encore parfaitement le stream async sur le pull
        # On garde le sync pour simplifier l'admin
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
    ) -> AsyncGenerator[Union[str, InferenceMetrics], None]:
        """
        Génère une réponse en streaming ASYNCHRONE et renvoie les métriques à la fin.
        """

        # Injection du System Prompt
        final_messages = messages.copy()
        if system_prompt:
            final_messages.insert(0, {"role": "system", "content": system_prompt})

        timer = MetricsCalculator()
        timer.start()

        full_response_text = ""

        # Variables pour stats Ollama
        eval_count = 0
        eval_duration = 0
        prompt_eval_count = 0
        load_duration = 0

        client = AsyncClient()

        try:
            # Appel Asynchrone
            stream = await client.chat(
                model=model_name,
                messages=final_messages,
                stream=True,
                options={"temperature": temperature},
            )

            async for chunk in stream:
                # 1. Traitement du contenu texte
                if "message" in chunk and "content" in chunk["message"]:
                    content = chunk["message"]["content"]
                    full_response_text += content
                    yield content

                # 2. Capture des stats à la fin (Ollama specific)
                if "done" in chunk and chunk["done"]:
                    eval_count = chunk.get("eval_count", 0)
                    eval_duration = chunk.get("eval_duration", 1)
                    prompt_eval_count = chunk.get("prompt_eval_count", 0)
                    load_duration = chunk.get("load_duration", 0)

            timer.stop()

            # 3. Calcul des Métriques
            if eval_count == 0:
                eval_count = len(full_response_text) / 4

            duration_s = timer.duration
            tps = eval_count / duration_s if duration_s > 0 else 0

            metrics = InferenceMetrics(
                model_name=model_name,
                input_tokens=prompt_eval_count,
                output_tokens=int(eval_count),
                total_duration_s=round(duration_s, 2),
                load_duration_s=round(load_duration / 1e9, 2),
                tokens_per_second=round(tps, 1),
            )

            yield metrics

        except Exception as e:
            logger.error(f"Erreur inférence {model_name}: {e}")
            # Ne pas yield de string, laisser InferenceService gérer l'erreur
            raise e  # Relancer l'exception pour que InferenceService la capture
