"""Barre haute (story 1.9) dans un vrai navigateur : pastille et panneau d'Ollama, interrupteur du
cloud, CO2 de session, bandeaux de connexion, accessibilité et aucune requête hors de 127.0.0.1.

Ollama n'est jamais le vrai : le serveur pointe sur un port fermé (« arrêté »), ou sur FakeOllama
que le test allume et éteint. Le vrai Ollama de la machine n'est pas sollicité."""

from __future__ import annotations

import time

import pytest

from .test_shell import (
    assert_no_axe_violations,
    assert_no_horizontal_scroll,
    open_display_menu,
    wait_for,
    wait_ready,
)

NBSP = "\N{NO-BREAK SPACE}"
OLLAMA_DOWN = "Ollama ne répond pas"
OLLAMA_UP = "Ollama disponible"
CLOUD_HELP = (
    "Désactivé à chaque ouverture de la page. Activé, les données envoyées aux modèles cloud "
    "quittent la machine."
)
BANNER_LOST = "Connexion au serveur perdue, nouvelle tentative…"
BANNER_RESTARTED = "Le serveur a redémarré. Les exécutions en cours sont perdues."
# Échéances (non des pauses : l'attente s'arrête à l'état voulu). Le démarrage d'un serveur peut
# durer plus de 30 s sur un poste saturé, et le flux ne se reconnecte qu'après son délai de reprise.
LOST_WAIT_MS = 45_000
RESTART_WAIT_MS = 90_000


def pill(page):
    return page.locator("#ollama-button")


def wait_pill(page, text: str, timeout_s: float = 10.0) -> float:
    """Attend le libellé de la pastille Ollama ; rend les secondes écoulées."""
    started = time.monotonic()
    wait_for(
        page,
        f"() => document.getElementById('ollama-label').textContent === {text!r}",
        timeout_s,
    )
    return time.monotonic() - started


def open_panel(page, button_id: str, panel_id: str):
    page.locator(f"#{button_id}").click()
    panel = page.locator(f"#{panel_id}")
    panel.wait_for(state="visible")
    return panel


def make_screen_available(page, screen_id: str = "arena-compare") -> None:
    """Rend un second écran disponible (comme dans test_shell) pour changer d'écran."""
    page.evaluate(
        """async (id) => {
            const registry = await import('/static/core/registry.js');
            const screen = registry.SCREENS.find((s) => s.id === id);
            screen.status = 'available';
            screen.load = async () => ({
                mount(host) {
                    const h1 = document.createElement('h1');
                    h1.textContent = 'Arène';
                    host.append(h1);
                    return () => host.replaceChildren();
                },
            });
        }""",
        screen_id,
    )


def run_scripted(page, server, **body) -> None:
    """Joue un run scripté jusqu'à sa feuille comptée dans la session (deux runs du même genre ne
    tournent pas ensemble : run_busy)."""

    def counted() -> int:
        session = page.request.get(f"{server.base_url}/api/carbon/session").json()
        return session["measured_runs"] + session["unmeasurable_runs"]

    before = counted()
    response = page.request.post(f"{server.base_url}/api/test/runs", data=body)
    assert response.ok, response.text()
    deadline = time.monotonic() + 10
    while counted() == before:
        assert time.monotonic() < deadline, "la feuille n'est pas comptée"
        time.sleep(0.05)


@pytest.fixture
def bar(page, server):
    """La coquille ouverte, la barre haute branchée sur le flux (Ollama arrêté)."""
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_pill(page, OLLAMA_DOWN)
    return page


@pytest.fixture
def fresh_bar(backend, page):
    """Comme `bar`, sur un serveur neuf : la session carbone y est vide (le serveur de `bar` sert
    tout le module, et chaque run scripté y ajoute sa feuille)."""
    server = backend.start()
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_pill(page, OLLAMA_DOWN)
    return page, server


# --- Ollama -----------------------------------------------------------------------------------


