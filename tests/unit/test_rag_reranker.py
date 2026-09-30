"""
Reranker de l'Assistant documentaire (story 9) : changement de reranker seul, « Aucun »,
échec de chargement, embedding changé sans perdre le reranker, scores réels des stratégies.
Aucun téléchargement : embeddings, reranker et base vectorielle simulés.
Usage: python -m pytest tests/unit/test_rag_reranker.py -v
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from src.core.rag.models_factory import RAGModelsFactory
from src.core.rag.strategies.hyde import HyDERetrievalStrategy
from src.core.rag.strategies.naive import NaiveRetrievalStrategy
from src.core.rag.strategies.self_rag import SelfRAGStrategy
from src.core.rag_engine import RAGEngine, RerankerLoadError


class FakeReranker:
    """CrossEncoder simulé : score lu dans `scores` d'après le texte de l'extrait."""

    def __init__(self, name, scores=None):
        self.name = name
        self.scores = scores or {}

    def predict(self, pairs):
        return [self.scores.get(text, 0.0) for _query, text in pairs]


@pytest.fixture
def loads(monkeypatch):
    """Chargements simulés et comptés ; le reranker « casse » ne se charge pas."""
    calls = {"embedding": [], "reranker": []}

    def get_embedding_model(model_name, device="cpu"):
        calls["embedding"].append(model_name)
        return f"embedding:{model_name}"

    def get_reranker_model(model_name, device="cpu"):
        calls["reranker"].append(model_name)
        if not model_name or model_name == "casse":
            return None
        return FakeReranker(model_name)

    monkeypatch.setattr(RAGModelsFactory, "get_embedding_model", staticmethod(get_embedding_model))
    monkeypatch.setattr(RAGModelsFactory, "get_reranker_model", staticmethod(get_reranker_model))
    monkeypatch.setattr("src.core.rag_engine.VectorStoreManager", MagicMock())
    return calls


def test_reranker_chosen_is_applied(loads):
    engine = RAGEngine("e1", reranker_model_name=None)
    engine.set_reranker("R")
    assert engine.current_reranker_name == "R"
    assert engine.reranker_model.name == "R"
    # Reranker seul : ni embedding rechargé, ni base changée.
    assert loads["embedding"] == ["e1"]


def test_search_uses_chosen_reranker(loads):
    engine = RAGEngine("e1", reranker_model_name="R")
    strategy = MagicMock()
    engine.set_strategy(strategy)
    engine.search("q", k=2)
    assert strategy.retrieve.call_args.kwargs["reranker"] is engine.reranker_model
    assert engine.reranker_model.name == "R"


def test_no_reranker_removes_it(loads):
    engine = RAGEngine("e1", reranker_model_name="R")
    engine.set_reranker(None)
    assert engine.current_reranker_name is None and engine.reranker_model is None


def test_embedding_failure_leaves_engine_unchanged(loads, monkeypatch):
    """Embedding qui ne se charge pas : nom, modèle et base restent ceux d'avant."""

    def broken(model_name, device="cpu"):
        raise OSError(f"dossier illisible : {model_name}")

    engine = RAGEngine("e1", reranker_model_name="R")
    before = (engine.embedding_model, engine.vector_manager)
    monkeypatch.setattr(RAGModelsFactory, "get_embedding_model", staticmethod(broken))
    with pytest.raises(OSError):
        engine.set_embedding("e2")
    assert engine.current_embedding_name == "e1"
    assert (engine.embedding_model, engine.vector_manager) == before
    assert engine.reranker_model.name == "R"


def test_embedding_change_keeps_reranker(loads):
    engine = RAGEngine("e1", reranker_model_name="R")
    reranker = engine.reranker_model
    engine.set_embedding("e2")
    assert engine.current_embedding_name == "e2"
    assert engine.reranker_model is reranker and engine.current_reranker_name == "R"


def test_reranker_load_failure_falls_back_to_none(loads):
    engine = RAGEngine("e1", reranker_model_name="R")
    with pytest.raises(RerankerLoadError) as err:
        engine.set_reranker("casse")
    assert err.value.reranker_name == "casse"
    assert engine.current_reranker_name is None and engine.reranker_model is None


def test_default_reranker_that_fails_is_not_shown_active(loads):
    engine = RAGEngine("e1", reranker_model_name="casse")
    assert engine.current_reranker_name is None and engine.reranker_model is None


# ---------------------------------------------------------------------------
# Stratégies : ordre et score du reranker, k extraits
# ---------------------------------------------------------------------------


def _docs():
    return [
        Document(page_content="faible", metadata={"source": "a.md"}),
        Document(page_content="fort", metadata={"source": "b.md"}),
        Document(page_content="moyen", metadata={"source": "c.md"}),
        Document(page_content="nul", metadata={"source": "d.md"}),
    ]


@pytest.fixture
def store():
    store = MagicMock()
    store.similarity_search.side_effect = lambda query, k: _docs()[:k]
    return store


RERANKER = FakeReranker("R", {"faible": 0.1, "fort": 0.9, "moyen": 0.5, "nul": 0.0})


def test_naive_orders_by_reranker_scores(store):
    docs = NaiveRetrievalStrategy().retrieve("q", store, k=2, reranker=RERANKER)
    assert [d.page_content for d in docs] == ["fort", "moyen"]
    assert [d.metadata["rerank_score"] for d in docs] == [0.9, 0.5]


def _hyde():
    strategy = HyDERetrievalStrategy()
    return strategy, patch.object(
        strategy, "_generate_hypothesis", new_callable=AsyncMock, return_value="hypothèse"
    )


def test_hyde_returns_k_without_reranker(store):
    strategy, generate = _hyde()
    with generate:
        docs = strategy.retrieve("q", store, k=2)
    assert len(docs) == 2
    assert all("rerank_score" not in d.metadata for d in docs)


def test_hyde_orders_by_reranker_scores(store):
    strategy, generate = _hyde()
    with generate:
        docs = strategy.retrieve("q", store, k=2, reranker=RERANKER)
    assert [d.page_content for d in docs] == ["fort", "moyen"]
    assert [d.metadata["rerank_score"] for d in docs] == [0.9, 0.5]


@patch("src.core.rag.strategies.self_rag.LLMProvider")
def test_self_rag_keeps_reranker_scores(provider, store):
    async def grader(*args, **kwargs):
        yield "yes"

    provider.chat_stream = MagicMock(side_effect=grader)
    docs = SelfRAGStrategy().retrieve("q", store, k=2, reranker=RERANKER)
    assert [d.page_content for d in docs] == ["fort", "moyen"]
    assert [d.metadata["rerank_score"] for d in docs] == [0.9, 0.5]
