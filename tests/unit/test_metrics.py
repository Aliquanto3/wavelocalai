"""
Tests unitaires pour le module metrics.
Usage: pytest tests/unit/test_metrics.py -v
"""

import asyncio
import time

import pytest

from src.core.metrics import InferenceMetrics, MetricsCalculator


class TestInferenceMetrics:
    """Tests de la dataclass InferenceMetrics."""

    def test_creation_complete(self):
        """Test création avec tous les paramètres."""
        metrics = InferenceMetrics(
            model_name="test-model",
            input_tokens=10,
            output_tokens=20,
            total_duration_s=5.5,
            load_duration_s=0.5,
            tokens_per_second=4.0,
            model_size_gb=1.5,
            energy_wh=0.1,
            carbon_g=0.05,
        )

        assert metrics.model_name == "test-model"
        assert metrics.input_tokens == 10
        assert metrics.output_tokens == 20
        assert metrics.total_duration_s == 5.5
        assert metrics.tokens_per_second == 4.0
        assert metrics.energy_wh == 0.1
        assert metrics.carbon_g == 0.05

    def test_creation_minimal(self):
        """Test création avec paramètres minimaux."""
        metrics = InferenceMetrics(
            model_name="test",
            input_tokens=5,
            output_tokens=10,
            total_duration_s=2.0,
            load_duration_s=0.1,
            tokens_per_second=5.0,
        )

        # Les champs optionnels devraient avoir des valeurs par défaut
        assert metrics.model_size_gb == 0.0
        assert metrics.energy_wh is None
        assert metrics.carbon_g is None


class TestMetricsCalculator:
    """Tests de MetricsCalculator (chronomètre)."""

    def test_duration_calculation(self):
        """Test mesure de durée."""
        calc = MetricsCalculator()

        calc.start()
        time.sleep(0.1)  # Attend 100ms
        calc.stop()

        duration = calc.duration

        # Devrait être proche de 0.1s (tolérance de 50ms)
        assert 0.05 < duration < 0.15

    def test_multiple_measurements(self):
        """Test mesures multiples."""
        calc = MetricsCalculator()

        # Premier chrono
        calc.start()
        time.sleep(0.05)
        calc.stop()
        duration1 = calc.duration

        # Deuxième chrono (réinitialisation)
        calc.start()
        time.sleep(0.1)
        calc.stop()
        duration2 = calc.duration

        # La deuxième mesure devrait être différente
        assert duration2 > duration1
        assert 0.08 < duration2 < 0.15

    def test_duration_before_stop(self):
        """Test accès à duration avant stop."""
        calc = MetricsCalculator()
        calc.start()

        # end_time est encore à 0
        duration = calc.duration

        # Devrait retourner une valeur négative ou 0
        assert duration <= 0 or duration == calc.start_time


# ========================================
# NOUVEAUX TESTS (Validation du Stream)
# ========================================


@pytest.mark.asyncio
class TestMetricsStreaming:
    """Tests de la consommation de flux mixtes (Texte + Métriques)."""

    async def test_mixed_stream_consumption(self):
        """Simule la consommation d'un stream contenant Texte ET Métriques."""

        # 1. Simuler le générateur du LLMProvider (Mock)
        async def mock_llm_stream():
            yield "Bonjour"
            yield " le monde"
            # L'objet métrique arrive à la fin du stream
            yield InferenceMetrics(
                model_name="test",
                input_tokens=5,
                output_tokens=5,
                total_duration_s=1.0,
                load_duration_s=0.1,
                tokens_per_second=10.0,
                model_size_gb=4.5,  # La valeur qu'on veut récupérer
                carbon_g=0.12,  # La valeur qu'on veut récupérer
            )

        # 2. Simuler la logique de consommation côté UI (comme dans chat.py / eval.py)
        full_text = ""
        captured_metrics = None

        async for chunk in mock_llm_stream():
            if isinstance(chunk, str):
                full_text += chunk
            elif isinstance(chunk, InferenceMetrics):
                captured_metrics = chunk

        # 3. Assertions
        assert full_text == "Bonjour le monde"

        assert captured_metrics is not None, "L'objet métrique n'a pas été capturé"
        assert isinstance(captured_metrics, InferenceMetrics)

        # Vérification des valeurs critiques pour l'EvalOps Dashboard
        assert captured_metrics.model_size_gb == 4.5
        assert captured_metrics.carbon_g == 0.12
