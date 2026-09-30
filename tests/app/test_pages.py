"""
Tests de rendu des pages Streamlit avec AppTest.
Usage: python -m pytest tests/app -v
"""

import pytest
from streamlit.testing.v1 import AppTest

from tests.app.conftest import APP_DIR

# Le premier rendu importe torch, crewai, chromadb... : délai large.
RENDER_TIMEOUT_S = 120

PAGES = [
    "Accueil.py",
    "views/01_Socle_Hardware.py",
    "views/02_Inference_Arena.py",
    "views/03_RAG_Knowledge.py",
    "views/04_Agent_Lab.py",
]


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page):
    """La page s'exécute sans exception et rend un titre."""
    at = AppTest.from_file(str(APP_DIR / page), default_timeout=RENDER_TIMEOUT_S)
    try:
        at.run()

        assert not at.exception, [e.value for e in at.exception]
        assert len(at.title) >= 1, "La page devrait rendre un st.title"
    finally:
        # Arrête le tracker CodeCarbon démarré par la page, même si une assertion échoue.
        if "tracker" in at.session_state:
            at.session_state["tracker"].stop()
