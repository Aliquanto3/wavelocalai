"""
Modèles Mistral cloud intégrés (`MISTRAL_CLOUD_MODELS`) : liste du provider avec et sans clé,
détection et collisions avec les tags Ollama locaux, routage de la fabrique, LLM de CrewAI,
nom du fournisseur, refus de téléchargement, CO₂ inconnu et place des juges. Catalogue
simulé, aucun réseau, aucun Ollama.

Usage: python -m pytest tests/unit/test_mistral_cloud_models.py -q
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.core import crew_engine, model_defaults
from src.core.answer_carbon import answer_carbon_mg
from src.core.crew_engine import CrewFactory
from src.core.llm_provider import LLMProvider
from src.core.model_detector import (
    MISTRAL_CLOUD_CONTEXT,
    MISTRAL_CLOUD_MODELS,
    get_model_provider,
    is_api_model,
    is_mistral_cloud_tag,
)
from src.core.providers.mistral_provider import MistralProvider
from src.core.providers.provider_factory import LLMProviderFactory, is_cloud_tag

MISTRAL_TAGS = [
    "mistral-small-latest",
    "mistral-medium-latest",
    "mistral-large-latest",
    "ministral-8b-latest",
]
# Tags Ollama locaux proches : un « : » (variante) les distingue des tags cloud.
LOCAL_LOOKALIKES = ["ministral-3:8b", "mistral:7b", "mistral-small3.2:24b", "mistral-nemo:12b"]


@pytest.fixture(autouse=True)
def empty_catalog():
    """Aucune entrée de data/models.json : seule la liste intégrée est testée."""
    with patch("src.core.model_detector.MODELS_DB", {}):
        yield


def _provider(api_key: str | None = "cle-test") -> MistralProvider:
    with (
        patch("src.core.providers.mistral_provider.MISTRAL_AVAILABLE", True),
        patch("src.core.providers.mistral_provider.Mistral", MagicMock()),
    ):
        return MistralProvider(api_key=api_key or "")


def test_builtin_list_is_the_verified_one():
    assert list(MISTRAL_CLOUD_MODELS) == MISTRAL_TAGS


# --- Liste du provider ---


def test_list_models_with_key_offers_builtin_models():
    with patch("src.core.providers.mistral_provider.get_cloud_models_from_db", return_value=[]):
        models = _provider().list_models()

    assert [m["model"] for m in models] == MISTRAL_TAGS
    assert [m["name"] for m in models] == [
        "Mistral Small",
        "Mistral Medium",
        "Mistral Large",
        "Ministral 8B",
    ]
    for model in models:
        assert model["type"] == "cloud"
        assert model["provider"] == "mistral"
        assert model["context_length"] == MISTRAL_CLOUD_CONTEXT == 262144


def test_list_models_without_key_is_empty():
    with patch("src.core.providers.mistral_provider.get_cloud_models_from_db") as from_db:
        provider = _provider(api_key=None)
        provider._api_key = None
        assert provider.list_models() == []
    from_db.assert_not_called()


def test_list_models_declares_tool_calling():
    """Appel de fonctions publié par Mistral pour les quatre : badge « outils vérifiés »."""
    with patch("src.core.providers.mistral_provider.get_cloud_models_from_db", return_value=[]):
        models = _provider().list_models()

    assert all(model_defaults.tools_verified(m["model"], m["capabilities"], {}) for m in models)


def _factory_with_real_mistral() -> LLMProviderFactory:
    """Fabrique avec un vrai MistralProvider (clé de test) et un Ollama local simulé."""
    factory = object.__new__(LLMProviderFactory)
    local = SimpleNamespace(
        is_local=True,
        list_models=lambda: [
            {"model": "qwen2.5:1.5b", "type": "local", "size": 2**30, "details": {}}
        ],
    )
    factory._providers = {"ollama": local, "mistral": _provider()}
    return factory


def test_list_all_models_hides_mistral_when_cloud_is_off():
    with patch("src.core.providers.mistral_provider.get_cloud_models_from_db", return_value=[]):
        factory = _factory_with_real_mistral()
        local_only = factory.list_all_models(include_cloud=False)
        with_cloud = factory.list_all_models(include_cloud=True)

    assert [m["model"] for m in local_only] == ["qwen2.5:1.5b"]
    assert [m["model"] for m in with_cloud] == ["qwen2.5:1.5b", *MISTRAL_TAGS]
    assert {m["provider"] for m in with_cloud if m["model"] in MISTRAL_TAGS} == {"mistral"}


def test_menu_keeps_local_first_and_badges_mistral_as_cloud(monkeypatch):
    import src.app.ui as ui

    monkeypatch.setattr(ui, "available_memory_gb", lambda: 16.0)
    monkeypatch.setattr(ui, "machine_benchmark", lambda: {})
    monkeypatch.setattr(ui, "cloud_enabled", lambda: True)
    monkeypatch.setattr("src.core.model_defaults.load_versioned_catalog", lambda path=None: {})
    monkeypatch.setattr("src.core.model_defaults.MODELS_DB", {})
    with patch("src.core.providers.mistral_provider.get_cloud_models_from_db", return_value=[]):
        models = [*_provider().list_models(), {"model": "qwen2.5:1.5b", "type": "local"}]

    menu = ui.model_menu(models, cloud_types=("api", "cloud"))

    assert menu.display_to_tag[menu.labels[0]] == "qwen2.5:1.5b"
    cloud_labels = [label for label in menu.labels if menu.display_to_tag[label] in MISTRAL_TAGS]
    assert len(cloud_labels) == 4
    assert all(label.endswith("· Cloud") for label in cloud_labels)


def test_list_models_adds_models_json_api_entries_without_duplicate():
    from_db = [
        {"model": "mistral-small-latest", "name": "Doublon", "type": "cloud"},
        {"model": "mistral-large-2512", "name": "Mistral Large 2512", "type": "cloud"},
    ]
    with patch(
        "src.core.providers.mistral_provider.get_cloud_models_from_db", return_value=from_db
    ):
        models = _provider().list_models()

    assert [m["model"] for m in models] == [*MISTRAL_TAGS, "mistral-large-2512"]
    assert [m["name"] for m in models if m["model"] == "mistral-small-latest"] == ["Mistral Small"]


# --- Détection et collisions ---


@pytest.mark.parametrize("tag", MISTRAL_TAGS)
def test_builtin_tags_are_api_models(tag):
    assert is_mistral_cloud_tag(tag)
    assert is_api_model(tag) is True
    assert get_model_provider(tag) == "mistral_api"
    assert is_cloud_tag(tag) is True


@pytest.mark.parametrize("tag", ["Mistral-Small-Latest", " mistral-large-latest "])
def test_detection_is_exact_like_the_tag_sent_to_the_api(tag):
    """Appartenance exacte (comme Groq) : un tag détecté est toujours celui de l'API."""
    assert not is_mistral_cloud_tag(tag)


