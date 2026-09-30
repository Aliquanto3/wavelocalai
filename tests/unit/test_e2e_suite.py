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


# ---------------------------------------------------------------------------
# Compteur d'exécutions du script (trames simulées, sans navigateur)
# ---------------------------------------------------------------------------


def _frame(kind: str, status: str = "FINISHED_SUCCESSFULLY") -> bytes:
    """Trame binaire du serveur : un ForwardMsg `new_session` ou `script_finished`."""
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    msg = ForwardMsg()
    if kind == "new_session":
        msg.new_session.script_run_id = "run"
    else:
        msg.script_finished = ForwardMsg.ScriptFinishedStatus.Value(status)
    return msg.SerializeToString()


def _delta_frame() -> bytes:
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    msg = ForwardMsg()
    msg.delta.new_element.markdown.body = "texte"
    return msg.SerializeToString()


class FakeWebSocket:
    def __init__(self):
        self.handlers = {}

    def on(self, event, handler):
        self.handlers[event] = handler

    def receive(self, payload):
        self.handlers["framereceived"](payload)


class FakePage:
    """Page Playwright simulée : chaque attente livre la trame suivante du serveur."""

    def __init__(self):
        self.handlers = {}
        self.socket = FakeWebSocket()
        self.pending: list = []
        self.keys: list[str] = []
        self.keyboard = type("Keyboard", (), {"press": lambda _, key: self.keys.append(key)})()

    def on(self, event, handler):
        self.handlers[event] = handler

    def connect(self):
        self.handlers["websocket"](self.socket)

    def wait_for_timeout(self, ms):
        if self.pending:
            self.socket.receive(self.pending.pop(0))
        else:
            import time

            time.sleep(0.001)

    def wait_for_selector(self, *args, **kwargs):
        return None

    def wait_for_function(self, *args, **kwargs):
        return None


@pytest.fixture
def fake_page():
    from tests.e2e import helpers

    page = FakePage()
    helpers.track_script_runs(page)
    page.connect()
    return page


def test_script_runs_counts_frames(fake_page):
    """`new_session` ouvre une exécution ; `script_finished` la clôt, sauf
    FINISHED_EARLY_FOR_RERUN ; texte, deltas et trames illisibles sont ignorés."""
    from tests.e2e import helpers

    runs = helpers._runs(fake_page)
    for payload in ("texte", b"\xff\xff\xff", _delta_frame(), _frame("new_session")):
        fake_page.socket.receive(payload)
    assert (runs.started, runs.finished) == (1, 0)
    fake_page.socket.receive(_frame("script_finished", "FINISHED_EARLY_FOR_RERUN"))
    assert runs.finished == 0
    fake_page.socket.receive(_frame("new_session"))
    fake_page.socket.receive(_frame("script_finished"))
    assert (runs.started, runs.finished) == (2, 2)
    assert helpers.script_runs(fake_page) == 2


def test_wait_script_run_ignores_run_started_before_action(fake_page):
    """Une exécution déjà en cours à l'action ne compte pas, ni une exécution coupée par
    `st.rerun()` : l'attente s'arrête à la fin de l'exécution suivante."""
    from tests.e2e import helpers

    fake_page.socket.receive(_frame("new_session"))  # exécution en cours avant l'action
    since = helpers.script_runs(fake_page)
    fake_page.pending = [
        _frame("script_finished"),  # fin de l'exécution d'avant l'action
        _frame("new_session"),
        _frame("script_finished", "FINISHED_EARLY_FOR_RERUN"),  # st.rerun()
        _frame("new_session"),
        _delta_frame(),
        _frame("script_finished"),
    ]
    helpers.wait_script_run(fake_page, since, timeout_ms=5_000)
    assert fake_page.pending == []
    assert helpers._runs(fake_page).finished == since + 2


def test_wait_script_run_fails_without_run(fake_page):
    from tests.e2e import helpers

    since = helpers.script_runs(fake_page)
    fake_page.pending = [_frame("new_session")]
    with pytest.raises(AssertionError, match="Aucune exécution du script terminée"):
        helpers.wait_script_run(fake_page, since, timeout_ms=200, what="choix")


