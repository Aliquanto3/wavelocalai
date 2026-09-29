"""
Tests unitaires pour InferenceService.
Usage: pytest tests/unit/test_inference_service.py -v
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.inference_service import InferenceCallbacks, InferenceResult, InferenceService
from src.core.metrics import InferenceMetrics, ReasoningChunk

# ========================================
# 1. FIXTURES (Données de test réutilisables)
# ========================================


@pytest.fixture
def mock_stream_response():
    """Simule un stream Ollama typique (CORRIGÉ)."""

    async def fake_stream():
        # Simule 3 tokens
        yield "Bonjour"
        yield " le"
        yield " monde"
        # Puis les métriques
        yield InferenceMetrics(
            model_name="test-model",
            input_tokens=5,
            output_tokens=10,
            total_duration_s=1.5,
            load_duration_s=0.2,
            tokens_per_second=6.7,
        )

    return fake_stream  # ⬅️ On retourne la fonction, pas la coroutine


@pytest.fixture
def mock_llm_provider(mock_stream_response):
    """Mock de LLMProvider pour éviter les vraies requêtes Ollama."""
    with patch("src.core.inference_service.LLMProvider") as mock:
        # ✅ CORRECTION : On fait en sorte que chat_stream retourne un async generator
        # En appelant mock_stream_response() à chaque appel
        mock.chat_stream = MagicMock(side_effect=lambda *args, **kwargs: mock_stream_response())
        yield mock


# ========================================
# 2. TESTS BASIQUES (Sans Ollama)
# ========================================


@pytest.mark.asyncio
async def test_inference_simple(mock_llm_provider):
    """Test basique : le service retourne un résultat."""
    result = await InferenceService.run_inference(
        model_tag="test-model", messages=[{"role": "user", "content": "Test"}], temperature=0.0
    )

    assert result.error is None, f"Ne devrait pas y avoir d'erreur: {result.error}"
    assert result.clean_text == "Bonjour le monde", "Texte mal assemblé"
    assert result.metrics is not None, "Les métriques doivent être présentes"
    assert result.metrics.tokens_per_second == 6.7


@pytest.mark.asyncio
async def test_inference_avec_system_prompt(mock_llm_provider):
    """Vérifie que le system_prompt est bien passé."""
    await InferenceService.run_inference(
        model_tag="test-model",
        messages=[{"role": "user", "content": "Hello"}],
        system_prompt="Tu es un assistant strict.",
    )

    # Vérification que chat_stream a été appelé avec le bon argument
    mock_llm_provider.chat_stream.assert_called_once()
    call_kwargs = mock_llm_provider.chat_stream.call_args.kwargs
    assert call_kwargs["system_prompt"] == "Tu es un assistant strict."


@pytest.mark.asyncio
async def test_callbacks_sont_appeles(mock_llm_provider):
    """Test que les callbacks on_token et on_metrics sont invoqués."""
    tokens_received = []
    metrics_received = []

    async def on_token(token: str):
        tokens_received.append(token)

    async def on_metrics(m: InferenceMetrics):
        metrics_received.append(m)

    callbacks = InferenceCallbacks(on_token=on_token, on_metrics=on_metrics)

    result = await InferenceService.run_inference(
        model_tag="test-model", messages=[{"role": "user", "content": "Test"}], callbacks=callbacks
    )

    # Vérifications
    assert len(tokens_received) == 3, f"Devrait avoir reçu 3 tokens, reçu {len(tokens_received)}"
    assert "".join(tokens_received) == "Bonjour le monde"
    assert len(metrics_received) == 1, "Devrait avoir reçu 1 objet métriques"
    assert result.clean_text == "Bonjour le monde"


@pytest.mark.asyncio
async def test_extraction_thought():
    """Test que les balises <think> sont correctement extraites."""

    # Mock avec une pensée
    async def stream_with_thought():
        yield "<think>Je réfléchis...</think>La réponse est 42."
        yield InferenceMetrics(
            model_name="test",
            input_tokens=1,
            output_tokens=1,
            total_duration_s=1.0,
            load_duration_s=0.1,
            tokens_per_second=1.0,
        )

    with patch("src.core.inference_service.LLMProvider") as mock:
        # ✅ CORRECTION : Utiliser side_effect au lieu de return_value
        mock.chat_stream = MagicMock(side_effect=lambda *args, **kwargs: stream_with_thought())

        result = await InferenceService.run_inference(
            model_tag="test-model", messages=[{"role": "user", "content": "Test"}]
        )

        assert result.thought == "Je réfléchis...", f"Pensée mal extraite: {result.thought}"
        assert result.clean_text == "La réponse est 42.", f"Texte mal nettoyé: {result.clean_text}"


def _metrics():
    return InferenceMetrics(
        model_name="test",
        input_tokens=1,
        output_tokens=1,
        total_duration_s=1.0,
        load_duration_s=0.1,
        tokens_per_second=1.0,
    )


async def _run_stream(*items, callbacks=None):
    async def stream():
        for item in items:
            yield item
        yield _metrics()

    with patch("src.core.inference_service.LLMProvider") as mock:
        mock.chat_stream = MagicMock(side_effect=lambda *args, **kwargs: stream())
        return await InferenceService.run_inference(
            model_tag="test-model",
            messages=[{"role": "user", "content": "Test"}],
            callbacks=callbacks,
        )


@pytest.mark.asyncio
async def test_reasoning_chunks_never_counted_as_answer():
    """Raisonnement d'Ollama (`ReasoningChunk`) : dans `thought`, jamais dans le texte ; les
    tokens de la réponse seuls passent par `on_token`."""
    tokens, thoughts = [], []

    async def on_token(token):
        tokens.append(token)

    async def on_thought(thought):
        thoughts.append(thought)

    result = await _run_stream(
        ReasoningChunk("Je pèse "),
        ReasoningChunk("les options."),
        "La réponse.",
        callbacks=InferenceCallbacks(on_token=on_token, on_thought=on_thought),
    )

    assert result.thought == "Je pèse les options."
    assert result.clean_text == "La réponse."
    assert result.raw_text == "La réponse."
    assert tokens == ["La réponse."]
    assert thoughts == ["Je pèse les options."]


@pytest.mark.asyncio
async def test_reasoning_only_gives_empty_answer():
    """Tout dans le raisonnement (Qwen 3.5 0.8B) : réponse vide, raisonnement gardé."""
    result = await _run_stream(ReasoningChunk("Tout mon texte part ici."))

    assert result.clean_text == ""
    assert result.thought == "Tout mon texte part ici."
    assert result.error is None


@pytest.mark.asyncio
async def test_think_tags_only_give_empty_answer():
    """Balises `<think>` seules : même traitement, plus de repli sur le texte brut."""
    result = await _run_stream("<think>x</think>")

    assert result.clean_text == ""
    assert result.thought == "x"


@pytest.mark.asyncio
async def test_reasoning_chunks_then_think_tags():
    """Raisonnement transmis à part en premier, puis celui des balises `<think>`."""
    result = await _run_stream(ReasoningChunk("A"), "<think>B</think>Réponse")

    assert result.thought == "A\n\nB"
    assert result.clean_text == "Réponse"


# ========================================
# 3. TESTS DE ROBUSTESSE
# ========================================


@pytest.mark.asyncio
async def test_timeout():
    """Test que le timeout fonctionne."""

    # Mock qui ne yield jamais (simule un modèle bloqué)
    async def stream_qui_bloque():
        await asyncio.sleep(10)  # Attend 10 secondes
        yield "Trop tard"

    with patch("src.core.inference_service.LLMProvider") as mock:
        mock.chat_stream = MagicMock(side_effect=lambda *args, **kwargs: stream_qui_bloque())

        result = await InferenceService.run_inference(
            model_tag="test-model",
            messages=[{"role": "user", "content": "Test"}],
            timeout=1,  # ⬅️ Timeout de 1 seconde
        )

        assert result.error is not None, "Devrait avoir une erreur"
        assert "Timeout" in result.error, f"L'erreur devrait mentionner le timeout: {result.error}"
        # Délai identifiable sans analyser le texte de l'erreur.
        assert result.timed_out is True
        assert result.timeout_s == 1
        assert result.metrics is None


@pytest.mark.asyncio
async def test_gestion_erreur_ollama():
    """Test la gestion d'une erreur Ollama (ex: modèle introuvable)."""

    async def stream_qui_crash():
        raise Exception("Model 'fake-model' not found")
        yield  # Jamais atteint

    with patch("src.core.inference_service.LLMProvider") as mock:
        mock.chat_stream = MagicMock(side_effect=lambda *args, **kwargs: stream_qui_crash())

        result = await InferenceService.run_inference(
            model_tag="fake-model", messages=[{"role": "user", "content": "Test"}]
        )

        assert result.error is not None
        assert "not found" in result.error.lower(), f"Message d'erreur inattendu: {result.error}"
        assert result.timed_out is False
        assert result.metrics is None


