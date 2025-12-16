import logging
import tempfile
from pathlib import Path

# Loaders
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.config import DATA_DIR

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Pipeline d'ingestion multi-formats.
    Support actuel : PDF, TXT, MD, DOCX.
    """

    @staticmethod
    def _validate_path(file_path: str) -> Path:
        """
        Valide et sécurise un chemin de fichier.
        Vérifie l'existence et restreint l'accès aux dossiers autorisés (Data & Temp).
        """
        # 1. Résolution absolue
        path = Path(file_path).resolve()

        if not path.exists():
            raise FileNotFoundError(f"Fichier introuvable : {path}")

        if not path.is_file():
            raise ValueError(f"Ce n'est pas un fichier : {path}")

        # 2. Sécurité : Allowlist des dossiers
        allowed_dirs = [
            Path(tempfile.gettempdir()).resolve(),  # Dossier Temp Système
            DATA_DIR.resolve(),  # Dossier Data du projet
        ]

        # Vérifie si le fichier est dans un des dossiers autorisés
        # is_relative_to est robuste aux symlinks et différences de montage
        is_allowed = any(path.is_relative_to(d) for d in allowed_dirs)

        if not is_allowed:
            logger.warning(f"⛔ Accès refusé (Security) : {path}")
            raise ValueError(
                f"Accès refusé : Le fichier doit être dans {tempfile.gettempdir()} ou {DATA_DIR}"
            )

        return path

    def process_file(self, file_path: str, original_name: str) -> list[Document]:
        """Charge et découpe un fichier."""
        # Validation Sécurité
        try:
            safe_path = self._validate_path(file_path)
        except (ValueError, FileNotFoundError) as e:
            logger.error(f"❌ Erreur validation {original_name} : {e}")
            raise e  # On remonte l'erreur pour les tests

        ext = safe_path.suffix.lower()
        docs = []

        try:
            if ext == ".pdf":
                loader = PyPDFLoader(str(safe_path))
                docs = loader.load()
            elif ext in [".txt", ".md"]:
                loader = TextLoader(str(safe_path), encoding="utf-8")
                docs = loader.load()
            elif ext == ".docx":
                # Nécessite pip install docx2txt
                loader = Docx2txtLoader(str(safe_path))
                docs = loader.load()
            else:
                logger.warning(f"Extension non supportée : {ext}")
                return []

            # Nettoyage métadonnées
            for doc in docs:
                doc.metadata["source"] = original_name
                doc.metadata["file_path"] = str(safe_path)

            # Chunking
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=800, chunk_overlap=100, separators=["\n\n", "\n", ".", " ", ""]
            )
            splits = text_splitter.split_documents(docs)
            logger.info(f"✅ Ingestion {original_name} : {len(splits)} chunks.")
            return splits

        except Exception as e:
            logger.error(f"❌ Erreur parsing {original_name} : {e}")
            return []
