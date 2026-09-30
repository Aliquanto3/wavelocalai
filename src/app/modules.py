"""
Modules de l'application : nom unique, icône Material, fichier et chemin d'URL.

Source unique du menu (Accueil.py) et des liens de l'accueil (home.py). Noms, ordre et icônes
d'EXPERIENCE.md (Information Architecture) ; les chemins d'URL gardent les anciens noms de
fichiers (/Inference_Arena…) pour que les liens et les scripts d'audit existants restent valides.
"""

from dataclasses import dataclass

HOME_TITLE = "Accueil"
HOME_ICON = ":material/home:"
# Titre de l'onglet du navigateur et du h1 de l'accueil.
APP_NAME = "WaveLocalAI"


@dataclass(frozen=True)
class Module:
    path: str  # relatif à src/app (dossier du script principal)
    title: str
    icon: str
    url_path: str
    pitch: str  # phrase sans jargon affichée sur l'accueil


ARENA = Module(
    path="views/02_Inference_Arena.py",
    title="Arène des modèles",
    icon=":material/leaderboard:",
    url_path="Inference_Arena",
    pitch="Comparez plusieurs petits modèles sur votre question : qualité, vitesse et CO₂.",
)
DOCUMENTS = Module(
    path="views/03_RAG_Knowledge.py",
    title="Assistant documentaire",
    icon=":material/description:",
    url_path="RAG_Knowledge",
    pitch="Interrogez vos documents et retrouvez les passages qui fondent chaque réponse.",
)
AGENTS = Module(
    path="views/04_Agent_Lab.py",
    title="Agents autonomes",
    icon=":material/smart_toy:",
    url_path="Agent_Lab",
    pitch="Confiez une tâche outillée à un agent ou à une équipe d'agents.",
)
SOBRIETY = Module(
    path="views/01_Socle_Hardware.py",
    title="Sobriété et matériel",
    icon=":material/eco:",
    url_path="Socle_Hardware",
    pitch="Voyez la machine, sa charge et les émissions de CO₂ mesurées.",
)

# Ordre du menu et de l'accueil.
MODULES = (ARENA, DOCUMENTS, AGENTS, SOBRIETY)
# Module mis en avant sur l'accueil.
RECOMMENDED = ARENA
