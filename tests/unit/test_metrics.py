"""
Tests unitaires pour le module metrics.
Usage: pytest tests/unit/test_metrics.py -v
"""

import asyncio
import re
from pathlib import Path

import pytest

from src.core.metrics import InferenceMetrics, MetricsCalculator, ollama_metrics


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

    @staticmethod
    def _fake_clock(monkeypatch, *ticks):
        """Horloge scriptée : la durée ne dépend plus de la charge du runner CI."""
        values = iter(ticks)
        monkeypatch.setattr("src.core.metrics.time.perf_counter", lambda: next(values))

    def test_duration_calculation(self, monkeypatch):
        """Test mesure de durée."""
        self._fake_clock(monkeypatch, 10.0, 10.1)
        calc = MetricsCalculator()

        calc.start()
        calc.stop()

        assert calc.duration == pytest.approx(0.1)

    def test_multiple_measurements(self, monkeypatch):
        """Test mesures multiples."""
        self._fake_clock(monkeypatch, 1.0, 1.05, 2.0, 2.1)
        calc = MetricsCalculator()

        # Premier chrono
        calc.start()
        calc.stop()
        duration1 = calc.duration

        # Deuxième chrono (réinitialisation)
        calc.start()
        calc.stop()
        duration2 = calc.duration

        assert duration1 == pytest.approx(0.05)
        assert duration2 == pytest.approx(0.1)

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


# ========================================
# Débit d'Ollama (D3) : eval_count / eval_duration, comme scripts/benchmark_slm.py
# ========================================


BENCHMARK_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_slm.py"


def _final_chunk(**fields):
    """Chunk final d'Ollama au format dict (durées en nanosecondes)."""
    return {"done": True, "message": {"content": ""}, **fields}


class TestOllamaMetrics:
    """Métriques calculées depuis le chunk final d'Ollama (src.core.metrics.ollama_metrics)."""

    def test_throughput_excludes_load_and_prefill(self):
        """157 tokens en 2 s de génération : 78,5 tokens/s, même si l'appel a duré 12 s."""
        chunk = _final_chunk(
            eval_count=157,
            eval_duration=2_000_000_000,
            prompt_eval_count=30,
            prompt_eval_duration=500_000_000,
            load_duration=8_000_000_000,
            total_duration=11_000_000_000,
        )
        m = ollama_metrics("qwen2.5:1.5b", chunk, wall_duration_s=12.0)

        assert m.tokens_per_second == 78.5
        assert m.load_duration_s == 8.0
        assert m.load_measured is True
        assert m.total_duration_s == 11.0
        assert m.output_tokens == 157
        assert m.input_tokens == 30
        assert m.eval_duration_s == 2.0
        assert m.prompt_eval_duration_s == 0.5

    def test_same_formula_as_benchmark(self):
        """Le benchmark calcule toujours `output_tokens / (eval_duration_ns / 1e9)`, arrondi à
        2 décimales, avec repli sur la durée murale : lu en texte (ni importé ni modifié)."""
        source = (BENCHMARK_SCRIPT).read_text(encoding="utf-8")
        compact = re.sub(r"\s+", "", source)
        assert 'eval_duration_ns=getattr(chunk,"eval_duration",None)oreval_duration_ns' in compact
        assert (
            "ifeval_duration_ns:tokens_per_second=round(output_tokens/(eval_duration_ns/1e9),2)"
            "else:tokens_per_second=round(output_tokens/duration,2)ifduration>0else0"
        ) in compact

        eval_ns, output = 3_123_456_789, 211
        m = ollama_metrics("m", _final_chunk(eval_count=output, eval_duration=eval_ns), 10.0)
        assert m.tokens_per_second == round(output / (eval_ns / 1e9), 2)
        assert m.throughput_estimated is False

    def test_pydantic_chunk(self):
        """Chunk objet (ollama.ChatResponse) : mêmes champs lus en attributs."""
        from ollama import ChatResponse, Message

        chunk = ChatResponse(
            model="m",
            done=True,
            message=Message(role="assistant", content=""),
            eval_count=157,
            eval_duration=2_000_000_000,
            load_duration=8_000_000_000,
            total_duration=11_000_000_000,
        )
        m = ollama_metrics("m", chunk, wall_duration_s=12.0)
        assert m.tokens_per_second == 78.5
        assert m.load_duration_s == 8.0
        assert m.total_duration_s == 11.0

    def test_missing_eval_duration_falls_back_to_wall_time(self):
        m = ollama_metrics("m", _final_chunk(eval_count=100), wall_duration_s=4.0)
        assert m.tokens_per_second == 25.0
        assert m.throughput_estimated is True

    def test_real_zero_eval_count_is_kept(self):
        """eval_count = 0 renvoyé par Ollama : 0 token, pas l'estimation depuis le texte."""
        m = ollama_metrics("m", _final_chunk(eval_count=0, eval_duration=10**9), 1.0, 50)
        assert m.output_tokens == 0
        assert m.tokens_per_second == 0.0

    def test_load_measured_only_when_load_duration_present(self):
        without = ollama_metrics("m", _final_chunk(eval_count=10, eval_duration=10**9), 1.0)
        assert without.load_measured is False
        warm = ollama_metrics(
            "m", _final_chunk(eval_count=10, eval_duration=10**9, load_duration=0), 1.0
        )
        assert warm.load_measured is True
        assert warm.load_duration_s == 0.0

    def test_zero_eval_duration_falls_back_without_division_by_zero(self):
        m = ollama_metrics("m", _final_chunk(eval_count=100, eval_duration=0), 4.0)
        assert m.tokens_per_second == 25.0
        assert m.eval_duration_s is None
        assert m.throughput_estimated is True

    def test_zero_wall_time_without_eval_duration(self):
        m = ollama_metrics("m", _final_chunk(eval_count=100), wall_duration_s=0.0)
        assert m.tokens_per_second == 0.0

    def test_total_duration_falls_back_to_wall_time(self):
        m = ollama_metrics("m", _final_chunk(eval_count=10, eval_duration=10**9), 3.456)
        assert m.total_duration_s == 3.46
        assert m.load_duration_s == 0.0

    def test_no_final_chunk(self):
        """Flux sans chunk final : tokens estimés, débit sur la durée murale, sans exception."""
        m = ollama_metrics("m", None, wall_duration_s=2.0, fallback_output_tokens=10)
        assert m.output_tokens == 10
        assert m.tokens_per_second == 5.0
        assert m.input_tokens == 0
        assert m.load_measured is False
        assert m.throughput_estimated is True