@pytest.mark.parametrize("tag", LOCAL_LOOKALIKES)
def test_local_ollama_tags_stay_local(tag):
    assert not is_mistral_cloud_tag(tag)
    assert is_api_model(tag) is False
    assert get_model_provider(tag) == "ollama"
    assert is_cloud_tag(tag) is False


@pytest.mark.parametrize("tag", ["", None, "mistral", "mistral-small", "mistral-large-latest:7b"])
def test_other_names_are_not_builtin_tags(tag):
    assert not is_mistral_cloud_tag(tag)


# --- Routage de la fabrique ---


def _factory(*, with_mistral: bool) -> LLMProviderFactory:
    factory = object.__new__(LLMProviderFactory)
    factory._providers = {"ollama": MagicMock(provider_name="ollama")}
    if with_mistral:
        factory._providers["mistral"] = MagicMock(provider_name="mistral")
    return factory


@pytest.mark.parametrize("tag", MISTRAL_TAGS)
def test_factory_routes_builtin_tags_to_mistral(tag):
    factory = _factory(with_mistral=True)
    assert factory.get_provider(tag) is factory._providers["mistral"]


@pytest.mark.parametrize("tag", LOCAL_LOOKALIKES)
def test_factory_keeps_lookalikes_on_ollama(tag):
    factory = _factory(with_mistral=True)
    assert factory.get_provider(tag) is factory._providers["ollama"]


def test_factory_without_mistral_key_refuses_instead_of_sending_to_ollama():
    with pytest.raises(ValueError, match="Mistral non disponible"):
        _factory(with_mistral=False).get_provider("mistral-small-latest")


