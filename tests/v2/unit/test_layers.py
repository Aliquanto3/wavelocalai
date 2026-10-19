"""Test AST du sens des dépendances de la v2 (AD-4, AD-2, AD-21).

Le contrôleur `check_package` lit le code source sans l'importer. Il est paramétré par la racine
du paquet pour que ses propres tests lui soumettent des arbres pièges, écrits dans un dossier
temporaire : aucune violation ne reste dans `src/wavelocalai/`.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

PACKAGE = "wavelocalai"
REAL_ROOT = Path(__file__).resolve().parents[3] / "src" / PACKAGE

# Modules de base : ils n'importent rien du paquet, tous peuvent les importer.
BASE = {"config", "errors", "telemetry"}

# Une flèche du diagramme d'AD-4 = « peut importer » (arêtes directes, pas transitives).
SERVICES = {"inference", "rag", "agents", "evaluation"}
ALLOWED: dict[str, set[str]] = {
    "web": SERVICES | {"runs", "models", "greenops", "hardware", "store"},
    "inference": {"runs", "models", "greenops", "hardware"},
    "rag": {"inference", "runs", "models", "greenops", "hardware", "store"},
    "agents": {"inference", "runs", "models", "greenops", "hardware"},
    "evaluation": {"inference", "runs", "models", "greenops", "hardware"},
    "greenops": {"runs", "store"},
    "runs": {"store"},
    "models": {"store"},
    "hardware": set(),
    "store": set(),
}
COMPONENTS = set(ALLOWED) | BASE

WEB_ONLY = {"fastapi", "starlette", "uvicorn"}
LAZY_ONLY = {
    "codecarbon",
    "fastembed",
    "pypdf",
    "docx",
    "ecologits",
    "openai",
    "anthropic",
    "mistralai",
    # Outils des agents (story 6.2) : importés dans les fonctions seulement.
    "pandas",
    "matplotlib",
    "numexpr",
    "func_timeout",
    "psutil",
    # Envoi d'email des agents (story 6.3) : `agents/outbox.py`, dans les fonctions seulement.
    "smtplib",
    "email",
}


def _module_parts(root: Path, path: Path) -> list[str]:
    parts = [PACKAGE, *path.relative_to(root).with_suffix("").parts]
    return parts[:-1] if parts[-1] == "__init__" else parts


def _package_parts(root: Path, path: Path) -> list[str]:
    parts = _module_parts(root, path)
    return parts if path.name == "__init__.py" else parts[:-1]


def _is_type_checking(node: ast.If) -> bool:
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _walk_imports(tree: ast.AST):
    """Produit (noeud, au_niveau_du_module) pour les imports, les appels et les accès d'attribut.

    Ignore le code sous TYPE_CHECKING. Les `Call` et `Attribute` servent aux imports qui ne passent
    pas par une instruction `import` (C1 : `importlib.import_module`, `__import__`, et
    `import wavelocalai` suivi d'un accès d'attribut).
    """

    def visit(node: ast.AST, module_level: bool):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.If) and _is_type_checking(child):
                for orelse in child.orelse:
                    yield from visit_one(orelse, module_level)
                continue
            yield from visit_one(child, module_level)

    def visit_one(node: ast.AST, module_level: bool):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Call, ast.Attribute)):
            yield node, module_level
        inner = module_level and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        yield from visit(node, inner)

    yield from visit(tree, True)


def _imported(node: ast.Import | ast.ImportFrom, package: list[str]) -> list[list[str]]:
    """Noms de modules visés par un import, en parties absolues (imports `from` inclus)."""
    if isinstance(node, ast.Import):
        return [alias.name.split(".") for alias in node.names]
    if node.level:
        base = package[: len(package) - (node.level - 1)]
        base = [*base, *(node.module.split(".") if node.module else [])]
    else:
        base = node.module.split(".") if node.module else []
    if base == [PACKAGE]:
        # `from wavelocalai import runs` : la cible est dans les noms importés.
        return [[PACKAGE, alias.name] for alias in node.names]
    return [base]


def _package_aliases(tree: ast.AST) -> set[str]:
    """Noms qui désignent le paquet racine (`import wavelocalai [as x]`, `import wavelocalai.y`)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            parts = alias.name.split(".")
            if parts[0] != PACKAGE:
                continue
            if alias.asname is None:
                names.add(PACKAGE)
            elif len(parts) == 1:
                names.add(alias.asname)
    return names


def _is_dynamic_import(call: ast.Call) -> bool:
    """Vrai pour `importlib.import_module(...)`, `import_module(...)` et `__import__(...)`."""
    func = call.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    return name in {"import_module", "__import__"}