def test_ollama_stopped_the_pill_says_it_in_words_and_the_panel_explains(bar):
    assert pill(bar).inner_text().strip() == OLLAMA_DOWN  # un libellé, pas la seule couleur
    assert pill(bar).get_attribute("data-state") == "down"
    panel = open_panel(bar, "ollama-button", "ollama-panel")
    assert panel.locator("#ollama-state").inner_text() == "Indisponible"
    assert panel.locator("#ollama-version").inner_text() == "inconnue"
    assert panel.locator(".wl-error-message").inner_text() == "Ollama ne répond pas sur ce poste."
    assert "Lancez Ollama" in panel.locator(".wl-error-action").inner_text()
    assert panel.get_by_role("button", name="Réessayer").is_visible()


def test_ollama_started_then_stopped_the_pill_follows_in_under_3_s(backend, fake_ollama, page):
    backend.ollama_port = fake_ollama.port
    server = backend.start()
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_pill(page, OLLAMA_DOWN)

    fake_ollama.start()
    elapsed = wait_pill(page, OLLAMA_UP)
    assert elapsed < 3.0, f"{elapsed:.1f} s pour voir Ollama démarré"
    assert pill(page).get_attribute("data-state") == "up"

    panel = open_panel(page, "ollama-button", "ollama-panel")
    assert panel.locator("#ollama-state").inner_text() == "Disponible"
    assert panel.locator("#ollama-version").inner_text() == "0.9.9"
    wait_for(page, "() => document.getElementById('ollama-loaded').textContent.includes('qwen2.5')")
    assert panel.locator("#ollama-loaded li").all_inner_texts() == [f"qwen2.5:1.5b, 2{NBSP}Go"]
    assert f"{NBSP}Go utilisés sur" in panel.locator("#ollama-memory").inner_text()
    assert panel.locator("wl-error").is_hidden()  # plus d'erreur quand tout va bien

    fake_ollama.stop()
    wait_pill(page, OLLAMA_DOWN, timeout_s=10)
    assert panel.locator("#ollama-state").inner_text() == "Indisponible"


def test_retry_asks_again_and_reports_the_new_state(backend, fake_ollama, page):
    backend.ollama_port = fake_ollama.port
    server = backend.start()
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_pill(page, OLLAMA_DOWN)
    panel = open_panel(page, "ollama-button", "ollama-panel")
    retry = panel.get_by_role("button", name="Réessayer")

    fake_ollama.start()
    retry.click()
    assert panel.locator("#ollama-retry").inner_text() == "Vérification en cours…"
    wait_pill(page, OLLAMA_UP, timeout_s=5)
    assert panel.locator("#ollama-retry").inner_text() == "Réessayer"


def test_the_pill_panel_closes_with_escape_and_hands_the_focus_back(bar):
    open_panel(bar, "ollama-button", "ollama-panel")
    bar.keyboard.press("Escape")
    assert bar.locator("#ollama-panel").is_hidden()
    assert bar.evaluate("document.activeElement.id") == "ollama-button"


def test_opening_a_panel_closes_the_others(bar):
    open_panel(bar, "ollama-button", "ollama-panel")
    open_panel(bar, "co2-button", "co2-panel")
    assert bar.locator("#ollama-panel").is_hidden()
    open_display_menu(bar)
    assert bar.locator("#co2-panel").is_hidden()


# --- Cloud ------------------------------------------------------------------------------------


def test_cloud_switch_is_off_by_default_with_its_help(bar):
    switch = bar.get_by_role("switch", name="Autoriser le cloud")
    assert not switch.is_checked()
    # L'aide est la description accessible de l'interrupteur ; le bouton d'aide la montre.
    description = bar.evaluate("() => document.getElementById('cloud-help').textContent.trim()")
    assert description == CLOUD_HELP
    assert switch.get_attribute("aria-describedby") == "cloud-help"
    bar.get_by_role("button", name="Aide sur l'autorisation du cloud").click()
    assert bar.locator("#cloud-help").inner_text() == CLOUD_HELP


