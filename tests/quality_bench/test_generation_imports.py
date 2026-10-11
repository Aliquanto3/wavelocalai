"""Graphe d'import AST de ``generation/`` (spine, sens des dépendances ; AD-15) : ni
``grading/``, ``judge/``, ``stats/``, ``report/`` ni ``questions/importers/``, aucune
bibliothèque réseau, ni ``nltk`` ni spaCy, jamais ``nltk.download`` ; ``httpx2`` seulement par
``ollama/client.py`` ; de ``questions/``, ``schema.py`` seul."""

from __future__ import annotations

import ast

from .test_vendored import _graph, _module_path, _rel

FORBIDDEN_DIRS = ("grading", "judge", "stats", "report", "questions/importers")
FORBIDDEN_LIBRARIES = (
    "anthropic",
    "openai",
    "huggingface_hub",
    "datasets",
    "urllib.request",
    "httpx",
    "requests",
    "nltk",
    "spacy",
)
ALLOWED_QUESTIONS = {"questions/__init__.py", "questions/schema.py"}


def _generation_graph():
    return {
        name: (_rel(_module_path(name)), external)
        for name, external in _graph(["generation"]).items()
    }


def test_graph_reaches_expected_modules():
    reached = {relative for relative, _ in _generation_graph().values()}
    assert {
        "generation/runner.py",
        "generation/commands.py",
        "ollama/client.py",
        "envs/registry.py",
        "questions/schema.py",
    } <= reached


def test_graph_stays_out_of_forbidden_directories():
    for relative, _ in _generation_graph().values():
        for directory in FORBIDDEN_DIRS:
            assert not relative.startswith(directory + "/"), f"generation atteint {relative}"
        if relative.startswith("questions/"):
            assert relative in ALLOWED_QUESTIONS, f"generation atteint {relative}"


def test_graph_imports_no_network_or_nlp_library():
    for relative, external in _generation_graph().values():
        for module in external:
            for library in FORBIDDEN_LIBRARIES:
                assert module != library and not module.startswith(
                    library + "."
                ), f"{relative} importe {module}"
            if module == "httpx2" or module.startswith("httpx2."):
                assert relative == "ollama/client.py", f"{relative} importe {module}"


def test_graph_never_calls_nltk_download():
    for name in _graph(["generation"]):
        tree = ast.parse(_module_path(name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "download":
                owner = node.value
                assert not (isinstance(owner, ast.Name) and owner.id == "nltk"), name
