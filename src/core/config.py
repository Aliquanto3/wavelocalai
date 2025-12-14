import os
from pathlib import Path

from dotenv import load_dotenv

# Chargement du .env
load_dotenv()

# Définition des chemins absolus
ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
CHROMA_DIR = DATA_DIR / "chroma"

# Source de vérité unique pour les modèles
MODELS_JSON_PATH = DATA_DIR / "models.json"

# Création des dossiers s'ils n'existent pas
LOGS_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# Configuration API
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# --- CONFIGURATION GREEN IT (Restaurée) ---
DEFAULT_COUNTRY_ISO_CODE = os.getenv("WAVELOCAL_COUNTRY_ISO", "FRA")
DEFAULT_PUE = float(os.getenv("WAVELOCAL_PUE", "1.1"))


def get_emissions_path() -> str:
    return str(LOGS_DIR / "emissions.csv")
