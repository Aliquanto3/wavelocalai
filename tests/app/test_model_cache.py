"""
Cache court de la liste des modèles et du sélecteur (st.cache_data, 15 s).

Aucun Ollama : `LLMProvider.list_models` est simulé et compté.
Usage: python -m pytest tests/app/test_model_cache.py -v
"""

from streamlit.testing.v1 import AppTest

from src.app import ui
from src.core.llm_provider import LLMProvider
from tests.app.conftest import APP_DIR, FAKE_LOCAL_MODELS, THIRD_LOCAL_MODEL
from tests.app.test_pages import RENDER_TIMEOUT_S

ARENA_PAGE = "views/02_Inference_Arena.py"
LLAMA = "Llama3.2 · Local"


def _serve(monkeypatch, models):
    """list_models renvoie `models` (liste modifiable) ; les appels sont comptés."""
    calls = []

    def _list(cloud_enabled=True):
        calls.append(cloud_enabled)
        return [dict(m) for m in models]

    monkeypatch.setattr(LLMProvider, "list_models", staticmethod(_list))
    return calls


def test_installed_models_called_once_within_ttl(monkeypatch):
    calls = _serve(monkeypatch, FAKE_LOCAL_MODELS)

    first = ui.installed_models(cloud_on=False)
    second = ui.installed_models(cloud_on=False)

    assert first == second
    assert len(first) == 2
    assert calls == [False]


def test_installed_models_keyed_by_cloud_toggle(monkeypatch):
    calls = _serve(monkeypatch, FAKE_LOCAL_MODELS)

    ui.installed_models(cloud_on=False)
    ui.installed_models(cloud_on=True)
    ui.installed_models(cloud_on=True)

    assert calls == [False, True]


def test_empty_list_is_not_cached(monkeypatch):
    """Ollama arrêté ou rien d'installé : la liste vide n'est pas gardée, un modèle
    installé juste après apparaît au rerun suivant."""
    models: list[dict] = []
    calls = _serve(monkeypatch, models)

    assert ui.installed_models(cloud_on=False) == []
    models.extend(FAKE_LOCAL_MODELS)

    assert len(ui.installed_models(cloud_on=False)) == 2
    assert len(calls) == 2


def test_invalidate_refreshes_installed_models(monkeypatch):
    models = list(FAKE_LOCAL_MODELS)
    _serve(monkeypatch, models)
    assert len(ui.installed_models(cloud_on=False)) == 2

    models.append(THIRD_LOCAL_MODEL)
    assert len(ui.installed_models(cloud_on=False)) == 2  # encore le cache

    ui.invalidate_model_caches()

    assert len(ui.installed_models(cloud_on=False)) == 3


def test_model_menu_computed_once_per_inputs(monkeypatch):
    models = [dict(m) for m in FAKE_LOCAL_MODELS]
    ranked = []
    real_rank = ui.rank_models

    def _count(*args, **kwargs):
        ranked.append(1)
        return real_rank(*args, **kwargs)

    monkeypatch.setattr(ui, "rank_models", _count)

    first = ui.model_menu(models)
    second = ui.model_menu(models)
    assert first == second
    assert len(ranked) == 1

    # Autre liste de modèles : autre clé, recalcul.
    ui.model_menu([*models, dict(THIRD_LOCAL_MODEL)])
    assert len(ranked) == 2

    # Invalidation (installation, « Rafraîchir ») : recalcul.
    ui.invalidate_model_caches()
    ui.model_menu(models)
    assert len(ranked) == 3


def test_refresh_button_shows_model_installed_since(monkeypatch):
    """Un modèle installé pendant la session apparaît après « Rafraîchir » (Gestion des
    modèles), sans attendre la fin du cache."""
    models = list(FAKE_LOCAL_MODELS)
    _serve(monkeypatch, models)
    at = AppTest.from_file(str(APP_DIR / ARENA_PAGE), default_timeout=RENDER_TIMEOUT_S)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    try:
        (compare,) = [m for m in at.multiselect if m.label == "Modèles à comparer"]
        assert LLAMA not in compare.options

        models.append(THIRD_LOCAL_MODEL)
        at.run()
        (compare,) = [m for m in at.multiselect if m.label == "Modèles à comparer"]
        assert LLAMA not in compare.options  # liste en cache

        (refresh,) = [b for b in at.button if b.label == "Rafraîchir"]
        refresh.click().run()
        assert not at.exception, [e.value for e in at.exception]
        (compare,) = [m for m in at.multiselect if m.label == "Modèles à comparer"]
        assert LLAMA in compare.options
    finally:
        if "tracker" in at.session_state:
            at.session_state["tracker"].stop()
