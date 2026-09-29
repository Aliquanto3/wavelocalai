import logging
from collections.abc import Callable
from typing import TypeVar

from langchain_huggingface import HuggingFaceEmbeddings
from sentence_transformers import CrossEncoder

from src.core.config import DATA_DIR

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _load_offline_first(load: Callable[..., T], model_name: str) -> T:
    """Charge d'abord sans réseau (`data/models` ou cache Hugging Face) ; seulement si le
    modèle n'y est pas (OSError), recharge avec le réseau autorisé (téléchargement). Aucune
    variable globale HF_HUB_OFFLINE : le premier téléchargement légitime reste possible."""
    try:
        return load(local_files_only=True)
    except OSError as e:
        logger.info(f"{model_name} absent en local et du cache, téléchargement : {e}")
        return load()


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
            logger.warning(
                f"Modèle local introuvable : {model_path}. Cache Hugging Face, puis Hub."
            )
            model_path_str = model_name
        else:
            model_path_str = str(model_path)

        logger.info(f"🔌 Chargement Embedding : {model_name}")

        def load(**offline: bool) -> HuggingFaceEmbeddings:
            return HuggingFaceEmbeddings(
                model_name=model_path_str,
                model_kwargs={
                    "device": device,
                    "trust_remote_code": True,  # Indispensable pour Jina/Bert-Flash
                    **offline,
                },
                encode_kwargs={"normalize_embeddings": True},
            )

        return _load_offline_first(load, model_name)

    @staticmethod
    def get_reranker_model(model_name: str, device: str = "cpu") -> CrossEncoder | None:
        """
        Charge un modèle CrossEncoder (Reranker).
        """
        if not model_name:
            return None

        model_path = RAGModelsFactory.RERANKERS_PATH / model_name

        if not model_path.exists():
            logger.warning(
                f"Reranker local introuvable : {model_path}. Cache Hugging Face, puis Hub."
            )
            model_path_str = model_name
        else:
            model_path_str = str(model_path)

        logger.info(f"🔌 Chargement Reranker : {model_name}")
        try:

            def load(**offline: bool) -> CrossEncoder:
                return CrossEncoder(
                    model_path_str,
                    device=device,
                    trust_remote_code=True,  # Indispensable pour Jina Reranker
                    **offline,
                )

            return _load_offline_first(load, model_name)
        except Exception as e:
            logger.error(f"Erreur chargement reranker {model_name}: {e}")
            return None