@pytest.mark.asyncio
async def test_callback_erreur():
    """Test que le callback on_error est appelé en cas de crash."""
    errors_received = []

    async def on_error(error: str):
        errors_received.append(error)

    callbacks = InferenceCallbacks(on_error=on_error)

    async def stream_qui_crash():
        raise RuntimeError("Crash simulé")
        yield

    with patch("src.core.inference_service.LLMProvider") as mock:
        mock.chat_stream = MagicMock(side_effect=lambda *args, **kwargs: stream_qui_crash())

        await InferenceService.run_inference(
            model_tag="test-model",
            messages=[{"role": "user", "content": "Test"}],
            callbacks=callbacks,
        )

        assert (
            len(errors_received) == 1
        ), f"Le callback on_error devrait avoir été appelé. Reçu: {errors_received}"
        assert "Crash simulé" in errors_received[0]


# ========================================
# 4. TESTS BATCH (Parallélisation)
# ========================================


@pytest.mark.asyncio
async def test_batch_inference():
    """Test que run_batch_inference traite plusieurs prompts."""

    async def fake_stream():
        yield "Réponse"
        yield InferenceMetrics(
            model_name="test",
            input_tokens=1,
            output_tokens=1,
            total_duration_s=0.5,
            load_duration_s=0.1,
            tokens_per_second=2.0,
        )

    with patch("src.core.inference_service.LLMProvider") as mock:
        mock.chat_stream = MagicMock(side_effect=lambda *args, **kwargs: fake_stream())

        prompts = ["Test 1", "Test 2", "Test 3"]

        results = await InferenceService.run_batch_inference(
            model_tag="test-model", prompts=prompts, max_concurrent=2  # Max 2 inférences parallèles
        )

        assert len(results) == 3, "Devrait avoir 3 résultats"
        errors = [r.error for r in results if r.error]
        assert len(errors) == 0, f"Aucune erreur ne devrait survenir: {errors}"
        assert all(r.clean_text == "Réponse" for r in results)


@pytest.mark.asyncio
async def test_batch_avec_erreur_partielle():
    """Test batch quand un des prompts échoue."""
    call_count = [0]

    async def fake_stream_intermittent():
        call_count[0] += 1
        if call_count[0] == 2:  # Le 2ème prompt crash
            raise Exception("Erreur sur prompt 2")
        yield "OK"
        yield InferenceMetrics(
            model_name="test",
            input_tokens=1,
            output_tokens=1,
            total_duration_s=0.5,
            load_duration_s=0.1,
            tokens_per_second=2.0,
        )

    with patch("src.core.inference_service.LLMProvider") as mock:
        mock.chat_stream = MagicMock(side_effect=lambda *args, **kwargs: fake_stream_intermittent())

        prompts = ["OK 1", "Crash", "OK 3"]

        results = await InferenceService.run_batch_inference(
            model_tag="test-model", prompts=prompts
        )

        assert len(results) == 3
        assert results[0].error is None, f"Le 1er doit réussir: {results[0].error}"
        assert results[1].error is not None, "Le 2ème doit échouer"
        assert "Erreur sur prompt 2" in results[1].error
        assert results[2].error is None, f"Le 3ème doit réussir: {results[2].error}"
