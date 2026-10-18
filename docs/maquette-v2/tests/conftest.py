"""Banc de la maquette : un http.server dans un thread (serveur.py), Edge ou Chromium piloté par
Playwright. Rien n'est téléchargé : l'exécutable vient de WAVELOCALAI_E2E_CHROMIUM, sinon d'Edge
installé à son emplacement habituel, sinon du Chromium de Playwright s'il est déjà là. Toute
requête hors de 127.0.0.1 est bloquée et fait échouer le test ; toute exception JavaScript ou
erreur de console aussi.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from serveur import make_server  # noqa: E402

CHROMIUM_ENV = "WAVELOCALAI_E2E_CHROMIUM"
EDGE_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
CHROMIUM_ARGS = [
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-sync",
    "--no-pings",
]
EXTERNAL_URL = re.compile(r"^(?!http://127\.0\.0\.1[:/]|data:|blob:|about:)")
VIEWPORT = {"width": 1440, "height": 900}
FAST = 50  # vitesse du simulateur pendant les tests


def load_routes() -> list[dict]:
    return json.loads((ROOT / "donnees" / "routes.json").read_text("utf-8"))["routes"]


def route_path(route: dict) -> str:
    return route.get("example") or route["path"]


def screens() -> list[dict]:
    """Une route par écran (la première qui l'utilise)."""
    seen: dict[str, dict] = {}
    for route in load_routes():
        seen.setdefault(route.get("screen") or route["slug"], route)
    return list(seen.values())


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    server = make_server(0, ROOT)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _executable() -> str | None:
    if os.environ.get(CHROMIUM_ENV):
        return os.environ[CHROMIUM_ENV]
    return next((path for path in EDGE_PATHS if Path(path).is_file()), None)


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(executable_path=_executable(), args=CHROMIUM_ARGS)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(
                f"Navigateur introuvable. Indiquez Edge ou Chromium dans {CHROMIUM_ENV}. "
                f"Détail : {(str(exc).splitlines() or [repr(exc)])[0]}",
                pytrace=False,
            )
        yield chromium
        chromium.close()


@pytest.fixture
def context(browser):
    blocked: list[str] = []
    ctx = browser.new_context(viewport=VIEWPORT, locale="fr-FR", color_scheme="light")
    ctx.route(EXTERNAL_URL, lambda route: (blocked.append(route.request.url), route.abort()))
    ctx.set_default_timeout(15_000)
    yield ctx
    ctx.close()
    assert not blocked, f"Requêtes hors de 127.0.0.1 : {blocked}"


@pytest.fixture
def page(context):
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


def wait_for(page, condition: str, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if page.evaluate(condition):
            return
        time.sleep(0.05)
    pytest.fail(f"condition jamais vraie : {condition}")


def open_route(
    page,
    base_url: str,
    path: str,
    *,
    theme: str = "light",
    projection: bool = False,
    speed: int = FAST,
) -> None:
    """Ouvre la maquette sur `path`, thème et projection posés avant le premier rendu."""
    page.add_init_script(
        f"""try {{
            localStorage.setItem('wl.theme', '{theme}');
            localStorage.setItem('wl.projection', '{"1" if projection else "0"}');
            localStorage.setItem('wl.maquette.panel', '0');
        }} catch (e) {{}}"""
    )
    page.goto(f"{base_url}/#{path}")
    wait_for(page, "() => window.__maquette && window.__maquette.ready === true")
    page.evaluate(f"() => window.__maquette.setSpeed({speed})")
    wait_for(page, "() => document.querySelector('section.screen:not([hidden]) h1') !== null")


def assert_no_axe_violations(page, what: str) -> None:
    from axe_playwright_python.sync_playwright import Axe

    results = Axe().run(page)
    assert results.violations_count == 0, f"{what} :\n{results.generate_report()}"


def assert_no_horizontal_scroll(page, what: str) -> None:
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, f"{what} : défilement horizontal de {overflow} px"
