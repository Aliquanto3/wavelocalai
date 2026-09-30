"""
Tests de l'import de documents dans la page « Assistant documentaire » (story 4), avec AppTest.

AppTest 1.64 ne sait ni déposer un fichier dans st.file_uploader ni rejouer un fragment : le
sélecteur renvoie des fichiers simulés (et enregistre la clé reçue) et le bouton « Indexer les
documents » est considéré comme cliqué dès que le dialogue s'affiche, sauf si `click` est faux. Le reste est réel : dialogue, RAGEngine, Chroma
sous tmp_path (conftest), st.rerun et affichage du résultat au run suivant.
Usage: python -m pytest tests/app/test_rag_upload_page.py -v
"""

from types import SimpleNamespace

import pytest
import streamlit
from streamlit.testing.v1 import AppTest

from src.app.formatting import NBSP
from tests.app.conftest import APP_DIR
from tests.app.test_pages import RENDER_TIMEOUT_S

RAG_PAGE = "views/03_RAG_Knowledge.py"
MD_TEXT = "# Note de cadrage\n\n" + "L'atelier porte sur les modèles de langage locaux. " * 60
INDEX_BUTTON = "Indexer les documents"


class FakeUpload:
    """Double de streamlit UploadedFile : un nom et des octets."""

    def __init__(self, name: str, content: str):
        self.name = name
        self._data = content.encode("utf-8")

    def getvalue(self) -> bytes:
        return self._data


@pytest.fixture
def upload(monkeypatch):
    """Simule le dépôt de fichiers et le clic sur « Indexer les documents » (désactivable)."""
    state = SimpleNamespace(files=[], click=True, keys=[])
    real_button = streamlit.button

    def button(label, *args, **kwargs):
        clicked = real_button(label, *args, **kwargs)
        return clicked or (state.click and label == INDEX_BUTTON)

    def file_uploader(*args, key=None, **kwargs):
        state.keys.append(key)
        return list(state.files)

    monkeypatch.setattr(streamlit, "file_uploader", file_uploader)
    monkeypatch.setattr(streamlit, "button", button)
    return state


def _page():
    return AppTest.from_file(str(APP_DIR / RAG_PAGE), default_timeout=RENDER_TIMEOUT_S)


def _base_caption(at):
    (caption,) = [c.value for c in at.sidebar.caption if "indexé" in c.value]
    return caption


def _import(at, label="Importer des documents"):
    """Ouvre le dialogue d'import ; l'indexation suit si le clic est simulé (fixture upload)."""
    (button,) = [b for b in at.button if b.label == label]
    button.click().run()
    assert not at.exception, [e.value for e in at.exception]


def test_import_indexes_and_shows_result(upload):
    """Import d'un .md : légende de la barre latérale augmentée, message de résultat affiché
    après la fermeture du dialogue, puis retiré au run suivant."""
    at = _page()
    at.run()
    assert _base_caption(at) == f"0{NBSP}document indexé · 0{NBSP}extrait"

    upload.files.append(FakeUpload("cadrage.md", MD_TEXT))
    _import(at)
    assert upload.keys == ["rag_uploader_0"]

    count = at.session_state["rag_engine"].get_stats()["count"]
    assert count > 1
    assert _base_caption(at) == f"1{NBSP}document indexé · {count}{NBSP}extraits"
    assert [s.value for s in at.success] == [
        f"{count}{NBSP}extraits ajoutés depuis 1{NBSP}document."
    ]
    assert not at.error
    # Le dialogue est fermé : son bouton n'est plus rendu, la base n'est plus vide.
    assert INDEX_BUTTON not in [b.label for b in at.button]
    assert [t.label for t in at.tabs] == ["Discussion", "Évaluation de la qualité"]

    upload.files.clear()
    at.run()
    assert not at.success
    assert _base_caption(at) == f"1{NBSP}document indexé · {count}{NBSP}extraits"

    # Après un import réussi, le dialogue rouvert présente un sélecteur neuf (clé renouvelée).
    upload.click = False
    _import(at, "Gérer la base documentaire")
    assert upload.keys[-1] == "rag_uploader_1"


