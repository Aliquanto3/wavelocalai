import logging

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from src.core.config import CHROMA_DIR

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """
    Gère l'accès à ChromaDB.
    Isole les collections par modèle d'embedding pour éviter les conflits de dimensions.
    """

    def __init__(self, embedding_function: Embeddings, model_name: str):
        self.embedding_function = embedding_function
        # Nom de collection "safe" (ex: "docs_bge-m3")
        safe_name = model_name.replace("/", "_").replace("-", "_").replace(".", "")
        self.collection_name = f"wavelocal_{safe_name}"
        self.persist_dir = str(CHROMA_DIR)

        self._init_db()

    def _init_db(self):
        logger.info(f"📂 Connexion ChromaDB Collection : {self.collection_name}")
        self.db = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embedding_function,
            persist_directory=self.persist_dir,
        )

    def get_store(self) -> Chroma:
        return self.db

    def get_stats(self) -> dict:
        try:
            data = self.db.get()
            return {
                "count": len(data["ids"]) if data else 0,
                "sources": (
                    list({m.get("source") for m in data["metadatas"]})
                    if data and data["metadatas"]
                    else []
                ),
                "collection": self.collection_name,
            }
        except Exception:
            return {"count": 0, "sources": [], "collection": self.collection_name}

    def clear(self):
        """Supprime uniquement la collection active."""
        try:
            self.db.delete_collection()
            self._init_db()  # Re-creation vide
            logger.info(f"🧹 Collection {self.collection_name} purgée.")
        except Exception as e:
            logger.error(f"Erreur purge : {e}")
