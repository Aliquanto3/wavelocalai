"""Tests du banc de qualité difficile : sans Ollama ni réseau, dans ``.venv-quality``.

Commande : ``.venv-quality\\Scripts\\python -m pytest tests/quality_bench``. Lancé depuis un
autre venv (``.venv``, ``.venv-app``) sans les dépendances du banc, le dossier est ignoré avec
un message plutôt que d'échouer à la collecte.
"""

from __future__ import annotations

import importlib.util
import os
import warnings
from pathlib import Path

import pytest

# dotenv : importé par src.core.telemetry, que la CLI appelle en tête ; huggingface_hub et
# pyarrow : importeurs des jeux publics (story 2) ; absl à nltk : correction (story 4).
REQUIRED_MODULES = (
    "httpx2",
    "yaml",
    "jsonschema",
    "dotenv",
    "huggingface_hub",
    "pyarrow",
    "absl",
    "langdetect",
    "immutabledict",
    "emoji",
    "syllapy",
    "mpmath",
    "nltk",
)
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

# Données NLTK réelles de la machine (fetch-nltk), relevées avant que la fixture autouse ne
# redirige $QUALITY_BENCH_DATA vers tmp_path.
_REAL_DATA_ROOT = os.environ.get("QUALITY_BENCH_DATA") or str(
    Path(__file__).resolve().parents[2] / "data" / "quality_bench"
)
REAL_NLTK_DATA = Path(_REAL_DATA_ROOT) / "nltk_data"


@pytest.fixture(autouse=True)
def _isolated_data_root(tmp_path, monkeypatch):
    """Jamais d'écriture dans ``data/`` ni dans ``benchmarks/quality/`` réels : la racine des
    données et celle des exports versionnés pointent sur ``tmp_path``."""
    root = tmp_path / "quality_bench_data"
    monkeypatch.setenv("QUALITY_BENCH_DATA", str(root))
    monkeypatch.setenv("QUALITY_BENCH_EXPORTS", str(tmp_path / "quality_bench_exports"))
    monkeypatch.delenv("QUALITY_BENCH_MACHINE", raising=False)
    return root


@pytest.fixture(autouse=True)
def _skip_integration_unless_enabled(request):
    """Le marqueur ``integration`` (Ollama réel) est sauté sauf ``QUALITY_BENCH_INTEGRATION=1``."""
    if request.node.get_closest_marker("integration") and os.environ.get(INTEGRATION_ENV) != "1":
        pytest.skip(f"test d'intégration : définir {INTEGRATION_ENV}=1 pour le lancer")


@pytest.fixture
def bench_nltk_data(monkeypatch):
    """Les vérificateurs de consignes lisent les données NLTK réelles de la machine
    (``$QUALITY_BENCH_DATA/nltk_data``, en lecture seule) ; échec explicite si ``fetch-nltk``
    n'a pas tourné."""
    from scripts.quality_bench.common import paths
    from scripts.quality_bench.grading import nlp

    monkeypatch.setattr(paths, "nltk_data_dir", lambda: REAL_NLTK_DATA)
    missing = nlp.missing_resources()
    if missing:
        pytest.fail(
            f"Données NLTK absentes de {REAL_NLTK_DATA} : {missing}. Lancer "
            r"`.venv-quality\Scripts\python -m scripts.quality_bench fetch-nltk` avant les tests.",
            pytrace=False,
        )
    return REAL_NLTK_DATA
