"""
Tests des messages du garde-fou mémoire (src/core/resource_manager.py), affichés tels quels
dans l'agent : français, Go, virgule décimale, sans exclamation.
Usage: python -m pytest tests/unit/test_resource_manager.py -v
"""

import pytest

from src.core.resource_manager import ResourceManager

NBSP = " "


@pytest.fixture
def ram(monkeypatch):
    """Fixe le besoin par modèle et la mémoire disponible (en Go)."""

    def configure(needed_gb, available_gb):
        monkeypatch.setattr(
            ResourceManager, "estimate_model_ram", staticmethod(lambda t: needed_gb)
        )
        monkeypatch.setattr(
            ResourceManager, "get_available_ram_gb", staticmethod(lambda: available_gb)
        )

    return configure


def _assert_french(message):
    assert "GB" not in message
    assert "!" not in message
    for word in ("RAM Insuffisante", "crash", "Dispo", "sidebar", "Buffer"):
        assert word not in message


def test_blocked_message(ram):
    ram(needed_gb=4.26, available_gb=1.2)

    result = ResourceManager.check_resources("qwen2.5:1.5b", auto_free=False)

    assert not result.allowed
    _assert_french(result.message)
    assert f"4,3{NBSP}Go nécessaires" in result.message
    # Accord sur la valeur affichée : 1,2 Go « libre », 0,5 Go « réservé ».
    assert f"1,2{NBSP}Go libre dont 0,5{NBSP}Go réservé au système" in result.message
    assert "modèle plus petit" in result.message
    assert "barre latérale" in result.message


def test_allowed_message(ram):
    ram(needed_gb=1.5, available_gb=8.0)

    result = ResourceManager.check_resources("qwen2.5:1.5b", n_instances=2, auto_free=False)

    assert result.allowed
    _assert_french(result.message)
    assert f"3,0{NBSP}Go nécessaires (2 × 1,5{NBSP}Go)" in result.message
    assert f"7,5{NBSP}Go disponibles" in result.message
