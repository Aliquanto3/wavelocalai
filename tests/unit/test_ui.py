"""
Tests des libellés et sélecteurs de modèles partagés par les pages (src/app/ui.py).
Usage: python -m pytest tests/unit/test_ui.py -v
"""

import pytest

import src.app.ui as ui

GB = 1024**3

FRIENDLY = {
    "qwen2.5:1.5b": "Qwen 2.5 1.5B",
    "gemma3:1b": "Gemma 3 1B",
    "mistral-large-2512": "Mistral Large",
    "gpt-4o-mini": "GPT-4o mini",
    "llama3.1:8b": "Llama 3.1 8B",
    "glm-4.6:cloud": "Glm-4.6",
}

# Modèles locaux au format de LLMProvider.list_models (taille du téléchargement en octets).
QWEN = {
    "model": "qwen2.5:1.5b",
    "type": "local",
    "size": 1 * GB,
    "details": {"parameter_size": "1.5B"},
}
GEMMA = {
    "model": "gemma3:1b",
    "type": "local",
    "size": 0.8 * GB,
    "details": {"parameter_size": "1B"},
}
LLAMA = {
    "model": "llama3.1:8b",
    "type": "local",
    "size": 4.9 * GB,
    "details": {"parameter_size": "8.0B"},
}


@pytest.fixture(autouse=True)
def isolated_rule(monkeypatch):
    """Noms lisibles fixes, aucun catalogue (ni versionné ni data/models.json), 16 Go
    disponibles : l'ordre ne dépend pas de la machine."""
    monkeypatch.setattr(ui, "get_friendly_name_from_tag", FRIENDLY.__getitem__)
    monkeypatch.setattr(ui, "available_memory_gb", lambda: 16.0)
    monkeypatch.setattr("src.core.model_defaults.load_versioned_catalog", lambda path=None: {})
    monkeypatch.setattr("src.core.model_defaults.MODELS_DB", {})


def test_model_label_suffixes():
    assert ui.model_label("Qwen 2.5 1.5B", is_cloud=False) == "Qwen 2.5 1.5B · Local"
    assert ui.model_label("Mistral Large", is_cloud=True) == "Mistral Large · Cloud"


def test_model_menu_default_cloud_types():
    """Par défaut, seul le type « cloud » est distant : « api » reste local. Locaux d'abord,
    cloud en dernier ; chaque libellé renvoie à son propre tag."""
    models = [
        QWEN,
        {"model": "mistral-large-2512", "type": "cloud"},
        {"model": "gpt-4o-mini", "type": "api"},
    ]

    menu = ui.model_menu(models)

    # « api » traité en local, sans taille connue : après le local qui tient.
    assert menu.labels == [
        "Qwen 2.5 1.5B · Local",
        "GPT-4o mini · Local",
        "Mistral Large · Cloud",
    ]
    assert menu.display_to_tag == {
        "Mistral Large · Cloud": "mistral-large-2512",
        "GPT-4o mini · Local": "gpt-4o-mini",
        "Qwen 2.5 1.5B · Local": "qwen2.5:1.5b",
    }
    assert menu.tag_to_friendly["gpt-4o-mini"] == "GPT-4o mini"


def test_model_menu_with_api_as_cloud():
    """Locaux d'abord (le plus rapide qui tient en tête), puis cloud ; tags inchangés."""
    models = [
        QWEN,
        {"model": "gpt-4o-mini", "type": "api"},
        GEMMA,
        {"model": "mistral-large-2512", "type": "cloud"},
    ]

    menu = ui.model_menu(models, cloud_types=("cloud", "api"))

    assert menu.labels == [
        "Gemma 3 1B · Local",
        "Qwen 2.5 1.5B · Local",
        "GPT-4o mini · Cloud",
        "Mistral Large · Cloud",
    ]
    assert [menu.display_to_tag[label] for label in menu.labels] == [
        "gemma3:1b",
        "qwen2.5:1.5b",
        "gpt-4o-mini",
        "mistral-large-2512",
    ]


def test_model_menu_defaults():
    """Juge = plus gros local qui tient ; Arène = petits locaux qui tiennent, hors juge."""
    cloud = {"model": "mistral-large-2512", "type": "cloud"}
    menu = ui.model_menu([cloud, LLAMA, QWEN, GEMMA])

    assert menu.labels[0] == "Gemma 3 1B · Local"
    assert menu.labels[-1] == "Mistral Large · Cloud"
    assert menu.judge_default == "Llama 3.1 8B · Local"
    assert menu.arena_defaults == ["Gemma 3 1B · Local", "Qwen 2.5 1.5B · Local"]
    assert menu.weak_judges == {"Gemma 3 1B · Local", "Qwen 2.5 1.5B · Local"}


