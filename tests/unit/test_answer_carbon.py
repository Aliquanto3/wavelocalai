"""
CO₂ d'une réponse (story 23) : une seule règle, commune aux six onglets, choisie selon
l'origine réelle du modèle (celle de son badge). Catalogue simulé : aucun fichier local,
aucun réseau.

Usage: python -m pytest tests/unit/test_answer_carbon.py -v
"""

from unittest.mock import patch

import pytest

from src.core.answer_carbon import answer_carbon_mg
from src.core.green_monitor import CarbonCalculator

CATALOG = {
    "Qwen 2.5 1.5B": {
        "ollama_tag": "qwen2.5:1.5b",
        "type": "local",
        "params_act": "1.5B",
        "params_tot": "1.5B",
    },
    "Mistral Large": {
        "ollama_tag": "mistral-large-2512",
        "type": "api",
        "params_act": "123B",
        "params_tot": "123B",
    },
    # Tag distant servi par Ollama, décrit dans le catalogue (paramètres actifs connus).
    "GPT-OSS 120B Cloud": {
        "ollama_tag": "gpt-oss:120b-cloud",
        "type": "local",
        "params_act": "5.1B",
        "params_tot": "117B",
    },
    # Paramètres actifs absents : repli sur les paramètres totaux.
    "Dense Cloud": {"ollama_tag": "dense:cloud", "type": "local", "params_tot": "30B"},
}


@pytest.fixture(autouse=True)
def catalog():
    with patch.dict("src.core.models_db.MODELS_DB", CATALOG, clear=True):
        yield


def _local_mg(tokens):
    return CarbonCalculator.compute_local_theoretical_g(tokens) * 1000


def _cloud_mg(params, tokens):
    return CarbonCalculator.compute_mistral_impact_g(params, tokens) * 1000


def test_local_model_same_figures_as_before():
    """7,6 mg pour 40 tokens, 3,8 mg pour 20, 1 140 mg pour 6 000 (formule locale)."""
    assert answer_carbon_mg("qwen2.5:1.5b", 40, is_cloud=False) == pytest.approx(7.6)
    assert answer_carbon_mg("qwen2.5:1.5b", 20, is_cloud=False) == pytest.approx(3.8)
    assert answer_carbon_mg("qwen2.5:1.5b", 6000, is_cloud=False) == pytest.approx(1140)
    assert answer_carbon_mg("qwen2.5:1.5b", 0, is_cloud=False) == 0.0


def test_catalog_cloud_model_uses_cloud_formula():
    assert answer_carbon_mg("mistral-large-2512", 100, is_cloud=True) == pytest.approx(
        _cloud_mg(123.0, 100)
    )


def test_remote_tag_outside_catalog_is_unknown_never_local():
    """Tag distant d'Ollama hors catalogue, badge Cloud : CO₂ inconnu (None), pas local."""
    assert answer_carbon_mg("glm-4.6:cloud", 100, is_cloud=True) is None


def test_remote_tag_with_known_size_uses_cloud_formula():
    """Type « local » au catalogue, mais badge Cloud : formule cloud, jamais locale."""
    carbon = answer_carbon_mg("gpt-oss:120b-cloud", 100, is_cloud=True)
    assert carbon == pytest.approx(_cloud_mg(5.1, 100))
    assert carbon != pytest.approx(_local_mg(100))
    # Paramètres actifs absents : paramètres totaux.
    assert answer_carbon_mg("dense:cloud", 100, is_cloud=True) == pytest.approx(
        _cloud_mg(30.0, 100)
    )


def test_real_origin_overrides_catalog_type():
    assert answer_carbon_mg("mistral-large-2512", 100, is_cloud=False) == pytest.approx(
        _local_mg(100)
    )


def test_unknown_origin_follows_catalog_type():
    assert answer_carbon_mg("mistral-large-2512", 100) == pytest.approx(_cloud_mg(123.0, 100))
    assert answer_carbon_mg("qwen2.5:1.5b", 100) == pytest.approx(_local_mg(100))
    assert answer_carbon_mg("gpt-oss:120b-cloud", 100) == pytest.approx(_local_mg(100))
    # Hors catalogue, origine inconnue : formule locale.
    assert answer_carbon_mg("llama3.2:1b", 40) == pytest.approx(7.6)


@pytest.mark.parametrize(
    "tokens", [None, True, False, float("nan"), float("inf"), float("-inf"), -1, "40"]
)
def test_invalid_tokens_are_unknown(tokens):
    assert answer_carbon_mg("qwen2.5:1.5b", tokens, is_cloud=False) is None


@pytest.mark.parametrize("tag", [None, ""])
def test_missing_tag_is_unknown(tag):
    assert answer_carbon_mg(tag, 40, is_cloud=False) is None


def test_catalog_found_by_tag_not_by_label():
    """La fiche vient du tag (nom du catalogue), jamais d'un libellé « Nom (tag) »."""
    assert answer_carbon_mg("mistral-large-2512", 100, is_cloud=True) is not None
    assert answer_carbon_mg("Mistral Large (mistral-large-2512)", 100, is_cloud=True) is None


def test_zero_tokens_is_zero_even_for_unknown_cloud_size():
    """0 token : 0 quelle que soit la formule, même pour un tag distant hors catalogue."""
    assert answer_carbon_mg("glm-4.6:cloud", 0, is_cloud=True) == 0.0
    assert answer_carbon_mg("mistral-large-2512", 0, is_cloud=True) == 0.0


def test_catalog_failure_is_unknown_never_raises():
    def broken(*args, **kwargs):
        raise ValueError("catalogue illisible")

    with patch("src.core.answer_carbon.get_model_info", broken):
        assert answer_carbon_mg("qwen2.5:1.5b", 40, is_cloud=False) is None
    with patch("src.core.answer_carbon.get_friendly_name_from_tag", broken):
        assert answer_carbon_mg("mistral-large-2512", 40, is_cloud=True) is None


def test_only_the_core_calls_carbon_formulas():
    """Plus aucune copie de la règle dans l'interface : seul le cœur appelle les formules."""
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[2] / "src" / "app"
    offenders = [
        str(path.relative_to(app_dir))
        for path in app_dir.rglob("*.py")
        if "compute_local_theoretical_g" in (text := path.read_text(encoding="utf-8"))
        or "compute_mistral_impact_g" in text
    ]
    assert offenders == []
