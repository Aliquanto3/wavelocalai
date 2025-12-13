import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma

# LangChain Imports
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Config
from src.core.config import CHROMA_DIR, DATA_DIR

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RAGEngine:
    """
    Moteur de Retrieval Augmented Generation (RAG).
    Gère l'ingestion de documents et la recherche sémantique via ChromaDB.
    """

    def __init__(self, collection_name: str = "wavelocal_docs"):
        self.collection_name = collection_name
        self.persist_directory = str(CHROMA_DIR)

        # Initialisation du modèle d'embedding
        logger.info("Chargement du modèle d'embedding local...")
        self.embedding_function = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        # Connexion à la base vectorielle
        self.vector_store = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embedding_function,
            persist_directory=self.persist_directory,
        )

    def _validate_file_path(self, file_path: str) -> Path:
        """
        Valide et sécurise un chemin de fichier.

        Args:
            file_path: Chemin du fichier à valider

        Returns:
            Path absolu et résolu du fichier

        Raises:
            ValueError: Si le chemin est invalide ou en dehors des zones autorisées
            FileNotFoundError: Si le fichier n'existe pas
        """
        # 1. Conversion en Path et résolution complète (résout les ".." et symlinks)
        safe_path = Path(file_path).resolve()

        # 2. Définition des répertoires autorisés
        allowed_dirs = [
            Path(tempfile.gettempdir()).resolve(),  # Dossier temp système
            DATA_DIR.resolve(),  # Dossier data du projet
        ]

        # 3. Vérification que le fichier est dans une zone autorisée
        is_allowed = any(safe_path.is_relative_to(allowed_dir) for allowed_dir in allowed_dirs)

        if not is_allowed:
            logger.error(f"Tentative d'accès à un chemin non autorisé : {safe_path}")
            raise ValueError(
                f"Accès refusé : Le fichier doit être dans {tempfile.gettempdir()} ou {DATA_DIR}"
            )

        # 4. Vérification d'existence
        if not safe_path.exists():
            raise FileNotFoundError(f"Fichier introuvable : {safe_path}")

        # 5. Vérification que c'est bien un fichier (pas un dossier)
        if not safe_path.is_file():
            raise ValueError(f"Le chemin ne pointe pas vers un fichier : {safe_path}")

        logger.info(f"✅ Validation réussie pour : {safe_path}")
        return safe_path

    def ingest_file(self, file_path: str, original_filename: str) -> int:
        """
        Lit, découpe et indexe un fichier avec validation de sécurité.

        Args:
            file_path: Chemin du fichier (sera validé)
            original_filename: Nom original du fichier (pour métadonnées)

        Returns:
            Nombre de chunks créés

        Raises:
            ValueError: Si le fichier est en dehors des zones autorisées
            FileNotFoundError: Si le fichier n'existe pas
        """
        # ✅ SÉCURITÉ : Validation du chemin AVANT toute opération
        safe_path = self._validate_file_path(file_path)
        file_path_str = str(safe_path)

        # Détection du type de fichier (basé sur l'extension validée)
        if file_path_str.endswith(".pdf"):
            loader = PyPDFLoader(file_path_str)
        elif file_path_str.endswith(".txt") or file_path_str.endswith(".md"):
            loader = TextLoader(file_path_str, encoding="utf-8")
        else:
            raise ValueError(f"Format non supporté : {safe_path.suffix}")

        # Chargement des documents
        docs = loader.load()

        # Ajout des métadonnées
        for doc in docs:
            doc.metadata["source"] = original_filename
            doc.metadata["file_path"] = file_path_str  # Chemin validé

        # Découpage en chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=50, separators=["\n\n", "\n", ".", " ", ""]
        )
        splits = text_splitter.split_documents(docs)

        # Indexation
        if splits:
            self.vector_store.add_documents(splits)
            logger.info(f"Ingestion terminée : {len(splits)} chunks pour {original_filename}")

        return len(splits)

    async def ingest_file_async(self, file_path: str, original_filename: str) -> int:
        """
        Version asynchrone de ingest_file (thread pool).

        Args:
            file_path: Chemin du fichier
            original_filename: Nom original

        Returns:
            Nombre de chunks créés
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.ingest_file, file_path, original_filename)

    def search(self, query: str, k: int = 4) -> list[Document]:
        """Recherche sémantique."""
        return self.vector_store.similarity_search(query, k=k)

    def clear_database(self):
        """Supprime la collection."""
        try:
            self.vector_store.delete_collection()
            # Force re-init
            self.vector_store = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embedding_function,
                persist_directory=self.persist_directory,
            )
            logger.info("Base vectorielle purgée.")
        except Exception as e:
            logger.error(f"Erreur purge DB: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Retourne le nombre de documents vectorisés en base."""
        try:
            data = self.vector_store.get()
            return {
                "count": len(data["ids"]) if data else 0,
                "sources": list(set([m.get("source") for m in data["metadatas"]]))
                if data and data["metadatas"]
                else [],
            }
        except Exception:
            return {"count": 0, "sources": []}
