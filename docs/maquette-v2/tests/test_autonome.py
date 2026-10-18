"""Page autonome `maquette-autonome.html` (décision 1) : à jour par rapport aux sources, et
fonctionnelle ouverte en file:// (routes, parcours, axe) sans erreur ni avertissement de console."""

from __future__ import annotations

import re
import sys

import pytest
from conftest import (
    FAST,
    ROOT,
    VIEWPORT,
    assert_no_axe_violations,
    load_routes,
    route_path,
    wait_for,
)

sys.path.insert(0, str(ROOT))

import construire_autonome  # noqa: E402

PAGE = ROOT / "maquette-autonome.html"
# En file:// seule la page elle-même est un fichier : le reste est embarqué (data:, blob:).
EXTERNE = re.compile(r"^(?!data:|blob:|about:)")


def test_page_autonome_a_jour():
    actuel = PAGE.read_bytes().decode("utf-8").replace("\r\n", "\n") if PAGE.exists() else ""
    assert actuel == construire_autonome.construire(), (
        "maquette-autonome.html n'est pas à jour : lancez python docs/maquette-v2/construire_autonome.py"
    )


@pytest.fixture
def context(browser):
    """Remplace le contexte du conftest : ici seule la page autonome peut être lue sur le disque."""
    refused: list[str] = []
    ctx = browser.new_context(viewport=VIEWPORT, locale="fr-FR", color_scheme="light")

    def garder(route):
        url = route.request.url
        if url.split("#")[0] == PAGE.as_uri():
            route.continue_()
        else:
            refused.append(url)
            route.abort()

    ctx.route(EXTERNE, garder)
    ctx.set_default_timeout(15_000)
    yield ctx
    ctx.close()
    assert not refused, f"Requêtes hors de la page autonome : {refused}"


def ouvrir(page) -> None:
    page.add_init_script(
        "try { localStorage.setItem('wl.theme', 'light'); localStorage.setItem('wl.projection', '0');"
        " localStorage.setItem('wl.maquette.panel', '0'); } catch (e) {}"
    )
    page.goto(PAGE.as_uri())
    wait_for(page, "() => window.__maquette && window.__maquette.ready === true", 20)
    page.evaluate(f"() => window.__maquette.setSpeed({FAST})")


def visible_h1(page) -> str | None:
    return page.evaluate(
        "() => document.querySelector('section.screen:not([hidden]) h1')?.textContent ?? null"
    )


def test_toutes_les_routes_en_file(page):
    ouvrir(page)
    assert page.evaluate("() => location.protocol") == "file:"
    for route in load_routes():
        path = route_path(route)
        page.evaluate("(path) => window.__maquette.navigate(path)", path)
        wait_for(page, "() => document.querySelector('section.screen:not([hidden]) h1') !== null")
        assert visible_h1(page), f"{path} : aucun titre"
        assert not page.evaluate(
            "() => !!document.querySelector('section.screen:not([hidden]) [role=alert] + pre.help')"
        ), f"{path} : échec du chargement de l'écran"
    # Police et sprite embarqués.
    assert page.evaluate("() => document.fonts.check('16px Inter')")
    assert page.evaluate("() => !!document.querySelector('symbol#i-home')")


def test_parcours_en_file(page):
    ouvrir(page)
    result = page.evaluate("() => window.__maquette.runParcours('flow-2')")
    assert result["played"], "aucune étape jouée"
    assert_no_axe_violations(page, "page autonome, fin du Flow 2")


@pytest.mark.parametrize("path", ["/", "/arene/comparer", "/documents/base", "/modeles"])
def test_axe_en_file(page, path):
    ouvrir(page)
    page.evaluate("(path) => window.__maquette.navigate(path)", path)
    page.wait_for_timeout(300)
    assert_no_axe_violations(page, f"page autonome {path}")
