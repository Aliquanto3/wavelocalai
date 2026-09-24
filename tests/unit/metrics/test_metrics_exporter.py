# tests/unit/test_metrics_exporter.py
"""
Tests unitaires pour MetricsExporter.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.core.exporters.metrics_exporter import (
    MetricPoint,
    MetricsExporter,
    get_metrics_exporter,
)


class TestMetricPoint:
    """Tests de MetricPoint."""

    def test_to_prometheus_simple(self):
        """Test format Prometheus sans labels."""
        point = MetricPoint(
            name="test_metric",
            value=42.5,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
        )

        result = point.to_prometheus()

        assert "test_metric" in result
        assert "42.5" in result

    def test_to_prometheus_with_labels(self):
        """Test format Prometheus avec labels."""
        point = MetricPoint(
            name="test_metric",
            value=42.5,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            labels={"model": "qwen2.5", "type": "local"},
        )

        result = point.to_prometheus()

        assert 'model="qwen2.5"' in result
        assert 'type="local"' in result

    def test_to_dict(self):
        """Test conversion en dict."""
        point = MetricPoint(
            name="test_metric",
            value=42.5,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            labels={"model": "test"},
        )

        result = point.to_dict()

        assert result["name"] == "test_metric"
        assert result["value"] == 42.5
        assert result["labels"]["model"] == "test"


class TestMetricsExporter:
    """Tests de MetricsExporter."""

    def setup_method(self):
        """Crée un exporter temporaire pour chaque test."""
        self.temp_dir = tempfile.mkdtemp()
        self.exporter = MetricsExporter(output_dir=self.temp_dir)

    def test_record_simple(self):
        """Test enregistrement simple."""
        self.exporter.record("test_metric", 42.5)

        assert self.exporter.get_buffer_size() == 1

    def test_record_inference(self):
        """Test enregistrement d'une inférence complète."""
        self.exporter.record_inference(
            model_tag="qwen2.5:1.5b",
            duration_s=1.5,
            tokens_per_second=33.3,
            input_tokens=10,
            output_tokens=50,
            carbon_mg=0.5,
            is_local=True,
        )

        # Devrait créer 5 métriques
        assert self.exporter.get_buffer_size() == 5

    def test_export_json(self):
        """Test export JSON."""
        self.exporter.record("metric_a", 10)
        self.exporter.record("metric_b", 20)

        json_str = self.exporter.export_json()
        data = json.loads(json_str)

        assert len(data) == 2
        assert data[0]["name"] == "metric_a"

    def test_export_prometheus(self):
        """Test export Prometheus."""
        self.exporter.record("test_metric", 42.5, labels={"model": "test"})

        result = self.exporter.export_prometheus()

        assert "# HELP" in result
        assert "# TYPE" in result
        assert "test_metric" in result

    def test_export_to_file_json(self):
        """Test export vers fichier JSON."""
        self.exporter.record("test", 100)

        path = self.exporter.export_to_file(format="json", filename="test.json")

        assert path.exists()
        content = json.loads(path.read_text())
        assert len(content) == 1

    def test_export_to_file_prometheus(self):
        """Test export vers fichier Prometheus."""
        self.exporter.record("test", 100)

        path = self.exporter.export_to_file(format="prometheus", filename="test.prom")

        assert path.exists()
        assert "test" in path.read_text()

    def test_flush(self):
        """Test vidage du buffer."""
        self.exporter.record("a", 1)
        self.exporter.record("b", 2)

        count = self.exporter.flush()

        assert count == 2
        assert self.exporter.get_buffer_size() == 0

    def test_get_latest_metrics(self):
        """Test récupération des dernières métriques."""
        for i in range(10):
            self.exporter.record(f"metric_{i % 2}", i)

        # Toutes les métriques
        all_metrics = self.exporter.get_latest_metrics()
        assert len(all_metrics) == 10

        # Filtrées par nom
        filtered = self.exporter.get_latest_metrics(name="metric_0")
        assert len(filtered) == 5

        # Avec limite
        limited = self.exporter.get_latest_metrics(limit=3)
        assert len(limited) == 3


class TestMetricsExporterSingleton:
    """Tests du singleton."""

    def test_singleton_returns_same_instance(self):
        """Test que get_metrics_exporter retourne la même instance."""
        exporter1 = get_metrics_exporter()
        exporter2 = get_metrics_exporter()
        assert exporter1 is exporter2