def _dynamic_target(call: ast.Call, package: list[str]) -> list[str]:
    """Parties du module chargé par un appel dynamique ; `[]` si le nom n'est pas un littéral."""
    first = call.args[0] if call.args else None
    if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
        return []
    name = first.value
    dots = len(name) - len(name.lstrip("."))
    if dots:  # relatif : au `package=` donné s'il est littéral, sinon au paquet du fichier
        given = call.args[1] if len(call.args) > 1 else None
        for keyword in call.keywords:
            if keyword.arg == "package":
                given = keyword.value
        if isinstance(given, ast.Constant) and isinstance(given.value, str):
            package = given.value.split(".")
        base = package[: len(package) - (dots - 1)]
        return [*base, *[part for part in name.lstrip(".").split(".") if part]]
    return name.split(".")


def _getattr_target(call: ast.Call, aliases: set[str]) -> str | None:
    """`getattr(wavelocalai, "runs")` : rend « runs » ; sinon None."""
    if not (isinstance(call.func, ast.Name) and call.func.id == "getattr" and len(call.args) >= 2):
        return None
    obj, attr = call.args[0], call.args[1]
    is_alias = isinstance(obj, ast.Name) and obj.id in aliases
    if is_alias and isinstance(attr, ast.Constant) and isinstance(attr.value, str):
        return attr.value
    return None


def check_package(root: Path) -> list[str]:
    """Liste les violations d'AD-4 / AD-2 / AD-21 dans l'arbre `root` (paquet `wavelocalai`)."""
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        component = path.relative_to(root).parts[0].removesuffix(".py")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        package = _package_parts(root, path)
        aliases = _package_aliases(tree)
        for node, module_level in _walk_imports(tree):
            where = f"{rel}:{node.lineno}"
            if isinstance(node, ast.Attribute):
                # `import wavelocalai` puis `wavelocalai.runs...` : la cible est l'attribut.
                if isinstance(node.value, ast.Name) and node.value.id in aliases:
                    violations.extend(_layer_violation(where, component, node.attr))
                continue
            if isinstance(node, ast.Call):
                target = _getattr_target(node, aliases)
                if target is not None:
                    violations.extend(_layer_violation(where, component, target))
                if not _is_dynamic_import(node):
                    continue
                dynamic = _dynamic_target(node, package)
                if not dynamic:
                    violations.append(
                        f"{where} : import dynamique dont le nom n'est pas un littéral "
                        "(non vérifiable)"
                    )
                    continue
                targets = [dynamic]
            else:
                targets = _imported(node, package)
            for parts in targets:
                top = parts[0] if parts else ""
                if top == "src":
                    violations.append(f"{where} importe src.* (la v2 n'importe jamais la v1)")
                if top in WEB_ONLY and component != "web":
                    violations.append(f"{where} importe {top} hors de web/")
                if top in LAZY_ONLY and module_level:
                    violations.append(
                        f"{where} importe {top} au niveau du module (import paresseux)"
                    )
                if top == PACKAGE and len(parts) > 1:
                    violations.extend(_layer_violation(where, component, parts[1]))
    return violations


def _layer_violation(where: str, component: str, target: str) -> list[str]:
    if component == "__main__":  # le lanceur assemble l'application
        return []
    if component == "__init__":
        return [f"{where} : l'__init__ racine importe {target}"]
    if target == component or target not in COMPONENTS:
        return []
    if component not in COMPONENTS:
        return [f"{where} : {component} est hors du Structural Seed et importe {target}"]
    if component in BASE:
        return [f"{where} : le module de base {component} importe {target}"]
    if target in BASE:
        return []
    if target == "web":
        return [f"{where} : {component} importe web/ (aucun paquet n'importe web/)"]
    if target not in ALLOWED[component]:
        return [f"{where} : {component} importe {target}, contre le diagramme d'AD-4"]
    return []


# --- Le paquet réel respecte les règles -------------------------------------------------------


def test_real_package_has_no_violation():
    assert check_package(REAL_ROOT) == []


def test_real_package_matches_structural_seed():
    dirs = {
        p.name for p in REAL_ROOT.iterdir() if p.is_dir() and not p.name.startswith((".", "__"))
    }
    assert dirs == set(ALLOWED)
    for name in dirs:
        assert (REAL_ROOT / name / "__init__.py").exists()
    for name in BASE:
        assert (REAL_ROOT / f"{name}.py").exists()
    assert (REAL_ROOT / "__main__.py").exists()


# --- Le contrôleur détecte bien les violations (modules pièges en dossier temporaire) ----------


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / PACKAGE
    for rel, code in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(code), encoding="utf-8")
    return root


