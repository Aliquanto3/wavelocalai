# src/core/model_detector.py
"""
Module central de détection du type de modèle.
SOURCE UNIQUE DE VÉRITÉ : models.json via models_db.py
"""

import logging

# Import depuis la source unique
from src.core.models_db import MODELS_DB

logger = logging.getLogger(__name__)


def get_model_info(model_tag: str) -> dict | None:
    """
    Récupère les infos d'un modèle depuis models.json.

    Args:
        model_tag: Tag du modèle (ex: "qwen2.5:1.5b", "devstral-2512")

    Returns:
        dict: Infos du modèle ou None
    """
    for _model_name, model_info in MODELS_DB.items():
        if model_info.get("ollama_tag") == model_tag:
            return model_info

    logger.debug(f"Modèle non trouvé dans models.json : {model_tag}")
    return None


def is_api_model(model_tag: str) -> bool:
    """
    Détecte si un modèle est de type API.

    Args:
        model_tag: Tag du modèle

    Returns:
        bool: True si API, False si local
    """
    model_info = get_model_info(model_tag)

    if model_info:
        model_type = model_info.get("type", "local")
        result = model_type == "api"

        if result:
            logger.debug(f"✅ {model_tag} détecté comme API via models.json")
        else:
            logger.debug(f"✅ {model_tag} détecté comme LOCAL via models.json")

        return result

    # Fallback : Si pas dans models.json, considérer comme local
    logger.warning(f"⚠️ {model_tag} non trouvé dans models.json, fallback = LOCAL")
    return False


def get_model_provider(model_tag: str) -> str:
    """
    Retourne le nom du provider (pour logging/debug).

    Returns:
        str: "mistral_api", "ollama", ou "unknown"
    """
    if is_api_model(model_tag):
        model_info = get_model_info(model_tag)
        editor = model_info.get("editor", "Unknown") if model_info else "Unknown"

        if "mistral" in editor.lower():
            return "mistral_api"
        else:
            return "api_unknown"
    else:
        return "ollama"


# Test unitaire intégré
if __name__ == "__main__":
    print("=" * 80)
    print("TEST DE DÉTECTION DE MODÈLES")
    print("=" * 80)

    test_cases = [
        "qwen2.5:1.5b",
        "mistral-large-2512",
        "devstral-2512",
        "mistral:7b",
        "model-inconnu",
    ]

    for tag in test_cases:
        is_api = is_api_model(tag)
        provider = get_model_provider(tag)
        info = get_model_info(tag)

        print(f"\n🔍 {tag}")
        print(f"   API ? {is_api}")
        print(f"   Provider : {provider}")
        if info:
            print(f"   Éditeur : {info.get('editor')}")
            print(f"   Type : {info.get('type')}")
