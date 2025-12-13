import os
from pathlib import Path

# Définition des chemins absolus basés sur la racine du projet
# On remonte de 2 niveaux depuis src/core/config.py pour trouver la racine
ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
CHROMA_DIR = DATA_DIR / "chroma"

# Création des dossiers s'ils n'existent pas (sécurité)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# Configuration par défaut Green IT
DEFAULT_COUNTRY_ISO_CODE = "FRA"  # France par défaut (Wavestone HQ)
DEFAULT_PUE = 1.0  # 1.0 car nous sommes en Local (pas de cooling de datacenter cloud)

def get_emissions_path() -> str:
    """Retourne le chemin complet vers le fichier CSV de CodeCarbon"""
    return str(LOGS_DIR / "emissions.csv")