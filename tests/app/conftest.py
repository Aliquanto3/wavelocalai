"""
Banc de test des pages Streamlit (AppTest), sans Ollama, clé d'API, réseau ni téléchargement.

Les providers sont simulés : modèles locaux factices, embeddings déterministes, pas de
reranker. Chroma, CodeCarbon et l'historique d'émissions sont redirigés vers tmp_path.
"""

import json
import os
from pathlib import Path

import pytest

# Aucun accès au Hub Hugging Face, même si un chargement réel était tenté.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "src" / "app"
TEST_CATALOG = ROOT_DIR / "tests" / "fixtures" / "models_catalog_test.json"

# Format renvoyé par OllamaProvider.list_models (model_dump d'ollama + type + provider).
FAKE_LOCAL_MODELS = [
    {
        "model": "qwen2.5:1.5b",
        "size": 986_061_892,
        "digest": "0" * 64,
        "details": {"family": "qwen2", "parameter_size": "1.5B", "quantization_level": "Q4_K_M"},
        "type": "local",
        "provider": "ollama",
    },
    {
        "model": "gemma3:1b",
        "size": 815_319_791,
        "digest": "1" * 64,
        "details": {"family": "gemma3", "parameter_size": "1B", "quantization_level": "Q4_K_M"},
        "type": "local",
        "provider": "ollama",
    },
]


@pytest.fixture(autouse=True)
def offline_app_env(tmp_path, monkeypatch):
    """Isole chaque test de page : providers simulés, écritures dans tmp_path."""
    from langchain_core.embeddings import DeterministicFakeEmbedding

    from src.core.llm_provider import LLMProvider
    from src.core.models_db import MODELS_DB
    from src.core.rag.models_factory import RAGModelsFactory

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    # Chroma envoie une télémétrie anonyme par défaut.
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "False")

    # Catalogue de test à la place de data/models.json (local, non versionné).
    # Lu avant clear() : une erreur de lecture ne vide pas MODELS_DB.
    test_catalog = json.loads(TEST_CATALOG.read_text(encoding="utf-8"))
    original_catalog = dict(MODELS_DB)
    MODELS_DB.clear()
    MODELS_DB.update(test_catalog)

    # Modèles : uniquement des modèles locaux factices, aucun appel à Ollama.
    monkeypatch.setattr(
        LLMProvider,
        "list_models",
        staticmethod(lambda cloud_enabled=True: [dict(m) for m in FAKE_LOCAL_MODELS]),
    )
    monkeypatch.setattr(LLMProvider, "health_check", staticmethod(lambda: {"ollama": True}))

    # RAG : embeddings déterministes, pas de reranker, aucun téléchargement.
    monkeypatch.setattr(
        RAGModelsFactory,
        "get_embedding_model",
        staticmethod(lambda model_name, device="cpu": DeterministicFakeEmbedding(size=32)),
    )
    monkeypatch.setattr(
        RAGModelsFactory,
        "get_reranker_model",
        staticmethod(lambda model_name, device="cpu": None),
    )

    # Écritures : Chroma, CodeCarbon et historique d'émissions dans tmp_path.
    chroma_dir = tmp_path / "chroma"
    logs_dir = tmp_path / "logs"
    chroma_dir.mkdir()
    logs_dir.mkdir()
    monkeypatch.setattr("src.core.rag.vector_store.CHROMA_DIR", chroma_dir)
    monkeypatch.setattr("src.core.green_monitor.LOGS_DIR", logs_dir)
    monkeypatch.setattr("src.core.config.EMISSIONS_DIR", logs_dir / "emissions")

    yield tmp_path

    MODELS_DB.clear()
    MODELS_DB.update(original_catalog)
