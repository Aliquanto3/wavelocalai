"""Accueil (story 1.11) dans un vrai navigateur : titre, quatre cartes d'état en direct, squelette,
Ollama arrêté puis démarré, pause sur `visibilitychange`, modules, accessibilité (axe-core, clair et
sombre, sans exclusion) et aucune requête hors de 127.0.0.1.

Ollama n'est jamais le vrai : le serveur pointe sur un port fermé (« arrêté »), ou sur FakeOllama
que le test allume et éteint."""

from __future__ import annotations

import re
import time

import pytest

from .test_discussion import import_docs
from .test_shell import (
    assert_no_axe_violations,
    assert_no_horizontal_scroll,
    open_display_menu,
    wait_for,
    wait_ready,
)
from .test_topbar import LOCAL_CO2, NBSP, apply_theme, run_scripted

BUDGET_MS = 5000  # « en 5 secondes » : de l'ouverture de la page à des cartes remplies
CARDS = ["system", "mode", "cpu", "memory"]
STREAM_SUFFIX = "/api/system/stream"


def card(page, name: str):
    return page.locator(f'[data-card="{name}"]')


def card_text(page, name: str) -> str:
    return " ".join(card(page, name).inner_text().split())


def wait_card(page, name: str, text: str, timeout_s: float = 10.0) -> None:
    """Attend que la carte contienne `text`."""
    wait_for(
        page,
        f"() => document.querySelector('[data-card=\"{name}\"]')?.innerText.includes({text!r})",
        timeout_s,
    )


def cards_filled(page) -> bool:
    return page.evaluate(
        """() => ['system', 'cpu', 'memory'].every((name) => {
            const card = document.querySelector(`[data-card="${name}"]`);
            return card && card.getAttribute('aria-busy') === 'false';
        })"""
    )


def stream_requests(traffic) -> int:
    return sum(1 for url in traffic.urls if url.endswith(STREAM_SUFFIX))


def set_tab_hidden(page, hidden: bool) -> None:
    """Simule un onglet masqué puis de retour (le navigateur de test n'a qu'un onglet visible)."""
    page.evaluate(
        """(hidden) => {
            Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
            Object.defineProperty(document, 'visibilityState', {
                configurable: true,
                get: () => (hidden ? 'hidden' : 'visible'),
            });
            document.dispatchEvent(new Event('visibilitychange'));
        }""",
        hidden,
    )


@pytest.fixture
def home(page, server):
    """L'Accueil ouvert, Ollama arrêté, les cartes remplies."""
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_card(page, "system", "Indisponible")
    return page


@pytest.fixture
def home_with_ollama(backend, fake_ollama, page):
    """L'Accueil sur un serveur neuf dont Ollama (le FakeOllama) répond."""
    backend.ollama_port = fake_ollama.port
    fake_ollama.start()
    server = backend.start()
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_card(page, "system", "Disponible")
    return page, server, fake_ollama


# --- Contenu ----------------------------------------------------------------------------------


def test_home_shows_a_single_title_the_tagline_and_four_filled_cards(home):
    assert home.locator("h1:visible").count() == 1
    assert home.locator("h1:visible").inner_text() == "Accueil"
    assert home.title() == "Accueil · WaveLocalAI"
    assert home.locator(".lead").inner_text() == (
        "Le démonstrateur d'IA générative souveraine, frugale et sécurisée."
    )
    assert home.locator("[data-card]").count() == len(CARDS)
    wait_for(home, "() => document.querySelector('[data-card=\"cpu\"]').innerText.includes('%')")
    wait_for(
        home, "() => document.querySelector('[data-card=\"memory\"]').innerText.includes('Go')"
    )
    # Formats fr-FR : entier et espace insécable devant « % », virgule décimale devant « Go ».
    cpu = card(home, "cpu").locator(".wl-metric-value").inner_text()
    assert re.fullmatch(rf"\d+{NBSP}%", cpu), cpu
    memory = card(home, "memory").locator(".wl-metric-value").inner_text()
    assert re.fullmatch(rf"\d+(,\d+)?{NBSP}Go", memory), memory
    assert re.search(rf"sur \d+(,\d+)?{NBSP}Go", card(home, "memory").inner_text())
    assert "en direct" in card_text(home, "cpu")