# --- Mode Équipe (CrewAI) ---


@pytest.mark.parametrize("tag", MISTRAL_TAGS)
def test_crew_llm_targets_mistral_api(tag, monkeypatch):
    monkeypatch.setattr(crew_engine, "MISTRAL_API_KEY", "cle-mistral-test")

    llm = CrewFactory._get_native_llm(tag, temperature=0.2)

    assert llm.base_url == "https://api.mistral.ai/v1"
    assert llm.model == tag


@pytest.mark.parametrize("tag", LOCAL_LOOKALIKES)
def test_crew_llm_keeps_lookalikes_on_ollama(tag, monkeypatch):
    monkeypatch.setattr(crew_engine, "MISTRAL_API_KEY", "cle-mistral-test")
    factory = SimpleNamespace(
        get_provider_by_name=lambda name: SimpleNamespace(base_url="http://127.0.0.1:11434")
    )
    monkeypatch.setattr(crew_engine, "get_provider_factory", lambda: factory)

    llm = CrewFactory._get_native_llm(tag)

    assert "11434" in llm.base_url
    assert "mistral.ai" not in llm.base_url


# --- Nom du fournisseur et téléchargement ---


@pytest.mark.parametrize("tag", MISTRAL_TAGS)
def test_cloud_provider_name_is_mistral(tag):
    from src.app.states import _cloud_provider_name

    assert _cloud_provider_name(tag) == "Mistral"


@pytest.mark.parametrize("tag", LOCAL_LOOKALIKES)
def test_cloud_provider_name_none_for_local_lookalikes(tag):
    from src.app.states import _cloud_provider_name

    assert _cloud_provider_name(tag) is None


@pytest.mark.parametrize("tag", MISTRAL_TAGS)
def test_pull_model_refuses_builtin_tags(tag):
    with pytest.raises(ValueError, match="Impossible de télécharger"):
        LLMProvider.pull_model(tag)


# --- CO2 inconnu ---


@pytest.mark.parametrize("tag", MISTRAL_TAGS)
@pytest.mark.parametrize("is_cloud", [True, None])
def test_carbon_is_unknown_never_zero(tag, is_cloud):
    """Pas de taille publiée pour les tags `-latest` : None, jamais 0 (même sans origine)."""
    assert answer_carbon_mg(tag, 120, is_cloud) is None


@pytest.mark.parametrize("tag", MISTRAL_TAGS)
def test_carbon_without_token_stays_zero(tag):
    assert answer_carbon_mg(tag, 0, True) == 0.0


# --- Juge ---


def test_opus_stays_default_cloud_judge_with_mistral_models():
    tags = [*MISTRAL_TAGS, "claude-opus-5-5", "claude-sonnet-5-5"]

    assert min(tags, key=model_defaults.cloud_judge_rank) == "claude-opus-5-5"
    ranks = {t: model_defaults.cloud_judge_rank(t)[0] for t in MISTRAL_TAGS}
    assert ranks["mistral-large-latest"] < ranks["mistral-medium-latest"]
    # Sans Claude, Mistral Large est le meilleur juge Mistral.
    assert min(MISTRAL_TAGS, key=model_defaults.cloud_judge_rank) == "mistral-large-latest"


# --- Clé refusée ---

KEY_REFUSED = 'API error occurred: Status 401. Body: {"detail":"Invalid API Key"}'


def test_refused_key_is_named_in_french():
    from src.app.states import generation_failure_advice, inference_error_message

    advice = generation_failure_advice("mistral-small-latest", KEY_REFUSED)
    assert advice.startswith("Clé d'API Mistral refusée")
    result = SimpleNamespace(interrupted=False, timed_out=False, error=KEY_REFUSED)
    assert "Clé d'API Mistral refusée" in inference_error_message(result, "mistral-large-latest")


def test_other_errors_keep_the_generic_advice():
    from src.app.states import generation_failure_advice

    assert "ne répond pas" in generation_failure_advice("mistral-small-latest", "timeout")
    # Modèle local : jamais de message de clé, même avec « 401 » dans l'erreur.
    assert "Ollama" in generation_failure_advice("qwen2.5:1.5b", KEY_REFUSED)