def test_untracked_page_is_an_error():
    from tests.e2e import helpers

    with pytest.raises(AssertionError, match="Compteur d'exécutions absent"):
        helpers.script_runs(FakePage())


class FakeTagLocator:
    """Locator simulé : `count()` d'une fonction, `click()` d'une action ; `.first` = lui-même."""

    def __init__(self, count=lambda: 0, click=None):
        self._count, self._click = count, click

    @property
    def first(self):
        return self

    def count(self):
        return self._count()

    def click(self):
        self._click()


class FakeTagList:
    """`st.multiselect` sans bouton « clear all » : chaque clic sur la croix d'une étiquette
    la retire et déclenche une exécution du script."""

    def __init__(self, page, tags: list[str]):
        self.page, self.tags, self.clicks = page, list(tags), []

    def get_by_role(self, role, name=None):
        return FakeTagLocator()

    def _remove_first(self):
        # Aucune exécution en attente au clic : chaque clic attend donc la sienne.
        assert self.page.pending == [], "clic avant la fin du rerun du clic précédent"
        self.clicks.append(self.tags.pop(0))
        self.page.pending += [_frame("new_session"), _frame("script_finished")]

    def locator(self, selector):
        if selector == "[data-tag] button":
            return FakeTagLocator(click=self._remove_first)
        return FakeTagLocator(count=lambda: len(self.tags))


def test_multiselect_clear_waits_each_removal_rerun(fake_page):
    """Sans « clear all » : un clic par étiquette, chacun attend son propre rerun."""
    from tests.e2e import helpers

    multiselect = FakeTagList(fake_page, ["A · Local", "B · Local"])
    helpers.multiselect_clear(fake_page, multiselect)
    assert multiselect.clicks == ["A · Local", "B · Local"]
    assert fake_page.pending == []
    assert helpers._runs(fake_page).finished == 2
    assert fake_page.keys == ["Escape"]


def test_multiselect_clear_empty_list_returns_at_once(fake_page):
    from tests.e2e import helpers

    multiselect = FakeTagList(fake_page, [])
    helpers.multiselect_clear(fake_page, multiselect)
    assert multiselect.clicks == [] and fake_page.keys == []


# ---------------------------------------------------------------------------
# Relance d'une génération interrompue (flux Ollama tronqué)
# ---------------------------------------------------------------------------


def _generation(fake_page, interruptions: int):
    """(launch, interrupted, appels) : chaque lancement produit une exécution complète ; les
    `interruptions` premiers passages sont interrompus."""
    calls = {"launch": 0, "retry": 0}

    def launch():
        calls["launch"] += 1
        fake_page.pending += [_frame("new_session"), _frame("script_finished")]

    def interrupted():
        return calls["launch"] <= interruptions

    def before_retry():
        calls["retry"] += 1

    return launch, interrupted, before_retry, calls


def test_generate_succeeds_on_second_attempt(fake_page):
    from tests.e2e import helpers

    launch, interrupted, before_retry, calls = _generation(fake_page, interruptions=1)
    attempts = helpers.generate(
        fake_page, launch, interrupted, 5_000, before_retry=before_retry, what="Chat libre"
    )
    assert attempts == 2
    assert calls == {"launch": 2, "retry": 1}


def test_generate_skips_after_three_interruptions(fake_page):
    from tests.e2e import helpers

    launch, interrupted, before_retry, calls = _generation(fake_page, interruptions=99)
    with pytest.raises(pytest.skip.Exception, match="Ollama 0.34.2") as skipped:
        helpers.generate(
            fake_page, launch, interrupted, 5_000, before_retry=before_retry, what="Arène"
        )
    assert helpers.GENERATION_ATTEMPTS == 3
    assert calls == {"launch": 3, "retry": 2}
    assert "Arène : génération interrompue 3 fois de suite" in str(skipped.value)


def test_generate_waits_for_run_before_judging(fake_page):
    """Sans exécution terminée après le lancement, `generate` échoue (jamais de skip)."""
    from tests.e2e import helpers

    with pytest.raises(AssertionError, match="Aucune exécution du script terminée"):
        helpers.generate(fake_page, lambda: None, lambda: False, 200)