def test_mode_card_says_local_then_cloud_when_the_cloud_is_allowed(home):
    mode = card(home, "mode")
    assert mode.locator("wl-badge").inner_text().strip() == "Local"
    assert "Les données restent sur ce poste." in card_text(home, "mode")
    assert "CO₂ de la session" in card_text(home, "mode")

    home.get_by_role("switch", name="Autoriser le cloud").check()
    wait_card(home, "mode", "Cloud")
    assert mode.locator("wl-badge").inner_text().strip() == "Cloud"
    assert "Le cloud est autorisé" in card_text(home, "mode")


def test_mode_card_follows_the_co2_of_the_session(backend, page):
    server = backend.start()
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_card(page, "mode", "aucune réponse mesurée")
    run_scripted(page, server, origin="local", co2=LOCAL_CO2)
    wait_card(page, "mode", f"1,8{NBSP}mg")


def test_ollama_stopped_the_system_card_says_it_and_what_to_do_while_links_stay_active(home):
    system = card(home, "system")
    assert system.locator(".wl-metric-value").inner_text() == "Indisponible"
    text = card_text(home, "system")
    assert "Démarrez Ollama, puis cliquez sur Réessayer" in text
    assert "Aucun modèle local disponible" in text
    assert system.get_by_role("button", name="Réessayer").is_visible()
    # Les liens restent actifs : la marque et le lien « Accueil » de la navigation.
    assert home.locator("a.brand").get_attribute("href") == "#/"
    assert home.locator('#module-list a[href="#/"]').is_visible()
    home.locator("a.brand").click()
    assert home.evaluate("location.hash") in ("", "#/")
    assert home.locator("h1:visible").inner_text() == "Accueil"


def test_ollama_started_then_stopped_the_system_card_follows(home_with_ollama):
    page, _server, fake_ollama = home_with_ollama
    system = card(page, "system")
    assert system.locator(".wl-metric-value").inner_text() == "Disponible"
    assert "Ollama 0.9.9" in card_text(page, "system")
    wait_card(page, "system", "1 modèle chargé en mémoire")
    assert "Aucun modèle local disponible" not in card_text(page, "system")
    assert system.locator("button").count() == 1  # « Réessayer », masqué tant qu'Ollama répond
    assert system.locator("button").is_hidden()

    fake_ollama.stop()
    wait_card(page, "system", "Indisponible")
    assert "Aucun modèle local disponible" in card_text(page, "system")


def test_retry_button_shows_the_wait_then_the_new_state(backend, fake_ollama, page):
    backend.ollama_port = fake_ollama.port
    server = backend.start()
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_card(page, "system", "Indisponible")
    button = card(page, "system").get_by_role("button", name="Réessayer")
    button.focus()

    fake_ollama.start()
    # Le clic et la lecture dans la même tâche : l'état d'attente est posé de façon synchrone.
    waiting = page.evaluate(
        """() => {
            const button = document.querySelector('[data-card="system"] button');
            button.click();
            return [button.textContent, button.getAttribute('aria-disabled')];
        }"""
    )
    assert waiting == ["Vérification en cours…", "true"]
    wait_card(page, "system", "Disponible", timeout_s=6)
    assert button.is_hidden()
    # Revue 1.11 : le focus ne tombe pas sur `body` quand le bouton disparaît.
    assert page.evaluate("document.activeElement.dataset.card") == "system"


# --- Squelette et connexion perdue ------------------------------------------------------------


