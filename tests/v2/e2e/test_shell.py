"""Coquille de la v2 (story 1.8) dans un vrai navigateur : rendu sans API, navigation, thème,
projection, responsive et accessibilité (axe-core, clair et sombre, sans exclusion)."""

from __future__ import annotations

import time

import pytest
from axe_playwright_python.sync_playwright import Axe

PLANNED_REASON = "Pas encore disponible dans cette préversion"
MODULES = ["Accueil", "Arène", "Documents", "Agents", "Sobriété", "Modèles"]
SHELL_BUDGET_MS = 300
SCREEN_CHANGE_BUDGET_MS = 150


def wait_for(page, condition: str, timeout_s: float = 10.0) -> None:
    """Attend qu'une fonction JS `() => ...` rende une valeur vraie. Sans `wait_for_function` :
    il évalue une chaîne (`eval`), ce que la politique de contenu de la page refuse."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if page.evaluate(condition):
            return
        time.sleep(0.05)
    pytest.fail(f"condition jamais vraie : {condition}")


def wait_ready(page) -> None:
    wait_for(page, "() => performance.getEntriesByName('shell-ready').length > 0")


@pytest.fixture
def shell(page, server):
    """La coquille ouverte à l'Accueil, prête (routeur démarré)."""
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    return page


def module_links(page):
    return page.locator("#module-list a")


def open_display_menu(page):
    page.get_by_role("button", name="Affichage").click()
    page.locator("#display-panel").wait_for(state="visible")


def assert_no_axe_violations(page, what: str) -> None:
    results = Axe().run(page)
    assert results.violations_count == 0, f"{what} :\n{results.generate_report()}"


def assert_no_horizontal_scroll(page) -> None:
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, f"défilement horizontal de {overflow} px"


# --- Rendu sans API, aucune requête hors de 127.0.0.1 -----------------------------------------


def shell_timings(page, url: str) -> dict:
    page.goto(url)
    wait_ready(page)
    wait_for(page, "() => performance.getEntriesByName('first-contentful-paint').length > 0")
    return page.evaluate(
        """() => ({
            fcp: performance.getEntriesByName('first-contentful-paint')[0].startTime,
            ready: performance.getEntriesByName('shell-ready')[0].startTime,
        })"""
    )


def test_shell_renders_under_300_ms_without_waiting_for_the_api_ollama_stopped(page, server):
    # Un premier chargement chauffe le serveur et le navigateur (imports, polices système) ; la
    # mesure est la médiane de cinq chargements suivants, que la charge de la machine fausse moins.
    # Chaque appel `fetch` vers `/api/` note si le repère `shell-ready` était déjà posé.
    page.add_init_script(
        """(() => {
            const original = window.fetch.bind(window);
            window.__apiCalls = [];
            window.fetch = (input, init) => {
                const url = String(input instanceof Request ? input.url : input);
                if (url.includes('/api/')) window.__apiCalls.push({
                    url, ready: performance.getEntriesByName('shell-ready').length > 0,
                });
                return original(input, init);
            };
        })()"""
    )
    shell_timings(page, f"{server.base_url}/")
    runs = [shell_timings(page, f"{server.base_url}/") for _ in range(5)]
    fcp = sorted(run["fcp"] for run in runs)[2]
    ready = sorted(run["ready"] for run in runs)[2]
    assert fcp < SHELL_BUDGET_MS and ready < SHELL_BUDGET_MS, runs
    assert len(module_links(page).all()) == len(MODULES)
    # Rien de `/api/` n'est demandé avant que la coquille soit rendue : la barre haute branche son
    # flux après le repère `shell-ready` (story 1.9), elle ne l'attend pas.
    wait_for(
        page, "() => window.__apiCalls.some((call) => call.url.endsWith('/api/system/stream'))"
    )
    calls = page.evaluate("() => window.__apiCalls")
    assert [call for call in calls if not call["ready"]] == [], calls


def test_every_request_stays_on_127_0_0_1(shell, server, traffic):
    open_display_menu(shell)
    shell.reload()
    wait_ready(shell)
    assert traffic.urls
    assert all(url.startswith(server.base_url + "/") for url in traffic.urls), traffic.urls
    assert traffic.blocked == []


# --- Structure et navigation ------------------------------------------------------------------


def test_landmarks_language_and_skip_link(shell):
    assert shell.get_attribute("html", "lang") == "fr"
    for landmark in ("banner", "navigation", "main", "contentinfo"):
        assert shell.get_by_role(landmark).count() == 1, landmark
    assert shell.locator("h1").filter(visible=True).count() == 1

    shell.keyboard.press("Tab")
    skip = shell.get_by_role("link", name="Aller au contenu")
    assert skip.evaluate("el => el === document.activeElement")
    assert skip.bounding_box()["y"] >= 0  # visible quand il a le focus
    shell.keyboard.press("Enter")
    assert shell.evaluate("document.activeElement.id") == "main"
    assert shell.evaluate("location.hash") in (
        "",
        "#/",
    )  # le lien d'évitement ne change pas de route