@pytest.mark.asyncio
async def test_ollama_provider_stream_yields_d3_metrics(monkeypatch):
    """OllamaProvider.chat_stream : le débit vient d'eval_duration, pas de la durée murale."""
    from src.core.providers.ollama_provider import OllamaProvider

    chunks = [
        {"done": False, "message": {"content": "Bonjour"}},
        _final_chunk(
            eval_count=157,
            eval_duration=2_000_000_000,
            load_duration=8_000_000_000,
            total_duration=11_000_000_000,
        ),
    ]

    class FakeClient:
        async def chat(self, **kwargs):
            async def stream():
                for chunk in chunks:
                    yield chunk

            return stream()

    provider = OllamaProvider()
    monkeypatch.setattr(provider, "_create_async_client", lambda: FakeClient())

    items = [item async for item in provider.chat_stream("qwen2.5:1.5b", [])]

    assert items[0] == "Bonjour"
    metrics = items[-1]
    assert isinstance(metrics, InferenceMetrics)
    assert metrics.tokens_per_second == 78.5
    assert metrics.load_duration_s == 8.0
    assert metrics.total_duration_s == 11.0


@pytest.mark.asyncio
async def test_ollama_provider_stream_with_chat_response_objects(monkeypatch):
    """Chemin de production : le client asynchrone d'ollama renvoie des ChatResponse."""
    from ollama import ChatResponse, Message

    from src.core.providers.ollama_provider import OllamaProvider

    chunks = [
        ChatResponse(model="m", done=False, message=Message(role="assistant", content="Bon")),
        ChatResponse(model="m", done=False, message=Message(role="assistant", content="jour")),
        ChatResponse(
            model="m",
            done=True,
            message=Message(role="assistant", content=""),
            prompt_eval_count=30,
            prompt_eval_duration=500_000_000,
            eval_count=157,
            eval_duration=2_000_000_000,
            load_duration=8_000_000_000,
            total_duration=11_000_000_000,
        ),
    ]

    class FakeClient:
        async def chat(self, **kwargs):
            async def stream():
                for chunk in chunks:
                    yield chunk

            return stream()

    provider = OllamaProvider()
    monkeypatch.setattr(provider, "_create_async_client", lambda: FakeClient())

    items = [item async for item in provider.chat_stream("qwen2.5:1.5b", [])]

    assert items[:2] == ["Bon", "jour"]
    metrics = items[-1]
    assert isinstance(metrics, InferenceMetrics)
    assert metrics.tokens_per_second == 78.5
    assert metrics.throughput_estimated is False
    assert metrics.load_measured is True
    assert metrics.load_duration_s == 8.0
    assert metrics.total_duration_s == 11.0
    assert metrics.input_tokens == 30
    assert metrics.prompt_eval_duration_s == 0.5
