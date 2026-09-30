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

# Modèle d'embedding par défaut, partagé par le moteur et l'assistant documentaire : le nom de
# la collection Chroma en dérive, un seul nom évite deux collections pour le même modèle.
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class RerankerLoadError(RuntimeError):
    """Le modèle de reclassement choisi n'a pas pu être chargé : aucun n'est appliqué."""

    def __init__(self, reranker_name: str):
        super().__init__(f"Chargement du reranker impossible : {reranker_name}")
        self.reranker_name = reranker_name


class RAGEngine:
    """
    Façade principale du module RAG (Version 2.0).
    Orchestre les composants : Store, Models, Strategies.
    """

    def __init__(
        self,
        embedding_model_name: str = DEFAULT_EMBEDDING_MODEL,
        reranker_model_name: str = None,
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
        """Charge les modèles au démarrage. Un reranker qui ne se charge pas n'est pas
        appliqué, et son nom n'est pas affiché comme actif."""
        logger.info(
            f"🔄 Init RAG Engine avec Embedding={self.current_embedding_name}, Reranker={self.current_reranker_name}"
        )
        self.embedding_model = RAGModelsFactory.get_embedding_model(self.current_embedding_name)
        if not self._load_reranker(self.current_reranker_name):
            logger.warning(f"Reranker non chargé : {self.current_reranker_name}")

    def _load_reranker(self, reranker_name: str | None) -> bool:
        """Charge `reranker_name` (None : aucun). En échec, aucun reranker n'est appliqué et
        la fonction renvoie False."""
        model = RAGModelsFactory.get_reranker_model(reranker_name) if reranker_name else None
        if reranker_name and model is None:
            self.current_reranker_name = None
            self.reranker_model = None
            return False
        self.current_reranker_name = reranker_name
        self.reranker_model = model
        return True

    def set_reranker(self, reranker_name: str | None):
        """Change le seul reranker (None : aucun), sans toucher à l'embedding ni à la base.
        Lève RerankerLoadError si le modèle ne se charge pas : aucun reranker n'est alors
        appliqué."""
        if reranker_name == self.current_reranker_name:
            return
        logger.info(f"🔀 Changement de reranker : {reranker_name}")
        if not self._load_reranker(reranker_name):
            raise RerankerLoadError(reranker_name)

    def set_embedding(self, embedding_name: str):
        """Change le seul modèle d'embedding, et la collection qui en dérive ; le reranker
        reste celui choisi."""
        if not embedding_name or embedding_name == self.current_embedding_name:
            return
        # Chargement d'abord : en échec, l'exception remonte et le moteur reste inchangé.
        embedding_model = RAGModelsFactory.get_embedding_model(embedding_name)
        # La collection Chroma dérive du modèle d'embedding.
        vector_manager = VectorStoreManager(embedding_model, embedding_name)
        self.embedding_model = embedding_model
        self.vector_manager = vector_manager
        self.current_embedding_name = embedding_name

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