def test_model_menu_depends_on_available_memory(monkeypatch):
    """4 Go disponibles : le 8B (≈ 6 Go estimés) ne tient pas, il passe après les autres
    locaux et le juge devient un petit modèle, marqué peu fiable ; les deux petits restent
    présélectionnés."""
    monkeypatch.setattr(ui, "available_memory_gb", lambda: 4.0)
    menu = ui.model_menu([LLAMA, QWEN, GEMMA])

    assert menu.labels == ["Gemma 3 1B · Local", "Qwen 2.5 1.5B · Local", "Llama 3.1 8B · Local"]
    assert menu.arena_defaults == ["Gemma 3 1B · Local", "Qwen 2.5 1.5B · Local"]
    assert menu.judge_default == "Qwen 2.5 1.5B · Local"
    assert menu.judge_default in menu.weak_judges


def test_model_menu_disambiguates_same_display_name(monkeypatch):
    """Deux tags au même nom affiché : les deux restent proposés, libellés complétés par le
    tag ; le nom affiché des résultats suit."""
    names = dict(FRIENDLY, **{"qwen2.5:7b": "Qwen 2.5 1.5B"})
    monkeypatch.setattr(ui, "get_friendly_name_from_tag", names.__getitem__)
    twin = {"model": "qwen2.5:7b", "type": "local", "size": 4 * GB}
    menu = ui.model_menu([twin, QWEN, GEMMA])

    assert menu.labels == [
        "Gemma 3 1B · Local",
        "Qwen 2.5 1.5B (qwen2.5:1.5b) · Local",
        "Qwen 2.5 1.5B (qwen2.5:7b) · Local",
    ]
    assert menu.display_to_tag["Qwen 2.5 1.5B (qwen2.5:7b) · Local"] == "qwen2.5:7b"
    assert menu.tag_to_friendly["qwen2.5:1.5b"] == "Qwen 2.5 1.5B (qwen2.5:1.5b)"
    assert menu.tag_to_friendly["gemma3:1b"] == "Gemma 3 1B"
    assert len(set(menu.labels)) == 3


def test_available_memory_is_measured_once_per_session(monkeypatch):
    """La mémoire est mesurée une fois par session, modèles déjà chargés dans Ollama
    compris : l'ordre ne bouge pas quand un modèle chargé occupe de la mémoire entre deux
    reruns."""
    monkeypatch.undo()  # retire la mémoire simulée par la fixture
    readings = iter([12.0, 2.0])
    monkeypatch.setattr(ui.ResourceManager, "get_available_ram_gb", lambda: next(readings))
    monkeypatch.setattr(ui.LLMProvider, "loaded_models_ram_gb", lambda timeout=2.0: 1.5)
    state: dict = {}
    monkeypatch.setattr(ui.st, "session_state", state)

    assert ui.available_memory_gb() == 13.5
    assert ui.available_memory_gb() == 13.5
    assert state[ui.MEMORY_SNAPSHOT_KEY] == 13.5


def test_remote_ollama_tag_is_labelled_cloud():
    """Tag distant servi par Ollama (`x:cloud`) : libellé « · Cloud », après les locaux,
    jamais présélectionné."""
    remote = {"model": "glm-4.6:cloud", "type": "local", "size": 384}
    menu = ui.model_menu([remote, QWEN, GEMMA])

    assert menu.labels[-1] == "Glm-4.6 · Cloud"
    assert menu.display_to_tag["Glm-4.6 · Cloud"] == "glm-4.6:cloud"
    assert "Glm-4.6 · Cloud" not in menu.arena_defaults
    assert menu.judge_default != "Glm-4.6 · Cloud"


def test_model_menu_ignores_entry_without_model():
    menu = ui.model_menu([{"type": "local", "size": 1}, {"model": ""}, QWEN])
    assert menu.labels == ["Qwen 2.5 1.5B · Local"]


def test_available_memory_adds_only_local_ollama_models(monkeypatch):
    """Hôte Ollama distant : LLMProvider.loaded_models_ram_gb renvoie 0, la mémoire
    disponible est la seule mémoire libre de cette machine."""
    monkeypatch.undo()
    monkeypatch.setattr(ui.ResourceManager, "get_available_ram_gb", lambda: 8.0)
    monkeypatch.setattr(ui.LLMProvider, "loaded_models_ram_gb", lambda timeout=2.0: 0.0)
    monkeypatch.setattr(ui.st, "session_state", {})
    assert ui.available_memory_gb() == 8.0
