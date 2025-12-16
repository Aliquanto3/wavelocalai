import asyncio
import logging

from langchain_core.documents import Document

from src.core.rag.ingestion import IngestionPipeline

# Nouveaux modules
from src.core.rag.models_factory import RAGModelsFactory
from src.core.rag.strategies.base import RetrievalStrategy
from src.core.rag.strategies.naive import NaiveRetrievalStrategy
from src.core.rag.vector_store import VectorStoreManager

logger = logging.getLogger(__name__)


class RAGEngine:
    """
    Façade principale du module RAG (Version 2.0).
    Orchestre les composants : Store, Models, Strategies.
    """

    def __init__(
        self, embedding_model_name: str = "all-MiniLM-L6-v2", reranker_model_name: str = None
    ):

        self.current_embedding_name = embedding_model_name
        self.current_reranker_name = reranker_model_name

        # 1. Chargement des Modèles
        self._load_models()

        # 2. Initialisation Vector Store (Chroma)
        self.vector_manager = VectorStoreManager(self.embedding_model, self.current_embedding_name)

        # 3. Pipeline d'Ingestion
        self.ingestion_pipeline = IngestionPipeline()

        # 4. Stratégie par défaut
        self.strategy: RetrievalStrategy = NaiveRetrievalStrategy()

    def _load_models(self):
        """Charge ou recharge les modèles."""
        logger.info(
            f"🔄 Init RAG Engine avec Embedding={self.current_embedding_name}, Reranker={self.current_reranker_name}"
        )
        self.embedding_model = RAGModelsFactory.get_embedding_model(self.current_embedding_name)
        self.reranker_model = RAGModelsFactory.get_reranker_model(self.current_reranker_name)

    def set_models(self, embedding_name: str = None, reranker_name: str = None):
        """Permet de changer de modèles à chaud (Switching)."""
        changed = False
        if embedding_name and embedding_name != self.current_embedding_name:
            self.current_embedding_name = embedding_name
            changed = True

        if reranker_name != self.current_reranker_name:  # Peut être None -> None
            self.current_reranker_name = reranker_name
            # Pas besoin de tout recharger si juste reranker change, mais simple ici
            changed = True

        if changed:
            self._load_models()
            # Si l'embedding change, on doit changer de Vector Store !
            self.vector_manager = VectorStoreManager(
                self.embedding_model, self.current_embedding_name
            )

    def set_strategy(self, strategy: RetrievalStrategy):
        """Change la stratégie de recherche (Naive, HyDE, etc.)."""
        logger.info(f"🔀 Changement de stratégie : {strategy.__class__.__name__}")
        self.strategy = strategy

    def ingest_file(self, file_path: str, original_filename: str) -> int:
        """Ingestion synchrone."""
        chunks = self.ingestion_pipeline.process_file(file_path, original_filename)
        if chunks:
            self.vector_manager.get_store().add_documents(chunks)
        return len(chunks)

    async def ingest_file_async(self, file_path: str, original_filename: str) -> int:
        """Ingestion asynchrone (wrapper)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.ingest_file, file_path, original_filename)

    def search(self, query: str, k: int = 4) -> list[Document]:
        """Exécute la recherche via la stratégie active."""
        return self.strategy.retrieve(
            query=query,
            vector_store=self.vector_manager.get_store(),
            k=k,
            reranker=self.reranker_model,
        )

    def get_stats(self) -> dict:
        """Récupère les stats de la collection active."""
        return self.vector_manager.get_stats()

    def clear_database(self):
        """Purge la collection active."""
        self.vector_manager.clear()
