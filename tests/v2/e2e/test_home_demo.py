"""Carte « Démo recommandée » de l'Accueil (story 3.6) dans un vrai navigateur : l'Arène en titre,
« Arène des modèles » en sous-titre (D-10), sa phrase, les modèles prêts du défaut `arena` avec leur
badge, « Lancer une comparaison » toujours actif (D-11), sans modèle local : la phrase qui le dit et,
si le cloud est autorisé, des modèles cloud. La liste des modèles et le défaut sont simulés
(`page.route`), comme pour l'écran de l'Arène ; Ollama n'est jamais le vrai.
"""

from __future__ import annotations

import pytest

from .test_arena import BASE_MODEL, NBSP, install_models
from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready

NUAGE = {**BASE_MODEL, "tag": "fake:nuage", "name": "Nuage 70B", "origin": "cloud"}
BRUME = {**BASE_MODEL, "tag": "fake:brume", "name": "Brume 30B", "origin": "cloud"}


def open_home(page, server, **install):
    install_models(page, **install)
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    page.locator("[data-demo]").wait_for()
    wait_for(page, "() => document.querySelector('[data-demo]').dataset.state === 'ready'")


def demo(page):
    return page.locator("[data-demo]")


def allow_cloud(page):
    page.evaluate(
        """async () => {
            const { store } = await import('/static/core/store.js');
            store.set({ allowCloud: true });
        }"""
    )


def test_the_card_names_the_arena_and_lists_the_ready_models_with_their_badge(page, server):
    open_home(page, server)
    section = page.get_by_role("region", name="Démo recommandée")
    assert section.get_by_role("heading", level=2).inner_text() == "Démo recommandée"
    card = demo(page)
    assert card.get_by_role("heading", level=3).inner_text() == "Arène"
    assert card.locator(".home-demo-long").inner_text() == "Arène des modèles"  # D-10
    assert card.locator(".home-demo-text").inner_text() == (
        f"Comparez plusieurs petits modèles sur votre question{NBSP}: qualité, vitesse et CO₂."
    )
    assert card.locator(".home-demo-label").inner_text() == f"Prêts{NBSP}:"
    names = card.locator(".home-demo-item .home-demo-model").all_inner_texts()
    assert names == ["Alpha 1B", "Bravo 2B"]  # le défaut `arena` : les modèles locaux prêts
    badges = card.locator(".home-demo-item wl-badge").evaluate_all(
        "(nodes) => nodes.map((n) => n.getAttribute('kind'))"
    )
    assert badges == ["local", "local"]
    launch = card.get_by_role("link", name="Lancer une comparaison")
    assert launch.get_attribute("href") == "#/arene/comparer"
    assert page.locator("h1:visible").inner_text() == "Accueil"  # D-9 : un seul h1


def test_the_launch_link_opens_the_arena_with_the_default_models_selected(page, server):
    open_home(page, server)
    demo(page).get_by_role("link", name="Lancer une comparaison").click()
    wait_for(page, "() => location.hash === '#/arene/comparer'")
    page.locator("section[data-screen=arena-compare]").wait_for(state="visible")
    wait_for(page, "() => document.querySelector('wl-model-picker')?.values.length === 2")
    assert page.evaluate("document.querySelector('wl-model-picker').values") == ["fake:a", "fake:b"]
    assert page.get_by_role("heading", level=1).inner_text() == "Arène"


def test_without_a_local_model_the_card_says_so_and_the_launch_stays_active(page, server):
    open_home(page, server, models=[], defaults=(), judge_tags=())
    card = demo(page)
    assert card.get_by_text("Aucun modèle local disponible").is_visible()
    assert card.locator(".home-demo-item").count() == 0
    hint = card.locator(".home-card-hint").inner_text()
    assert "Autorisez le cloud" in hint and "écran Modèles" in hint
    launch = card.get_by_role("link", name="Lancer une comparaison")
    assert launch.is_visible() and launch.get_attribute("aria-disabled") is None  # D-11
    launch.click()
    wait_for(page, "() => location.hash === '#/arene/comparer'")
    # L'Arène dit alors quoi faire (D-11, critère de la story 3.2).
    notice = page.locator(".wl-notice").filter(has_text="Aucun modèle local n'est prêt")
    notice.wait_for()
    assert "écran Modèles" in notice.inner_text()


def test_without_a_local_model_cloud_models_are_proposed_once_the_cloud_is_allowed(page, server):
    open_home(page, server, models=[], defaults=(), judge_tags=(), cloud=[NUAGE, BRUME])
    card = demo(page)
    assert card.locator(".home-demo-item").count() == 0  # cloud coupé : aucun modèle cloud
    allow_cloud(page)
    wait_for(
        page,
        "() => document.querySelectorAll('[data-demo] .home-demo-item').length === 2",
    )
    assert card.get_by_text("Aucun modèle local disponible").is_visible()
    assert card.locator(".home-demo-label").inner_text() == f"Modèles cloud disponibles{NBSP}:"
    names = card.locator(".home-demo-item .home-demo-model").all_inner_texts()
    assert names == ["Nuage 70B", "Brume 30B"]
    badges = card.locator(".home-demo-item wl-badge").evaluate_all(
        "(nodes) => nodes.map((n) => n.getAttribute('kind'))"
    )
    assert badges == ["cloud", "cloud"]
    assert card.get_by_role("link", name="Lancer une comparaison").is_visible()


def test_a_card_without_the_arena_does_not_exist(page, server):
    """Aucune carte ne mène à un écran absent : sans Arène disponible, pas de « Démo recommandée »."""
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    page.evaluate(
        """async () => {
            const registry = await import('/static/core/registry.js');
            for (const module of registry.MODULES) {
                for (const screen of module.screens) if (module.id === 'arena') screen.status = 'planned';
            }
            const home = await import('/static/screens/home.js');
            const host = document.createElement('section');
            host.id = 'second-home';
            document.getElementById('main').append(host);
            home.mount(host, {});
        }"""
    )
    assert page.locator("#second-home [data-demo]").count() == 0
    assert page.locator("#second-home").get_by_text("Démo recommandée").count() == 0


@pytest.mark.parametrize("width", [320, 1440])
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("state", ["ready", "no_local"])
def test_axe_finds_no_violation_on_the_demo_card(page, server, theme, width, state):
    if state == "ready":
        open_home(page, server)
    else:
        open_home(page, server, models=[], defaults=(), judge_tags=())
    page.set_viewport_size({"width": width, "height": 900})
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(page, f"Accueil, démo {state}, {width} px, thème {theme}")
    assert_no_horizontal_scroll(page)