def test_cards_show_a_skeleton_while_the_stream_has_not_answered_never_a_blank_page(
    page_tolerating_failed_requests, server
):
    page = page_tolerating_failed_requests
    page.route(f"**{STREAM_SUFFIX}", lambda route: route.abort())
    page.goto(f"{server.base_url}/")
    wait_ready(page)

    assert page.locator("h1:visible").inner_text() == "Accueil"
    for name in ("system", "cpu", "memory"):
        assert card(page, name).get_attribute("aria-busy") == "true", name
        assert card(page, name).locator(".home-skeleton").is_visible(), name
        assert "Chargement…" in card(page, name).locator(".home-skeleton").text_content()
    assert not cards_filled(page)

    # Le serveur ne répond plus : « Inconnu », jamais une valeur périmée ni un 0.
    wait_card(page, "system", "Inconnu")
    wait_card(page, "cpu", "inconnu")
    assert "Connexion au serveur perdue." in card_text(page, "system")
    assert card(page, "system").get_attribute("aria-busy") == "false"

    page.unroute(f"**{STREAM_SUFFIX}")
    wait_card(page, "system", "Indisponible", timeout_s=15)
    wait_for(page, "() => document.querySelector('[data-card=\"cpu\"]').innerText.includes('%')")


def test_the_cards_are_filled_in_under_5_seconds(page, server):
    page.goto(f"{server.base_url}/")  # un premier chargement chauffe le serveur et le navigateur
    wait_ready(page)
    elapsed = []
    for _ in range(3):
        page.goto(f"{server.base_url}/")
        started = time.monotonic()
        wait_for(page, "() => document.querySelector('[data-card]') !== null")
        deadline = started + 10
        while not cards_filled(page):
            assert time.monotonic() < deadline, "les cartes ne se remplissent pas"
            time.sleep(0.02)
        elapsed.append(page.evaluate("performance.now()"))
    assert max(elapsed) < BUDGET_MS, f"cartes remplies après {elapsed} ms"


# --- Pause de l'onglet masqué -----------------------------------------------------------------


def test_a_hidden_tab_pauses_the_cards_and_the_return_resumes_them(home_with_ollama, traffic):
    page, server, fake_ollama = home_with_ollama
    host = page.locator('[data-screen="home"]')
    assert host.get_attribute("data-live") == "true"
    opened = stream_requests(traffic)
    assert opened == 1

    set_tab_hidden(page, True)
    assert host.get_attribute("data-live") == "false"
    fake_ollama.stop()
    run_scripted(page, server, origin="local", co2=LOCAL_CO2)  # un carbon_updated manqué
    time.sleep(5)  # plus de deux échantillons du flux (2 s)
    assert card(page, "system").locator(".wl-metric-value").inner_text() == "Disponible"
    assert page.locator("#ollama-label").inner_text() == "Ollama disponible"
    assert stream_requests(traffic) == opened

    set_tab_hidden(page, False)
    assert host.get_attribute("data-live") == "true"
    wait_card(page, "system", "Indisponible", timeout_s=8)
    assert stream_requests(traffic) == opened + 1  # un flux, rouvert au retour
    # La somme du CO2 relue à la reconnexion : la réponse jouée pendant la pause est comptée.
    wait_card(page, "mode", f"1,8{NBSP}mg")
    assert page.locator("#co2-value").inner_text() == f"1,8{NBSP}mg"


def test_a_hidden_tab_stops_the_health_retries_and_the_return_restarts_them(
    page_tolerating_failed_requests, server
):
    # Revue 1.11 : `connection.status` reste `open` pendant la pause ; la relecture de
    # `/api/health` (identité inconnue, revue 1.9) ne doit pas tourner onglet masqué. Les
    # événements de Playwright ne sont relevés que pendant ses appels : `wait_for_timeout`.
    page = page_tolerating_failed_requests
    health = []
    page.on("request", lambda request: health.append(1) if "/api/health" in request.url else None)
    page.route("**/api/health", lambda route, request: route.abort())
    page.goto(f"{server.base_url}/")
    wait_card(page, "system", "Indisponible")
    page.wait_for_timeout(4500)
    assert len(health) >= 2  # la relecture tourne tant que le flux est ouvert

    set_tab_hidden(page, True)
    page.wait_for_timeout(500)  # une lecture déjà partie peut finir
    before = len(health)
    page.wait_for_timeout(5000)  # plus de deux délais de reprise (2 s)
    assert len(health) == before

    set_tab_hidden(page, False)
    page.wait_for_timeout(3000)
    assert len(health) > before