def test_cloud_choice_survives_a_change_of_screen_and_never_a_reload(bar):
    make_screen_available(bar)
    assert bar.locator("#footer-text").inner_text().startswith("Les données restent sur ce poste")

    bar.get_by_role("switch", name="Autoriser le cloud").check()
    assert bar.evaluate(
        "() => import('/static/core/store.js').then((m) => m.store.get().allowCloud)"
    )
    assert "le cloud est autorisé" in bar.locator("#footer-text").inner_text().lower()

    bar.evaluate("location.hash = '#/arene/comparer'")
    wait_for(bar, "() => document.title === 'Arène · WaveLocalAI'")
    assert bar.get_by_role("switch", name="Autoriser le cloud").is_checked()
    bar.evaluate("location.hash = '#/'")
    wait_for(bar, "() => document.title === 'Accueil · WaveLocalAI'")
    assert bar.get_by_role("switch", name="Autoriser le cloud").is_checked()

    # Jamais dans localStorage (ni dans sessionStorage) : la bascule vit dans le store.
    stored = bar.evaluate(
        """() => [...Object.entries(localStorage), ...Object.entries(sessionStorage)]
            .map(([key, value]) => key + '=' + value)"""
    )
    assert not any("cloud" in item.lower() or "true" in item.lower() for item in stored), stored

    bar.reload()
    wait_ready(bar)
    switch = bar.get_by_role("switch", name="Autoriser le cloud")
    assert not switch.is_checked()
    assert not bar.evaluate(
        "() => import('/static/core/store.js').then((m) => m.store.get().allowCloud)"
    )


def test_cloud_switch_works_from_the_keyboard(bar):
    switch = bar.get_by_role("switch", name="Autoriser le cloud")
    switch.focus()
    bar.keyboard.press("Space")
    assert switch.is_checked()
    bar.keyboard.press("Space")
    assert not switch.is_checked()


# --- CO2 de session ---------------------------------------------------------------------------

LOCAL_CO2 = {"mg": 1.8, "method": "codecarbon", "estimated": False}
CLOUD_CO2 = {"mg": 0.9, "method": "ecologits", "estimated": True}


def co2_rows(page) -> dict[str, str]:
    return {
        "pill": (
            page.locator("#co2-value").inner_text()
            if page.locator("#co2-value").is_visible()
            else ""
        ),
        "total": page.locator("#co2-total").inner_text(),
        "local": page.locator("#co2-local").inner_text(),
        "cloud": page.locator("#co2-cloud").inner_text(),
        "unmeasurable": page.locator("#co2-unmeasurable").inner_text(),
    }


def test_co2_panel_follows_carbon_updated_in_milligrams_then_grams(fresh_bar):
    bar, server = fresh_bar
    bar.locator("#co2-value").wait_for(state="visible")  # la somme de la session est chargée
    panel = open_panel(bar, "co2-button", "co2-panel")
    assert co2_rows(bar) == {
        "pill": f"0{NBSP}mg",
        "total": f"0{NBSP}mg",
        "local": f"0{NBSP}mg",
        "cloud": f"0{NBSP}mg",
        "unmeasurable": "Aucune réponse",
    }

    run_scripted(bar, server, origin="local", co2=LOCAL_CO2)
    run_scripted(bar, server, origin="cloud", co2=CLOUD_CO2)
    run_scripted(bar, server, origin="cloud")  # taille inconnue : non mesurable, jamais 0
    wait_for(bar, f"() => document.getElementById('co2-total').textContent === '2,7{NBSP}mg'")
    assert co2_rows(bar) == {
        "pill": f"2,7{NBSP}mg",
        "total": f"2,7{NBSP}mg",
        "local": f"1,8{NBSP}mg",
        "cloud": f"0,9{NBSP}mg (estimé)",
        "unmeasurable": "1 réponse",
    }
    assert panel.get_by_text("ne sont pas comptées dans le total").is_visible()

    # Au-delà de 1 g, une seule unité pour le total et ses parts.
    run_scripted(bar, server, origin="local", co2={**LOCAL_CO2, "mg": 1500.0})
    wait_for(bar, f"() => document.getElementById('co2-total').textContent === '1,5{NBSP}g'")
    rows = co2_rows(bar)
    assert rows["local"] == f"1,5{NBSP}g" and rows["cloud"] == f"0,0009{NBSP}g (estimé)"