def test_six_modules_planned_ones_are_disabled_focusable_links_with_a_visible_reason(shell):
    links = module_links(shell)
    assert [link.inner_text().strip() for link in links.all()] == MODULES

    home = links.nth(0)
    assert home.get_attribute("href") == "#/" and home.get_attribute("aria-current") == "page"
    assert home.get_attribute("aria-disabled") is None

    arena = links.nth(1)  # Arène : disponible depuis la story 2.2 (Chat libre)
    assert (
        arena.get_attribute("href") == "#/arene/chat"
        and arena.get_attribute("aria-disabled") is None
    )

    documents = links.nth(2)  # Documents : disponible depuis la story 4.2 (Base documentaire)
    assert (
        documents.get_attribute("href") == "#/documents/base"
        and documents.get_attribute("aria-disabled") is None
    )

    for index in range(3, len(MODULES)):
        link = links.nth(index)
        assert link.evaluate("el => el.tagName") == "A"
        assert link.get_attribute("href") is None
        assert link.get_attribute("aria-disabled") == "true"
        link.focus()
        assert link.evaluate("el => el === document.activeElement")
        reason = link.evaluate(
            "el => document.getElementById(el.getAttribute('aria-describedby')).innerText"
        )
        assert reason == PLANNED_REASON
    assert shell.get_by_text(PLANNED_REASON).filter(visible=True).count() == len(MODULES) - 3


@pytest.mark.parametrize("route", ["#/arene/comparer", "#/sobriete", "#/n-importe-quoi", "#main"])
def test_planned_or_unknown_route_goes_back_to_home(page, server, route):
    page.goto(f"{server.base_url}/{route}")
    wait_ready(page)
    assert page.evaluate("location.hash") == "#/"
    assert page.title() == "Accueil · WaveLocalAI"
    assert page.get_by_role("heading", level=1).inner_text() == "Accueil"


def test_each_route_sets_title_focuses_the_h1_announces_and_is_fast(shell):
    # Écran de test branché sur le registre réel : le routeur est celui de l'application.
    shell.evaluate(
        """async () => {
            const registry = await import('/static/core/registry.js');
            const screen = registry.SCREENS.find((s) => s.id === 'arena-compare');
            window.__calls = [];
            screen.status = 'available';
            screen.load = async () => {
                window.__calls.push('load');
                return {
                    mount(host, params) {
                        window.__calls.push('mount:' + JSON.stringify(params));
                        const h1 = document.createElement('h1');
                        h1.textContent = 'Arène';
                        host.append(h1);
                        return () => window.__calls.push('unmount');
                    },
                };
            };
        }"""
    )
    measure = """(hash) => new Promise((resolve) => {
        const started = performance.now();
        location.hash = hash;
        const check = () => {
            const active = document.activeElement;
            if (active && active.tagName === 'H1' && active.offsetParent !== null) {
                resolve(performance.now() - started);
            } else requestAnimationFrame(check);
        };
        check();
    })"""
    # Aller sur un écran chargé à la demande.
    elapsed = shell.evaluate(measure, "#/arene/comparer")
    assert elapsed < SCREEN_CHANGE_BUDGET_MS
    assert shell.title() == "Arène · WaveLocalAI"
    assert shell.evaluate("document.activeElement.textContent") == "Arène"
    wait_for(shell, "() => document.getElementById('announcer').textContent === 'Écran Arène'")

    # Revenir à l'Accueil, puis à l'écran déjà visité : gardé en mémoire (un seul load et mount).
    shell.evaluate("(hash) => { location.hash = hash }", "#/")
    wait_for(shell, "() => document.title === 'Accueil · WaveLocalAI'")
    assert shell.evaluate("document.activeElement.textContent") == "Accueil"
    elapsed = shell.evaluate(measure, "#/arene/comparer")
    assert elapsed < SCREEN_CHANGE_BUDGET_MS
    assert shell.evaluate("window.__calls") == ["load", "mount:{}"]

    # Un paramètre de chemin différent démonte l'écran puis le remonte avec ses paramètres.
    shell.evaluate("(hash) => { location.hash = hash }", "#/arene/comparer/abc123")
    wait_for(shell, "() => window.__calls.length === 4")
    assert shell.evaluate("window.__calls") == [
        "load",
        "mount:{}",
        "unmount",
        'mount:{"run_id":"abc123"}',
    ]


# --- Responsive -------------------------------------------------------------------------------


