"""Tests du banc de qualité difficile : sans Ollama ni réseau, dans ``.venv-quality``.

Commande : ``.venv-quality\\Scripts\\python -m pytest tests/quality_bench``. Lancé depuis un
autre venv (``.venv``, ``.venv-app``) sans les dépendances du banc, le dossier est ignoré avec
un message plutôt que d'échouer à la collecte.
"""

from __future__ import annotations

import importlib.util
import os
import warnings

import pytest

# dotenv : importé par src.core.telemetry, que la CLI appelle en tête.
REQUIRED_MODULES = ("httpx2", "yaml", "jsonschema", "dotenv")
MISSING_MODULES = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]

if MISSING_MODULES:
    collect_ignore_glob = ["*"]
    warnings.warn(
        f"tests/quality_bench ignoré : dépendances absentes {MISSING_MODULES}. Installer "
        "scripts/quality_bench/requirements.txt dans .venv-quality et lancer "
        r"`.venv-quality\Scripts\python -m pytest tests/quality_bench`.",
        stacklevel=1,
    )

INTEGRATION_ENV = "QUALITY_BENCH_INTEGRATION"


@pytest.fixture(autouse=True)
def _isolated_data_root(tmp_path, monkeypatch):
    """Jamais d'écriture dans ``data/`` réel : la racine des données pointe sur ``tmp_path``."""
    root = tmp_path / "quality_bench_data"
    monkeypatch.setenv("QUALITY_BENCH_DATA", str(root))
    monkeypatch.delenv("QUALITY_BENCH_MACHINE", raising=False)
    return root


@pytest.fixture(autouse=True)
def _skip_integration_unless_enabled(request):
    """Le marqueur ``integration`` (Ollama réel) est sauté sauf ``QUALITY_BENCH_INTEGRATION=1``."""
    if request.node.get_closest_marker("integration") and os.environ.get(INTEGRATION_ENV) != "1":
        pytest.skip(f"test d'intégration : définir {INTEGRATION_ENV}=1 pour le lancer")