def test_a_cloud_without_any_measure_reads_non_mesurable_never_zero(fresh_bar):
    bar, server = fresh_bar
    bar.locator("#co2-value").wait_for(state="visible")
    open_panel(bar, "co2-button", "co2-panel")
    run_scripted(bar, server, origin="cloud")  # ni mesure ni estimation : jamais « 0 mg »
    wait_for(bar, "() => document.getElementById('co2-unmeasurable').textContent === '1 réponse'")
    rows = co2_rows(bar)
    assert rows["cloud"] == "non mesurable" and rows["total"] == f"0{NBSP}mg"
    run_scripted(bar, server, origin="cloud", co2=CLOUD_CO2)
    wait_for(bar, "() => document.getElementById('co2-cloud').textContent.includes('(estimé)')")
    assert co2_rows(bar)["cloud"] == f"0,9{NBSP}mg (estimé)"


def test_co2_survives_a_reload_from_the_session_endpoint(fresh_bar):
    bar, server = fresh_bar
    run_scripted(bar, server, origin="local", co2=LOCAL_CO2)
    wait_for(bar, f"() => document.getElementById('co2-value').textContent === '1,8{NBSP}mg'")
    bar.reload()
    wait_ready(bar)
    wait_for(bar, f"() => document.getElementById('co2-value').textContent === '1,8{NBSP}mg'")
    open_panel(bar, "co2-button", "co2-panel")
    assert co2_rows(bar)["local"] == f"1,8{NBSP}mg"


def test_co2_badges_and_the_disabled_sobriety_link(bar):
    panel = open_panel(bar, "co2-button", "co2-panel")
    assert panel.locator("wl-badge").all_inner_texts() == ["Local", "Cloud"]
    link = panel.get_by_role("link", name="Détails dans Sobriété")
    # L'écran Sobriété n'existe pas encore : lien désactivé, raison visible, focalisable.
    assert link.get_attribute("aria-disabled") == "true" and link.get_attribute("href") is None
    assert (
        panel.locator("#co2-link-reason").inner_text()
        == "Pas encore disponible dans cette préversion"
    )
    link.focus()
    assert bar.evaluate("document.activeElement.id") == "co2-link"
    link.click(force=True)  # désactivé : le clic n'y fait rien
    assert bar.evaluate("location.hash") in ("", "#/")


def test_the_sobriety_link_goes_live_once_the_screen_is_available(bar):
    make_screen_available(bar, "sobriety")
    bar.evaluate("() => import('/static/core/topbar.js').then((m) => m.bindSobrietyLink())")
    link = open_panel(bar, "co2-button", "co2-panel").get_by_role(
        "link", name="Détails dans Sobriété"
    )
    assert link.get_attribute("href") == "#/sobriete"
    assert link.get_attribute("aria-disabled") is None
    assert bar.locator("#co2-link-reason").is_hidden()


# --- Connexion perdue, serveur redémarré ------------------------------------------------------


def test_banner_appears_after_three_failures_and_goes_when_the_server_is_back(
    backend, page_tolerating_failed_requests
):
    page = page_tolerating_failed_requests
    server = backend.start()
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_pill(page, OLLAMA_DOWN)
    banner = page.locator("#connection-banner")
    assert banner.is_hidden()

    backend.stop()
    banner.wait_for(state="visible", timeout=LOST_WAIT_MS)
    assert banner.inner_text().strip() == BANNER_LOST
    failures = page.evaluate(
        "() => import('/static/core/store.js').then((m) => m.store.get().connection.failures)"
    )
    assert failures >= 3
    # L'état d'Ollama n'est plus connu : la pastille ne ment pas.
    assert pill(page).inner_text().strip() == "Ollama, état inconnu"
    assert_no_horizontal_scroll(page)

    backend.start()
    banner.wait_for(state="hidden", timeout=RESTART_WAIT_MS)


def test_a_restarted_server_is_announced_with_a_reload_button(
    backend, page_tolerating_failed_requests
):
    page = page_tolerating_failed_requests
    server = backend.start()
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_pill(page, OLLAMA_DOWN)
    wait_for(page, "() => document.getElementById('restart-banner').hidden")

    backend.stop()
    page.locator("#connection-banner").wait_for(state="visible", timeout=LOST_WAIT_MS)
    backend.start()
    restarted = page.locator("#restart-banner")
    restarted.wait_for(state="visible", timeout=RESTART_WAIT_MS)
    assert BANNER_RESTARTED in restarted.inner_text()
    assert restarted.get_attribute("role") == "alert"

    page.evaluate("window.__same_page = true")
    restarted.get_by_role("button", name="Recharger").click()
    wait_ready(page)
    assert page.evaluate("window.__same_page") is None  # la page s'est rechargée
    assert page.locator("#restart-banner").is_hidden()


