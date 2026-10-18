"""Scénarios du panneau : pour chaque écran de donnees/routes.json, chaque scénario exporté par son
module (lu dans la page par `window.__maquette.scenarios()`) est joué, puis axe-core vérifie l'état
obtenu ; les états globaux et les parcours de bout en bout aussi. Le panneau lui-même s'ouvre et se
ferme au clavier."""

from __future__ import annotations

import json

import pytest
from conftest import (
    ROOT,
    assert_no_axe_violations,
    load_routes,
    open_route,
    route_path,
    screens,
    wait_for,
)

SCREENS = screens()
PARCOURS = json.loads((ROOT / "donnees" / "parcours.json").read_text("utf-8"))["parcours"]
GLOBAL_STATES = [
    ("ollama-arrete", True),
    ("cloud", True),
    ("connexion-perdue", True),
    ("serveur-redemarre", None),
    ("garde-fou-memoire", True),
    ("aucun-modele-local", True),
    ("projection", True),
    ("theme", "dark"),
]


def run_scenario(page, scenario_id: str) -> None:
    page.evaluate("(id) => window.__maquette.runScenario(id)", scenario_id)
    page.wait_for_timeout(150)


def scenario_ids(page) -> list[str]:
    return [item["id"] for item in page.evaluate("() => window.__maquette.scenarios()")]


@pytest.mark.parametrize(
    "route", SCREENS, ids=[route.get("screen") or route["slug"] for route in SCREENS]
)
def test_each_scenario_of_the_screen_passes_axe(page, base_url, route):
    path = route_path(route)
    open_route(page, base_url, path)
    failures: list[str] = []
    ids = scenario_ids(page)
    assert ids, f"{route['slug']} : aucun scénario exporté, les états de l'écran ne sont pas vérifiés"
    for scenario_id in ids:
        # Un scénario peut quitter l'écran (parcours) : on y revient avant le suivant.
        page.evaluate("(path) => window.__maquette.navigate(path)", path)
        try:
            run_scenario(page, scenario_id)
            assert_no_axe_violations(page, f"{route['slug']} / {scenario_id}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{scenario_id} : {str(exc)[:1500]}")
    assert not failures, "\n\n".join(failures)


@pytest.mark.parametrize("state", GLOBAL_STATES, ids=[state for state, _ in GLOBAL_STATES])
@pytest.mark.parametrize("path", ["/", "/arene/chat"])
def test_global_states_pass_axe(page, base_url, path, state):
    open_route(page, base_url, path)
    name, value = state
    page.evaluate("([id, value]) => window.__maquette.setGlobal(id, value)", [name, value])
    page.wait_for_timeout(400)
    assert_no_axe_violations(page, f"{path} avec l'état global {name}")


def test_connection_banners(page, base_url):
    open_route(page, base_url, "/")
    page.evaluate("() => window.__maquette.setGlobal('connexion-perdue', true)")
    page.locator("#connection-banner").wait_for(state="visible")
    assert page.locator("#ollama-label").inner_text() == "Ollama, état inconnu"
    page.evaluate("() => window.__maquette.setGlobal('connexion-perdue', false)")
    page.locator("#connection-banner").wait_for(state="hidden")
    page.evaluate("() => window.__maquette.setGlobal('serveur-redemarre')")
    page.locator("#restart-banner").wait_for(state="visible")
    assert "Recharger" in page.locator("#restart-banner").inner_text()


@pytest.mark.parametrize("journey", PARCOURS, ids=[journey["id"] for journey in PARCOURS])
def test_parcours_run_end_to_end(page, base_url, journey):
    open_route(page, base_url, "/")
    result = page.evaluate("(id) => window.__maquette.runParcours(id)", journey["id"])
    assert len(result["played"]) + len(result["skipped"]) == sum(
        1 for step in journey["steps"] if step.get("scenario")
    )
    assert_no_axe_violations(page, f"fin du parcours {journey['id']}")


def test_flow_1_plays_the_home_steps(page, base_url):
    open_route(page, base_url, "/")
    result = page.evaluate("() => window.__maquette.runParcours('flow-1')")
    assert "/ nominal" in result["played"]
    assert "/ suivre-demo-recommandee" in result["played"]


def test_panel_keyboard_and_axe(page, base_url):
    open_route(page, base_url, "/arene/chat")
    toggle = page.get_by_role("button", name="Scénarios (maquette)")
    toggle.focus()
    page.keyboard.press("Enter")
    panel = page.locator("#mq-panel")
    panel.wait_for(state="visible")
    assert toggle.get_attribute("aria-expanded") == "true"
    assert_no_axe_violations(page, "panneau Scénarios ouvert")
    # Un scénario de l'écran se joue depuis le panneau, au clavier.
    button = panel.locator('button[data-scenario="conversation-rouverte"]')
    button.focus()
    page.keyboard.press("Enter")
    wait_for(page, "() => document.querySelectorAll('.wl-msg-assistant').length >= 2")
    panel.locator("select").first.focus()
    page.keyboard.press("Escape")
    panel.wait_for(state="hidden")
    assert page.evaluate("() => document.activeElement.textContent") == "Scénarios (maquette)"


def test_every_route_module_exports_mount_and_scenarios(page, base_url):
    open_route(page, base_url, "/")
    for route in load_routes():
        screen = route.get("screen") or route["slug"]
        exports = page.evaluate(
            "async (screen) => { const m = await import(`./js/screens/${screen}.js`);"
            " return { mount: typeof (m.mount ?? m.render), scenarios: Array.isArray(m.scenarios) }; }",
            screen,
        )
        assert exports == {"mount": "function", "scenarios": True}, f"{screen} : {exports}"
