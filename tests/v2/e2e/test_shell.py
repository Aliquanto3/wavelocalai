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

    documents = links.nth(2)  # Documents : disponible depuis la story 4.5 (Discussion)
    assert (
        documents.get_attribute("href") == "#/documents"
        and documents.get_attribute("aria-disabled") is None
    )

    sobriety = links.nth(4)  # Sobriété : disponible depuis la story 5.1
    assert (
        sobriety.get_attribute("href") == "#/sobriete"
        and sobriety.get_attribute("aria-disabled") is None
    )

    models = links.nth(5)  # Modèles : disponible depuis la story 5.3 (installation)
    assert (
        models.get_attribute("href") == "#/modeles"
        and models.get_attribute("aria-disabled") is None
    )

    for index in (3,):  # Agents : à venir
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
    assert shell.get_by_text(PLANNED_REASON).filter(visible=True).count() == len(MODULES) - 5


# Les routes de la maquette (D-8) sont `planned` : taper l'adresse renvoie à l'Accueil.
MOCKUP_ROUTES = [
    "#/arene/references",
    "#/arene/banc/run-1",
    "#/documents/evaluation/run-1",
    "#/agents/equipe/run-1",
    "#/modeles/qwen2.5%3A1.5b",
]


@pytest.mark.parametrize(
    "route",
    ["#/arene/banc", "#/n-importe-quoi", "#main", *MOCKUP_ROUTES],
)
def test_planned_or_unknown_route_goes_back_to_home(page, server, route):
    page.goto(f"{server.base_url}/{route}")
    wait_ready(page)
    assert page.evaluate("location.hash") == "#/"
    assert page.title() == "Accueil · WaveLocalAI"
    assert page.get_by_role("heading", level=1).inner_text() == "Accueil"


def test_a_planned_mockup_route_has_no_active_link_anywhere(shell):
    """D-8 : ni l'Accueil ni la barre haute n'ont de lien actif vers une route de la maquette ;
    les onglets de l'Arène (écrans à venir) sont des liens désactivés, sans `href`."""
    for prefix in ("#/arene/references", "#/arene/banc", "#/documents/evaluation"):
        assert shell.locator(f'a[href^="{prefix}"]').count() == 0, prefix
    for prefix in ("#/agents/equipe",):
        assert shell.locator(f'a[href^="{prefix}"]').count() == 0, prefix


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


def set_system_scheme(page, scheme: str) -> None:
    page.emulate_media(color_scheme=scheme)


def choose_theme(page, label: str) -> None:
    open_display_menu(page)
    page.get_by_label(label).check()
    page.keyboard.press("Escape")


def test_the_system_theme_follows_prefers_color_scheme_live_and_is_remembered(shell):
    shell.evaluate("window.__same_page = true")
    open_display_menu(shell)
    values = [radio.get_attribute("value") for radio in shell.locator('input[name="theme"]').all()]
    assert values == ["light", "dark", "system"]
    shell.keyboard.press("Escape")

    set_system_scheme(shell, "dark")
    choose_theme(shell, "Système")
    assert shell.get_attribute("html", "data-theme") == "dark"
    assert shell.get_attribute("html", "data-theme-choice") == "system"
    assert shell.evaluate("localStorage.getItem('wl.theme')") == "system"
    assert shell.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(10, 10, 20)"

    # Le réglage du système change pendant que la page est ouverte : le thème suit, sans recharger.
    set_system_scheme(shell, "light")
    wait_for(shell, "() => document.documentElement.dataset.theme === 'light'")
    assert shell.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(255, 255, 255)"
    set_system_scheme(shell, "dark")
    wait_for(shell, "() => document.documentElement.dataset.theme === 'dark'")
    assert shell.evaluate("window.__same_page") is True

    shell.reload()
    wait_ready(shell)
    assert shell.get_attribute("html", "data-theme") == "dark"
    assert shell.get_attribute("html", "data-theme-choice") == "system"
    open_display_menu(shell)
    assert shell.get_by_label("Système").is_checked()


def test_an_explicit_choice_ignores_the_system_and_light_stays_the_default(page, server):
    set_system_scheme(page, "dark")  # un système sombre ne change pas le défaut : Clair
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    assert page.get_attribute("html", "data-theme") == "light"
    assert page.get_attribute("html", "data-theme-choice") == "light"
    open_display_menu(page)
    assert page.get_by_label("Clair").is_checked()
    page.keyboard.press("Escape")

    choose_theme(page, "Clair")
    set_system_scheme(page, "light")
    set_system_scheme(page, "dark")
    assert page.get_attribute("html", "data-theme") == "light"  # Clair choisi : système sans effet

    choose_theme(page, "Système")
    assert page.get_attribute("html", "data-theme") == "dark"
    choose_theme(page, "Sombre")
    set_system_scheme(page, "light")
    assert page.get_attribute("html", "data-theme") == "dark"


def test_the_system_theme_still_applies_when_storage_is_blocked(page, server):
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', { get() { throw new Error('bloqué'); } })"
    )
    set_system_scheme(page, "dark")
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    choose_theme(page, "Système")
    assert page.get_attribute("html", "data-theme") == "dark"
    set_system_scheme(page, "light")
    wait_for(page, "() => document.documentElement.dataset.theme === 'light'")


