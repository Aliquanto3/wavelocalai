"""
Gestionnaire de la base de données des modèles.
Charge les définitions depuis un fichier JSON externe pour plus de flexibilité.
"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# On utilise config pour avoir le chemin DATA_DIR fiable
from src.core.config import DATA_DIR

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Chemin du fichier JSON
MODELS_JSON_PATH = DATA_DIR / "models.json"

def load_models_db() -> Dict[str, Any]:
    """Charge la base de données des modèles depuis le fichier JSON."""
    if not MODELS_JSON_PATH.exists():
        logger.warning(f"Fichier {MODELS_JSON_PATH} introuvable. Création d'un fichier vide.")
        save_models_db({})
        return {}

    try:
        with open(MODELS_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Erreur de syntaxe dans models.json : {e}")
        return {}
    except Exception as e:
        logger.error(f"Erreur de lecture de models.json : {e}")
        return {}

def save_models_db(data: Dict[str, Any]):
    """Sauvegarde la base de données dans le fichier JSON (Pour usages futurs)."""
    try:
        with open(MODELS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Impossible de sauvegarder models.json : {e}")

# --- Chargement initial (Singleton pattern via module level variable) ---
# Cela maintient la compatibilité avec le reste du code qui importe MODELS_DB
MODELS_DB = load_models_db()

# --- FONCTIONS UTILITAIRES (Compatibilité conservée) ---

def reload_db():
    """Force le rechargement depuis le disque (utile après une modification)."""
    global MODELS_DB
    MODELS_DB = load_models_db()

def get_model_info(friendly_name: str) -> Optional[Dict[str, Any]]:
    return MODELS_DB.get(friendly_name, None)

def get_all_friendly_names(local_only: bool = False) -> List[str]:
    if local_only:
        return [name for name, info in MODELS_DB.items() if info.get("type") == "local"]
    return list(MODELS_DB.keys())

def get_all_languages() -> List[str]:
    langs = set()
    for info in MODELS_DB.values():
        if "langs" in info:
            langs.update(info["langs"])
    return sorted(list(langs))

def get_friendly_name_from_tag(tag: str) -> str:
    # 1. Match exact
    for name, info in MODELS_DB.items():
        db_tag = info.get('ollama_tag', '')
        if tag == db_tag or tag == f"{db_tag}:latest":
            return name
    
    # 2. Nettoyage hf.co (Fallback pour modèles inconnus)
    if "hf.co" in tag:
        parts = tag.split('/')
        # Nettoyage agressif pour avoir un nom lisible
        clean_name = parts[-1].replace(":latest", "").replace("-GGUF", "").replace("-gguf", "").replace("-Q4_K_M", "")
        return f"📦 {clean_name}"
        
    # 3. Fallback standard
    return tag.replace(":latest", "")

def extract_thought(content: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrait le contenu entre les balises <think> (pour modèles CoT/Reasoning).
    Retourne un tuple : (pensée_extraite, contenu_nettoyé)
    """
    if not content: 
        return None, None
    
    # Regex non-gourmande pour capturer tout ce qui est entre les balises
    pattern = r"<think>(.*?)</think>"
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        thought = match.group(1).strip()
        # On supprime la balise et son contenu pour avoir le texte propre
        clean_content = re.sub(pattern, "", content, flags=re.DOTALL).strip()
        return thought, clean_content
        
    return None, content