# --- Accessibilité, responsive, trafic --------------------------------------------------------


def apply_theme(page, theme: str) -> None:
    if theme == "dark":
        open_display_menu(page)
        page.get_by_label("Sombre").check()
        page.keyboard.press("Escape")
    assert page.get_attribute("html", "data-theme") == theme


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_top_bar_in_every_state(bar, server, theme):
    apply_theme(bar, theme)
    run_scripted(bar, server, origin="local", co2=LOCAL_CO2)
    run_scripted(bar, server, origin="cloud")
    wait_for(
        bar, "() => document.getElementById('co2-unmeasurable').textContent !== 'Aucune réponse'"
    )
    assert_no_axe_violations(bar, f"barre haute fermée, thème {theme}")

    for button, panel in (
        ("ollama-button", "ollama-panel"),
        ("co2-button", "co2-panel"),
        ("cloud-help-button", "cloud-help"),
    ):
        open_panel(bar, button, panel)
        assert_no_axe_violations(bar, f"panneau {panel} ouvert, thème {theme}")
        bar.keyboard.press("Escape")

    bar.get_by_role("switch", name="Autoriser le cloud").check()
    assert_no_axe_violations(bar, f"cloud autorisé, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_with_the_connection_banners(
    backend, page_tolerating_failed_requests, theme
):
    page = page_tolerating_failed_requests
    server = backend.start()
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    apply_theme(page, theme)
    backend.stop()
    page.locator("#connection-banner").wait_for(state="visible", timeout=LOST_WAIT_MS)
    assert_no_axe_violations(page, f"bandeau de connexion perdue, thème {theme}")
    page.evaluate(
        "() => import('/static/core/store.js').then((m) => m.store.set({ serverRestarted: true }))"
    )
    page.locator("#restart-banner").wait_for(state="visible")
    assert_no_axe_violations(page, f"bandeau de redémarrage, thème {theme}")


@pytest.mark.parametrize("width", [320, 768, 1024, 1440])
def test_top_bar_has_no_horizontal_scroll_and_panels_stay_in_the_window(bar, server, width):
    run_scripted(bar, server, origin="local", co2=LOCAL_CO2)
    bar.set_viewport_size({"width": width, "height": 900})
    assert_no_horizontal_scroll(bar)
    for button, panel in (
        ("ollama-button", "ollama-panel"),
        ("co2-button", "co2-panel"),
        ("cloud-help-button", "cloud-help"),
    ):
        open_panel(bar, button, panel)
        assert_no_horizontal_scroll(bar)
        box = bar.locator(f"#{panel}").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width, (panel, box)
        bar.keyboard.press("Escape")


def test_the_module_menu_still_folds_under_1024_px_with_the_tools_in_the_bar(bar):
    bar.set_viewport_size({"width": 800, "height": 900})
    assert bar.get_by_role("button", name="Menu").is_visible()
    assert bar.locator("#module-list a").first.is_hidden()
    assert pill(bar).is_visible() and bar.locator("#co2-button").is_visible()
    assert bar.get_by_role("switch", name="Autoriser le cloud").is_visible()


def test_the_top_bar_never_leaves_127_0_0_1(bar, server, traffic):
    open_panel(bar, "ollama-button", "ollama-panel")
    open_panel(bar, "co2-button", "co2-panel")
    bar.reload()
    wait_ready(bar)
    wait_pill(bar, OLLAMA_DOWN)
    assert traffic.api_calls()  # la barre parle bien au serveur...
    assert all(url.startswith(server.base_url + "/") for url in traffic.urls), traffic.urls
    assert traffic.blocked == []  # ...et à lui seul


def test_only_one_system_stream_is_open_for_the_whole_page(bar, server, traffic):
    make_screen_available(bar)
    bar.evaluate("location.hash = '#/arene/comparer'")
    wait_for(bar, "() => document.title === 'Arène · WaveLocalAI'")
    bar.evaluate("location.hash = '#/'")
    assert sum(1 for url in traffic.urls if url.endswith("/api/system/stream")) == 1