SWITCH_LOOK = """(selector) => {
    const input = document.querySelector(selector);
    const label = input.closest('label');
    const track = getComputedStyle(input);
    return {
        role: input.getAttribute('role'),
        type: input.type,
        structure: label.className + '>' + input.parentElement.className + '>'
            + [...input.parentElement.children].map((el) => el.tagName.toLowerCase()).join('+'),
        width: track.width,
        height: track.height,
        radius: track.borderTopLeftRadius,
        borderStyle: track.borderTopStyle,
        border: track.borderTopColor,
        background: track.backgroundColor,
        thumb: getComputedStyle(input, '::before').backgroundColor,
        check: getComputedStyle(input.parentElement.querySelector('.switch-check')).opacity,
        label: label.innerText.trim(),
    };
}"""
CLOUD = "#cloud-switch"
PROJECTION = 'input[name="projection"]'


def switch_look(page, selector: str) -> dict:
    """Rendu de la piste, du curseur et de l'icône d'un interrupteur."""
    return page.evaluate(SWITCH_LOOK, selector)


def test_projection_and_cloud_are_switches_with_the_same_wl_switch_rendering(shell):
    open_display_menu(shell)
    cloud, projection = switch_look(shell, CLOUD), switch_look(shell, PROJECTION)
    for look in (cloud, projection):
        assert (look["role"], look["type"]) == ("switch", "checkbox")
        assert look["structure"] == "switch>switch-box>input+svg"
    shared = ["width", "height", "radius", "borderStyle", "border", "background", "thumb", "check"]
    assert {k: cloud[k] for k in shared} == {k: projection[k] for k in shared}
    assert (cloud["label"], projection["label"]) == ("Autoriser le cloud", "Mode projection")
    # Éteint : piste surface-alt bordée ink-secondary, curseur surface, icône cachée.
    assert cloud["background"] == "rgb(246, 245, 250)" and cloud["border"] == "rgb(74, 74, 94)"
    assert cloud["thumb"] == "rgb(255, 255, 255)" and cloud["check"] == "0"
    assert cloud["radius"] != "0px" and cloud["width"] == "44px" and cloud["height"] == "24px"


@pytest.mark.parametrize(
    ("theme", "fill"), [("light", "rgb(69, 29, 199)"), ("dark", "rgb(106, 77, 230)")]
)
def test_switch_state_reads_in_the_shape_not_only_in_the_color(shell, theme, fill):
    if theme == "dark":
        choose_theme(shell, "Sombre")
    open_display_menu(shell)
    shell.get_by_label("Mode projection").check()
    shell.locator(CLOUD).check()  # un clic hors du menu Affichage le referme
    open_display_menu(shell)
    for selector in (CLOUD, PROJECTION):
        # La piste change de couleur en 0,15 s (transition) : on lit l'état final.
        wait_for(
            shell,
            f"() => getComputedStyle(document.querySelector('{selector}')).backgroundColor"
            f" === '{fill}'",
        )
        on = switch_look(shell, selector)
        assert on["background"] == fill and on["check"] == "1", selector
    # La forme change aussi : l'icône `check` est dans le curseur, passé de gauche à droite.
    offsets = shell.evaluate(
        """() => ['#cloud-switch', 'input[name="projection"]'].map((selector) => {
            const input = document.querySelector(selector);
            return input.parentElement.querySelector('.switch-check').getBoundingClientRect().left
                - input.getBoundingClientRect().left;
        })"""
    )
    assert all(offset > 15 for offset in offsets), offsets
    shell.locator(CLOUD).uncheck()
    assert switch_look(shell, CLOUD)["check"] == "0"


def test_projection_switch_works_from_the_keyboard(shell):
    open_display_menu(shell)
    projection = shell.get_by_role("switch", name="Mode projection")
    projection.focus()
    shell.keyboard.press("Space")
    assert projection.is_checked() and shell.get_attribute("html", "data-projection") == "true"
    shell.keyboard.press("Space")
    assert not projection.is_checked()
    assert shell.get_attribute("html", "data-projection") == "false"


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
    shell.keyboard.press("Escape")
    assert_no_axe_violations(shell, "mode projection, menu fermé")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_in_projection_mode_with_every_theme(shell, theme):
    if theme == "dark":
        choose_theme(shell, "Sombre")
    open_display_menu(shell)
    shell.get_by_label("Mode projection").check()
    shell.locator(CLOUD).check()
    assert_no_axe_violations(shell, f"mode projection, interrupteurs activés, thème {theme}")
    shell.set_viewport_size({"width": 320, "height": 800})
    assert_no_axe_violations(shell, f"mode projection à 320 px, thème {theme}")
    assert_no_horizontal_scroll(shell)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_shell_and_the_home_in_system_theme(shell, scheme):
    set_system_scheme(shell, scheme)
    choose_theme(shell, "Système")
    assert shell.get_attribute("html", "data-theme") == scheme
    assert shell.get_by_role("heading", level=1).inner_text() == "Accueil"
    assert_no_axe_violations(shell, f"coquille et Accueil, Système {scheme}")
    open_display_menu(shell)
    assert_no_axe_violations(shell, f"menu Affichage ouvert, Système {scheme}")
    shell.set_viewport_size({"width": 320, "height": 800})
    assert_no_axe_violations(shell, f"menu Affichage à 320 px, Système {scheme}")
    assert_no_horizontal_scroll(shell)
    # Le système change : le thème suit, et la page reste sans violation.
    other = "dark" if scheme == "light" else "light"
    set_system_scheme(shell, other)
    wait_for(shell, f"() => document.documentElement.dataset.theme === '{other}'")
    assert_no_axe_violations(shell, f"après le changement du système vers {other}")
