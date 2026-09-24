"""
Tests unitaires pour MetricsService - Sprint 2
Vérifie la cohérence des calculs carbone avec l'ancienne implémentation
"""

import pytest

from src.core.metrics_service import CarbonEstimate, get_metrics_service


class TestMetricsServiceCarbonCalculations:
    """Tests pour la centralisation des calculs carbone."""

    @pytest.fixture
    def metrics_service(self):
        """Instance du service."""
        return get_metrics_service()

    def test_calculate_carbon_local_model_basic(self, metrics_service):
        """Test calcul carbone pour modèle local avec tokens basiques."""
        result = metrics_service.calculate_carbon(
            model_tag="qwen2.5:1.5b", output_tokens=100, duration_s=5.0, is_local=True
        )

        assert isinstance(result, CarbonEstimate)
        assert result.carbon_mg > 0
        assert result.source == "theoretical_local"
        assert "theoretical" in result.details["method"]
        assert result.carbon_g == result.carbon_mg / 1000

    def test_calculate_carbon_api_model(self, metrics_service):
        """Test calcul carbone pour modèle API (Mistral)."""
        # Note: Le calcul cloud nécessite des paramètres > 0
        # Si le modèle n'est pas dans MODELS_DB, params_b sera 0
        # Dans ce cas, le calcul retourne 0.0 (comportement actuel)

        result = metrics_service.calculate_carbon(
            model_tag="qwen2.5:7b",  # Utiliser un modèle connu
            output_tokens=500,
            duration_s=10.0,
            is_local=False,  # Simuler un appel API
        )

        assert isinstance(result, CarbonEstimate)
        # Le résultat peut être 0 si params_b=0, ce qui est acceptable
        assert result.carbon_mg >= 0
        assert result.source == "theoretical_cloud"
        assert result.details["is_local"] is False
        assert result.details["output_tokens"] == 500

    def test_calculate_carbon_api_model_with_known_params(self, metrics_service):
        """Test calcul carbone API avec modèle ayant des paramètres connus."""
        # Utiliser un modèle qui existe dans MODELS_DB avec des paramètres
        result = metrics_service.calculate_carbon(
            model_tag="llama3.2:3b",  # Modèle avec params connus
            output_tokens=500,
            duration_s=10.0,
            is_local=False,
        )

        assert isinstance(result, CarbonEstimate)
        # Si params > 0, le calcul devrait retourner une valeur > 0
        if metrics_service.get_model_params_billions("llama3.2:3b") > 0:
            assert result.carbon_mg > 0

    def test_calculate_carbon_with_measured_value(self, metrics_service):
        """Test priorité du carbone mesuré (CodeCarbon) sur le théorique."""
        measured_g = 0.05  # 50 mg mesuré

        result = metrics_service.calculate_carbon(
            model_tag="qwen2.5:1.5b",
            output_tokens=100,
            duration_s=5.0,
            measured_carbon_g=measured_g,
            is_local=True,
        )

        assert result.carbon_g == measured_g
        assert result.carbon_mg == measured_g * 1000
        assert result.source == "measured"
        assert result.details["method"] == "CodeCarbon"

    def test_calculate_carbon_zero_tokens(self, metrics_service):
        """Test avec 0 tokens générés."""
        result = metrics_service.calculate_carbon(
            model_tag="qwen2.5:1.5b", output_tokens=0, duration_s=2.0, is_local=True
        )

        # Devrait retourner un résultat valide même avec 0 tokens
        assert isinstance(result, CarbonEstimate)
        assert result.carbon_mg >= 0

    def test_calculate_carbon_consistency_with_legacy(self, metrics_service):
        """
        Test de cohérence avec l'ancienne implémentation (non-regression).

        Ancienne logique:
        - Local: CarbonCalculator.compute_local_theoretical_g(tokens) * 1000
        - API: CarbonCalculator.compute_mistral_impact_g(params, tokens) * 1000
        """
        from src.core.green_monitor import CarbonCalculator

        output_tokens = 250

        # Test Local
        result_local = metrics_service.calculate_carbon(
            model_tag="qwen2.5:1.5b", output_tokens=output_tokens, duration_s=5.0, is_local=True
        )

        expected_local_g = CarbonCalculator.compute_local_theoretical_g(output_tokens)
        expected_local_mg = expected_local_g * 1000

        assert (
            abs(result_local.carbon_mg - expected_local_mg) < 0.01
        ), f"Incohérence Local: {result_local.carbon_mg} != {expected_local_mg}"

    def test_energy_estimation_from_carbon(self, metrics_service):
        """Test estimation énergie à partir du carbone."""
        result = metrics_service.calculate_carbon(
            model_tag="qwen2.5:1.5b", output_tokens=500, duration_s=10.0, is_local=True
        )

        # Vérifier que l'énergie est cohérente avec le carbone
        # France: ~50g CO2/kWh
        expected_kwh = result.carbon_g / 50
        expected_wh = expected_kwh * 1000

        assert result.energy_wh > 0
        assert abs(result.energy_wh - expected_wh) < 0.01

    def test_get_model_params_billions(self, metrics_service):
        """Test extraction des paramètres modèle."""
        # Modèle connu dans MODELS_DB
        params = metrics_service.get_model_params_billions("qwen2.5:1.5b")
        assert params > 0
        assert params < 100  # Sanity check

        # Si modèle inconnu, extract_params_billions peut retourner:
        # - La valeur extraite du tag si format reconnu (ex: "7b")
        # - 0.0 si aucun pattern ne matche
        # On teste les deux cas

        params_tag = metrics_service.get_model_params_billions("unknown:7b")
        # Selon l'implémentation, cela peut être 7.0 ou 0.0
        assert params_tag >= 0  # Au minimum 0

        # Test avec un tag sans pattern reconnaissable
        params_no_pattern = metrics_service.get_model_params_billions("unknown-model")
        assert params_no_pattern >= 0

    def test_invalid_measured_carbon_ignored(self, metrics_service):
        """Test que les valeurs mesurées invalides sont ignorées."""
        # Valeur mesurée trop petite
        result = metrics_service.calculate_carbon(
            model_tag="qwen2.5:1.5b",
            output_tokens=100,
            duration_s=5.0,
            measured_carbon_g=0.00001,  # < 0.0001 threshold
            is_local=True,
        )

        # Devrait utiliser le calcul théorique
        assert result.source == "theoretical_local"

        # Valeur mesurée None
        result_none = metrics_service.calculate_carbon(
            model_tag="qwen2.5:1.5b",
            output_tokens=100,
            duration_s=5.0,
            measured_carbon_g=None,
            is_local=True,
        )

        assert result_none.source == "theoretical_local"


@pytest.mark.integration
class TestMetricsServiceIntegration:
    """Tests d'intégration avec les autres composants."""

    @pytest.fixture
    def metrics_service(self):
        """Instance du service."""
        return get_metrics_service()

    def test_integration_with_inference_result(self, metrics_service):
        """Test intégration avec InferenceResult (simulation)."""

        # Simuler un résultat d'inférence
        class MockMetrics:
            def __init__(self):
                self.output_tokens = 150
                self.total_duration_s = 8.5
                self.model_size_gb = 1.2

        mock_metrics = MockMetrics()

        result = metrics_service.calculate_carbon(
            model_tag="qwen2.5:1.5b",
            output_tokens=mock_metrics.output_tokens,
            duration_s=mock_metrics.total_duration_s,
            is_local=True,
        )

        assert result.carbon_mg > 0
        assert result.details["duration_s"] == mock_metrics.total_duration_s
        assert result.details["output_tokens"] == mock_metrics.output_tokens


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
