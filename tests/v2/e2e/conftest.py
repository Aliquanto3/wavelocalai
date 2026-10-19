"""Banc E2E de la v2 : le vrai serveur dans un sous-processus, Chromium piloté par Playwright.

- Le serveur écoute sur un port libre de 127.0.0.1, avec un dossier de données temporaire (jamais
  `data/`), Ollama pointé sur un port fermé (aucun vrai réseau) et aucune clé cloud.
- Aucun navigateur n'est téléchargé : Chromium déjà installé pour Playwright, ou l'exécutable de
  `WAVELOCALAI_E2E_CHROMIUM` (Edge convient), comme pour la v1 (`tests/e2e/conftest.py`).
- Toute requête hors de 127.0.0.1 est bloquée et relevée ; le test qui la provoque échoue.
- Les tests de ce dossier portent le marqueur `e2e` (posé ici) : `pytest tests/v2 -m e2e`.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from wavelocalai.web.routes_static import STATIC_HEADERS

from ..conftest import closed_port

CHROMIUM_ENV = "WAVELOCALAI_E2E_CHROMIUM"
# Services de fond de Chromium (mises à jour de composants, synchronisation) : coupés, pour
# qu'aucune requête ne quitte la machine, même hors des pages.
CHROMIUM_ARGS = [
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-sync",
    "--no-pings",
]
PAGE_TIMEOUT_MS = 15_000
VIEWPORT = {"width": 1440, "height": 900}
# Tout ce qui n'est pas 127.0.0.1 (ni data:, blob:, about:) est une sortie de la machine.
EXTERNAL_URL = re.compile(r"^(?!http://127\.0\.0\.1[:/]|data:|blob:|about:)")
CLOUD_KEY_VARS = ("OPENAI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY", "MISTRAL_API_KEY")


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/v2/e2e/" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)


@dataclass
class Server:
    base_url: str
    process: subprocess.Popen


def _wait_healthy(
    base_url: str, process: subprocess.Popen, log_path: Path, timeout_s: float = 30.0
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = log_path.read_text("utf-8")
            pytest.fail(f"le serveur s'est arrêté au démarrage : {output}")
        try:
            with urllib.request.urlopen(
                f"{base_url}/api/health", timeout=2
            ) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    pytest.fail("le serveur n'a pas démarré à temps")


class Backend:
    """`python -m wavelocalai` sur un port fixe, qu'un test peut arrêter puis relancer.

    Données en dossier temporaire, route de test et modèle `fake` actifs (`WAVELOCALAI_TESTING`),
    aucune clé cloud. `ollama_port` : où le serveur cherche Ollama (par défaut un port fermé).
    `config` : un `.toml` de réglages (`--config`), par exemple une table de prix cloud de test.
    """

    def __init__(
        self, data_dir: Path, ollama_port: int | None = None, config: Path | None = None
    ) -> None:
        self.config = config
        self.data_dir = data_dir
        self.port = closed_port()
        self.ollama_port = ollama_port or closed_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.process: subprocess.Popen | None = None
        self._log = None

    def start(self) -> Server:
        env = {
            **os.environ,
            "WAVELOCALAI_OLLAMA_HOST": f"http://127.0.0.1:{self.ollama_port}",
            "WAVELOCALAI_TESTING": "1",
            **dict.fromkeys(CLOUD_KEY_VARS, ""),
        }
        # Sorties dans un fichier, jamais un tube : un tube non lu se remplit et bloque le serveur.
        log_path = self.data_dir / "server-output.log"
        self._log = log_path.open("a", encoding="utf-8")
        self.process = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "-m",
                "wavelocalai",
                "--port",
                str(self.port),
                "--data-dir",
                str(self.data_dir),
                *(["--config", str(self.config)] if self.config else []),
            ],
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_healthy(self.base_url, self.process, log_path)
        except BaseException:
            self.stop()
            raise
        return Server(self.base_url, self.process)

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if self._log is not None:
            self._log.close()
            self._log = None


@pytest.fixture(scope="module")
def server(tmp_path_factory) -> Iterator[Server]:
    """Le serveur sur un port libre, Ollama arrêté."""
    backend = Backend(tmp_path_factory.mktemp("e2e-data"))
    try:
        yield backend.start()
    finally:
        backend.stop()


@pytest.fixture
def backend(tmp_path) -> Iterator[Backend]:
    """Un serveur que le test démarre, arrête et relance lui-même."""
    created = Backend(tmp_path)
    yield created
    created.stop()


class FakeOllama:
    """Un Ollama minimal (`/api/version`, `/api/ps`, déchargement `keep_alive: 0` d'`/api/generate`)
    qu'un test allume et éteint : le vrai Ollama, utilisé ailleurs sur la machine, n'est jamais
    sollicité."""

    VERSION = "0.9.9"
    MODELS = [{"name": "qwen2.5:1.5b", "size": 2 * 1024**3, "size_vram": 1024**3}]

    def __init__(self, port: int) -> None:
        self.port = port
        self.models = [dict(model) for model in self.MODELS]  # `/api/ps` : modèles chargés
        self.unloaded: list[str] = []  # modèles déchargés par `keep_alive: 0`
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path == "/api/version":
                    body = {"version": owner.VERSION}
                elif self.path == "/api/ps":
                    body = {"models": owner.models}
                else:
                    self.send_error(404)
                    return
                payload = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):  # noqa: N802
                if self.path not in ("/api/generate", "/api/embed"):
                    self.send_error(404)
                    return
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                assert request.get("keep_alive") == 0, request
                owner.unloaded.append(request["model"])
                owner.models = [m for m in owner.models if m["name"] != request["model"]]
                payload = json.dumps({"model": request["model"], "done": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


@pytest.fixture
def fake_ollama() -> Iterator[FakeOllama]:
    ollama = FakeOllama(closed_port())
    yield ollama
    ollama.stop()


@pytest.fixture(scope="session")
def browser():
    """Chromium de Playwright, ou l'exécutable de WAVELOCALAI_E2E_CHROMIUM. Rien n'est téléchargé."""
    from playwright.sync_api import sync_playwright

    executable = os.environ.get(CHROMIUM_ENV) or None
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(executable_path=executable, args=CHROMIUM_ARGS)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(
                "Chromium introuvable pour Playwright. Installez-le une fois, hors des tests : "
                f"python -m playwright install chromium ; ou indiquez un exécutable dans "
                f"{CHROMIUM_ENV}. Détail : {(str(exc).splitlines() or [repr(exc)])[0]}",
                pytrace=False,
            )
        yield chromium
        chromium.close()


@dataclass
class Traffic:
    """Ce que le navigateur a demandé : toutes les URL, et celles qui sortent de la machine."""

    urls: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)

    def api_calls(self) -> list[str]:
        return [url for url in self.urls if "/api/" in url]


@pytest.fixture
def traffic() -> Traffic:
    return Traffic()


@pytest.fixture
def context(browser, traffic: Traffic):
    """Contexte de navigation neuf ; en fin de test, aucune requête n'est sortie de la machine."""
    ctx = browser.new_context(viewport=VIEWPORT, locale="fr-FR", color_scheme="light")

    def block(route):
        traffic.blocked.append(route.request.url)
        route.abort()

    ctx.route(EXTERNAL_URL, block)
    ctx.on("request", lambda request: traffic.urls.append(request.url))
    ctx.set_default_timeout(PAGE_TIMEOUT_MS)
    yield ctx
    ctx.close()
    assert not traffic.blocked, f"Requêtes du navigateur hors de la machine : {traffic.blocked}"
    outside = [u for u in traffic.urls if EXTERNAL_URL.match(u)]
    assert not outside, f"Requêtes du navigateur hors de 127.0.0.1 : {outside}"


def _watch_problems(pg, ignore: tuple[str, ...] = ()) -> list[str]:
    problems: list[str] = []
    pg.on("pageerror", lambda error: problems.append(f"exception : {error}"))

    def on_console(message) -> None:
        if message.type in {"error", "warning"} and not any(
            part in message.text for part in ignore
        ):
            problems.append(f"console {message.type} : {message.text}")

    pg.on("console", on_console)
    return problems


@pytest.fixture
def page(context):
    """Onglet neuf ; toute exception JavaScript ou erreur de console fait échouer le test."""
    pg = context.new_page()
    problems = _watch_problems(pg)
    yield pg
    assert not problems, f"Problèmes JavaScript : {problems}"


@pytest.fixture
def page_tolerating_failed_requests(context):
    """Comme `page`, mais les échecs de chargement d'une ressource ne sont pas des problèmes : le
    test coupe le serveur, et le navigateur le dit en console (« Failed to load resource »)."""
    pg = context.new_page()
    problems = _watch_problems(pg, ignore=("Failed to load resource", "ERR_"))
    yield pg
    assert not problems, f"Problèmes JavaScript : {problems}"


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript"}


@pytest.fixture
def fixtures_url(context, server) -> str:
    """Base des pages d'essai de `tests/v2/e2e/fixtures/` : le navigateur les croit servies par le
    serveur (même origine, mêmes en-têtes), mais elles viennent du disque par une interception.
    Le serveur de production n'en sert aucune."""
    root = FIXTURES_DIR.resolve()

    def serve(route) -> None:
        name = route.request.url.split("/__fixtures__/", 1)[1].split("?")[0]
        path = (root / name).resolve()
        if root not in path.parents or not path.is_file():
            route.fulfill(status=404, body="absent")
            return
        route.fulfill(
            status=200,
            body=path.read_bytes(),
            headers={**STATIC_HEADERS, "Content-Type": FIXTURE_TYPES[path.suffix]},
        )

    context.route(re.compile(r"/__fixtures__/"), serve)
    return f"{server.base_url}/__fixtures__"
