"""Banc E2E de la v2 : le vrai serveur dans un sous-processus, Chromium piloté par Playwright.

- Le serveur écoute sur un port libre de 127.0.0.1, avec un dossier de données temporaire (jamais
  `data/`), Ollama pointé sur un port fermé (aucun vrai réseau) et aucune clé cloud.
- Aucun navigateur n'est téléchargé : Chromium déjà installé pour Playwright, ou l'exécutable de
  `WAVELOCALAI_E2E_CHROMIUM` (Edge convient), comme pour la v1 (`tests/e2e/conftest.py`).
- Toute requête hors de 127.0.0.1 est bloquée et relevée ; le test qui la provoque échoue.
- Les tests de ce dossier portent le marqueur `e2e` (posé ici) : `pytest tests/v2 -m e2e`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

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


@pytest.fixture(scope="module")
def server(tmp_path_factory) -> Iterator[Server]:
    """`python -m wavelocalai` sur un port libre, données en dossier temporaire, Ollama arrêté."""
    data_dir = tmp_path_factory.mktemp("e2e-data")
    port = closed_port()
    env = {
        **os.environ,
        "WAVELOCALAI_OLLAMA_HOST": f"http://127.0.0.1:{closed_port()}",
        **dict.fromkeys(CLOUD_KEY_VARS, ""),
    }
    # Sorties dans un fichier, jamais un tube : un tube non lu se remplit et bloque le serveur.
    log_path = data_dir / "server-output.log"
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "wavelocalai", "--port", str(port), "--data-dir", str(data_dir)],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_healthy(base_url, process, log_path)
        yield Server(base_url, process)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        log.close()


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


@pytest.fixture
def page(context):
    """Onglet neuf ; toute exception JavaScript ou erreur de console fait échouer le test."""
    pg = context.new_page()
    problems: list[str] = []
    pg.on("pageerror", lambda error: problems.append(f"exception : {error}"))
    pg.on(
        "console",
        lambda message: (
            problems.append(f"console {message.type} : {message.text}")
            if message.type in {"error", "warning"}
            else None
        ),
    )
    yield pg
    assert not problems, f"Problèmes JavaScript : {problems}"