# --- Modules ----------------------------------------------------------------------------------


def test_planned_modules_have_no_card_on_the_home(home):
    # L'Arène (story 2.2), la Base documentaire (story 4.2), Sobriété (story 5.1) et l'Agent seul
    # (story 6.4) sont livrés : leurs liens seuls figurent ; les modules à venir n'en ont aucun.
    assert home.locator(".home-module-link").count() == 4
    assert home.locator('[data-screen="home"] a.home-module-link[href^="#/sobriete"]').count() == 1
    assert home.locator('[data-screen="home"] a.home-module-link[href^="#/arene"]').count() == 1
    assert home.locator('[data-screen="home"] a.home-module-link[href^="#/documents"]').count() == 1
    assert home.locator('[data-screen="home"] a.home-module-link[href^="#/agents"]').count() == 1
    # La barre haute les montre désactivés, avec leur raison.
    assert (
        "Pas encore disponible dans cette préversion" in home.locator("#module-list").inner_text()
    )


def mount_second_home(page, every_module: bool = False) -> None:
    """Rend l'écran Arène disponible dans le registre (ou le premier écran de chaque module, avec
    `every_module`), puis monte un second Accueil : ses liens de modules. Le premier est masqué
    pour que les identifiants restent uniques."""
    page.evaluate(
        """async (everyModule) => {
            const registry = await import('/static/core/registry.js');
            const modules = registry.MODULES.filter((module) =>
                everyModule ? module.id !== 'home' : module.id === 'arena');
            for (const module of modules) module.screens[0].status = 'available';
            document.querySelector('[data-screen="home"]').hidden = true;
            const home = await import('/static/screens/home.js');
            const host = document.createElement('section');
            host.id = 'second-home';
            document.getElementById('main').append(host);
            home.mount(host, {});
        }""",
        every_module,
    )


def test_an_available_module_gets_a_link_with_its_summary(home):
    mount_second_home(home)
    links = home.locator("#second-home .home-module-link")
    # L'Arène, les Documents (Discussion, story 4.5), l'Agent seul (story 6.4), puis Sobriété (5.1).
    assert links.count() == 4
    assert links.nth(3).get_attribute("href") == "#/sobriete"
    assert links.nth(2).get_attribute("href") == "#/agents/seul"
    assert links.nth(1).get_attribute("href") == "#/documents"
    # Le résumé de la carte « Documents » est celui de la base (story 4.9) ; base vide ici.
    summary = links.nth(1).locator(".home-module-summary")
    wait_for(
        home,
        '() => document.querySelector(\'#second-home a[href="#/documents"] '
        ".home-module-summary')?.textContent.includes('indexé')",
    )
    assert summary.inner_text() == "0 document indexé · 0 extrait"
    assert links.first.get_attribute("href") == "#/arene/chat"
    assert "Arène" in links.first.inner_text()
    assert "Comparer plusieurs petits modèles" in links.first.inner_text()
    assert f"question{NBSP}:" in links.first.inner_text()
    # D-10 : le nom court, le nom long et le résumé de chaque module disponible.
    assert links.nth(1).locator(".home-module-name").inner_text() == "Documents"
    assert links.nth(1).locator(".home-module-long").inner_text() == "Assistant documentaire"
    assert links.first.locator(".home-module-name").inner_text() == "Arène"
    assert links.first.locator(".home-module-long").inner_text() == "Arène des modèles"
    # La carte « Démo recommandée » (story 3.6) n'est pas un lien de module : `test_home_demo.py`.
    assert home.locator("#second-home [data-demo]").count() == 1