# ---------------------------------------------------------------------------
# Sélecteurs : attente du rerun du serveur, jamais d'un état du navigateur
# ---------------------------------------------------------------------------


class FakeLocator:
    """Locator simulé : `count()` lu sur le widget, `click()` délégué."""

    def __init__(self, count, click):
        self.count = count
        self.click = click

    @property
    def first(self):
        return self


class FakeWidget:
    """Sélecteur simulé : `tags` étiquettes choisies (multiselect). « Tout effacer » vide la
    liste dans le navigateur tout de suite, et le serveur relance le script ensuite."""

    def __init__(self, page, tags: int = 0):
        self.page = page
        self.tags = tags
        self.clicks = 0

    def click(self):
        self.clicks += 1

    def clear_all(self):
        self.clicks += 1
        self.tags = 0
        self.page.pending += [_frame("new_session"), _frame("script_finished")]

    def locator(self, selector):
        return FakeLocator(lambda: self.tags, self.click)

    def get_by_role(self, *args, **kwargs):
        return FakeLocator(lambda: 1, self.clear_all)


class FakeKeyboard:
    def type(self, text):
        pass

    def press(self, key):
        pass


@pytest.fixture
def widget_page(fake_page, monkeypatch):
    """Page simulée avec clavier ; `waits` relève les attentes de rerun (`since`)."""
    from tests.e2e import helpers

    fake_page.keyboard = FakeKeyboard()
    fake_page.waits = []
    real_wait = helpers.wait_script_run

    def wait(page, since, *args, **kwargs):
        page.waits.append(since)
        real_wait(page, since, 5_000)

    monkeypatch.setattr(helpers, "wait_script_run", wait)
    return fake_page


def test_select_option_waits_for_server_run(widget_page, monkeypatch):
    """Nouvelle valeur : la valeur affichée change tout de suite dans le navigateur, le
    helper attend pourtant la fin de l'exécution que le choix déclenche."""
    from tests.e2e import helpers

    shown = {"value": "Gemma 3 1B · Local"}

    def pick(page, text, tag):
        shown["value"] = "Granite 4 · Local"
        page.pending += [_frame("new_session"), _frame("script_finished")]
        return shown["value"]

    monkeypatch.setattr(helpers, "_pick", pick)
    monkeypatch.setattr(helpers, "selected_value", lambda box: shown["value"])
    assert (
        helpers.select_option(widget_page, FakeWidget(widget_page), "Granite 4")
        == "Granite 4 · Local"
    )
    assert widget_page.waits == [0]
    assert widget_page.pending == [], "rerun du serveur non attendu"


def test_select_option_already_selected_does_not_wait(widget_page, monkeypatch):
    """Valeur déjà choisie : le serveur ne relance pas le script, rien à attendre."""
    from tests.e2e import helpers

    monkeypatch.setattr(helpers, "_pick", lambda page, text, tag: "Gemma 3 1B · Local")
    monkeypatch.setattr(helpers, "selected_value", lambda box: "Gemma 3 1B · Local")
    assert (
        helpers.select_option(widget_page, FakeWidget(widget_page), "Gemma 3 1B")
        == "Gemma 3 1B · Local"
    )
    assert widget_page.waits == []


def test_multiselect_add_waits_for_server_run(widget_page, monkeypatch):
    from tests.e2e import helpers

    values = []

    def pick(page, text, tag):
        values.append("Granite 4 · Local")
        page.pending += [_frame("new_session"), _frame("script_finished")]
        return "Granite 4 · Local"

    monkeypatch.setattr(helpers, "_pick", pick)
    monkeypatch.setattr(helpers, "multiselect_values", lambda ms: list(values))
    assert (
        helpers.multiselect_add(widget_page, FakeWidget(widget_page), "Granite 4")
        == "Granite 4 · Local"
    )
    assert widget_page.waits == [0]
    assert widget_page.pending == []


def test_multiselect_clear_waits_for_server_run(widget_page):
    """« Tout effacer » : l'étiquette disparaît du navigateur avant le rerun ; le helper attend
    la fin de l'exécution déclenchée."""
    from tests.e2e import helpers

    widget = FakeWidget(widget_page, tags=2)
    helpers.multiselect_clear(widget_page, widget)
    assert widget.clicks == 1
    assert widget_page.waits == [0]
    assert widget_page.pending == []


