# src/core/repositories/benchmark_repository.py
"""
Repository pour la persistance des benchmarks.
Permet de sauvegarder, charger et comparer les résultats de benchmarks.
"""

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Résultat d'un benchmark individuel."""

    id: str | None
    benchmark_id: str
    model_tag: str
    prompt: str
    response: str
    input_tokens: int
    output_tokens: int
    duration_s: float
    tokens_per_second: float
    carbon_mg: float
    timestamp: datetime
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convertit en dictionnaire pour la sérialisation."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["metadata"] = json.dumps(self.metadata) if self.metadata else None
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkResult":
        """Crée une instance depuis un dictionnaire."""
        # Filtrer les champs qui ne font pas partie du dataclass
        valid_fields = {
            "id",
            "benchmark_id",
            "model_tag",
            "prompt",
            "response",
            "input_tokens",
            "output_tokens",
            "duration_s",
            "tokens_per_second",
            "carbon_mg",
            "timestamp",
            "metadata",
        }
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        # Convertir timestamp
        if "timestamp" in filtered_data and isinstance(filtered_data["timestamp"], str):
            filtered_data["timestamp"] = datetime.fromisoformat(filtered_data["timestamp"])

        # Parser metadata JSON
        if filtered_data.get("metadata") and isinstance(filtered_data["metadata"], str):
            filtered_data["metadata"] = json.loads(filtered_data["metadata"])

        return cls(**filtered_data)


@dataclass
class BenchmarkSummary:
    """Résumé agrégé d'un benchmark."""

    benchmark_id: str
    model_tag: str
    num_runs: int
    avg_tokens_per_second: float
    avg_duration_s: float
    total_carbon_mg: float
    created_at: datetime
    completed_at: datetime | None


