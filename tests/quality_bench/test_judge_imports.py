"""Graphe d'import AST du juge (spine, sens des dépendances ; AD-15) : ``anthropic`` et
``openai`` importés dans ``judge/`` seulement ; ``judge/`` n'atteint que ``ollama/``,
``questions/`` (schéma) et ``common/`` ; ``generation/`` et ``grading/`` n'atteignent jamais
``judge/``."""

from __future__ import annotations

import pytest

from .test_vendored import PACKAGE, _graph, _imports, _module_path, _rel

CLOUD_LIBRARIES = ("anthropic", "openai")


def _package_files():
    return sorted(path for path in PACKAGE.rglob("*.py") if "__pycache__" not in path.parts)


def _matches(module: str, library: str) -> bool:
    return module == library or module.startswith(library + ".")


def test_cloud_sdks_are_imported_in_judge_only():
    importers = set()
    for path in _package_files():
        _, external = _imports(path)
        if any(_matches(module, lib) for module in external for lib in CLOUD_LIBRARIES):
            importers.add(_rel(path))
    assert importers == {"judge/haiku.py", "judge/mimo.py"}


def test_judge_graph_stays_inside_its_permissions():
    reached = {_rel(_module_path(name)) for name in _graph(["judge"])}
    assert {"judge/commands.py", "judge/haiku.py", "ollama/client.py", "common/jsonl.py"} <= reached
    for relative in reached:
        top = relative.split("/")[0]
        assert top in ("judge", "ollama", "questions", "common", "__init__.py"), relative
        if top == "questions":
            allowed = ("questions/__init__.py", "questions/schema.py", "questions/checks.py")
            assert relative in allowed, relative


@pytest.mark.parametrize("start", ["generation", "grading"])
def test_generation_and_grading_never_reach_judge(start):
    for name, external in _graph([start]).items():
        relative = _rel(_module_path(name))
        assert not relative.startswith("judge/"), f"{start} atteint {relative}"
        for module in external:
            for library in CLOUD_LIBRARIES:
                assert not _matches(module, library), f"{relative} importe {module}"