def test_the_documents_card_keeps_its_tagline_when_the_base_cannot_be_read(
    backend, page_tolerating_failed_requests
):
    """Sans réponse du serveur, la carte garde sa phrase d'accroche : jamais un chiffre inventé."""
    page = page_tolerating_failed_requests
    server = backend.start()
    page.route(
        re.compile(r"/api/rag/documents$"),
        lambda route: route.fulfill(status=500, content_type="application/json", body="{}"),
    )
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_card(page, "system", "Indisponible")
    page.wait_for_timeout(500)
    link = page.locator('[data-screen="home"] a.home-module-link[href="#/documents"]')
    assert link.locator(".home-module-summary").inner_text() == (
        "Interroger ses documents et voir les sources."
    )


def test_the_documents_card_counts_the_indexed_documents_and_their_extracts(backend, page):
    """« N documents indexés · M extraits » : les documents prêts, lus sur le serveur, au singulier
    jusqu'à 1 (comme la Discussion)."""
    server = backend.start()
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    summary = page.locator(
        '[data-screen="home"] a.home-module-link[href="#/documents"] .home-module-summary'
    )
    wait_for(
        page,
        '() => document.querySelector(\'[data-screen="home"] a[href="#/documents"] '
        ".home-module-summary')?.textContent === '0 document indexé · 0 extrait'",
    )
    import_docs(
        page,
        server,
        **{
            "a.txt": ("text/plain", b"Un texte."),
            "b.txt": ("text/plain", b"Un autre texte."),
        },
    )
    page.evaluate("location.hash = '#/documents/base'")
    wait_for(page, "() => document.querySelector('[data-screen=\"home\"]').hidden")
    page.evaluate("location.hash = '#/'")  # le routeur garde l'Accueil monté : il relit la base
    wait_for(
        page,
        '() => document.querySelector(\'[data-screen="home"] a[href="#/documents"] '
        ".home-module-summary')?.textContent === '2 documents indexés · 2 extraits'",
    )
    assert summary.inner_text() == "2 documents indexés · 2 extraits"


def test_the_base_summary_is_read_once_per_display_and_once_per_tab_return(backend, page, traffic):
    """Une lecture au premier affichage (le routeur monte l'Accueil masqué puis l'affiche : pas de
    double appel), une par retour sur l'Accueil, une par retour de l'onglet ; aucune ailleurs."""
    server = backend.start()

    def reads() -> int:
        return sum(1 for url in traffic.urls if url.endswith("/api/rag/documents"))

    page.goto(f"{server.base_url}/")
    wait_ready(page)
    wait_card(page, "system", "Indisponible")
    page.wait_for_timeout(800)
    assert reads() == 1
    page.evaluate("location.hash = '#/documents/base'")
    wait_for(page, "() => document.querySelector('[data-screen=\"home\"]').hidden")
    page.wait_for_timeout(500)
    before = reads()  # la Base lit la même route : on ne compte que ce que l'Accueil ajoute
    set_tab_hidden(page, True)
    set_tab_hidden(page, False)
    page.wait_for_timeout(500)
    after_tab = reads()  # l'Accueil masqué ne relit rien (la Base peut relire la sienne)
    page.evaluate("location.hash = '#/'")
    wait_for(page, "() => !document.querySelector('[data-screen=\"home\"]').hidden")
    page.wait_for_timeout(500)
    assert reads() == after_tab + 1
    set_tab_hidden(page, True)
    set_tab_hidden(page, False)
    page.wait_for_timeout(500)
    assert reads() == after_tab + 2
    assert before <= after_tab


# Nom court du menu, nom long (EXPERIENCE.md, D-10), lien (premier écran du module).
MODULE_LINKS = [
    ("Arène", "Arène des modèles", "#/arene/chat"),
    ("Documents", "Assistant documentaire", "#/documents"),
    ("Agents", "Agents autonomes", "#/agents/seul"),
    ("Sobriété", "Sobriété et matériel", "#/sobriete"),
    ("Modèles", "Installation et choix par usage", "#/modeles"),
]