class BenchmarkRepository:
    """
    Repository pour stocker et récupérer les résultats de benchmarks.

    Utilise SQLite pour la persistance locale.
    """

    def __init__(self, db_path: str | Path | None = None):
        """
        Initialise le repository.

        Args:
            db_path: Chemin vers la base SQLite (défaut: data/benchmarks.db)
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent.parent / "data" / "benchmarks.db"

        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialise le schéma de la base de données."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_results (
                    id TEXT PRIMARY KEY,
                    benchmark_id TEXT NOT NULL,
                    model_tag TEXT NOT NULL,
                    prompt TEXT,
                    response TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    duration_s REAL,
                    tokens_per_second REAL,
                    carbon_mg REAL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_benchmark_id
                ON benchmark_results(benchmark_id)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_model_tag
                ON benchmark_results(model_tag)
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmarks (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    description TEXT,
                    config TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                )
            """
            )

            conn.commit()

    def save_result(self, result: BenchmarkResult) -> str:
        """
        Sauvegarde un résultat de benchmark.

        Args:
            result: Résultat à sauvegarder

        Returns:
            ID du résultat sauvegardé
        """
        import uuid

        if result.id is None:
            result.id = str(uuid.uuid4())

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO benchmark_results
                (id, benchmark_id, model_tag, prompt, response, input_tokens,
                 output_tokens, duration_s, tokens_per_second, carbon_mg,
                 timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    result.id,
                    result.benchmark_id,
                    result.model_tag,
                    result.prompt,
                    result.response,
                    result.input_tokens,
                    result.output_tokens,
                    result.duration_s,
                    result.tokens_per_second,
                    result.carbon_mg,
                    result.timestamp.isoformat(),
                    json.dumps(result.metadata) if result.metadata else None,
                ),
            )
            conn.commit()

        logger.info(f"Benchmark result saved: {result.id}")
        return result.id

    def save_results_batch(self, results: list[BenchmarkResult]) -> list[str]:
        """
        Sauvegarde plusieurs résultats en une seule transaction.

        Args:
            results: Liste des résultats

        Returns:
            Liste des IDs sauvegardés
        """
        import uuid

        ids = []
        with sqlite3.connect(self._db_path) as conn:
            for result in results:
                if result.id is None:
                    result.id = str(uuid.uuid4())
                ids.append(result.id)

                conn.execute(
                    """
                    INSERT OR REPLACE INTO benchmark_results
                    (id, benchmark_id, model_tag, prompt, response, input_tokens,
                     output_tokens, duration_s, tokens_per_second, carbon_mg,
                     timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        result.id,
                        result.benchmark_id,
                        result.model_tag,
                        result.prompt,
                        result.response,
                        result.input_tokens,
                        result.output_tokens,
                        result.duration_s,
                        result.tokens_per_second,
                        result.carbon_mg,
                        result.timestamp.isoformat(),
                        json.dumps(result.metadata) if result.metadata else None,
                    ),
                )
            conn.commit()

        logger.info(f"Saved {len(ids)} benchmark results in batch")
        return ids

    def get_result(self, result_id: str) -> BenchmarkResult | None:
        """Récupère un résultat par son ID."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM benchmark_results WHERE id = ?", (result_id,))
            row = cursor.fetchone()

            if row:
                return BenchmarkResult.from_dict(dict(row))
        return None

    def get_results_by_benchmark(self, benchmark_id: str) -> list[BenchmarkResult]:
        """Récupère tous les résultats d'un benchmark."""
        results = []
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM benchmark_results WHERE benchmark_id = ? ORDER BY timestamp",
                (benchmark_id,),
            )
            for row in cursor.fetchall():
                results.append(BenchmarkResult.from_dict(dict(row)))
        return results

    def get_results_by_model(self, model_tag: str, limit: int = 100) -> list[BenchmarkResult]:
        """Récupère les résultats pour un modèle spécifique."""
        results = []
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT * FROM benchmark_results
                   WHERE model_tag = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (model_tag, limit),
            )
            for row in cursor.fetchall():
                results.append(BenchmarkResult.from_dict(dict(row)))
        return results

    def get_summary_by_model(self, benchmark_id: str) -> list[BenchmarkSummary]:
        """
        Génère un résumé agrégé par modèle pour un benchmark.

        Args:
            benchmark_id: ID du benchmark

        Returns:
            Liste des résumés par modèle
        """
        summaries = []
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    model_tag,
                    COUNT(*) as num_runs,
                    AVG(tokens_per_second) as avg_tps,
                    AVG(duration_s) as avg_duration,
                    SUM(carbon_mg) as total_carbon,
                    MIN(timestamp) as first_run,
                    MAX(timestamp) as last_run
                FROM benchmark_results
                WHERE benchmark_id = ?
                GROUP BY model_tag
            """,
                (benchmark_id,),
            )

            for row in cursor.fetchall():
                summaries.append(
                    BenchmarkSummary(
                        benchmark_id=benchmark_id,
                        model_tag=row[0],
                        num_runs=row[1],
                        avg_tokens_per_second=row[2] or 0,
                        avg_duration_s=row[3] or 0,
                        total_carbon_mg=row[4] or 0,
                        created_at=datetime.fromisoformat(row[5]),
                        completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    )
                )

        return summaries

    def compare_models(
        self, model_tags: list[str], benchmark_id: str | None = None
    ) -> dict[str, dict[str, float]]:
        """
        Compare les performances de plusieurs modèles.

        Args:
            model_tags: Liste des modèles à comparer
            benchmark_id: Optionnel, filtrer par benchmark

        Returns:
            Dict {model_tag: {metric: value}}
        """
        comparison = {}

        with sqlite3.connect(self._db_path) as conn:
            for model_tag in model_tags:
                query = """
                    SELECT
                        AVG(tokens_per_second) as avg_tps,
                        AVG(duration_s) as avg_duration,
                        AVG(carbon_mg) as avg_carbon,
                        COUNT(*) as num_samples
                    FROM benchmark_results
                    WHERE model_tag = ?
                """
                params = [model_tag]

                if benchmark_id:
                    query += " AND benchmark_id = ?"
                    params.append(benchmark_id)

                cursor = conn.execute(query, params)
                row = cursor.fetchone()

                if row and row[3] > 0:  # num_samples > 0
                    comparison[model_tag] = {
                        "avg_tokens_per_second": row[0] or 0,
                        "avg_duration_s": row[1] or 0,
                        "avg_carbon_mg": row[2] or 0,
                        "num_samples": row[3],
                    }

        return comparison

    def list_benchmarks(self, limit: int = 50) -> list[dict[str, Any]]:
        """Liste les benchmarks récents."""
        benchmarks = []
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT DISTINCT benchmark_id,
                       MIN(timestamp) as started_at,
                       MAX(timestamp) as ended_at,
                       COUNT(*) as num_results
                FROM benchmark_results
                GROUP BY benchmark_id
                ORDER BY started_at DESC
                LIMIT ?
            """,
                (limit,),
            )

            for row in cursor.fetchall():
                benchmarks.append(dict(row))

        return benchmarks

    def delete_benchmark(self, benchmark_id: str) -> int:
        """
        Supprime tous les résultats d'un benchmark.

        Returns:
            Nombre de résultats supprimés
        """
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM benchmark_results WHERE benchmark_id = ?", (benchmark_id,)
            )
            conn.commit()
            deleted = cursor.rowcount

        logger.info(f"Deleted {deleted} results for benchmark {benchmark_id}")
        return deleted

    def export_to_csv(self, benchmark_id: str, output_path: str | Path) -> Path:
        """
        Exporte les résultats d'un benchmark en CSV.

        Args:
            benchmark_id: ID du benchmark
            output_path: Chemin du fichier de sortie

        Returns:
            Path du fichier créé
        """
        import csv

        output_path = Path(output_path)
        results = self.get_results_by_benchmark(benchmark_id)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            if results:
                writer = csv.DictWriter(f, fieldnames=results[0].to_dict().keys())
                writer.writeheader()
                for result in results:
                    writer.writerow(result.to_dict())

        logger.info(f"Exported {len(results)} results to {output_path}")
        return output_path


# Instance singleton
_benchmark_repository: BenchmarkRepository | None = None


def get_benchmark_repository() -> BenchmarkRepository:
    """Retourne l'instance singleton du repository."""
    global _benchmark_repository
    if _benchmark_repository is None:
        _benchmark_repository = BenchmarkRepository()
    return _benchmark_repository
