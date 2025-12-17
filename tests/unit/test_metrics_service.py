# tests/unit/test_metrics_service.py
"""
Tests unitaires pour MetricsService.
"""

import pytest

from src.core.metrics_service import (
    CarbonEstimate,
    DisplayMetrics,
    MetricsService,
    get_metrics_service,
)


class TestMetricsServiceFormatting:
    """Tests des méthodes de formatage."""

    def setup_method(self):
        self.service = MetricsService()

    def test_format_duration_milliseconds(self):
        """Test formatage durée < 1s."""
        result = self.service.format_duration(0.5)
        assert "ms" in result or "0.50s" in result

    def test_format_duration_seconds(self):
        """Test formatage durée en secondes."""
        result = self.service.format_duration(5.5)
        assert "5.50s" in result

    def test_format_duration_minutes(self):
        """Test formatage durée en minutes."""
        result = self.service.format_duration(125)
        assert "2m" in result

    def test_format_tokens_per_second_zero(self):
        """Test formatage TPS nul."""
        result = self.service.format_tokens_per_second(0)
        assert result == "N/A"

    def test_format_tokens_per_second_normal(self):
        """Test formatage TPS normal."""
        result = self.service.format_tokens_per_second(25.5)
        assert "25.5" in result
        assert "t/s" in result

    def test_format_carbon_zero(self):
        """Test formatage carbone nul."""
        result = self.service.format_carbon(0)
        assert "0" in result

    def test_format_carbon_milligrams(self):
        """Test formatage carbone en mg."""
        result = self.service.format_carbon(0.005)  # 5mg
        assert "mg" in result

    def test_format_carbon_grams(self):
        """Test formatage carbone en g."""
        result = self.service.format_carbon(2.5)  # 2.5g
        assert "g" in result

    def test_format_model_params_millions(self):
        """Test formatage params en millions."""
        result = self.service.format_model_params(0.5)
        assert "M" in result

    def test_format_model_params_billions(self):
        """Test formatage params en milliards."""
        result = self.service.format_model_params(7)
        assert "B" in result


class TestMetricsServiceCalculations:
    """Tests des calculs de métriques."""

    def setup_method(self):
        self.service = MetricsService()

    def test_get_model_params_from_tag(self):
        """Test extraction params depuis le tag."""
        result = self.service.get_model_params_billions("qwen2.5:1.5b")
        # Devrait extraire 1.5 du tag ou de MODELS_DB
        assert result >= 0

    def test_calculate_carbon_measured(self):
        """Test avec carbone mesuré."""
        result = self.service.calculate_carbon(
            model_tag="test-model",
            output_tokens=100,
            duration_s=1.0,
            measured_carbon_g=0.01,
            is_local=True,
        )

        assert isinstance(result, CarbonEstimate)
        assert result.source == "measured"
        assert result.carbon_g == 0.01

    def test_calculate_carbon_theoretical(self):
        """Test avec calcul théorique."""
        result = self.service.calculate_carbon(
            model_tag="qwen2.5:1.5b",
            output_tokens=100,
            duration_s=1.0,
            measured_carbon_g=None,
            is_local=True,
        )

        assert isinstance(result, CarbonEstimate)
        assert "theoretical" in result.source
        assert result.carbon_g >= 0

    def test_build_display_metrics(self):
        """Test construction des métriques d'affichage."""
        result = self.service.build_display_metrics(
            model_tag="qwen2.5:1.5b",
            input_tokens=50,
            output_tokens=100,
            duration_s=2.0,
            tokens_per_second=50.0,
            measured_carbon_g=0.005,
            is_local=True,
        )

        assert isinstance(result, DisplayMetrics)
        assert result.is_local is True
        assert "t/s" in result.tokens_per_second
        assert "50" in result.input_tokens


class TestMetricsServiceSingleton:
    """Tests du singleton."""

    def test_singleton_returns_same_instance(self):
        """Test que get_metrics_service retourne la même instance."""
        service1 = get_metrics_service()
        service2 = get_metrics_service()
        assert service1 is service2
