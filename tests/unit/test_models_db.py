"""
Tests unitaires pour models_db (gestion des modèles).
Usage: pytest tests/unit/test_models_db.py -v
"""

import json
from pathlib import Path

import pytest

from src.core.models_db import (
    MODELS_DB,
    extract_thought,
    get_all_friendly_names,
    get_all_languages,
    get_friendly_name_from_tag,
    get_model_info,
)

TEST_CATALOG = Path(__file__).resolve().parents[1] / "fixtures" / "models_catalog_test.json"


@pytest.fixture(autouse=True)
def test_catalog():
    """Remplace en place MODELS_DB (chargé à l'import depuis data/models.json, local
    et non versionné) par le catalogue de test, puis restaure le contenu d'origine."""
    catalog = json.loads(TEST_CATALOG.read_text(encoding="utf-8"))
    original = dict(MODELS_DB)
    MODELS_DB.clear()
    MODELS_DB.update(catalog)
    yield MODELS_DB
    MODELS_DB.clear()
    MODELS_DB.update(original)


class TestModelsDatabase:
    """Tests de la base de données des modèles."""

    def test_models_db_loaded(self):
        """Test que la DB est chargée et non vide."""
        assert MODELS_DB is not None
        assert len(MODELS_DB) > 0, "La DB devrait contenir au moins 1 modèle"

    def test_get_model_info_exists(self):
        """Test récupération d'un modèle existant."""
        # On prend le premier modèle de la DB
        first_model_name = list(MODELS_DB.keys())[0]

        info = get_model_info(first_model_name)

        assert info is not None
        assert "ollama_tag" in info
        assert "editor" in info

    def test_get_model_info_not_exists(self):
        """Test récupération d'un modèle inexistant."""
        info = get_model_info("ModeleInexistant123")
        assert info is None

    def test_get_all_friendly_names(self):
        """Test récupération de tous les noms."""
        names = get_all_friendly_names()

        assert isinstance(names, list)
        assert len(names) > 0

    def test_get_all_friendly_names_local_only(self):
        """Test filtrage des modèles locaux uniquement."""
        all_names = get_all_friendly_names(local_only=False)
        local_names = get_all_friendly_names(local_only=True)

        assert isinstance(local_names, list)
        # local_names devrait être un sous-ensemble de all_names
        assert len(local_names) <= len(all_names)

    def test_get_all_languages(self):
        """Test extraction de toutes les langues supportées."""
        langs = get_all_languages()

        assert isinstance(langs, list)
        assert len(langs) > 0
        # Devrait contenir au moins quelques langues courantes
        common_langs = {"en", "fr", "code"}
        assert len(common_langs.intersection(set(langs))) > 0


class TestFriendlyNameConversion:
    """Tests de conversion tag technique -> nom convivial."""

    def test_exact_match(self):
        """Test conversion avec match exact."""
        # Prend le premier modèle de la DB
        first_model_name = list(MODELS_DB.keys())[0]
        first_model_tag = MODELS_DB[first_model_name]["ollama_tag"]

        friendly = get_friendly_name_from_tag(first_model_tag)

        assert friendly == first_model_name

    def test_tag_with_latest(self):
        """Test conversion d'un tag avec :latest."""
        # Prend un tag et ajoute :latest
        first_model_tag = MODELS_DB[list(MODELS_DB.keys())[0]]["ollama_tag"]
        tag_with_latest = f"{first_model_tag}:latest"

        friendly = get_friendly_name_from_tag(tag_with_latest)

        # Devrait retourner le nom sans :latest
        assert ":latest" not in friendly

    def test_unknown_tag_hf_co(self):
        """Test conversion d'un tag HuggingFace inconnu."""
        unknown_tag = "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:IQ3_M"

        friendly = get_friendly_name_from_tag(unknown_tag)

        # Devrait nettoyer le nom
        assert "hf.co" not in friendly
        assert "📦" in friendly  # Emoji pour modèle manuel

    def test_unknown_tag_simple(self):
        """Test conversion d'un tag simple inconnu."""
        unknown_tag = "custom-model:latest"

        friendly = get_friendly_name_from_tag(unknown_tag)

        assert friendly == "Custom-model"


class TestThoughtExtraction:
    """Tests de l'extraction des balises <think>."""

    def test_extract_thought_present(self):
        """Test extraction quand pensée présente."""
        content = "<think>Je réfléchis...</think>La réponse est 42."

        thought, clean_text = extract_thought(content)

        assert thought == "Je réfléchis..."
        assert clean_text == "La réponse est 42."
        assert "<think>" not in clean_text

    def test_extract_thought_absent(self):
        """Test extraction quand pas de pensée."""
        content = "Réponse directe sans pensée."

        thought, clean_text = extract_thought(content)

        assert thought is None
        assert clean_text == content

    def test_extract_thought_multiline(self):
        """Test extraction avec pensée multi-lignes."""
        content = """<think>
        Étape 1: Analyser
        Étape 2: Calculer
        </think>Résultat final."""

        thought, clean_text = extract_thought(content)

        assert "Étape 1" in thought
        assert "Étape 2" in thought
        assert clean_text == "Résultat final."

    def test_extract_thought_empty_content(self):
        """Test avec contenu vide."""
        thought, clean_text = extract_thought("")

        assert thought is None
        assert clean_text is None

    def test_extract_thought_none_content(self):
        """Test avec None."""
        thought, clean_text = extract_thought(None)

        assert thought is None
        assert clean_text is None

    def test_extract_thought_multiple_tags(self):
        """Test avec plusieurs balises <think> (ne devrait prendre que la première)."""
        content = "<think>Pensée 1</think>Texte<think>Pensée 2</think>Suite"

        thought, clean_text = extract_thought(content)

        # La regex non-gourmande devrait prendre la première
        assert thought == "Pensée 1"
        # Le clean devrait retirer TOUTES les balises
        assert "<think>" not in clean_text
