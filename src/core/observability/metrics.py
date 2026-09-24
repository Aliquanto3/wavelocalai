# src/core/observability/metrics.py
"""
Metrics Service - Telemetry for AI Workloads.
Tracks Token consumption, Latency, and Costs.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MetricSnapshot:
    total_requests: int = 0
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_errors: int = 0
    avg_latency_ms: float = 0.0


class MetricsService:
    _instance = None

    def __init__(self):
        self._metrics = MetricSnapshot()
        self._latencies: list[float] = []

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = MetricsService()
        return cls._instance

    def record_transaction(
        self,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        success: bool = True,
    ):
        """Records a single LLM interaction."""
        self._metrics.total_requests += 1
        self._metrics.total_tokens_input += input_tokens
        self._metrics.total_tokens_output += output_tokens

        if not success:
            self._metrics.total_errors += 1

        self._latencies.append(latency_ms)

        # Keep window of last 1000 requests for avg calculation
        if len(self._latencies) > 1000:
            self._latencies.pop(0)

        # Update moving average
        if self._latencies:
            self._metrics.avg_latency_ms = sum(self._latencies) / len(self._latencies)

        # Log metric event (for ingestion by external tools)
        logging.info(
            "Metric Recorded",
            extra={
                "props": {
                    "type": "metric",
                    "provider": provider,
                    "latency_ms": latency_ms,
                    "tokens_total": input_tokens + output_tokens,
                }
            },
        )

    def get_snapshot(self) -> dict:
        return {
            "requests": self._metrics.total_requests,
            "tokens": {
                "input": self._metrics.total_tokens_input,
                "output": self._metrics.total_tokens_output,
                "total": self._metrics.total_tokens_input + self._metrics.total_tokens_output,
            },
            "performance": {
                "avg_latency_ms": round(self._metrics.avg_latency_ms, 2),
                "error_rate": round(
                    (self._metrics.total_errors / max(1, self._metrics.total_requests)) * 100, 2
                ),
            },
        }
