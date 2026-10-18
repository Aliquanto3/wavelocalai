"""Chaque route de donnees/routes.json, lue au moment de la collecte : un écran ajouté plus tard est
couvert sans toucher aux tests. Accessibilité (axe-core, clair et sombre, sans exclusion), largeurs
de 320 à 1 440 px sans défilement horizontal, projection, clavier."""

from __future__ import annotations

import pytest
from conftest import (
    assert_no_axe_violations,
    assert_no_horizontal_scroll,
    load_routes,
    open_route,
    route_path,
    wait_for,
)

ROUTES = load_routes()
IDS = [route["slug"] for route in ROUTES]
WIDTHS = (320, 768, 1024, 1440)


def settle(page) -> None:
    """Laisse le temps au premier état du système et aux résumés simulés d'arriver."""
    wait_for(
        page, "() => window.__maquette.ready && document.documentElement.dataset.ready === 'true'"
    )
    page.wait_for_timeout(250)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("route", ROUTES, ids=IDS)
def test_axe_without_violation(page, base_url, route, theme):
    open_route(page, base_url, route_path(route), theme=theme)
    settle(page)
    assert page.evaluate("() => window.__maquette.current().slug") == route["slug"]
    assert page.title() == f"{route['title']} · WaveLocalAI"
    assert page.locator("section.screen:not([hidden]) h1").count() == 1
    assert_no_axe_violations(page, f"{route['slug']} en thème {theme}")


@pytest.mark.parametrize("route", ROUTES, ids=IDS)
def test_widths_without_horizontal_scroll(page, base_url, route):
    open_route(page, base_url, route_path(route))
    settle(page)
    for width in WIDTHS:
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(100)
        assert_no_horizontal_scroll(page, f"{route['slug']} à {width} px")


@pytest.mark.parametrize("route", ROUTES, ids=IDS)
def test_projection(page, base_url, route):
    open_route(page, base_url, route_path(route), projection=True)
    settle(page)
    assert page.evaluate("() => document.documentElement.dataset.projection") == "true"
    assert page.locator(".footer").is_hidden()
    assert_no_axe_violations(page, f"{route['slug']} en projection")
    for width in (320, 1024):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_timeout(100)
        assert_no_horizontal_scroll(page, f"{route['slug']} en projection à {width} px")


@pytest.mark.parametrize("route", ROUTES, ids=IDS)
def test_keyboard_reaches_content(page, base_url, route):
    """Tab : d'abord « Aller au contenu », qui mène au `main` ; le Tab suivant est dans l'écran."""
    open_route(page, base_url, route_path(route))
    settle(page)
    page.locator("body").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.id") == "skip-link"
    outline = page.evaluate("() => getComputedStyle(document.activeElement).outlineStyle")
    assert outline != "none", "focus non visible sur le lien d'évitement"
    page.keyboard.press("Enter")
    assert page.evaluate("() => document.activeElement.id") == "main"
    focusable = page.evaluate(
        """() => [...document.querySelectorAll('#main section.screen:not([hidden]) :is(a[href], button, input, select, textarea, [tabindex="0"])')]
            .some((el) => !el.disabled && el.offsetParent !== null)"""
    )
    page.keyboard.press("Tab")
    if not focusable:
        return  # écran sans élément interactif (écran à construire) : rien à atteindre
    inside = page.evaluate("() => document.getElementById('main').contains(document.activeElement)")
    assert inside, "le Tab après « Aller au contenu » ne mène pas dans le contenu"
    style = page.evaluate(
        "() => { const s = getComputedStyle(document.activeElement); return s.outlineStyle + ' ' + s.outlineWidth; }"
    )
    assert not style.startswith("none"), f"focus non visible dans le contenu : {style}"
