import logging

from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import CrossEncoder

from src.core.config import DATA_DIR

logger = logging.getLogger(__name__)


class RAGModelsFactory:
    """
    Factory pour charger les modèles d'embedding et de reranking
    depuis le stockage local (data/models).
    """

    MODELS_PATH = DATA_DIR / "models"
    EMBEDDINGS_PATH = MODELS_PATH / "embeddings"
    RERANKERS_PATH = MODELS_PATH / "rerankers"

    @staticmethod
    def get_embedding_model(model_name: str, device: str = "cpu") -> HuggingFaceEmbeddings:
        """
        Charge un modèle d'embedding local compatible LangChain.
        """
        model_path = RAGModelsFactory.EMBEDDINGS_PATH / model_name

        # Fallback si le dossier n'existe pas (ex: nom HF direct)
        if not model_path.exists():
            logger.warning(f"Modèle local introuvable : {model_path}. Tentative chargement HF Hub.")
            model_path_str = model_name
        else:
            model_path_str = str(model_path)

        logger.info(f"🔌 Chargement Embedding : {model_name}")

        # ✅ CORRECTION ICI : Ajout de trust_remote_code=True
        return HuggingFaceEmbeddings(
            model_name=model_path_str,
            model_kwargs={
                "device": device,
                "trust_remote_code": True,  # <--- Indispensable pour Jina/Bert-Flash
            },
            encode_kwargs={"normalize_embeddings": True},
        )

    @staticmethod
    def get_reranker_model(model_name: str, device: str = "cpu") -> CrossEncoder | None:
        """
        Charge un modèle CrossEncoder (Reranker).
        """
        if not model_name:
            return None

        model_path = RAGModelsFactory.RERANKERS_PATH / model_name

        if not model_path.exists():
            logger.warning(f"Reranker local introuvable : {model_path}. Tentative HF Hub.")
            model_path_str = model_name
        else:
            model_path_str = str(model_path)

        logger.info(f"🔌 Chargement Reranker : {model_name}")
        try:
            # ✅ CORRECTION ICI : Ajout de trust_remote_code=True
            return CrossEncoder(
                model_path_str,
                device=device,
                trust_remote_code=True,  # <--- Indispensable pour Jina Reranker
            )
        except Exception as e:
            logger.error(f"Erreur chargement reranker {model_name}: {e}")
            return None
