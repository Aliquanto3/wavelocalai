# src/core/exporters/metrics_exporter.py
"""
Exporter de métriques vers différents formats.
Supporte JSON, CSV et format Prometheus.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """Point de métrique individuel."""

    name: str
    value: float
    timestamp: datetime
    labels: dict[str, str] | None = None

    def to_prometheus(self) -> str:
        """Formate en format Prometheus."""
        labels_str = ""
        if self.labels:
            label_pairs = [f'{k}="{v}"' for k, v in self.labels.items()]
            labels_str = "{" + ",".join(label_pairs) + "}"

        unix_ms = int(self.timestamp.timestamp() * 1000)
        return f"{self.name}{labels_str} {self.value} {unix_ms}"

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


class MetricsExporter:
    """
    Exporter de métriques multi-format.

    Supporte :
    - JSON (fichier ou string)
    - CSV
    - Prometheus text format
    - OpenTelemetry (préparation future)
    """

    def __init__(self, output_dir: str | Path | None = None):
        """
        Initialise l'exporter.

        Args:
            output_dir: Répertoire de sortie pour les fichiers
        """
        if output_dir is None:
            output_dir = Path(__file__).parent.parent.parent.parent / "data" / "exports"

        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._metrics_buffer: list[MetricPoint] = []

    def record(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """
        Enregistre une métrique dans le buffer.

        Args:
            name: Nom de la métrique (ex: "inference_duration_seconds")
            value: Valeur numérique
            labels: Labels optionnels (ex: {"model": "qwen2.5:1.5b"})
            timestamp: Timestamp (défaut: maintenant)
        """
        point = MetricPoint(
            name=name,
            value=value,
            timestamp=timestamp or datetime.now(),
            labels=labels,
        )
        self._metrics_buffer.append(point)

    def record_inference(
        self,
        model_tag: str,
        duration_s: float,
        tokens_per_second: float,
        input_tokens: int,
        output_tokens: int,
        carbon_mg: float,
        is_local: bool = True,
    ) -> None:
        """
        Enregistre les métriques d'une inférence.

        Crée automatiquement plusieurs métriques avec les bons labels.
        """
        labels = {
            "model": model_tag,
            "type": "local" if is_local else "cloud",
        }
        now = datetime.now()

        self.record("wavelocalai_inference_duration_seconds", duration_s, labels, now)
        self.record("wavelocalai_inference_tokens_per_second", tokens_per_second, labels, now)
        self.record("wavelocalai_inference_input_tokens", input_tokens, labels, now)
        self.record("wavelocalai_inference_output_tokens", output_tokens, labels, now)
        self.record("wavelocalai_inference_carbon_mg", carbon_mg, labels, now)

    def export_prometheus(self, include_help: bool = True) -> str:
        """
        Exporte les métriques au format Prometheus.

        Args:
            include_help: Inclure les commentaires HELP et TYPE

        Returns:
            String au format Prometheus text exposition
        """
        lines = []

        if include_help:
            lines.extend(
                [
                    "# HELP wavelocalai_inference_duration_seconds Duration of inference in seconds",
                    "# TYPE wavelocalai_inference_duration_seconds gauge",
                    "# HELP wavelocalai_inference_tokens_per_second Token generation speed",
                    "# TYPE wavelocalai_inference_tokens_per_second gauge",
                    "# HELP wavelocalai_inference_carbon_mg Carbon emissions in milligrams",
                    "# TYPE wavelocalai_inference_carbon_mg gauge",
                    "",
                ]
            )

        for point in self._metrics_buffer:
            lines.append(point.to_prometheus())

        return "\n".join(lines)

    def export_json(self) -> str:
        """Exporte les métriques en JSON."""
        return json.dumps(
            [p.to_dict() for p in self._metrics_buffer],
            indent=2,
            default=str,
        )

    def export_to_file(
        self,
        format: str = "json",
        filename: str | None = None,
    ) -> Path:
        """
        Exporte les métriques vers un fichier.

        Args:
            format: Format de sortie ("json", "prometheus", "csv")
            filename: Nom du fichier (auto-généré si None)

        Returns:
            Path du fichier créé
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if filename is None:
            filename = f"metrics_{timestamp}.{format}"

        output_path = self._output_dir / filename

        if format == "json":
            content = self.export_json()
        elif format == "prometheus":
            content = self.export_prometheus()
        elif format == "csv":
            content = self._export_csv_string()
        else:
            raise ValueError(f"Format non supporté: {format}")

        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Metrics exported to {output_path}")

        return output_path

    def _export_csv_string(self) -> str:
        """Génère le contenu CSV."""
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["timestamp", "name", "value", "labels"])

        for point in self._metrics_buffer:
            labels_str = json.dumps(point.labels) if point.labels else ""
            writer.writerow(
                [
                    point.timestamp.isoformat(),
                    point.name,
                    point.value,
                    labels_str,
                ]
            )

        return output.getvalue()

    def flush(self) -> int:
        """
        Vide le buffer de métriques.

        Returns:
            Nombre de métriques supprimées
        """
        count = len(self._metrics_buffer)
        self._metrics_buffer.clear()
        return count

    def get_buffer_size(self) -> int:
        """Retourne le nombre de métriques dans le buffer."""
        return len(self._metrics_buffer)

    def get_latest_metrics(
        self,
        name: str | None = None,
        limit: int = 100,
    ) -> list[MetricPoint]:
        """
        Récupère les dernières métriques du buffer.

        Args:
            name: Filtrer par nom de métrique
            limit: Nombre maximum de résultats

        Returns:
            Liste des métriques
        """
        metrics = self._metrics_buffer

        if name:
            metrics = [m for m in metrics if m.name == name]

        return metrics[-limit:]


# Instance singleton
_metrics_exporter: MetricsExporter | None = None


def get_metrics_exporter() -> MetricsExporter:
    """Retourne l'instance singleton de l'exporter."""
    global _metrics_exporter
    if _metrics_exporter is None:
        _metrics_exporter = MetricsExporter()
    return _metrics_exporter
