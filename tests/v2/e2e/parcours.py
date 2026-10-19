"""Aides des parcours de bout en bout (story 8.3) : naviguer par la coquille, sans recharger.

Un parcours ouvre la page une seule fois (`page.goto`), pose un repère (`window.__noReload`), puis ne
change d'écran qu'en cliquant la navigation de l'application ; en fin de parcours, la page n'a connu
qu'une navigation.
"""

from __future__ import annotations

from .test_shell import wait_for


def mark_no_reload(page) -> None:
    """Pose le repère qu'un rechargement effacerait."""
    page.evaluate("window.__noReload = true")


def assert_never_reloaded(page) -> None:
    """La page est celle du début : repère intact, une seule entrée de navigation."""
    assert page.evaluate("window.__noReload") is True
    assert page.evaluate("performance.getEntriesByType('navigation').length") == 1


def open_module(page, module: str) -> None:
    """Clique le module de la navigation (nom court : « Sobriété », « Modèles », « Agents »…)."""
    page.locator("#module-list").get_by_role("link", name=module, exact=True).click()


def open_tab(page, module: str, tab: str, screen: str) -> None:
    """Clique l'onglet d'écran d'un module, puis attend l'écran affiché."""
    page.get_by_role("navigation", name=f"Écrans du module {module}").get_by_role(
        "link", name=tab, exact=True
    ).click()
    wait_for(page, f"() => document.querySelector('[data-screen=\"{screen}\"]:not([hidden])')")


def wait_screen(page, screen: str) -> None:
    wait_for(page, f"() => document.querySelector('[data-screen=\"{screen}\"]:not([hidden])')")
