# src/core/metrics_service.py
"""
Service centralisé pour les calculs de métriques.
Extrait la logique métier des tabs UI.
"""

from dataclasses import dataclass
from typing import Any

from src.core.green_monitor import CarbonCalculator
from src.core.models_db import MODELS_DB
from src.core.utils import extract_params_billions


@dataclass
class DisplayMetrics:
    """Métriques formatées pour l'affichage UI."""

    tokens_per_second: str
    total_duration: str
    input_tokens: str
    output_tokens: str
    carbon_mg: str
    carbon_formatted: str
    energy_wh: str
    model_params: str
    is_local: bool


@dataclass
class CarbonEstimate:
    """Estimation carbone pour une inférence."""

    carbon_g: float
    carbon_mg: float
    energy_wh: float
    source: str  # "measured", "estimated", "theoretical"
    details: dict[str, Any]


class MetricsService:
    """
    Service pour les calculs et le formatage des métriques.

    Centralise la logique dispersée dans les tabs UI :
    - Calcul du carbone (théorique vs mesuré)
    - Formatage des durées et tokens
    - Extraction des paramètres modèle
    """

    def get_model_params_billions(self, model_tag: str) -> float:
        """
        Récupère le nombre de paramètres d'un modèle en milliards.

        Args:
            model_tag: Tag du modèle (ex: "qwen2.5:1.5b")

        Returns:
            float: Nombre de paramètres en milliards
        """
        # Chercher dans MODELS_DB
        for _name, info in MODELS_DB.items():
            if info.get("ollama_tag") == model_tag:
                params = info.get("params") or info.get("params_act") or info.get("params_tot")
                if params:
                    return extract_params_billions(params)

        # Fallback : extraire du tag lui-même
        return extract_params_billions(model_tag)

    def calculate_carbon(
        self,
        model_tag: str,
        output_tokens: int,
        duration_s: float,
        measured_carbon_g: float | None = None,
        is_local: bool = True,
    ) -> CarbonEstimate:
        """
        Calcule ou estime les émissions carbone d'une inférence.

        Priorité :
        1. Carbone mesuré (CodeCarbon) si disponible et > 0
        2. Calcul théorique basé sur les paramètres du modèle

        Args:
            model_tag: Tag du modèle
            output_tokens: Nombre de tokens générés
            duration_s: Durée de l'inférence en secondes
            measured_carbon_g: Carbone mesuré par CodeCarbon (optionnel)
            is_local: True si modèle local, False si API cloud

        Returns:
            CarbonEstimate avec les détails du calcul
        """
        params_b = self.get_model_params_billions(model_tag)

        # Si carbone mesuré disponible et significatif
        if measured_carbon_g is not None and measured_carbon_g > 0.0001:
            return CarbonEstimate(
                carbon_g=measured_carbon_g,
                carbon_mg=measured_carbon_g * 1000,
                energy_wh=self._estimate_energy_from_carbon(measured_carbon_g),
                source="measured",
                details={
                    "method": "CodeCarbon",
                    "model_params_b": params_b,
                    "duration_s": duration_s,
                },
            )

        # Calcul théorique via CarbonCalculator
        if is_local:
            # Utiliser la méthode statique existante
            carbon_g = CarbonCalculator.compute_local_theoretical_g(output_tokens)
            source = "theoretical_local"
        else:
            # Pour les modèles cloud (Mistral, etc.)
            carbon_g = CarbonCalculator.compute_mistral_impact_g(params_b, output_tokens)
            source = "theoretical_cloud"

        return CarbonEstimate(
            carbon_g=carbon_g,
            carbon_mg=carbon_g * 1000,
            energy_wh=self._estimate_energy_from_carbon(carbon_g),
            source=source,
            details={
                "method": "theoretical",
                "model_params_b": params_b,
                "output_tokens": output_tokens,
                "duration_s": duration_s,
                "is_local": is_local,
            },
        )

    def _estimate_energy_from_carbon(self, carbon_g: float) -> float:
        """
        Estime l'énergie consommée à partir du carbone.
        Utilise le mix énergétique français (~50g CO2/kWh).
        """
        co2_per_kwh_france = 50  # g CO2/kWh
        if carbon_g <= 0:
            return 0.0
        kwh = carbon_g / co2_per_kwh_france
        return kwh * 1000  # Convertir en Wh

    def format_duration(self, duration_s: float) -> str:
        """Formate une durée en secondes pour l'affichage."""
        if duration_s < 0.01:
            return "< 0.01s"
        elif duration_s < 1:
            return f"{duration_s * 1000:.0f}ms"
        elif duration_s < 60:
            return f"{duration_s:.2f}s"
        else:
            minutes = int(duration_s // 60)
            seconds = duration_s % 60
            return f"{minutes}m {seconds:.1f}s"

    def format_tokens_per_second(self, tps: float) -> str:
        """Formate le débit de tokens pour l'affichage."""
        if tps <= 0:
            return "N/A"
        elif tps < 1:
            return f"{tps:.2f} t/s"
        elif tps < 100:
            return f"{tps:.1f} t/s"
        else:
            return f"{tps:.0f} t/s"

    def format_carbon(self, carbon_g: float) -> str:
        """Formate les émissions carbone pour l'affichage."""
        if carbon_g <= 0:
            return "~0 mg"

        carbon_mg = carbon_g * 1000

        if carbon_mg < 0.01:
            return "< 0.01 mg"
        elif carbon_mg < 1:
            return f"{carbon_mg:.3f} mg"
        elif carbon_mg < 100:
            return f"{carbon_mg:.2f} mg"
        elif carbon_mg < 1000:
            return f"{carbon_mg:.1f} mg"
        else:
            return f"{carbon_g:.3f} g"

    def format_model_params(self, params_b: float) -> str:
        """Formate le nombre de paramètres pour l'affichage."""
        if params_b <= 0:
            return "?"
        elif params_b < 1:
            return f"{params_b * 1000:.0f}M"
        elif params_b < 10:
            return f"{params_b:.1f}B"
        else:
            return f"{params_b:.0f}B"

    def build_display_metrics(
        self,
        model_tag: str,
        input_tokens: int,
        output_tokens: int,
        duration_s: float,
        tokens_per_second: float,
        measured_carbon_g: float | None = None,
        is_local: bool = True,
    ) -> DisplayMetrics:
        """
        Construit les métriques formatées pour l'affichage UI.

        Args:
            model_tag: Tag du modèle
            input_tokens: Tokens d'entrée
            output_tokens: Tokens générés
            duration_s: Durée totale
            tokens_per_second: Débit de génération
            measured_carbon_g: Carbone mesuré (optionnel)
            is_local: True si modèle local

        Returns:
            DisplayMetrics prêtes pour l'affichage
        """
        carbon = self.calculate_carbon(
            model_tag=model_tag,
            output_tokens=output_tokens,
            duration_s=duration_s,
            measured_carbon_g=measured_carbon_g,
            is_local=is_local,
        )

        params_b = self.get_model_params_billions(model_tag)

        return DisplayMetrics(
            tokens_per_second=self.format_tokens_per_second(tokens_per_second),
            total_duration=self.format_duration(duration_s),
            input_tokens=f"{input_tokens:,}",
            output_tokens=f"{output_tokens:,}",
            carbon_mg=f"{carbon.carbon_mg:.2f}",
            carbon_formatted=self.format_carbon(carbon.carbon_g),
            energy_wh=f"{carbon.energy_wh:.4f}",
            model_params=self.format_model_params(params_b),
            is_local=is_local,
        )


# Instance singleton
_metrics_service: MetricsService | None = None


def get_metrics_service() -> MetricsService:
    """Retourne l'instance singleton du service de métriques."""
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService()
    return _metrics_service
