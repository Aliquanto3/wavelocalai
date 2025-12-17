import json
import logging
import re
from typing import Any

# On pointe vers le fichier unique désormais
from src.core.config import MODELS_JSON_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- CHARGEMENT UNIQUE ---
def load_models_db() -> dict[str, Any]:
    """Charge la source de vérité unique (models.json)."""
    if not MODELS_JSON_PATH.exists():
        return {}
    try:
        with open(MODELS_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erreur models.json : {e}")
        return {}


MODELS_DB = load_models_db()

# --- HELPERS MODELS ---


def get_cloud_models_from_db() -> list[dict[str, Any]]:
    """Retourne la liste des modèles configurés comme API/Cloud dans le JSON."""
    cloud_models = []
    for friendly_name, info in MODELS_DB.items():
        if info.get("type") == "api":
            m = info.copy()
            m["name"] = friendly_name
            m["model"] = info.get("ollama_tag", friendly_name)
            m["type"] = "cloud"
            if "size" not in m:
                m["size"] = 0
            cloud_models.append(m)
    return cloud_models


def guess_editor_from_tag(tag: str) -> str:
    tag_lower = tag.lower()
    if "gemma" in tag_lower:
        return "Google"
    if "llama" in tag_lower:
        return "Meta"
    if "qwen" in tag_lower:
        return "Alibaba"
    # Correction SIM114 : Combinaison des ifs
    if "mistral" in tag_lower or "mixtral" in tag_lower or "codestral" in tag_lower:
        return "Mistral AI"
    if "phi" in tag_lower:
        return "Microsoft"
    if "vicuna" in tag_lower:
        return "LMSYS"
    if "falcon" in tag_lower:
        return "TII UAE"
    if "/" in tag:
        return tag.split("/")[0].capitalize()
    return "Community"


def get_friendly_name_from_tag(tag: str) -> str:
    for name, info in MODELS_DB.items():
        if info.get("ollama_tag") == tag or tag == f"{info.get('ollama_tag')}:latest":
            return name

    if "hf.co" in tag:
        return f"📦 {tag.split('/')[-1]}"
    return tag.split(":")[0].capitalize()


def get_model_info(friendly_name: str) -> dict[str, Any] | None:  # Correction UP007
    return MODELS_DB.get(friendly_name)


def get_all_friendly_names(local_only: bool = False) -> list[str]:
    if local_only:
        return [name for name, info in MODELS_DB.items() if info.get("type") == "local"]
    return list(MODELS_DB.keys())


def get_all_languages() -> list[str]:
    langs = set()
    for info in MODELS_DB.values():
        if "langs" in info:
            langs.update(info["langs"])
    # Correction C414 : Suppression du list() inutile
    return sorted(langs)


def get_model_card(tag: str, ollama_info: dict[str, Any] = None) -> dict[str, Any]:
    """Crée une fiche standardisée pour l'UI."""
    friendly_name = (
        ollama_info.get("name")
        if ollama_info and "name" in ollama_info
        else get_friendly_name_from_tag(tag)
    )
    db_info = MODELS_DB.get(friendly_name, {})

    is_cloud = False
    # Correction SIM102 : if imbriqué
    if (ollama_info and ollama_info.get("type") == "cloud") or db_info.get("type") == "api":
        is_cloud = True

    editor = db_info.get("editor", guess_editor_from_tag(tag))
    desc = db_info.get("desc", "Description manquante.")

    size_bytes = ollama_info.get("size", 0) if ollama_info else 0
    size_str = db_info.get("size_gb")
    if not size_str:
        size_str = f"{round(size_bytes / (1024**3), 2)} GB" if size_bytes > 0 else "API"

    benchmark = db_info.get("benchmark_stats", {})

    return {
        "id": tag,
        "name": friendly_name,
        "editor": editor,
        "description": desc,
        "size_str": size_str,
        "status_icon": "☁️" if is_cloud else ("🛡️" if db_info else "🆕"),
        "status_text": "Cloud" if is_cloud else ("Validé" if db_info else "Nouveau"),
        "is_cloud": is_cloud,
        "metrics": {
            "speed": f"{benchmark.get('speed_s', '—')} s",
            "ram": f"{benchmark.get('ram_usage_gb', '—')} GB",
            "co2": benchmark.get("co2_emissions_kg"),
            "ctx": db_info.get("ctx", "—"),
        },
        "specs": {"params": db_info.get("params_tot", "—")},
    }


def extract_thought(content: str) -> tuple[str | None, str | None]:
    """
    Extrait le contenu des balises <think> (ex: DeepSeek R1).
    Retourne (thought, content_cleaned).
    """
    if not content:
        return None, None
    pattern = r"<think>(.*?)</think>"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip(), re.sub(pattern, "", content, flags=re.DOTALL).strip()
    return None, content