def test_import_reports_each_failed_file(upload):
    """Un fichier vide et un fichier valide : une erreur nommant le fichier, un succès pour
    l'autre ; le compteur ne compte que le fichier indexé."""
    upload.files.extend([FakeUpload("vide.txt", ""), FakeUpload("cadrage.md", MD_TEXT)])
    at = _page()
    at.run()
    _import(at)

    count = at.session_state["rag_engine"].get_stats()["count"]
    assert _base_caption(at) == f"1{NBSP}document indexé · {count}{NBSP}extraits"
    assert [s.value for s in at.success] == [
        f"{count}{NBSP}extraits ajoutés depuis 1{NBSP}document."
    ]
    (error,) = [e.value for e in at.error]
    assert "« vide.txt »" in error and "aucun texte extrait" in error


def test_import_all_failed_shows_errors_only(upload, monkeypatch):
    """Tous en échec : aucun succès, une erreur par fichier, trace dans « Détails techniques »,
    base toujours vide."""
    from src.core.rag_engine import RAGEngine

    def ingest_file(self, file_path, original_filename):
        raise RuntimeError("collection verrouillée")

    monkeypatch.setattr(RAGEngine, "ingest_file", ingest_file)
    upload.files.extend([FakeUpload("a.md", MD_TEXT), FakeUpload("b.txt", "Texte.")])
    at = _page()
    at.run()
    _import(at)

    assert not at.success
    errors = [e.value for e in at.error]
    assert len(errors) == 2
    assert "« a.md »" in errors[0] and "« b.txt »" in errors[1]
    assert [e.label for e in at.expander].count("Détails techniques") == 2
    assert any("collection verrouillée" in c.value for c in at.code)
    assert _base_caption(at) == f"0{NBSP}document indexé · 0{NBSP}extrait"
    assert "Votre base documentaire est vide" in [h.value for h in at.header]

    # Échec total : même clé au dialogue suivant, la sélection reste disponible pour réessayer.
    upload.click = False
    _import(at)
    assert upload.keys == ["rag_uploader_0", "rag_uploader_0"]


def test_files_chosen_without_click_index_nothing(upload):
    """Fichiers choisis, bouton non cliqué : rien n'est indexé ni affiché."""
    upload.click = False
    upload.files.append(FakeUpload("cadrage.md", MD_TEXT))
    at = _page()
    at.run()
    _import(at)

    assert INDEX_BUTTON in [b.label for b in at.button]
    assert at.session_state["rag_engine"].get_stats()["count"] == 0
    assert not at.success
    assert not at.error
    assert "rag_last_ingest" not in at.session_state
    assert _base_caption(at) == f"0{NBSP}document indexé · 0{NBSP}extrait"


def test_file_name_is_escaped_in_page(upload):
    """Nom de fichier à caractères Markdown : échappé dans le message d'erreur affiché."""
    upload.files.append(FakeUpload("vide_*[v2]*.txt", ""))
    at = _page()
    at.run()
    _import(at)

    (error,) = [e.value for e in at.error]
    assert r"« vide\_\*\[v2\]\*.txt »" in error


def test_default_embedding_fallback_matches_engine(tmp_path, monkeypatch):
    """Sans modèle d'embedding local, la liste de la barre latérale propose le nom du moteur :
    aucun changement de collection au rendu."""
    from src.core.rag_engine import DEFAULT_EMBEDDING_MODEL

    monkeypatch.setattr("src.core.config.DATA_DIR", tmp_path / "data")
    at = _page()
    at.run()

    assert not at.exception, [e.value for e in at.exception]
    engine = at.session_state["rag_engine"]
    assert engine.current_embedding_name == DEFAULT_EMBEDDING_MODEL
    (select,) = [s for s in at.sidebar.selectbox if s.label == "Modèle"]
    assert select.options == [DEFAULT_EMBEDDING_MODEL]
    assert select.value == DEFAULT_EMBEDDING_MODEL
