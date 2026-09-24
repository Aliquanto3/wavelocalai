import os
from pathlib import Path

from dotenv import load_dotenv

# Chargement du .env
load_dotenv()

# Définition des chemins absolus
ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma"
LOGS_DIR = DATA_DIR / "logs"
EMISSIONS_DIR = LOGS_DIR / "emissions"
BENCHMARKS_DIR = LOGS_DIR / "benchmarks"
OUTPUT_DIR = ROOT_DIR / "output"

# Source de vérité unique pour les modèles
MODELS_JSON_PATH = DATA_DIR / "models.json"

# Création des dossiers s'ils n'existent pas
# Création des dossiers
for path in [LOGS_DIR, CHROMA_DIR, EMISSIONS_DIR, BENCHMARKS_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# Marge de sécurité RAM (en GB) pour l'OS et les autres apps
SYSTEM_RAM_BUFFER_GB = 0.5

# --- CONFIGURATION OUTILS ---
# Timeout pour le calculateur (en secondes)
CALCULATOR_TIMEOUT = int(os.getenv("CALCULATOR_TIMEOUT", "5"))

# --- CONFIGURATION API (Centralisée) ---
# Utilisation de getenv avec fallback None pour la robustesse
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- CONFIGURATION GREEN IT ---
DEFAULT_COUNTRY_ISO_CODE = os.getenv("WAVELOCAL_COUNTRY_ISO", "FRA")
DEFAULT_PUE = float(os.getenv("WAVELOCAL_PUE", "1.1"))


def get_emissions_path() -> str:
    """Retourne le chemin du fichier de log des émissions carbone."""
    return str(EMISSIONS_DIR / "emissions.csv")
