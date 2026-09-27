"""
Garde-fous de la suite e2e (tests/e2e) : chaque module est marqué `e2e`, la suite par défaut
n'en sélectionne aucun, et la suite e2e se collecte sans Ollama ni navigateur. Vérifie aussi,
sans réseau, les protections de tests/e2e/launch_app.py : détection des hôtes externes, hook
d'audit réseau, redirection des écritures de l'app vers un dossier temporaire.

Usage: python -m pytest tests/unit/test_e2e_suite.py -v
"""

import ast
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
E2E_DIR = ROOT_DIR / "tests" / "e2e"
E2E_MODULES = sorted(E2E_DIR.glob("test_*.py"))


def _marks_e2e(node: ast.expr) -> bool:
    """`pytest.mark.e2e`, seul ou dans une liste ou un tuple."""
    if isinstance(node, (ast.List, ast.Tuple)):
        return any(_marks_e2e(elt) for elt in node.elts)
    return ast.unparse(node) == "pytest.mark.e2e"


def _pytestmark(path: Path) -> ast.expr | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets
        ):
            return stmt.value
    return None


def _collect(*args: str) -> subprocess.CompletedProcess:
    """`pytest --collect-only` dans un sous-processus, depuis la racine du dépôt ; `-q -q`
    compense le `-v` de pytest.ini : une ligne par test collecté."""
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-q",
            "-p",
            "no:cacheprovider",
            *args,
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=300,
    )


def test_e2e_modules_exist():
    assert E2E_MODULES, "tests/e2e ne contient aucun module de test"


@pytest.mark.parametrize("path", E2E_MODULES, ids=[p.name for p in E2E_MODULES])
def test_every_e2e_module_is_marked(path):
    """Chaque module de tests/e2e déclare `pytestmark = pytest.mark.e2e` : tous ses tests
    sont exclus par le `-m "not e2e"` de pytest.ini."""
    mark = _pytestmark(path)
    assert mark is not None and _marks_e2e(mark), f"{path.name} : pytestmark sans pytest.mark.e2e"


# Erreur de collecte signalée par pytest (import impossible, module en échec).
COLLECTION_ERROR_RE = re.compile(r"ERROR collecting|\b\d+ errors?\b|Interrupted:")


def test_default_run_selects_no_e2e_test():
    """Sans `-m`, la collecte de tests/e2e ne sélectionne aucun test : tous sont désélectionnés."""
    result = _collect("tests/e2e")
    output = result.stdout + result.stderr
    assert not COLLECTION_ERROR_RE.search(output), output
    assert re.search(r"no tests collected \(\d+ deselected\)", output), output
    assert "::" not in result.stdout, output


def test_e2e_suite_collects_without_errors():
    """`-m e2e` collecte tous les tests e2e, sans erreur d'import (ni Ollama ni navigateur
    ne sont nécessaires pour collecter)."""
    result = _collect("tests/e2e", "-m", "e2e")
    output = result.stdout + result.stderr
    assert not COLLECTION_ERROR_RE.search(output), output
    assert re.search(r"\b\d+ tests? collected\b", output), output
    collected = [line for line in result.stdout.splitlines() if "::" in line]
    assert collected, output
    modules = {line.split("::", 1)[0] for line in collected}
    assert modules == {f"tests/e2e/{p.name}" for p in E2E_MODULES}, modules


# ---------------------------------------------------------------------------
# Protections du lanceur e2e (sans réseau)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "[::1]", socket.gethostname()])
def test_local_hosts_are_local(host):
    from tests.e2e.launch_app import is_local_host

    assert is_local_host(host)


@pytest.mark.parametrize("host", ["192.0.2.1", "10.0.0.1", "example.com", "fonts.googleapis.com"])
def test_external_hosts_are_external(host):
    from tests.e2e.launch_app import is_local_host

    assert not is_local_host(host)


@pytest.mark.parametrize(
    ("url", "external"),
    [
        ("https://fonts.googleapis.com/css2?family=Inter", True),
        ("wss://example.com/socket", True),
        ("http://192.0.2.1:8501/", True),
        ("http://10.0.0.1/", True),
        ("http://localhost:8501/Agent_Lab", False),
        ("ws://127.0.0.1:8501/_stcore/stream", False),
        ("http://[::1]:8501/", False),
        ("data:image/png;base64,AAAA", False),
        ("blob:http://localhost:8501/1234", False),
        ("about:blank", False),
    ],
)
def test_browser_guard_classifies_urls(url, external):
    from tests.e2e.launch_app import is_external_url

    assert is_external_url(url) is external


def _run_python(code: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, *args],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "ANONYMIZED_TELEMETRY": "False", "PYTHONIOENCODING": "utf-8"},
        timeout=300,
    )


NETWORK_AUDIT_SCRIPT = """
import sys
from pathlib import Path
sys.path.insert(0, ".")
from tests.e2e.launch_app import install_network_audit
install_network_audit(Path(sys.argv[1]))
sys.audit("socket.getaddrinfo", "example.com", 443, 0, 0, 0)
sys.audit("socket.connect", None, ("192.0.2.1", 443))
sys.audit("socket.getaddrinfo", "localhost", 11434, 0, 0, 0)
sys.audit("socket.connect", None, ("127.0.0.1", 11434))
sys.audit("socket.connect", None, "/tmp/socket-unix")
print("audit-ok")
"""


def test_network_audit_logs_external_calls_only(tmp_path):
    """Le hook d'audit du lanceur consigne la résolution et la connexion externes, jamais les
    appels locaux (événements émis par sys.audit, aucun accès réseau)."""
    log = tmp_path / "external_connections.log"
    result = _run_python(NETWORK_AUDIT_SCRIPT, str(log))
    assert "audit-ok" in result.stdout, result.stdout + result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "dns example.com",
        "connect 192.0.2.1:443",
    ]


REDIRECT_SCRIPT = """
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from tests.e2e.launch_app import redirect_data
tmp = Path(sys.argv[1])
redirect_data(tmp)
from langchain_core.embeddings import DeterministicFakeEmbedding
import src.core.agent_tools as agent_tools
import src.core.config as config
import src.core.green_monitor as green_monitor
from src.core.exporters.metrics_exporter import MetricsExporter
from src.core.repositories.benchmark_repository import BenchmarkRepository
from src.core.rag.vector_store import VectorStoreManager
store = VectorStoreManager(DeterministicFakeEmbedding(size=8), "e2e-redirect")
print(json.dumps({
    "chroma": store.persist_dir,
    "emissions_file": str(green_monitor.app_emissions_path()),
    "emissions_dir": str(config.EMISSIONS_DIR),
    "benchmarks_dir": str(config.BENCHMARKS_DIR),
    "agent_outputs": str(agent_tools.OUTPUT_DIR),
    "benchmark_db": str(BenchmarkRepository()._db_path),
    "exports": str(MetricsExporter()._output_dir),
}))
"""


def test_redirect_data_keeps_every_write_in_tmp(tmp_path):
    """Avant tout parcours (et avant « Vider définitivement »), redirect_data envoie Chroma,
    émissions, fichiers de l'agent, base et exports de benchmark sous le dossier temporaire."""
    result = _run_python(REDIRECT_SCRIPT, str(tmp_path))
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    assert lines, result.stdout[-2000:] + result.stderr[-3000:]
    paths = json.loads(lines[-1])
    root = tmp_path.resolve()
    for name, path in paths.items():
        assert (
            Path(path).resolve().is_relative_to(root)
        ), f"{name} hors du dossier temporaire : {path}"
    assert any((tmp_path / "chroma").iterdir()), "Chroma n'a rien écrit dans le dossier temporaire"