def test_an_available_module_gets_a_link_with_short_name_long_name_and_summary(home):
    """D-10 : le nom court du menu en titre, le nom long en sous-titre, puis la phrase de résumé ;
    le `h1` reste « Accueil » (D-9)."""
    mount_second_home(home, every_module=True)
    links = home.locator("#second-home .home-module-link")
    assert links.count() == len(MODULE_LINKS)
    for index, (short, long, href) in enumerate(MODULE_LINKS):
        link = links.nth(index)
        assert link.get_attribute("href") == href
        assert link.locator(".home-module-name").inner_text() == short
        assert link.locator(".home-module-long").inner_text() == long
        summary = link.locator(".home-module-summary").inner_text()
        assert summary and summary != long
        # Ordre de lecture : titre, sous-titre, résumé.
        assert link.inner_text().splitlines() == [short, long, summary]
        # Le nom court est celui du menu de la barre haute.
        assert home.locator(f'#module-list a[data-module] span:text-is("{short}")').count() == 1


def test_the_home_keeps_a_single_h1_accueil(home):
    mount_second_home(home, every_module=True)
    headings = home.locator("#second-home h1")
    assert headings.count() == 1 and headings.inner_text() == "Accueil"
    assert home.locator("h1:visible").count() == 1


# --- Accessibilité, mise en page et trafic ----------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_home_in_every_state(home, theme):
    apply_theme(home, theme)
    assert_no_axe_violations(home, f"Accueil, Ollama arrêté, thème {theme}")
    home.get_by_role("switch", name="Autoriser le cloud").check()
    wait_card(home, "mode", "Cloud")
    assert_no_axe_violations(home, f"Accueil, cloud autorisé, thème {theme}")
    mount_second_home(home, every_module=True)
    assert_no_axe_violations(home, f"Accueil avec tous les liens de module, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_home_with_ollama_up(home_with_ollama, theme):
    page = home_with_ollama[0]
    apply_theme(page, theme)
    wait_card(page, "system", "1 modèle chargé en mémoire")
    assert_no_axe_violations(page, f"Accueil, Ollama disponible, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_skeleton_and_the_lost_connection(
    page_tolerating_failed_requests, server, theme
):
    page = page_tolerating_failed_requests
    page.route(f"**{STREAM_SUFFIX}", lambda route: route.abort())
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    apply_theme(page, theme)
    assert card(page, "cpu").get_attribute("aria-busy") == "true"
    assert_no_axe_violations(page, f"Accueil, squelettes, thème {theme}")
    wait_card(page, "system", "Inconnu")
    assert_no_axe_violations(page, f"Accueil, connexion perdue, thème {theme}")


@pytest.mark.parametrize("width", [320, 768, 1440])
def test_the_home_has_no_horizontal_scroll(home, width):
    home.set_viewport_size({"width": width, "height": 900})
    assert_no_horizontal_scroll(home)
    box = card(home, "memory").bounding_box()
    assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= width


def test_the_home_never_leaves_127_0_0_1(home, server, traffic):
    wait_for(home, "() => document.querySelector('[data-card=\"cpu\"]').innerText.includes('%')")
    assert traffic.urls
    assert all(url.startswith(server.base_url) for url in traffic.urls), traffic.urls
    assert not traffic.blocked


@pytest.mark.parametrize("width", [320, 768, 1440])
def test_the_home_with_every_module_link_has_no_horizontal_scroll(home, width):
    mount_second_home(home, every_module=True)
    home.set_viewport_size({"width": width, "height": 900})
    assert_no_horizontal_scroll(home)
    for link in home.locator("#second-home .home-module-link").all():
        box = link.bounding_box()
        assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= width


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_home_in_system_theme_with_every_module(home, scheme):
    home.emulate_media(color_scheme=scheme)
    open_display_menu(home)
    home.get_by_label("Système").check()
    home.keyboard.press("Escape")
    assert home.get_attribute("html", "data-theme") == scheme
    mount_second_home(home, every_module=True)
    assert_no_axe_violations(home, f"Accueil, tous les modules, Système {scheme}")
    home.set_viewport_size({"width": 320, "height": 900})
    assert_no_axe_violations(home, f"Accueil, tous les modules, 320 px, Système {scheme}")