@pytest.mark.parametrize(
    ("rel", "code", "expected"),
    [
        ("runs/trap.py", "from wavelocalai.web import app\n", "importe web/"),
        ("runs/trap.py", "from wavelocalai.rag import index\n", "contre le diagramme"),
        ("store/trap.py", "import wavelocalai.runs.hub\n", "contre le diagramme"),
        ("store/trap.py", "from .. import runs\n", "contre le diagramme"),
        ("models/trap.py", "from ..runs import hub\n", "contre le diagramme"),
        ("hardware/trap.py", "from wavelocalai.store import db\n", "contre le diagramme"),
        ("inference/trap.py", "from wavelocalai.agents import loop\n", "contre le diagramme"),
        ("greenops/trap.py", "from wavelocalai.models import port\n", "contre le diagramme"),
        ("config.py", "from wavelocalai import errors\n", "module de base"),
        ("errors.py", "from wavelocalai.store import db\n", "module de base"),
        ("__init__.py", "from wavelocalai import runs\n", "__init__ racine"),
        ("runs/trap.py", "from src.core import config\n", "src.*"),
        ("runs/trap.py", "def f():\n    import src.core\n", "src.*"),
        ("runs/trap.py", "import fastapi\n", "hors de web/"),
        ("rag/trap.py", "def f():\n    from starlette.requests import Request\n", "hors de web/"),
        ("store/trap.py", "import uvicorn\n", "hors de web/"),
        ("web/trap.py", "import codecarbon\n", "niveau du module"),
        ("rag/trap.py", "from pypdf import PdfReader\n", "niveau du module"),
        ("rag/trap.py", "import docx\n", "niveau du module"),
        (
            "rag/trap.py",
            "try:\n    import fastembed\nexcept ImportError:\n    fastembed = None\n",
            "niveau du module",
        ),
        ("models/trap.py", "from openai import OpenAI\n", "niveau du module"),
        ("models/trap.py", "import anthropic\n", "niveau du module"),
        ("models/trap.py", "import mistralai\n", "niveau du module"),
        ("greenops/trap.py", "from ecologits import tracers\n", "niveau du module"),
        ("cli.py", "from wavelocalai.runs import hub\n", "hors du Structural Seed"),
        # C1 : imports qui ne passent pas par `from ... import`.
        ("store/trap.py", "import wavelocalai\nx = wavelocalai.runs.hub\n", "contre le diagramme"),
        ("store/trap.py", "import wavelocalai as wl\ny = wl.runs\n", "contre le diagramme"),
        (
            "runs/trap.py",
            "import wavelocalai\ndef f():\n    return wavelocalai.web.app\n",
            "importe web/",
        ),
        (
            "store/trap.py",
            "import wavelocalai\nz = getattr(wavelocalai, 'runs')\n",
            "contre le diagramme",
        ),
        (
            "store/trap.py",
            "import importlib\nm = importlib.import_module('wavelocalai.runs.hub')\n",
            "contre le diagramme",
        ),
        (
            "store/trap.py",
            "from importlib import import_module\nm = import_module('wavelocalai.runs')\n",
            "contre le diagramme",
        ),
        (
            "store/trap.py",
            "import importlib\nm = importlib.import_module('.runs', package='wavelocalai')\n",
            "contre le diagramme",
        ),
        ("store/trap.py", "m = __import__('wavelocalai.runs')\n", "contre le diagramme"),
        ("runs/trap.py", "m = __import__('wavelocalai.web')\n", "importe web/"),
        (
            "rag/trap.py",
            "import importlib\nm = importlib.import_module('fastapi')\n",
            "hors de web/",
        ),
        (
            "rag/trap.py",
            "import importlib\nm = importlib.import_module('pypdf')\n",
            "niveau du module",
        ),
        (
            "runs/trap.py",
            "import importlib\ndef f(name):\n    return importlib.import_module(name)\n",
            "non vérifiable",
        ),
    ],
)
def test_trap_module_is_detected(tmp_path, rel, code, expected):
    root = _tree(tmp_path, {rel: code})
    found = check_package(root)
    assert found, f"violation non détectée pour {rel}"
    assert any(expected in line for line in found), found


@pytest.mark.parametrize(
    ("rel", "code"),
    [
        ("web/ok.py", "import fastapi\nfrom wavelocalai.rag import index\nimport uvicorn\n"),
        ("rag/ok.py", "from wavelocalai.inference import chat\nfrom wavelocalai.store import db\n"),
        ("agents/ok.py", "from ..inference import chat\nfrom ..config import Settings\n"),
        ("runs/ok.py", "from wavelocalai.store import db\nfrom .hub import Hub\n"),
        ("store/ok.py", "from wavelocalai import config, errors\n"),
        ("rag/ok.py", "def f():\n    import pypdf\n    from docx import Document\n"),
        ("models/ok.py", "def f():\n    from openai import OpenAI\n    import anthropic\n"),
        ("greenops/ok.py", "async def f():\n    import codecarbon\n    import ecologits\n"),
        (
            "rag/ok.py",
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import pypdf\n",
        ),
        ("__main__.py", "from wavelocalai.web import app\nfrom wavelocalai import config\n"),
        ("store/ok.py", "import wavelocalai\nv = wavelocalai.config\n"),
        ("rag/ok.py", "import importlib\nm = importlib.import_module('wavelocalai.inference')\n"),
        (
            "rag/ok.py",
            "def f():\n    import importlib\n    return importlib.import_module('pypdf')\n",
        ),
        ("runs/ok.py", "import importlib.util\nspec = importlib.util.find_spec('fastembed')\n"),
    ],
)
def test_legitimate_imports_are_accepted(tmp_path, rel, code):
    assert check_package(_tree(tmp_path, {rel: code})) == []
