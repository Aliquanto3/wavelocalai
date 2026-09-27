"""
Tests du socle : dépendances importables, serveur confiné à localhost, ouverture réseau documentée.
Usage: python -m pytest tests/app/test_socle.py -v
"""

import importlib

import pytest
import toml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from tests.app.conftest import ROOT_DIR


@pytest.mark.parametrize("module", ["ragas", "streamlit"])
def test_pinned_dependencies_import(module):
    """Les versions figées par constraints.txt s'importent (E1 : ragas cassé selon les versions)."""
    importlib.import_module(module)


def test_server_listens_on_localhost_only():
    """Le serveur n'écoute que sur la machine locale (F8, D5)."""
    config = toml.load(ROOT_DIR / ".streamlit" / "config.toml")

    assert config["server"]["address"] == "localhost"
    assert config["browser"]["gatherUsageStats"] is False


def test_network_opening_is_documented_as_explicit_choice():
    """L'ouverture au réseau est documentée comme un choix explicite (D5)."""
    readme = (ROOT_DIR / "README.md").read_text(encoding="utf-8")

    assert "--server.address 0.0.0.0" in readme


def _parse_requirement_lines(path):
    """Lignes de dépendance d'un fichier pip, sans commentaires ni lignes vides."""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            yield line


def test_constraints_cover_requirements():
    """constraints.txt fige chaque dépendance directe de requirements.txt, à une version
    qui satisfait le spécificateur déclaré."""
    pinned = {}
    for line in _parse_requirement_lines(ROOT_DIR / "constraints.txt"):
        spec = line.split(";", 1)[0].strip()
        if "==" not in spec:
            continue
        name, version = spec.split("==", 1)
        pinned.setdefault(canonicalize_name(name), []).append(version.strip())

    for line in _parse_requirement_lines(ROOT_DIR / "requirements.txt"):
        req = Requirement(line)
        name = canonicalize_name(req.name)

        assert name in pinned, f"{req.name} n'a pas de ligne nom==version dans constraints.txt"
        for version in pinned[name]:
            assert req.specifier.contains(
                version, prereleases=True
            ), f"{req.name}=={version} ne satisfait pas « {req.specifier} » (requirements.txt)"


def test_ci_runs_unit_and_app_tests_on_master():
    """La CI tourne sur chaque push et chaque PR vers master, et son étape de tests (sans
    continue-on-error) lance tests/unit et tests/app (E2)."""
    import yaml

    workflow = yaml.safe_load(
        (ROOT_DIR / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    )
    # YAML 1.1 : la clé « on » est lue comme le booléen True.
    triggers = workflow.get("on", workflow.get(True))
    assert "master" in triggers["push"]["branches"]
    assert "master" in triggers["pull_request"]["branches"]
    steps = workflow["jobs"]["test"]["steps"]
    runs = [s for s in steps if "pytest" in (s.get("run") or "")]
    assert runs, "aucune étape pytest dans le job test"
    assert all(not s.get("continue-on-error") for s in runs)
    assert any("tests/unit" in s["run"] and "tests/app" in s["run"] for s in runs)
