"""
Tests unitaires pour les stratégies RAG (Naive, HyDE, Self-RAG).
Isolation des composants externes (LLM, VectorStore) via Mocks.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from src.core.rag.strategies.hyde import HyDERetrievalStrategy

# Imports des stratégies
from src.core.rag.strategies.naive import NaiveRetrievalStrategy
from src.core.rag.strategies.self_rag import SelfRAGStrategy


@pytest.fixture
def mock_vector_store():
    """Simule ChromaDB."""
    store = MagicMock()
    # Simule un retour de 2 documents
    store.similarity_search.return_value = [
        Document(page_content="Doc 1", metadata={"source": "test"}),
        Document(page_content="Doc 2", metadata={"source": "test"}),
    ]
    return store


@pytest.fixture
def mock_reranker():
    """Simule un CrossEncoder."""
    reranker = MagicMock()
    # Simule des scores [0.9, 0.1]
    reranker.predict.return_value = [0.9, 0.1]
    return reranker


class TestNaiveStrategy:
    def test_retrieve_simple(self, mock_vector_store):
        strategy = NaiveRetrievalStrategy()
        docs = strategy.retrieve("query", mock_vector_store, k=2)

        mock_vector_store.similarity_search.assert_called_once_with("query", k=2)
        assert len(docs) == 2

    def test_retrieve_with_reranker(self, mock_vector_store, mock_reranker):
        strategy = NaiveRetrievalStrategy()
        # On demande k=1, la stratégie doit fetcher plus large (k*3) puis reranker
        docs = strategy.retrieve("query", mock_vector_store, k=1, reranker=mock_reranker)

        # Vérifie que le reranker a été appelé
        mock_reranker.predict.assert_called()
        # Vérifie qu'on a bien gardé le meilleur doc (score 0.9)
        assert len(docs) == 1
        assert docs[0].page_content == "Doc 1"


class TestHyDEStrategy:
    def test_hyde_generate_hypothesis(self, mock_vector_store):
        """Test que HyDE utilise l'hypothèse générée pour la recherche."""
        strategy = HyDERetrievalStrategy()

        # ✅ CORRECTION : On mocke directement la méthode interne _generate_hypothesis
        # Cela évite les conflits asyncio et isole le test de la logique LLM
        with patch.object(strategy, "_generate_hypothesis", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Ceci est une hypothèse générée."

            # Exécution
            # strategy.retrieve appelle asyncio.run(_generate_hypothesis(...))
            _ = strategy.retrieve("Ma question", mock_vector_store, k=2)

            # 1. Vérifie que la génération a été appelée avec la question
            mock_gen.assert_called_once_with("Ma question")

            # 2. Vérifie que la recherche vectorielle a bien eu lieu
            mock_vector_store.similarity_search.assert_called()

            # 3. Vérifie que c'est l'HYPOTHÈSE qui est cherchée, pas la question originale
            args, _ = mock_vector_store.similarity_search.call_args
            assert "hypothèse" in args[0]
            assert "Ma question" not in args[0]


class TestSelfRAGStrategy:
    @patch("src.core.rag.strategies.self_rag.LLMProvider")
    def test_self_rag_workflow(self, mock_provider, mock_vector_store):
        """Test le flux Retrieve -> Grade -> Generate."""
        strategy = SelfRAGStrategy()

        # Mock pour le Grading (Doit répondre 'yes' pour garder les docs)
        async def fake_grader_stream(*args, **kwargs):
            yield "yes"

        mock_provider.chat_stream = MagicMock(side_effect=fake_grader_stream)

        # Attention : Self-RAG utilise LangGraph qui est async.
        docs = strategy.retrieve("Question complexe", mock_vector_store, k=2)

        # Vérifie qu'on a bien des docs à la fin
        assert len(docs) > 0
        # Vérifie que la métadonnée est marquée
        assert docs[0].metadata.get("strategy") == "Self-RAG"
