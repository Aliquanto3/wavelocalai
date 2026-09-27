"""Télémétries coupées au démarrage de l'app (src/core/telemetry.py)."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.core.telemetry import TELEMETRY_OPT_OUTS, disable_telemetry

ROOT = Path(__file__).resolve().parents[2]


def test_disable_telemetry_sets_missing_and_keeps_existing(monkeypatch, tmp_path):
    for name in TELEMETRY_OPT_OUTS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "True")  # choix explicite conservé
    # Réactivation volontaire par le .env : lu avant, jamais écrasé.
    dotenv = tmp_path / ".env"
    dotenv.write_text("LANGSMITH_TRACING=true\n", encoding="utf-8")

    disable_telemetry(dotenv)

    assert os.environ["RAGAS_DO_NOT_TRACK"] == "true"
    assert os.environ["CREWAI_DISABLE_TELEMETRY"] == "true"
    assert os.environ["ANONYMIZED_TELEMETRY"] == "True"
    assert os.environ["LANGSMITH_TRACING"] == "true"


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in TELEMETRY_OPT_OUTS}


def test_ragas_does_not_track_after_eval_engine_import():
    """Constat du 27/09 : sans RAGAS_DO_NOT_TRACK, l'évaluation résolvait
    t.explodinggradients.com. L'import d'eval_engine suffit à couper Ragas."""
    pytest.importorskip("ragas")
    code = (
        "import src.core.eval_engine\n"
        "from ragas._analytics import do_not_track\n"
        "assert do_not_track(), 'Ragas suit toujours'\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=ROOT, env=_clean_env(), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]


def test_chroma_settings_without_telemetry():
    code = (
        "from src.core.telemetry import disable_telemetry\n"
        "disable_telemetry()\n"
        "from chromadb.config import Settings\n"
        "assert Settings().anonymized_telemetry is False\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=ROOT, env=_clean_env(), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]


def test_app_disables_telemetry_before_importing_src():
    """Accueil.py appelle disable_telemetry() avant tout autre import de src."""
    tree = ast.parse((ROOT / "src" / "app" / "Accueil.py").read_text(encoding="utf-8"))
    call_line = next(
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", None) == "disable_telemetry"
    )
    src_imports = [
        node.lineno
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("src.")
            and node.module != "src.core.telemetry"
        )
        or (isinstance(node, ast.Import) and any(a.name.startswith("src.") for a in node.names))
    ]
    assert src_imports and call_line < min(src_imports)


def test_e2e_env_does_not_mask_app_opt_outs():
    """La garde réseau e2e vérifie l'app elle-même : l'environnement de test ne coupe pas à
    sa place les télémétries que l'app doit couper."""
    from tests.e2e.conftest import APP_ENV

    assert not set(APP_ENV) & set(TELEMETRY_OPT_OUTS)
