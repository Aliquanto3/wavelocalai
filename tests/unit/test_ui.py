"""
Tests des libellés de modèles partagés par les pages (src/app/ui.py).
Usage: python -m pytest tests/unit/test_ui.py -v
"""

import pytest

import src.app.ui as ui

FRIENDLY = {
    "qwen2.5:1.5b": "Qwen 2.5 1.5B",
    "gemma3:1b": "Gemma 3 1B",
    "mistral-large-2512": "Mistral Large",
    "gpt-4o-mini": "GPT-4o mini",
}


@pytest.fixture(autouse=True)
def friendly_names(monkeypatch):
    """Noms lisibles fixes, indépendants de data/models.json."""
    monkeypatch.setattr(ui, "get_friendly_name_from_tag", FRIENDLY.__getitem__)


def test_model_label_suffixes():
    assert ui.model_label("Qwen 2.5 1.5B", is_cloud=False) == "Qwen 2.5 1.5B · Local"
    assert ui.model_label("Mistral Large", is_cloud=True) == "Mistral Large · Cloud"


def test_model_options_default_cloud_types():
    """Par défaut, seul le type « cloud » est distant : « api » reste local."""
    models = [
        {"model": "qwen2.5:1.5b", "type": "local"},
        {"model": "mistral-large-2512", "type": "cloud"},
        {"model": "gpt-4o-mini", "type": "api"},
    ]

    display_to_tag, tag_to_friendly, labels = ui.model_options(models)

    assert labels == ["Mistral Large · Cloud", "GPT-4o mini · Local", "Qwen 2.5 1.5B · Local"]
    assert display_to_tag == {
        "Mistral Large · Cloud": "mistral-large-2512",
        "GPT-4o mini · Local": "gpt-4o-mini",
        "Qwen 2.5 1.5B · Local": "qwen2.5:1.5b",
    }
    assert tag_to_friendly == {tag: FRIENDLY[tag] for tag in display_to_tag.values()}


def test_model_options_with_api_as_cloud():
    """Cloud puis local, chacun trié par nom ; chaque libellé renvoie à son propre tag."""
    models = [
        {"model": "qwen2.5:1.5b", "type": "local"},
        {"model": "gpt-4o-mini", "type": "api"},
        {"model": "gemma3:1b", "type": "local"},
        {"model": "mistral-large-2512", "type": "cloud"},
    ]

    display_to_tag, _, labels = ui.model_options(models, cloud_types=("cloud", "api"))

    assert labels == [
        "GPT-4o mini · Cloud",
        "Mistral Large · Cloud",
        "Gemma 3 1B · Local",
        "Qwen 2.5 1.5B · Local",
    ]
    assert [display_to_tag[label] for label in labels] == [
        "gpt-4o-mini",
        "mistral-large-2512",
        "gemma3:1b",
        "qwen2.5:1.5b",
    ]
