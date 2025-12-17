# tests/unit/test_benchmark_repository.py
"""
Tests unitaires pour BenchmarkRepository.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.core.repositories.benchmark_repository import (
    BenchmarkRepository,
    BenchmarkResult,
)


class TestBenchmarkRepository:
    """Tests du repository de benchmarks."""

    def setup_method(self):
        """Crée un repository temporaire pour chaque test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_benchmarks.db"
        self.repo = BenchmarkRepository(db_path=self.db_path)

    def _create_sample_result(
        self,
        benchmark_id: str = "test-bench-1",
        model_tag: str = "qwen2.5:1.5b",
    ) -> BenchmarkResult:
        """Crée un résultat de test."""
        return BenchmarkResult(
            id=None,
            benchmark_id=benchmark_id,
            model_tag=model_tag,
            prompt="Test prompt",
            response="Test response",
            input_tokens=10,
            output_tokens=50,
            duration_s=1.5,
            tokens_per_second=33.3,
            carbon_mg=0.5,
            timestamp=datetime.now(),
            metadata={"test": True},
        )

    def test_save_and_retrieve_result(self):
        """Test sauvegarde et récupération d'un résultat."""
        result = self._create_sample_result()

        result_id = self.repo.save_result(result)

        assert result_id is not None

        retrieved = self.repo.get_result(result_id)

        assert retrieved is not None
        assert retrieved.model_tag == "qwen2.5:1.5b"
        assert retrieved.benchmark_id == "test-bench-1"
        assert retrieved.tokens_per_second == 33.3

    def test_save_batch(self):
        """Test sauvegarde en batch."""
        results = [
            self._create_sample_result(model_tag="model-a"),
            self._create_sample_result(model_tag="model-b"),
            self._create_sample_result(model_tag="model-c"),
        ]

        ids = self.repo.save_results_batch(results)

        assert len(ids) == 3

        for result_id in ids:
            assert self.repo.get_result(result_id) is not None

    def test_get_results_by_benchmark(self):
        """Test récupération par benchmark ID."""
        # Créer des résultats pour 2 benchmarks différents
        for _ in range(3):
            self.repo.save_result(self._create_sample_result(benchmark_id="bench-a"))
        for _ in range(2):
            self.repo.save_result(self._create_sample_result(benchmark_id="bench-b"))

        results_a = self.repo.get_results_by_benchmark("bench-a")
        results_b = self.repo.get_results_by_benchmark("bench-b")

        assert len(results_a) == 3
        assert len(results_b) == 2

    def test_get_results_by_model(self):
        """Test récupération par modèle."""
        self.repo.save_result(self._create_sample_result(model_tag="model-x"))
        self.repo.save_result(self._create_sample_result(model_tag="model-x"))
        self.repo.save_result(self._create_sample_result(model_tag="model-y"))

        results = self.repo.get_results_by_model("model-x")

        assert len(results) == 2
        assert all(r.model_tag == "model-x" for r in results)

    def test_compare_models(self):
        """Test comparaison de modèles."""
        # Créer des résultats avec différentes performances
        for _i in range(5):
            result = self._create_sample_result(model_tag="fast-model")
            result.tokens_per_second = 50.0
            self.repo.save_result(result)

        for _i in range(5):
            result = self._create_sample_result(model_tag="slow-model")
            result.tokens_per_second = 20.0
            self.repo.save_result(result)

        comparison = self.repo.compare_models(["fast-model", "slow-model"])

        assert "fast-model" in comparison
        assert "slow-model" in comparison
        assert (
            comparison["fast-model"]["avg_tokens_per_second"]
            > comparison["slow-model"]["avg_tokens_per_second"]
        )

    def test_delete_benchmark(self):
        """Test suppression d'un benchmark."""
        for _ in range(5):
            self.repo.save_result(self._create_sample_result(benchmark_id="to-delete"))

        deleted = self.repo.delete_benchmark("to-delete")

        assert deleted == 5
        assert len(self.repo.get_results_by_benchmark("to-delete")) == 0

    def test_export_to_csv(self):
        """Test export CSV."""
        for _i in range(3):
            self.repo.save_result(self._create_sample_result())

        output_path = Path(self.temp_dir) / "export.csv"
        result_path = self.repo.export_to_csv("test-bench-1", output_path)

        assert result_path.exists()
        content = result_path.read_text()
        assert "qwen2.5:1.5b" in content
        assert "test-bench-1" in content