def test_multiselect_clear_empty_returns_at_once(widget_page):
    """Liste déjà vide : aucun clic, aucune attente."""
    from tests.e2e import helpers

    widget = FakeWidget(widget_page, tags=0)
    helpers.multiselect_clear(widget_page, widget)
    assert widget.clicks == 0
    assert widget_page.waits == []


# ---------------------------------------------------------------------------
# Écarts de contraste acceptés (test_accessibility.py)
# ---------------------------------------------------------------------------

ACCEPTED_PILL = {
    "scheme": "dark",
    "page": "Agent_Lab",
    "rule": "color-contrast",
    "component": "pills",
    "fg": "#7e65e9",
    "bg": "#161329",
    "ratio": 4.24,
}


def test_accepted_gap_matches_exact_gap_only():
    from tests.e2e.test_accessibility import accepted_gap

    gap = accepted_gap(ACCEPTED_PILL)
    assert gap is not None and "DESIGN.md" in gap["reference"]
    assert accepted_gap({**ACCEPTED_PILL, "fg": "#7E65E9"}) is gap


@pytest.mark.parametrize(
    "change",
    [
        {"ratio": 4.23},
        {"ratio": 4.25},
        {"fg": "#7e65ea"},
        {"bg": "#0a0a14"},
        {"component": "stSlider"},
        {"component": None},
        {"page": "Inference_Arena"},
        {"scheme": "light"},
        {"rule": "button-name"},
    ],
    ids=lambda c: next(iter(c)) + "=" + str(next(iter(c.values()))),
)
def test_neighbouring_gap_is_not_accepted(change):
    from tests.e2e.test_accessibility import accepted_gap

    assert accepted_gap({**ACCEPTED_PILL, **change}) is None


def _palette():
    from tests.e2e.test_accessibility import theme_colors

    return theme_colors("dark")


def test_classify_routes_accepted_gap():
    from tests.e2e.test_accessibility import classify

    assert classify(ACCEPTED_PILL, False, _palette()) == "accepted"


def test_inactive_and_native_take_priority_over_accepted_gap():
    """Un nœud inactif ou une couleur native reste dans sa catégorie, même identique à un
    écart accepté par ailleurs."""
    from tests.e2e.test_accessibility import classify

    assert classify(ACCEPTED_PILL, True, _palette()) == "inactive"
    # Palette sans la primaire : #7e65e9 devient une couleur native.
    assert classify(ACCEPTED_PILL, False, {"#ffffff"}) == "natives"


def test_neighbouring_gap_routes_to_failures():
    from tests.e2e.test_accessibility import classify

    assert classify({**ACCEPTED_PILL, "ratio": 4.1}, False, _palette()) == "failures"
    assert classify({**ACCEPTED_PILL, "rule": "button-name"}, True, _palette()) == "failures"


def test_report_and_session_summary_contents():
    """Rapport JSON : quatre catégories ; résumé de session : tout sauf les échecs, chacun
    avec sa catégorie lisible (renvoi à DESIGN.md pour l'écart accepté)."""
    from tests.e2e.test_accessibility import non_failing, sort_findings

    neighbour = {**ACCEPTED_PILL, "ratio": 4.1}
    native = {**ACCEPTED_PILL, "fg": "#00ff00", "component": "stCaption"}
    inactive = {**ACCEPTED_PILL, "component": "stCheckbox"}
    report = sort_findings(
        [(ACCEPTED_PILL, False), (neighbour, False), (native, False), (inactive, True)],
        _palette(),
    )
    assert set(report) == {"failures", "natives", "inactive", "accepted"}
    assert report["failures"] == [neighbour]
    assert [f["component"] for f in report["natives"]] == ["stCaption"]
    assert [f["component"] for f in report["inactive"]] == ["stCheckbox"]
    (accepted,) = report["accepted"]
    assert accepted["category"].startswith("écart accepté (DESIGN.md")
    summary = non_failing(report)
    assert len(summary) == 3 and all("category" in f for f in summary)
    assert neighbour not in summary
