"""
Point d'entrée de WaveLocalAI : navigation, barre latérale commune et contrôle cloud unique.

Le contenu de l'accueil vit dans home.py ; les modules dans views/. Seules les pages déclarées
ici existent. Le dossier ne doit pas s'appeler pages/ : sa seule présence fait exécuter par
Streamlit la première requête de chaque processus (et chaque exécution sous AppTest) en mode
multipage historique, sans ce routeur (anciens noms dans le menu, pas de contrôle cloud).
"""

import sys
from pathlib import Path

import streamlit as st

# --- SETUP PATH ---
root_path = Path(__file__).parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

# Avant tout import de src : les bibliothèques lisent leur variable de télémétrie à l'import.
from src.core.telemetry import disable_telemetry  # noqa: E402

disable_telemetry()

from src.app.modules import HOME_ICON, HOME_TITLE, MODULES  # noqa: E402
from src.app.states import ollama_available, render_ollama_down_alert  # noqa: E402
from src.app.ui import (  # noqa: E402  (après l'ajout de la racine)
    CLOUD_DEFAULT,
    CLOUD_KEY,
    FAVICON_PATH,
    render_logo,
)

try:
    from src.core.green_monitor import SESSION_PROJECT, GreenTracker
except ImportError:
    GreenTracker = None

CLOUD_TOGGLE_LABEL = "Autoriser le cloud"
CLOUD_TOGGLE_HELP = (
    "Désactivé, seuls les modèles locaux (Ollama) sont proposés. Activé, les données envoyées "
    "aux modèles cloud (Mistral, OpenAI) quittent la machine."
)

# Favicon local à chaque exécution : une icône Material de st.Page serait sinon téléchargée
# depuis fonts.gstatic.com pour l'onglet du navigateur.
st.set_page_config(
    page_icon=FAVICON_PATH,
    layout="wide",
    initial_sidebar_state="expanded",
)

pages = [
    st.Page("home.py", title=HOME_TITLE, icon=HOME_ICON, default=True),
    *(
        st.Page(module.path, title=module.title, icon=module.icon, url_path=module.url_path)
        for module in MODULES
    ),
]
page = st.navigation(pages)

# --- SUIVI CARBONE DE LA SESSION (singleton) ---
# Dans le routeur, exécuté à chaque page : un lien direct vers un module lance aussi le suivi.
if "tracker" not in st.session_state and GreenTracker:
    st.session_state.tracker = GreenTracker(project_name=SESSION_PROJECT)
    st.session_state.tracker.start()
    st.session_state.tracking_active = True

render_logo()

# --- CONTRÔLE LOCAL/CLOUD UNIQUE ---
# Local à chaque démarrage de session (D1), même si une clé d'API est présente : passer en
# Cloud est un geste explicite. Le widget est rendu à chaque exécution, quelle que soit la
# page : sa valeur (clé CLOUD_KEY) survit donc aux changements de page. Les pages lisent
# l'état par src.app.ui.cloud_enabled().
if CLOUD_KEY not in st.session_state:
    st.session_state[CLOUD_KEY] = CLOUD_DEFAULT

with st.sidebar:
    st.toggle(CLOUD_TOGGLE_LABEL, key=CLOUD_KEY, help=CLOUD_TOGGLE_HELP)

# --- SERVICE INDISPONIBLE ---
# En tête de chaque module (l'accueil l'affiche dans sa métrique « Système ») : Ollama
# interrogé en local, délai court, état mis en cache quelques secondes.
if page.url_path in {module.url_path for module in MODULES} and not ollama_available():
    render_ollama_down_alert()

page.run()
