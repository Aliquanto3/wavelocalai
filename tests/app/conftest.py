"""
Banc de test des pages Streamlit (AppTest), sans Ollama, clé d'API, réseau ni téléchargement.

Les providers sont simulés : modèles locaux factices, embeddings déterministes, pas de
reranker. Chroma, CodeCarbon et l'historique d'émissions sont redirigés vers tmp_path.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st

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
    # État d'Ollama (accueil, alerte en tête de module) et modèles en mémoire : simulés.
    # L'état est mis en cache par st.cache_data, partagé entre les AppTest du processus.
    monkeypatch.setattr(LLMProvider, "ollama_available", staticmethod(lambda timeout=2.0: True))
    monkeypatch.setattr(
        LLMProvider, "is_model_loaded", staticmethod(lambda model_name, timeout=2.0: True)
    )
    st.cache_data.clear()

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

    st.cache_data.clear()
    MODELS_DB.clear()
    MODELS_DB.update(original_catalog)


# ---------------------------------------------------------------------------
# États simulés (story 5) : aucun modèle, Ollama arrêté, inférence en échec
# ---------------------------------------------------------------------------

THIRD_LOCAL_MODEL = {
    "model": "llama3.2:1b",
    "size": 1_321_098_329,
    "digest": "2" * 64,
    "details": {"family": "llama", "parameter_size": "1.2B", "quantization_level": "Q8_0"},
    "type": "local",
    "provider": "ollama",
}


@pytest.fixture
def no_models(monkeypatch):
    """Aucun modèle installé : list_models renvoie une liste vide."""
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(LLMProvider, "list_models", staticmethod(lambda cloud_enabled=True: []))


@pytest.fixture
def ollama_down(monkeypatch, no_models):
    """Ollama arrêté : état « indisponible », aucun modèle listé, modèles en mémoire inconnus."""
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(LLMProvider, "ollama_available", staticmethod(lambda timeout=2.0: False))
    monkeypatch.setattr(
        LLMProvider, "is_model_loaded", staticmethod(lambda model_name, timeout=2.0: None)
    )


@pytest.fixture
def three_models(monkeypatch):
    """Trois modèles locaux installés (Arène à trois modèles)."""
    from src.core.llm_provider import LLMProvider

    models = [*FAKE_LOCAL_MODELS, THIRD_LOCAL_MODEL]
    monkeypatch.setattr(
        LLMProvider,
        "list_models",
        staticmethod(lambda cloud_enabled=True: [dict(m) for m in models]),
    )


@pytest.fixture
def fake_inference(monkeypatch):
    """
    InferenceService.run_inference simulé, sans Ollama : réponse mesurée par défaut, délai
    dépassé pour les tags de `timeouts`, erreur pour ceux de `errors`. Le juge de l'Arène
    (prompt « juge impartial ») répond `judge_reply`, ou échoue si `judge_error`. Métriques
    d'un appel Ollama (chargement et durée de génération mesurés) ; `output_tokens` fixe les
    tokens générés par tag (40 par défaut).
    """
    from src.core.inference_service import InferenceResult, InferenceService
    from src.core.metrics import InferenceMetrics

    state = SimpleNamespace(
        timeouts=set(),
        errors=set(),
        judge_reply="85",
        judge_error=False,
        calls=[],
        answer="Réponse simulée.",
        output_tokens={},
    )

    async def run_inference(
        model_tag,
        messages,
        temperature=0.7,
        system_prompt=None,
        callbacks=None,
        timeout=120,
    ):
        is_judge = "juge impartial" in (messages[-1].get("content") or "")
        state.calls.append(("judge" if is_judge else "model", model_tag))
        if (is_judge and state.judge_error) or (not is_judge and model_tag in state.timeouts):
            return InferenceResult(
                raw_text="",
                clean_text="",
                thought=None,
                metrics=None,
                error=f"Timeout ({timeout}s) dépassé pour {model_tag}",
                timed_out=True,
                timeout_s=timeout,
            )
        if not is_judge and model_tag in state.errors:
            return InferenceResult(
                raw_text="",
                clean_text="",
                thought=None,
                metrics=None,
                error="[Errno 111] Connection refused",
            )
        text = state.judge_reply if is_judge else state.answer
        if callbacks and callbacks.on_token:
            await callbacks.on_token(text)
        return InferenceResult(
            raw_text=text,
            clean_text=text,
            thought=None,
            metrics=InferenceMetrics(
                model_name=model_tag,
                input_tokens=12,
                output_tokens=state.output_tokens.get(model_tag, 40),
                total_duration_s=1.6,
                load_duration_s=0.1,
                tokens_per_second=25.0,
                load_measured=True,
                eval_duration_s=1.6,
            ),
        )

    monkeypatch.setattr(InferenceService, "run_inference", staticmethod(run_inference))
    return state


@pytest.fixture
def failing_inference(fake_inference):
    """Inférence en échec : délai dépassé pour les modèles installés."""
    fake_inference.timeouts.update(m["model"] for m in FAKE_LOCAL_MODELS)
    return fake_inference
