"""Télémétries coupées (`wavelocalai/telemetry.py`) et ordre des appels (AST, AD-19, AD-21)."""

from __future__ import annotations

import ast
import os
import textwrap
from pathlib import Path

import pytest

from wavelocalai.telemetry import TELEMETRY_OPT_OUTS, disable_telemetry
from wavelocalai.web.app import FASTAPI_TELEMETRY, create_app

from ..conftest import make_settings

SRC = Path(__file__).resolve().parents[3] / "src" / "wavelocalai"
TELEMETRY_LIBS = {"fastembed", "huggingface_hub"}


def test_fastapi_auto_configure_is_an_opt_out():
    assert TELEMETRY_OPT_OUTS["FASTAPI_OTEL_AUTO_CONFIGURE"] == "false"


def test_disable_telemetry_sets_missing_and_keeps_existing(monkeypatch, tmp_path):
    for name in TELEMETRY_OPT_OUTS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "0")  # choix explicite conservé
    dotenv = tmp_path / ".env"
    dotenv.write_text("DO_NOT_TRACK=0\n", encoding="utf-8")  # réactivation par le .env

    disable_telemetry(dotenv)

    assert os.environ["FASTAPI_OTEL_AUTO_CONFIGURE"] == "false"
    assert os.environ["OTEL_SDK_DISABLED"] == "true"
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "0"
    assert os.environ["DO_NOT_TRACK"] == "0"
    for name in TELEMETRY_OPT_OUTS:  # nettoyage : load_dotenv écrit dans os.environ
        monkeypatch.delenv(name, raising=False)


def test_app_is_created_with_native_telemetry_off_and_opt_outs_applied(monkeypatch, tmp_path):
    for name in TELEMETRY_OPT_OUTS:
        monkeypatch.delenv(name, raising=False)
    app = create_app(make_settings(tmp_path))
    assert FASTAPI_TELEMETRY == {
        "tracing": False,
        "metrics": False,
        "logs": False,
        "operation_spans": False,
        "auto_configure": False,
    }
    for key, value in FASTAPI_TELEMETRY.items():
        assert app._telemetry[key] is value  # noqa: SLF001
    assert os.environ["FASTAPI_OTEL_AUTO_CONFIGURE"] == "false"
    for name in TELEMETRY_OPT_OUTS:
        monkeypatch.delenv(name, raising=False)


# --- Ordre des appels (AST) -------------------------------------------------------------------


def _scope_bodies(tree: ast.Module):
    yield tree
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _own_nodes(scope: ast.AST):
    """Noeuds d'une portée, sans descendre dans les fonctions imbriquées."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stack.extend(ast.iter_child_nodes(node))


def _calls(scope: ast.AST, name: str) -> list[int]:
    lines = []
    for node in _own_nodes(scope):
        if isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if called == name:
                lines.append(node.lineno)
    return lines


def _imports_of(scope: ast.AST, libs: set[str]) -> list[int]:
    lines = []
    for node in _own_nodes(scope):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        if libs & set(names):
            lines.append(node.lineno)
    return lines


def check_telemetry_order(root: Path) -> list[str]:
    """Chaque import de fastembed/huggingface_hub est précédé d'un `disable_telemetry()` dans
    la même fonction (ou le même module) ; `create_app` l'appelle avant `FastAPI(...)`."""
    problems: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel == "telemetry.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for scope in _scope_bodies(tree):
            calls = _calls(scope, "disable_telemetry")
            for line in _imports_of(scope, TELEMETRY_LIBS):
                if not any(call < line for call in calls):
                    problems.append(
                        f"{rel}:{line} importe une bibliothèque à télémétrie sans "
                        "disable_telemetry() avant"
                    )
            if isinstance(scope, ast.FunctionDef) and scope.name == "create_app":
                builds = _calls(scope, "FastAPI")
                if not calls or not builds or min(calls) > min(builds):
                    problems.append(
                        f"{rel}: create_app doit appeler disable_telemetry() avant FastAPI()"
                    )
    return problems


def test_real_package_applies_telemetry_opt_outs_in_order():
    assert check_telemetry_order(SRC) == []
    assert "def create_app" in (SRC / "web" / "app.py").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "code",
    [
        "import fastembed\n",
        "def f():\n    from fastembed import TextEmbedding\n",
        "def f():\n    import huggingface_hub\n    disable_telemetry()\n",  # appel trop tard
        "def f():\n    from huggingface_hub import snapshot_download\n",
    ],
)
def test_import_without_prior_call_is_detected(tmp_path, code):
    (tmp_path / "rag").mkdir()
    (tmp_path / "rag" / "trap.py").write_text(textwrap.dedent(code), encoding="utf-8")
    assert check_telemetry_order(tmp_path)


def test_import_after_call_is_accepted_and_late_create_app_is_detected(tmp_path):
    (tmp_path / "rag").mkdir()
    (tmp_path / "rag" / "ok.py").write_text(
        "def f():\n    disable_telemetry()\n    from fastembed import TextEmbedding\n",
        encoding="utf-8",
    )
    assert check_telemetry_order(tmp_path) == []
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "app.py").write_text(
        "def create_app():\n    app = FastAPI()\n    disable_telemetry()\n", encoding="utf-8"
    )
    assert check_telemetry_order(tmp_path)
