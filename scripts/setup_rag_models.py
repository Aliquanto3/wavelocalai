"""
Script d'initialisation des modèles RAG (Embeddings & Rerankers).
Télécharge les modèles depuis HuggingFace pour une utilisation 100% hors-ligne.

Usage:
    python scripts/setup_rag_models.py --all
    python scripts/setup_rag_models.py --embeddings
    python scripts/setup_rag_models.py --rerankers
"""

import argparse
import logging
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

# Configuration du Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("RAG_Setup")

# --- CONFIGURATION DES CHEMINS ---
# On remonte de 2 niveaux depuis scripts/ pour atteindre la racine
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = DATA_DIR / "models"
EMBEDDINGS_DIR = MODELS_DIR / "embeddings"
RERANKERS_DIR = MODELS_DIR / "rerankers"

# --- CATALOGUE DES MODÈLES (Extensible) ---
# Format: "nom_dossier_local": "repo_huggingface_id"

EMBEDDING_MODELS: dict[str, str] = {
    "all-MiniLM-L6-v2": "sentence-transformers/all-MiniLM-L6-v2",  # Legacy / Rapide
    "bge-m3": "BAAI/bge-m3",  # Recommandé (Hybrid)
    "jina-embeddings-v3": "jinaai/jina-embeddings-v3",  # SOTA 2025
    "multilingual-e5-small": "intfloat/multilingual-e5-small",  # Light & Multi
}

RERANKER_MODELS: dict[str, str] = {
    "bge-reranker-base": "BAAI/bge-reranker-base",  # Standard
    "jina-reranker-v2": "jinaai/jina-reranker-v2-base-multilingual",  # Haute précision
    "mxbai-rerank-base-v1": "mixedbread-ai/mxbai-rerank-base-v1",  # User Choice (Benchmark Winner)
}


def ensure_dirs():
    """Crée l'arborescence nécessaire."""
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    RERANKERS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"📂 Dossiers vérifiés : {MODELS_DIR}")


def download_model(model_id: str, save_path: Path, is_sentence_transformer: bool = True):
    """
    Télécharge un modèle.
    Utilise snapshot_download pour récupérer tout le dossier (config, tokenizer, weights).
    """
    if save_path.exists() and any(save_path.iterdir()):
        logger.info(f"✅ Modèle déjà présent : {save_path.name}")
        return

    logger.info(f"⬇️ Téléchargement de {model_id} vers {save_path.name}...")
    try:
        # On utilise snapshot_download pour s'assurer d'avoir tous les fichiers (onnx, config, etc.)
        # ignore_patterns permet d'éviter de télécharger les fichiers poids superflus (ex: .h5 si on veut .bin)
        snapshot_download(
            repo_id=model_id,
            local_dir=str(save_path),
            local_dir_use_symlinks=False,  # Important pour la portabilité Windows
            ignore_patterns=["*.h5", "*.ot", "*.msgpack"],  # Optimisation espace
        )
        logger.info(f"✨ Succès : {model_id} installé.")
    except Exception as e:
        logger.error(f"❌ Échec téléchargement {model_id} : {e}")
        # Nettoyage en cas d'échec partiel
        if save_path.exists():
            shutil.rmtree(save_path)


def main():
    parser = argparse.ArgumentParser(description="Setup WaveLocalAI RAG Models")
    parser.add_argument("--all", action="store_true", help="Télécharger tous les modèles")
    parser.add_argument(
        "--embeddings", action="store_true", help="Télécharger uniquement les embeddings"
    )
    parser.add_argument(
        "--rerankers", action="store_true", help="Télécharger uniquement les rerankers"
    )

    args = parser.parse_args()

    # Par défaut, si aucun argument, on demande
    if not any([args.all, args.embeddings, args.rerankers]):
        print("⚠️ Aucun argument fourni.")
        print("Options: --all, --embeddings, --rerankers")
        return

    ensure_dirs()

    # 1. Embeddings
    if args.all or args.embeddings:
        logger.info("--- 🧠 TRAITEMENT DES EMBEDDINGS ---")
        for local_name, repo_id in EMBEDDING_MODELS.items():
            path = EMBEDDINGS_DIR / local_name
            download_model(repo_id, path)

    # 2. Rerankers
    if args.all or args.rerankers:
        logger.info("--- 🎯 TRAITEMENT DES RERANKERS ---")
        for local_name, repo_id in RERANKER_MODELS.items():
            path = RERANKERS_DIR / local_name
            download_model(repo_id, path)

    logger.info("🎉 Terminé ! Tous les modèles demandés sont prêts.")
    logger.info(f"📍 Localisation : {MODELS_DIR}")


if __name__ == "__main__":
    main()
