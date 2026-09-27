"""
Tests d'intégration pour InferenceService (nécessite Ollama).
Usage: pytest tests/integration/test_inference_ollama.py -v -m integration
"""

import pytest

from src.core.inference_service import InferenceService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_inference_reelle_ollama():
    """
    Test avec une vraie connexion Ollama.
    ⚠️ Requiert : Ollama lancé + modèle 'qwen2.5:1.5b' installé.

    Usage: pytest tests/integration/test_inference_ollama.py -v -m integration
    """
    result = await InferenceService.run_inference(
        model_tag="qwen2.5:1.5b",
        messages=[{"role": "user", "content": "Dis juste 'OK' (1 mot)"}],
        temperature=0.0,
        timeout=30,
    )

    assert result.error is None, f"Erreur Ollama : {result.error}"
    assert len(result.clean_text) > 0, "Le modèle devrait répondre quelque chose"
    assert result.metrics is not None
    assert result.metrics.tokens_per_second > 0
