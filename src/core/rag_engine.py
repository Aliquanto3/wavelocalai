import os
import shutil
from typing import List, Any, Dict
from pathlib import Path
import logging
import asyncio

# LangChain Imports
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

# Config
from src.core.config import CHROMA_DIR

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
        
        # 1. Initialisation du modèle d'embedding (Local - CPU Friendly)
        # On utilise all-MiniLM-L6-v2, très léger.
        logger.info("Chargement du modèle d'embedding local...")
        self.embedding_function = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        # 2. Connexion à la base vectorielle
        self.vector_store = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embedding_function,
            persist_directory=self.persist_directory
        )

    def ingest_file(self, file_path: str, original_filename: str) -> int:
        """Lit, découpe et indexe un fichier."""
        file_path = str(file_path)
        
        if file_path.endswith(".pdf"):
            loader = PyPDFLoader(file_path)
        elif file_path.endswith(".txt") or file_path.endswith(".md"):
            loader = TextLoader(file_path, encoding="utf-8")
        else:
            raise ValueError(f"Format non supporté : {file_path}")
            
        docs = loader.load()
        
        for doc in docs:
            doc.metadata["source"] = original_filename
            
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        splits = text_splitter.split_documents(docs)
        
        if splits:
            self.vector_store.add_documents(splits)
            logger.info(f"Ingestion terminée : {len(splits)} chunks pour {original_filename}")
            
        return len(splits)

    def search(self, query: str, k: int = 4) -> List[Document]:
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
                persist_directory=self.persist_directory
            )
            logger.info("Base vectorielle purgée.")
        except Exception as e:
            logger.error(f"Erreur purge DB: {e}")

    # --- Nouvelles méthodes d'introspection ---
    def get_stats(self) -> Dict[str, Any]:
        """Retourne le nombre de documents vectorisés en base."""
        try:
            # ChromaDB n'a pas de count() direct simple dans toutes les versions, 
            # mais on peut récupérer les IDs
            data = self.vector_store.get()
            return {
                "count": len(data['ids']) if data else 0,
                "sources": list(set([m.get('source') for m in data['metadatas']])) if data and data['metadatas'] else []
            }
        except Exception:
            return {"count": 0, "sources": []}
        
    async def ingest_file_async(self, file_path: str, original_filename: str) -> int:
        """
        Version asynchrone de ingest_file pour ne pas bloquer l'interface (Thread Pool).
        """
        loop = asyncio.get_running_loop()
        # On exécute la méthode bloquante (self.ingest_file) dans un thread séparé
        return await loop.run_in_executor(None, self.ingest_file, file_path, original_filename)