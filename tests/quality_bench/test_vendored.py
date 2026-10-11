"""Code emprunté (convention « Code emprunté » du spine, AD-10, AD-11, AD-15) : licences et
provenance, registre M-IFEval réduit au français, ni téléchargement, ni ``eval``/``exec``, ni
spaCy, ni ``MODEL_CONFIG_MAPPING`` ; graphe d'import de ``grading/`` et ``envs/`` hors des
modules et bibliothèques interdits."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "scripts" / "quality_bench"
PACKAGE_NAME = "scripts.quality_bench"
VENDORED_DIRS = (
    "grading/vendored/ifbench",
    "grading/vendored/mifeval_fr",
    "grading/vendored/bfcl",
    "grading/vendored/bbeh",
    "grading/vendored/oneruler",
    "envs/vendored/bfcl",
)
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
FORBIDDEN_PACKAGE_DIRS = ("judge", "questions/importers", "ollama", "generation")
FORBIDDEN_LIBRARIES = (
    "anthropic",
    "openai",
    "huggingface_hub",
    "datasets",
    "urllib.request",
    "httpx2",
    "httpx",
    "requests",
    "spacy",
)


def _vendored_files():
    return sorted(
        path
        for directory in VENDORED_DIRS
        for path in (PACKAGE / directory).rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _rel(path: Path) -> str:
    return path.relative_to(PACKAGE).as_posix()


@pytest.mark.parametrize("directory", VENDORED_DIRS)
def test_license_and_provenance_present(directory):
    folder = PACKAGE / directory
    assert (folder / "LICENSE").is_file()
    provenance = (folder / "PROVENANCE.md").read_text(encoding="utf-8")
    assert re.search(r"\*\*Commit :\*\* `[0-9a-f]{40}`", provenance)
    assert re.search(r"`[0-9a-f]{64}`", provenance)  # empreintes sha256 amont
    for heading in ("## Fichiers copiés", "## Modifications", "## Téléchargements retirés"):
        assert heading in provenance
    for path in folder.rglob("*.py"):
        if path.name != "__init__.py" and "__pycache__" not in path.parts:
            assert f"`{path.relative_to(folder).as_posix()}`" in provenance, path.name


def test_mifeval_registry_exposes_french_only():
    from scripts.quality_bench.grading.vendored.mifeval_fr.instructions_registry import (
        INSTRUCTION_DICT,
    )

    assert INSTRUCTION_DICT
    assert all(instruction_id.startswith("fr:") for instruction_id in INSTRUCTION_DICT)
    names = {path.name for path in (PACKAGE / "grading/vendored/mifeval_fr").rglob("*.py")}
    assert not names & {
        "en_instructions.py",
        "es_instructions.py",
        "ja_instructions.py",
        "en_instructions_util.py",
        "es_instructions_util.py",
        "ja_instructions_util.py",
    }


@pytest.mark.parametrize("path", _vendored_files(), ids=_rel)
def test_vendored_code_has_no_download_eval_spacy_or_model_config(path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "nltk.download" not in source
    assert "MODEL_CONFIG_MAPPING" not in source
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in FORBIDDEN_CALLS, f"{_rel(path)}:{node.lineno}"
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("download", "MODEL_CONFIG_MAPPING"), f"{_rel(path)}"
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0] == "spacy" for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "spacy"
            assert node.level > 0 or not (node.module or "").startswith(
                ("bfcl_eval", "ifbench", "instructions", "instruction_utils")
            ), f"{_rel(path)} : import amont non rendu relatif"


@pytest.mark.parametrize(
    "path",
    sorted((PACKAGE / "envs/vendored/bfcl").glob("*.py")),
    ids=_rel,
)
def test_environment_classes_have_no_clock_subprocess_or_global_random(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("now", "today", "utcnow", "time_ns"), _rel(path)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "fromtimestamp":
                assert any(keyword.arg == "tz" for keyword in node.keywords), _rel(path)
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id == "random":
                assert node.func.attr == "Random", f"{_rel(path)}:{node.lineno}"
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
            assert not any(name.split(".")[0] in ("subprocess", "os", "socket") for name in names)


# --- Graphe d'import de grading/ et envs/ --------------------------------------------------


def _module_path(dotted: str) -> Path | None:
    if not dotted.startswith(PACKAGE_NAME):
        return None
    parts = dotted.split(".")[2:]
    base = PACKAGE.joinpath(*parts)
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    if (base / "__init__.py").is_file():
        return base / "__init__.py"
    return None


def _dotted(path: Path) -> str:
    parts = list(path.relative_to(PACKAGE).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([PACKAGE_NAME, *parts])


def _imports(path: Path):
    """(modules du paquet atteints, imports absolus externes) d'un fichier."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = _dotted(path) if path.name == "__init__.py" else _dotted(path).rsplit(".", 1)[0]
    internal, external = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(PACKAGE_NAME):
                    internal.add(alias.name)
                else:
                    external.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".")
                base_parts = base_parts[: len(base_parts) - (node.level - 1)]
                base = ".".join(base_parts + ([node.module] if node.module else []))
            elif (node.module or "").startswith(PACKAGE_NAME):
                base = node.module
            else:
                external.add(node.module or "")
                external.update(f"{node.module}.{alias.name}" for alias in node.names)
                continue
            internal.add(base)
            internal.update(f"{base}.{alias.name}" for alias in node.names)
    modules = {name for name in internal if _module_path(name) is not None}
    # Les paquets parents s'exécutent aussi à l'import.
    for name in list(modules):
        parts = name.split(".")
        for index in range(3, len(parts)):
            if _module_path(".".join(parts[:index])) is not None:
                modules.add(".".join(parts[:index]))
    return modules, external


def _graph(start_dirs):
    todo = [
        _dotted(path)
        for directory in start_dirs
        for path in (PACKAGE / directory).rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    seen: dict[str, set[str]] = {}
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        internal, external = _imports(_module_path(name))
        seen[name] = external
        todo.extend(internal - set(seen))
    return seen


@pytest.mark.parametrize("start", ["grading", "envs"])
def test_import_graph_stays_out_of_forbidden_modules_and_libraries(start):
    graph = _graph([start])
    assert any(name.endswith(".vendored.bfcl.gorilla_file_system") for name in graph)
    for name, external in graph.items():
        relative = _rel(_module_path(name))
        for directory in FORBIDDEN_PACKAGE_DIRS:
            assert not relative.startswith(directory + "/"), f"{start} atteint {relative}"
        for module in external:
            for library in FORBIDDEN_LIBRARIES:
                assert module != library and not module.startswith(
                    library + "."
                ), f"{relative} importe {module}"
    if start == "envs":
        assert not any(_rel(_module_path(name)).startswith("grading/") for name in graph)


@pytest.mark.parametrize("start", ["grading", "envs"])
def test_import_graph_never_calls_nltk_download(start):
    for name in _graph([start]):
        source = _module_path(name).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Attribute) and node.attr == "download":
                owner = node.value
                assert not (isinstance(owner, ast.Name) and owner.id == "nltk"), name
