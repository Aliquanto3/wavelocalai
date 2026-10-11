"""Paquet : CLI, isolement des imports (AD-1, AD-9) et propriétaires uniques."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "scripts" / "quality_bench"
VENDORED = (PACKAGE / "grading" / "vendored", PACKAGE / "envs" / "vendored")


def _package_modules():
    return sorted(
        path
        for path in PACKAGE.rglob("*.py")
        if "__pycache__" not in path.parts
        and not any(vendored in path.parents for vendored in VENDORED)
    )


def _absolute_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module
            # « from urllib import request » : aussi « urllib.request ».
            for alias in node.names:
                yield f"{node.module}.{alias.name}"


def _rel(path: Path) -> str:
    return path.relative_to(PACKAGE).as_posix()


def test_package_has_modules():
    names = {_rel(path) for path in _package_modules()}
    assert {"__init__.py", "__main__.py", "common/jsonl.py", "ollama/client.py"} <= names


@pytest.mark.parametrize("path", _package_modules(), ids=_rel)
def test_forbidden_imports(path):
    """Ni ``scripts.benchmark_slm``, ni ``src.*`` hors ``src.core.telemetry``, ni la
    bibliothèque ``ollama``, ni ``httpx`` (seulement ``httpx2``)."""
    for module in _absolute_imports(path):
        root = module.split(".")[0]
        assert root not in ("ollama", "httpx"), f"{_rel(path)} importe {module}"
        assert not module.startswith("scripts.benchmark_slm"), f"{_rel(path)} importe {module}"
        assert module != "benchmark_slm", f"{_rel(path)} importe {module}"
        if root == "src":
            allowed = module == "src.core.telemetry" or module.startswith("src.core.telemetry.")
            assert allowed, f"{_rel(path)} importe {module}"


@pytest.mark.parametrize(
    "library, owners",
    [
        ("httpx2", {"ollama/client.py"}),
        ("yaml", {"common/config.py"}),
        ("jsonschema", {"common/schemas.py"}),
        # disable_telemetry() : en tête de la CLI, et dans chaque module qui importe une
        # bibliothèque à télémétrie (AD-15 ; tests/unit/test_telemetry.py).
        ("src", {"__main__.py", "questions/importers/remote.py"}),
        # Réseau des importeurs (AD-15) : un seul module télécharge les jeux publics.
        ("huggingface_hub", {"questions/importers/remote.py"}),
        ("datasets", {"questions/importers/remote.py"}),
        ("urllib.request", {"questions/importers/remote.py"}),
        ("nltk", {"questions/importers/nltk_data.py", "grading/nlp.py"}),
        ("langdetect", {"grading/registry.py"}),
        ("mpmath", set()),  # code emprunté seulement (envs/vendored/bfcl/math_api.py)
        ("pyarrow", {"questions/importers/jsonschemabench.py"}),
    ],
)
def test_single_owner_of_each_library(library, owners):
    importers = {
        _rel(path)
        for path in _package_modules()
        if any(
            module == library or module.startswith(library + ".")
            for module in _absolute_imports(path)
        )
    }
    assert importers <= owners, f"{library} importé hors de {owners} : {importers - owners}"


def test_json_dumps_only_in_canonical():
    """Seul ``common/canonical.py`` sérialise du JSON (AD-4)."""
    offenders = []
    for path in _package_modules():
        if _rel(path) == "common/canonical.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("dumps", "dump")
                and getattr(node.func.value, "id", None) == "json"
            ):
                offenders.append(f"{_rel(path)}:{node.lineno}")
    assert not offenders


def test_text_open_calls_pass_utf8_encoding():
    """Tout ``open()``, ``.open()``, ``.read_text()`` ou ``.write_text()`` texte passe
    ``encoding="utf-8"`` (convention « Encodage ») ; le mode binaire et ``os.open`` (descripteur
    brut) sont exceptés."""
    offenders = []
    for path in _package_modules():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                mode_index = 1  # open(fichier, mode)
            elif isinstance(func, ast.Attribute) and func.attr == "open":
                if getattr(func.value, "id", None) == "os":
                    continue
                mode_index = 0  # Path.open(mode)
            elif isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text"):
                mode_index = None
            else:
                continue
            mode = None
            if mode_index is not None and len(node.args) > mode_index:
                mode = node.args[mode_index]
            mode = next((kw.value for kw in node.keywords if kw.arg == "mode"), mode)
            if isinstance(mode, ast.Constant) and "b" in str(mode.value):
                continue
            encoding = next((kw.value for kw in node.keywords if kw.arg == "encoding"), None)
            if not (isinstance(encoding, ast.Constant) and encoding.value == "utf-8"):
                offenders.append(f"{_rel(path)}:{node.lineno}")
    assert not offenders


def test_main_calls_disable_telemetry_before_package_imports():
    tree = ast.parse((PACKAGE / "__main__.py").read_text(encoding="utf-8"))
    call_line = next(
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", None) == "disable_telemetry"
    )
    package_imports = [
        node.lineno
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and (node.level > 0 or (node.module or "").startswith("scripts"))
    ]
    assert all(line > call_line for line in package_imports)


def test_cli_help_exits_zero():
    env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "scripts.quality_bench", "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")[-2000:]
    assert "qualité" in result.stdout.decode("utf-8")


def test_cli_without_command_prints_help_and_fails():
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "scripts.quality_bench"],
        cwd=ROOT,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 2
    assert b"usage" in result.stdout


def test_scripts_has_no_init():
    """``scripts/`` reste un paquet namespace (Code Map de la story 1)."""
    assert not (ROOT / "scripts" / "__init__.py").exists()
    assert (PACKAGE / "__init__.py").exists()


NETWORK_FREE = (
    "questions/build.py",
    "questions/pinned.py",
    "questions/house.py",
    "questions/set_builder.py",
    "questions/review.py",
    "questions/generators/__init__.py",
    "questions/generators/oneruler_fr.py",
    "questions/generators/var_math.py",
)


def _relative_imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            yield node.module or ""


@pytest.mark.parametrize("name", NETWORK_FREE)
def test_story3_modules_never_reach_importers(name):
    """Générateurs, questions maison et construction du jeu : aucun import des importeurs
    (qui chargent ``huggingface_hub``), ni d'une bibliothèque réseau (AD-15)."""
    path = PACKAGE / name
    for module in _relative_imports(path):
        assert "importers" not in module.split("."), f"{name} importe {module}"
    for module in _absolute_imports(path):
        root = module.split(".")[0]
        assert root not in ("huggingface_hub", "datasets", "urllib", "httpx2", "stanza")


def test_var_math_never_calls_eval_or_exec():
    tree = ast.parse((PACKAGE / "questions/generators/var_math.py").read_text(encoding="utf-8"))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls & {"eval", "exec", "compile", "__import__"}
