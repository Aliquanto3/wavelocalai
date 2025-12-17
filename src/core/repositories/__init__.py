# src/core/repositories/__init__.py
"""Repositories pour la persistance des données."""

from src.core.repositories.benchmark_repository import BenchmarkRepository, get_benchmark_repository

__all__ = ["BenchmarkRepository", "get_benchmark_repository"]