def test_links_fold_into_a_menu_under_1024_px(shell):
    assert shell.locator("#nav-toggle").is_hidden()
    assert module_links(shell).first.is_visible()

    shell.set_viewport_size({"width": 800, "height": 900})
    toggle = shell.get_by_role("button", name="Menu")
    assert toggle.is_visible() and toggle.get_attribute("aria-expanded") == "false"
    assert module_links(shell).first.is_hidden()

    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "true"
    assert module_links(shell).first.is_visible()

    shell.keyboard.press("Escape")
    assert toggle.get_attribute("aria-expanded") == "false"
    assert shell.evaluate("document.activeElement.id") == "nav-toggle"


@pytest.mark.parametrize("width", [320, 375, 768, 1024, 1440])
def test_shell_has_no_horizontal_scroll(shell, width):
    shell.set_viewport_size({"width": width, "height": 900})
    assert_no_horizontal_scroll(shell)
    if width < 1024:
        shell.get_by_role("button", name="Menu").click()
        assert_no_horizontal_scroll(shell)
    open_display_menu(shell)
    assert_no_horizontal_scroll(shell)
    # Le panneau reste entièrement dans la fenêtre.
    box = shell.locator("#display-panel").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width


# --- Menu Affichage : thème, projection, mémoire ----------------------------------------------


def test_dark_theme_applies_without_reload_and_is_remembered(shell):
    shell.evaluate("window.__same_page = true")
    assert shell.get_attribute("html", "data-theme") == "light"

    open_display_menu(shell)
    shell.get_by_label("Sombre").check()
    assert shell.get_attribute("html", "data-theme") == "dark"
    assert shell.evaluate("window.__same_page") is True  # aucun rechargement
    assert shell.evaluate("localStorage.getItem('wl.theme')") == "dark"
    background = shell.evaluate("getComputedStyle(document.body).backgroundColor")
    assert background == "rgb(10, 10, 20)"  # surface-dark #0A0A14

    shell.reload()
    wait_ready(shell)
    assert shell.get_attribute("html", "data-theme") == "dark"
    open_display_menu(shell)
    assert shell.get_by_label("Sombre").is_checked()


def test_projection_mode_scales_type_hides_the_footer_and_is_remembered(shell):
    base = shell.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize)")
    assert shell.get_by_role("contentinfo").is_visible()

    open_display_menu(shell)
    shell.get_by_label("Mode projection").check()
    assert shell.get_attribute("html", "data-projection") == "true"
    scaled = shell.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize)")
    assert scaled == pytest.approx(base * 9 / 7, rel=0.01)
    assert shell.get_by_role("contentinfo").is_hidden()
    assert shell.evaluate("localStorage.getItem('wl.projection')") == "1"

    shell.reload()
    wait_ready(shell)
    assert shell.get_attribute("html", "data-projection") == "true"


def test_display_menu_closes_with_escape_and_returns_the_focus(shell):
    open_display_menu(shell)
    shell.keyboard.press("Escape")
    assert shell.locator("#display-panel").is_hidden()
    assert shell.evaluate("document.activeElement.id") == "display-button"


def test_theme_still_applies_when_storage_is_blocked(page, server):
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', { get() { throw new Error('bloqué'); } })"
    )
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    open_display_menu(page)
    page.get_by_label("Sombre").check()
    assert page.get_attribute("html", "data-theme") == "dark"


def test_font_stack_is_aptos_then_local_inter_then_sans_serif(shell, server):
    stack = shell.evaluate("getComputedStyle(document.body).fontFamily")
    assert stack == "Aptos, Inter, sans-serif"
    families = shell.evaluate("[...document.fonts].map((face) => face.family.replaceAll('\"', ''))")
    assert families.count("Inter") == 2  # droite et italique
    font = shell.request.get(f"{server.base_url}/static/fonts/InterVariable.woff2")
    assert font.ok and font.headers["content-type"] == "font/woff2"


# --- Accessibilité : axe-core sans exclusion, clair et sombre ---------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_shell(shell, theme):
    if theme == "dark":
        open_display_menu(shell)
        shell.get_by_label("Sombre").check()
        shell.keyboard.press("Escape")
    assert shell.get_attribute("html", "data-theme") == theme
    assert_no_axe_violations(shell, f"coquille, thème {theme}")

    open_display_menu(shell)
    assert_no_axe_violations(shell, f"coquille avec le menu Affichage ouvert, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_folded_menu_at_320_px(shell, theme):
    shell.set_viewport_size({"width": 320, "height": 800})
    if theme == "dark":
        open_display_menu(shell)
        shell.get_by_label("Sombre").check()
        shell.keyboard.press("Escape")
    shell.get_by_role("button", name="Menu").click()
    assert_no_axe_violations(shell, f"menu replié ouvert à 320 px, thème {theme}")


def test_axe_finds_no_violation_in_projection_mode(shell):
    open_display_menu(shell)
    shell.get_by_label("Mode projection").check()
    assert_no_axe_violations(shell, "mode projection")
