"""Graphes d'import AST de ``stats/`` et de ``report/`` (AD-17, spine : sens des dépendances).

- ``stats/`` n'importe que la bibliothèque standard, ``numpy``, ``scipy``, ``statsmodels`` et ses
  propres modules : aucun autre module du paquet.
- ``report/`` n'atteint ni ``generation/``, ni ``grading/``, ni ``judge/``, ni ``ollama/``, ni
  ``questions/importers/``, ni une bibliothèque réseau ; de ``questions/``, ``schema.py`` seul.
"""

from __future__ import annotations

import ast
import sys

import pytest

from .test_vendored import PACKAGE, _graph, _module_path, _rel

STATS_LIBRARIES = {"numpy", "scipy", "statsmodels"}
REPORT_FORBIDDEN_DIRS = ("generation", "grading", "judge", "ollama", "questions/importers", "envs")
NETWORK_LIBRARIES = (
    "anthropic",
    "openai",
    "huggingface_hub",
    "datasets",
    "urllib.request",
    "http.client",
    "httpx",
    "httpx2",
    "requests",
    "aiohttp",
)
# questions/checks.py : forme pure des critères vérifiés par le code, importée par schema.py.
ALLOWED_QUESTIONS = {"questions/__init__.py", "questions/schema.py", "questions/checks.py"}


def _stats_files():
    return sorted(p for p in (PACKAGE / "stats").rglob("*.py") if "__pycache__" not in p.parts)


@pytest.mark.parametrize("path", _stats_files(), ids=lambda p: _rel(p))
def test_stats_imports_only_stdlib_and_numeric_libraries(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # « from . import x » ou « from .x import y » : dans stats/ seulement.
                assert node.level == 1, f"{_rel(path)} remonte hors de stats/"
                continue
            modules = [node.module or ""]
        else:
            continue
        for module in modules:
            root = module.split(".")[0]
            assert (
                root in sys.stdlib_module_names or root in STATS_LIBRARIES
            ), f"{_rel(path)} importe {module}"


def test_stats_graph_stays_inside_stats():
    graph = _graph(["stats"])
    reached = {_rel(_module_path(name)) for name in graph}
    assert "stats/mcnemar.py" in reached
    assert all(relative.startswith("stats/") for relative in reached), reached


def _report_graph():
    return {
        name: (_rel(_module_path(name)), external) for name, external in _graph(["report"]).items()
    }


def test_report_graph_reaches_stats_and_common():
    reached = {relative for relative, _ in _report_graph().values()}
    assert {
        "report/commands.py",
        "report/inputs.py",
        "report/calibration.py",
        "report/calibration_measures.py",
        "report/calibration_markdown.py",
        "stats/spearman.py",
        "stats/wilson.py",
        "common/selection.py",
        "questions/schema.py",
    } <= reached


def test_report_graph_stays_out_of_forbidden_directories():
    for relative, _ in _report_graph().values():
        for directory in REPORT_FORBIDDEN_DIRS:
            assert not relative.startswith(directory + "/"), f"report atteint {relative}"
        if relative.startswith("questions/"):
            assert relative in ALLOWED_QUESTIONS, f"report atteint {relative}"


def test_report_graph_imports_no_network_library():
    for relative, external in _report_graph().values():
        for module in external:
            for library in NETWORK_LIBRARIES:
                assert module != library and not module.startswith(
                    library + "."
                ), f"{relative} importe {module}"
