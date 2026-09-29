"""
Service d'orchestration d'inférence découplé de l'UI.
Permet la réutilisation pour benchmarks, agents et évaluations.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from src.core.llm_provider import LLMProvider
from src.core.metrics import InferenceMetrics, ReasoningChunk
from src.core.models_db import extract_thought

# Logging
logger = logging.getLogger(__name__)


# ========================================
# 1. STRUCTURES DE DONNÉES
# ========================================


@dataclass
class InferenceResult:
    """Résultat complet d'une inférence.

    En cas d'échec, `error` est renseigné et `metrics` vaut None : tester `error` avant de lire
    les métriques. `timed_out` distingue un délai dépassé (délai en secondes dans `timeout_s`)
    des autres erreurs, sans analyser le texte de `error`.
    """

    raw_text: str
    clean_text: str
    thought: str | None
    metrics: InferenceMetrics | None
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    timed_out: bool = False
    timeout_s: float | None = None


@dataclass
class InferenceCallbacks:
    """
    Callbacks optionnels pour feedback temps réel.
    Permet au frontend de s'abonner aux événements sans couplage.
    """

    on_token: Callable[[str], Awaitable[None]] | None = None
    on_metrics: Callable[[InferenceMetrics], Awaitable[None]] | None = None
    on_thought: Callable[[str], Awaitable[None]] | None = None
    on_error: Callable[[str], Awaitable[None]] | None = None


# ========================================
# 2. SERVICE D'INFÉRENCE
# ========================================


class InferenceService:
    """
    Orchestrateur pur (sans dépendance UI) pour exécution d'inférences.

    Usage:
        # Sans callbacks (mode batch)
        result = await InferenceService.run_inference(model, messages)

        # Avec callbacks (mode streaming UI)
        callbacks = InferenceCallbacks(on_token=update_ui)
        result = await InferenceService.run_inference(model, messages, callbacks)
    """

    @staticmethod
    async def run_inference(
        model_tag: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        system_prompt: str | None = None,
        callbacks: InferenceCallbacks | None = None,
        timeout: int = 120,
    ) -> InferenceResult:
        """
        Exécute une inférence avec gestion complète des événements.

        Args:
            model_tag: Tag Ollama du modèle (ex: "qwen2.5:1.5b")
            messages: Historique de conversation [{"role": "user", "content": "..."}]
            temperature: Créativité du modèle (0.0 = déterministe, 1.0 = créatif)
            system_prompt: Instruction système optionnelle
            callbacks: Gestionnaires d'événements optionnels
            timeout: Timeout en secondes (défaut: 2 minutes)

        Returns:
            InferenceResult contenant texte, pensée et métriques

        Raises:
            asyncio.TimeoutError: Si l'inférence dépasse le timeout
            Exception: Erreurs Ollama ou réseau
        """
        try:
            # Protection timeout
            return await asyncio.wait_for(
                InferenceService._execute_inference(
                    model_tag, messages, temperature, system_prompt, callbacks
                ),
                timeout=timeout,
            )

        except asyncio.TimeoutError:
            error_msg = f"Timeout ({timeout}s) dépassé pour {model_tag}"
            logger.error(error_msg)
            if callbacks and callbacks.on_error:
                await callbacks.on_error(error_msg)
            return InferenceResult(
                raw_text="",
                clean_text="",
                thought=None,
                metrics=None,
                error=error_msg,
                timed_out=True,
                timeout_s=timeout,
            )

        except Exception as e:
            error_msg = f"Erreur inférence {model_tag}: {e}"
            logger.exception(error_msg)
            if callbacks and callbacks.on_error:
                await callbacks.on_error(str(e))
            return InferenceResult(
                raw_text="", clean_text="", thought=None, metrics=None, error=str(e)
            )

    @staticmethod
    async def _execute_inference(
        model_tag: str,
        messages: list[dict[str, str]],
        temperature: float,
        system_prompt: str | None,
        callbacks: InferenceCallbacks | None,
    ) -> InferenceResult:
        """Logique d'exécution interne (sans timeout wrapper)."""

        full_text = ""
        reasoning = ""
        final_metrics = None

        # Appel du provider
        stream = LLMProvider.chat_stream(
            model_name=model_tag,
            messages=messages,
            temperature=temperature,
            system_prompt=system_prompt,
        )

        # Consommation du stream
        async for item in stream:
            if isinstance(item, str):
                full_text += item
                # Callback token
                if callbacks and callbacks.on_token:
                    await callbacks.on_token(item)

            elif isinstance(item, ReasoningChunk):
                # Raisonnement transmis à part : jamais compté comme texte de réponse.
                reasoning += item.text

            elif isinstance(item, InferenceMetrics):
                final_metrics = item
                # Callback métriques
                if callbacks and callbacks.on_metrics:
                    await callbacks.on_metrics(item)

        # Pensée : raisonnement transmis à part en premier, puis balises <think> du texte.
        tag_thought, clean_text = extract_thought(full_text)
        parts = [part for part in (reasoning.strip(), tag_thought) if part]
        thought = "\n\n".join(parts) or None

        # Callback pensée (si détectée)
        if thought and callbacks and callbacks.on_thought:
            await callbacks.on_thought(thought)

        return InferenceResult(
            raw_text=full_text,
            # Pas de repli sur le texte brut : une réponse faite seulement de raisonnement
            # reste vide (l'Arène la marque « réponse vide », sans la juger).
            clean_text=clean_text or "",
            thought=thought,
            metrics=final_metrics,
        )

    @staticmethod
    async def run_batch_inference(
        model_tag: str, prompts: list[str], temperature: float = 0.7, max_concurrent: int = 3
    ) -> list[InferenceResult]:
        """
        Exécute plusieurs inférences en parallèle (pour benchmarks).

        Args:
            model_tag: Modèle à utiliser
            prompts: Liste de prompts à traiter
            temperature: Température d'inférence
            max_concurrent: Nombre d'inférences parallèles max

        Returns:
            Liste de résultats dans l'ordre des prompts
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _run_with_semaphore(prompt: str) -> InferenceResult:
            async with semaphore:
                messages = [{"role": "user", "content": prompt}]
                return await InferenceService.run_inference(model_tag, messages, temperature)

        tasks = [_run_with_semaphore(p) for p in prompts]
        return await asyncio.gather(*tasks, return_exceptions=False)


# ========================================
# 3. EXEMPLE D'USAGE (Tests)
# ========================================

if __name__ == "__main__":
    """Tests rapides du service."""

    async def test_simple():
        """Test basique sans callbacks."""
        print("🧪 Test 1: Inférence simple")
        result = await InferenceService.run_inference(
            model_tag="qwen2.5:1.5b",
            messages=[{"role": "user", "content": "Dis bonjour en 3 mots"}],
            temperature=0.0,
        )
        print(f"✅ Résultat: {result.clean_text}")
        print(f"📊 Tokens/s: {result.metrics.tokens_per_second if result.metrics else 'N/A'}")

    async def test_avec_callbacks():
        """Test avec callbacks (simulation UI)."""
        print("\n🧪 Test 2: Avec callbacks")

        current_text = ""

        async def on_token(token: str):
            nonlocal current_text
            current_text += token
            print(f"\r💬 Streaming: {current_text[:50]}...", end="", flush=True)

        async def on_metrics(m: InferenceMetrics):
            print(f"\n📈 Vitesse: {m.tokens_per_second} t/s")

        callbacks = InferenceCallbacks(on_token=on_token, on_metrics=on_metrics)

        result = await InferenceService.run_inference(
            model_tag="qwen2.5:1.5b",
            messages=[{"role": "user", "content": "Explique la photosynthèse en 50 mots"}],
            callbacks=callbacks,
        )
        print(f"\n✅ Texte final: {result.clean_text}")

    async def test_batch():
        """Test batch (benchmarks)."""
        print("\n🧪 Test 3: Batch de 3 prompts")

        prompts = ["Capitale de la France ?", "2 + 2 = ?", "Quelle est la couleur du ciel ?"]

        results = await InferenceService.run_batch_inference(
            model_tag="qwen2.5:1.5b", prompts=prompts, max_concurrent=2
        )

        for i, result in enumerate(results):
            print(f"✅ Prompt {i+1}: {result.clean_text[:30]}...")

    # Exécution des tests
    async def main():
        await test_simple()
        await test_avec_callbacks()
        await test_batch()

    asyncio.run(main())
