"""Écran Sobriété, historique carbone et remise à zéro (story 5.2) dans un vrai navigateur : période
et affichage, graphique en barres et tableau triable, session sans mesure, « Remettre le compteur
à zéro » (désactivé quand la session est vide, run actif, focus, annonce), accessibilité (axe-core,
clair et sombre), aucun appel avant `shell-ready`, aucune requête hors de 127.0.0.1.

Les sessions du passé viennent de `POST /api/test/carbon-sessions` (la CI ne peut pas attendre sept
jours) ; Ollama n'est jamais le vrai."""

from __future__ import annotations

import time

import pytest

from .test_home import set_tab_hidden
from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready
from .test_sobriety import GPU, UNMEASURED, norm, open_screen, screen_text, set_gpu, wait_screen
from .test_topbar import LOCAL_CO2, NBSP, apply_theme, run_scripted

HISTORY = '[data-screen="sobriety"] .sob-history'
EMPTY = "Aucune session mesurée pour l'instant."
EMPTY_WINDOW = f"Choisissez «{NBSP}Tout{NBSP}» pour voir les sessions plus anciennes."
CURRENT_NOTE = "La session en cours n'apparaît qu'une fois close."
RESET = "Remettre le compteur à zéro"
NOTHING = f"Rien à remettre à zéro{NBSP}: aucune réponse dans cette session."
DONE = "Compteur remis à zéro. La session précédente est dans l'historique."


def leaves(count: int, mg: float | None = 2.0, origin: str = "local") -> list[dict]:
    return [{"kind": "chat", "origin": origin, "mg": mg} for _ in range(count)]


def seed(page, server, *sessions) -> None:
    response = page.request.post(
        f"{server.base_url}/api/test/carbon-sessions", data={"sessions": list(sessions)}
    )
    assert response.ok, response.text()


def wait_history(page, timeout_s: float = 10.0) -> None:
    wait_for(
        page,
        f"() => document.querySelector({HISTORY!r})?.getAttribute('aria-busy') === 'false'",
        timeout_s,
    )


def open_history(backend, page, *sessions, width: int | None = None, gpu=GPU):
    """Un serveur neuf, ces sessions closes, l'écran ouvert et l'historique lu."""
    server = backend.start()
    set_gpu(page, server, gpu)
    if sessions:
        seed(page, server, *sessions)
    if width:
        page.set_viewport_size({"width": width, "height": 900})
    open_screen(page, server)
    wait_history(page)
    return server


def history_text(page) -> str:
    return norm(page.locator(HISTORY).inner_text())


def bars(page) -> int:
    return page.locator(f"{HISTORY} rect.wl-chart-bar").count()


def rows(page) -> list[list[str]]:
    return [
        [cell.inner_text() for cell in row.locator("th, td").all()]
        for row in page.locator(f"{HISTORY} tbody tr").all()
    ]


def segment(page, name: str):
    return page.get_by_role("radio", name=name, exact=True)


def reset_button(page):
    return page.get_by_role("button", name=RESET)


WEEK = {"days_ago": 1, "leaves": leaves(2) + leaves(1, 4.0, "cloud")}  # 8 mg : 4 local, 4 cloud
MONTH = {"days_ago": 10, "leaves": leaves(1, 3.0)}
OLD = {"days_ago": 40, "leaves": leaves(1, 5.0)}


# --- Historique -------------------------------------------------------------------------------


def test_without_any_session_the_history_says_so_and_draws_no_empty_chart(backend, page):
    open_history(backend, page)
    assert EMPTY in history_text(page)
    assert CURRENT_NOTE in history_text(page)
    assert page.locator(f"{HISTORY} svg.wl-chart-svg").count() == 0
    assert page.locator(f"{HISTORY} table").count() == 0
    # `all_text_contents()` (story 9.9) : `.section-label` les met en majuscules par CSS.
    headings = page.locator('[data-screen="sobriety"] h2').all_text_contents()
    assert headings == ["Santé du système", "Empreinte carbone de cette session", "Historique"]


def test_the_default_is_seven_days_as_a_chart_with_its_title_description_and_table_button(
    backend, page
):
    open_history(backend, page, WEEK, MONTH, OLD)
    assert segment(page, "7 jours").get_attribute("aria-checked") == "true"
    assert segment(page, "Graphique").get_attribute("aria-checked") == "true"
    assert bars(page) == 1  # une seule session close dans les sept derniers jours
    svg = page.locator(f"{HISTORY} svg.wl-chart-svg")
    assert svg.get_attribute("role") == "img"
    assert svg.locator("title").first.text_content() == "Émissions par session"
    assert "Une barre par session" in svg.locator("desc").text_content()
    assert page.locator(f"{HISTORY} wl-chart-svg").get_by_role("button", name="Voir le tableau")
    assert "milligramme" in history_text(page) and CURRENT_NOTE in history_text(page)
    assert f"8{NBSP}mg" in svg.locator("rect.wl-chart-bar title").text_content()
    assert svg.locator("text.wl-chart-value").text_content() == "8"  # valeur au-dessus de la barre


def test_the_period_segments_choose_seven_thirty_days_or_all(backend, page):
    open_history(backend, page, WEEK, MONTH, OLD)
    segment(page, "30 jours").click()
    wait_for(
        page,
        f"() => document.querySelectorAll('{HISTORY} rect.wl-chart-bar').length === 2",
    )
    segment(page, "Tout").click()
    wait_for(
        page,
        f"() => document.querySelectorAll('{HISTORY} rect.wl-chart-bar').length === 3",
    )
    segment(page, "7 jours").click()
    wait_for(
        page,
        f"() => document.querySelectorAll('{HISTORY} rect.wl-chart-bar').length === 1",
    )
    # La flèche droite change de segment au clavier, comme les autres groupes de segments.
    segment(page, "7 jours").focus()
    page.keyboard.press("ArrowRight")
    assert segment(page, "30 jours").get_attribute("aria-checked") == "true"


def test_a_period_without_session_points_to_all_when_older_sessions_exist(backend, page):
    open_history(backend, page, {"days_ago": 20, "leaves": leaves(1)})
    assert EMPTY_WINDOW in history_text(page)
    assert page.locator(f"{HISTORY} svg.wl-chart-svg").count() == 0
    segment(page, "Tout").click()
    wait_for(page, f"() => document.querySelectorAll('{HISTORY} rect.wl-chart-bar').length === 1")


def test_the_table_gives_the_same_content_sortable_with_the_keyboard(backend, page):
    open_history(backend, page, WEEK, MONTH, OLD)
    segment(page, "Tout").click()
    segment(page, "Tableau").click()
    wait_for(page, f"() => document.querySelectorAll('{HISTORY} tbody tr').length === 3")
    headers = page.locator(f"{HISTORY} thead th").all_inner_texts()
    assert [h.strip() for h in headers] == [
        "Début", "Fin", "Total", "Local", "Cloud (estimé)", "Non mesurables",
    ]  # fmt: skip
    table = rows(page)
    # Tri initial : la plus récente d'abord ; Total, Local et Cloud en mg seulement.
    assert [row[2] for row in table] == [f"8{NBSP}mg", f"3{NBSP}mg", f"5{NBSP}mg"]
    assert table[0][3] == f"4{NBSP}mg" and table[0][4] == f"4{NBSP}mg"
    assert table[1][4] == "aucun appel" and table[0][5] == "0"
    assert page.locator(f"{HISTORY} caption").inner_text() == (
        "Émissions de CO₂ par session, en milligrammes"
    )
    # Tri au clavier : Entrée sur « Total » ordonne du plus petit au plus grand.
    total = page.locator(f"{HISTORY} th button", has_text="Total")
    total.focus()
    page.keyboard.press("Enter")
    assert [row[2] for row in rows(page)] == [f"3{NBSP}mg", f"5{NBSP}mg", f"8{NBSP}mg"]
    assert page.locator(f"{HISTORY} th", has_text="Total").get_attribute("aria-sort") == "ascending"
    page.keyboard.press("Enter")
    assert [row[2] for row in rows(page)] == [f"8{NBSP}mg", f"5{NBSP}mg", f"3{NBSP}mg"]


def test_see_the_table_moves_from_the_chart_to_the_table(backend, page):
    open_history(backend, page, WEEK)
    page.get_by_role("button", name="Voir le tableau").click()
    assert segment(page, "Tableau").get_attribute("aria-checked") == "true"
    assert page.locator(f"{HISTORY} table").count() == 1
    assert page.evaluate("document.activeElement.classList.contains('wl-table-wrap')")


def test_a_session_with_nothing_measured_keeps_its_place_without_a_bar(backend, page):
    open_history(
        backend,
        page,
        WEEK,
        {"days_ago": 2, "leaves": leaves(2, None)},  # deux réponses non mesurables
    )
    assert bars(page) == 1  # une barre : la session mesurée
    svg = page.locator(f"{HISTORY} svg.wl-chart-svg")
    assert svg.locator("text.wl-chart-unmeasured").count() == 1
    unmeasured = svg.locator("text.wl-chart-unmeasured")
    assert unmeasured.evaluate("e => e.firstChild.textContent") == "non mesuré"
    assert svg.locator("line.wl-chart-bar-none").count() == 1  # un trait en pointillés, jamais 0
    segment(page, "Tableau").click()
    table = rows(page)
    assert len(table) == 2
    unmeasured = next(row for row in table if row[5] == "2")
    assert unmeasured[2] == "non mesuré" and unmeasured[3] == "non mesuré"
    assert unmeasured[4] == "aucun appel"
    assert f"0{NBSP}mg" not in history_text(page)


def test_below_640_px_the_table_is_the_default_and_the_choice_holds(backend, page):
    open_history(backend, page, WEEK, MONTH, width=500)
    assert segment(page, "Tableau").get_attribute("aria-checked") == "true"
    assert (
        page.locator(f"{HISTORY} table").count() == 1
        and page.locator(f"{HISTORY} svg.wl-chart-svg").count() == 0
    )
    segment(page, "Graphique").click()
    segment(page, "30 jours").click()
    wait_history(page)
    assert segment(page, "Graphique").get_attribute("aria-checked") == "true"  # le choix tient
    wait_for(page, f"() => document.querySelectorAll('{HISTORY} rect.wl-chart-bar').length === 2")


def test_the_session_in_progress_enters_the_history_only_once_closed(
    backend, page_tolerating_failed_requests
):
    page = page_tolerating_failed_requests
    server = open_history(backend, page)
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    wait_screen(page, f"1,8{NBSP}mg")
    page.wait_for_timeout(300)
    assert EMPTY in history_text(page) and CURRENT_NOTE in history_text(page)
    # Le serveur redémarre : la session est close (nouvelle `app_session` au démarrage).
    backend.stop()
    server = backend.start()
    page.goto(f"{server.base_url}/#/sobriete")
    wait_ready(page)
    wait_history(page)
    wait_for(page, f"() => document.querySelectorAll('{HISTORY} rect.wl-chart-bar').length === 1")


# --- Remettre le compteur à zéro --------------------------------------------------------------


def test_the_reset_is_disabled_with_its_reason_while_the_session_is_empty(backend, page):
    server = open_history(backend, page)
    button = reset_button(page)
    assert button.is_disabled()
    reason = page.locator("#sob-reset-why")
    assert reason.is_visible() and reason.inner_text() == NOTHING  # écrite, jamais en infobulle
    assert button.get_attribute("aria-describedby") == "sob-reset-why"
    run_scripted(page, server, kind="chat", origin="local", co2=UNMEASURED)
    wait_for(page, "() => !document.querySelector('.sob-reset-button').disabled")
    assert reason.is_hidden()  # une réponse non mesurable compte : le compteur n'est plus vide


def test_the_reset_starts_a_new_session_and_the_closed_one_enters_the_history(backend, page):
    server = open_history(backend, page)
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    run_scripted(page, server, kind="rag", origin="cloud", co2={**LOCAL_CO2, "mg": 0.9})
    wait_screen(page, f"2,7{NBSP}mg")
    assert EMPTY in history_text(page)
    before = page.request.get(f"{server.base_url}/api/carbon/session").json()["app_session"]["id"]

    reset_button(page).click()
    wait_screen(page, "Aucune réponse mesurée dans cette session")
    assert f"2,7{NBSP}mg" not in screen_text(page)
    assert page.locator(".sob-reset-status").inner_text() == DONE  # la fin est annoncée
    assert page.locator(".sob-reset-status").get_attribute("role") == "status"
    assert (
        reset_button(page).is_disabled() and page.locator("#sob-reset-why").inner_text() == NOTHING
    )
    # Le focus passe au titre de la section : le bouton désactivé ne peut pas le garder.
    assert page.evaluate("document.activeElement.id") == "sob-carbon-title"
    assert page.locator("#co2-value").inner_text() != f"2,7{NBSP}mg"  # la barre haute repart de 0
    after = page.request.get(f"{server.base_url}/api/carbon/session").json()
    assert after["app_session"]["id"] != before and after["total_mg"] == 0.0

    wait_for(page, f"() => document.querySelectorAll('{HISTORY} rect.wl-chart-bar').length === 1")
    segment(page, "Tableau").click()
    (row,) = rows(page)
    assert row[2] == f"2,7{NBSP}mg" and row[3] == f"1,8{NBSP}mg" and row[4] == f"0,9{NBSP}mg"


def test_a_run_active_during_the_reset_stays_counted_in_the_session_where_it_started(backend, page):
    server = open_history(backend, page)
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    slow = page.request.post(
        f"{server.base_url}/api/test/runs",
        data={
            "kind": "rag",
            "origin": "cloud",
            "script": [{"text": "a"}, {"sleep_s": 1.5}, {"text": "b"}],
            "co2": {"mg": 7.0, "method": "ecologits", "estimated": True},
        },
    )
    assert slow.ok, slow.text()
    reset_button(page).click()
    wait_screen(page, "Aucune réponse mesurée dans cette session")
    # La réponse lente finit après la remise à zéro : la nouvelle session reste vide, la session
    # close la compte (l'historique se relit à chaque `carbon_updated`).
    segment(page, "Tableau").click()
    wait_for(
        page,
        f"() => document.querySelector({HISTORY!r})?.innerText.includes('8,8')",
        timeout_s=15,
    )
    (row,) = rows(page)
    assert row[2] == f"8,8{NBSP}mg" and row[4] == f"7{NBSP}mg"
    assert "Aucune réponse mesurée dans cette session" in screen_text(page)


def test_a_failed_reset_keeps_the_counter_and_says_why(backend, page_tolerating_failed_requests):
    page = page_tolerating_failed_requests
    server = open_history(backend, page)
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    wait_screen(page, f"1,8{NBSP}mg")
    page.route(
        "**/api/carbon/session/reset",
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body='{"code":"internal","message":"Erreur interne.","action":"Réessayez.","detail":{}}',
        ),
    )
    reset_button(page).click()
    wait_for(page, "() => document.querySelector('.sob-reset-status').textContent !== ''")
    assert page.locator(".sob-reset-status").inner_text() == "Erreur interne. Réessayez."
    assert f"1,8{NBSP}mg" in screen_text(page) and reset_button(page).is_enabled()


# --- Appels, hors ligne, onglet masqué --------------------------------------------------------


def test_no_history_call_before_shell_ready_and_one_read_per_period_and_per_answer(
    backend, page, traffic
):
    server = backend.start()
    set_gpu(page, server, GPU)
    page.add_init_script(
        """(() => {
            window.__early = [];
            const original = window.fetch;
            window.fetch = (input, init) => {
                const url = typeof input === 'string' ? input : input.url;
                if (url.includes('/api/carbon/') && performance.getEntriesByName('shell-ready').length === 0) {
                    window.__early.push(url);
                }
                return original(input, init);
            };
        })();"""
    )
    open_screen(page, server)
    wait_history(page)
    assert page.evaluate("window.__early") == []  # AD-15 : rien avant le repère `shell-ready`
    reads = lambda: sum(1 for url in traffic.urls if "/api/carbon/history" in url)  # noqa: E731
    first = reads()
    assert first >= 1
    page.wait_for_timeout(2500)
    assert reads() == first  # jamais en boucle
    segment(page, "30 jours").click()
    wait_history(page)
    page.wait_for_timeout(300)
    assert reads() > first


def test_a_hidden_tab_does_not_read_the_history_and_the_return_does(backend, page, traffic):
    server = open_history(backend, page)
    reads = lambda: sum(1 for url in traffic.urls if "/api/carbon/history" in url)  # noqa: E731
    set_tab_hidden(page, True)
    before = reads()
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    page.wait_for_timeout(2500)
    assert reads() == before  # onglet masqué : rien n'est relu
    set_tab_hidden(page, False)
    wait_screen(page, f"1,8{NBSP}mg")
    page.wait_for_timeout(300)
    assert reads() > before


def test_a_screen_opened_in_a_hidden_tab_reads_the_history_only_once_shown(backend, page, traffic):
    server = backend.start()
    set_gpu(page, server, GPU)
    seed(page, server, WEEK)
    page.add_init_script(
        "Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });"
        "Object.defineProperty(document, 'visibilityState',"
        " { configurable: true, get: () => 'hidden' });"
    )
    page.goto(f"{server.base_url}/#/sobriete")
    wait_ready(page)
    page.wait_for_timeout(1000)
    reads = lambda: sum(1 for url in traffic.urls if "/api/carbon/history" in url)  # noqa: E731
    assert reads() == 0  # onglet masqué dès l'ouverture : rien n'est lu
    set_tab_hidden(page, False)
    wait_history(page)
    assert reads() == 1 and bars(page) == 1


def test_the_history_never_leaves_127_0_0_1(backend, page, traffic):
    server = open_history(backend, page, WEEK, MONTH)
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    reset_button(page).click()
    segment(page, "Tableau").click()
    page.wait_for_timeout(500)
    assert traffic.urls and all(url.startswith(server.base_url) for url in traffic.urls)
    assert not traffic.blocked


# --- Accessibilité et mise en page ------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_in_the_history_and_the_reset(backend, page, theme):
    server = open_history(
        backend, page, WEEK, MONTH, {"days_ago": 2, "leaves": leaves(2, None)}, OLD
    )
    apply_theme(page, theme)
    assert_no_axe_violations(page, f"Sobriété, historique en graphique, thème {theme}")
    segment(page, "Tout").click()
    wait_for(page, f"() => document.querySelectorAll('{HISTORY} rect.wl-chart-bar').length === 3")
    assert_no_axe_violations(page, f"Sobriété, historique complet, thème {theme}")
    segment(page, "Tableau").click()
    assert_no_axe_violations(page, f"Sobriété, historique en tableau, thème {theme}")
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    wait_for(page, "() => !document.querySelector('.sob-reset-button').disabled")
    assert_no_axe_violations(page, f"Sobriété, remise à zéro active, thème {theme}")
    reset_button(page).click()
    wait_screen(page, "Aucune réponse mesurée dans cette session")
    assert_no_axe_violations(page, f"Sobriété, remise à zéro faite, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_for_an_empty_history_and_a_period_without_session(
    backend, page, theme
):
    open_history(backend, page, {"days_ago": 20, "leaves": leaves(1)})
    apply_theme(page, theme)
    assert_no_axe_violations(page, f"Sobriété, période vide, thème {theme}")
    segment(page, "Tout").click()
    assert_no_axe_violations(page, f"Sobriété, un seul résultat, thème {theme}")


@pytest.mark.parametrize("width", [320, 768, 1440])
@pytest.mark.parametrize("view", ["Graphique", "Tableau"])
def test_the_history_has_no_horizontal_scroll(backend, page, width, view):
    sessions = [{"days_ago": index / 4, "leaves": leaves(2)} for index in range(1, 26)]
    open_history(backend, page, *sessions, width=width)
    segment(page, "Tout").click()
    segment(page, view).click()
    page.wait_for_timeout(300)
    assert_no_horizontal_scroll(page)
    box = page.locator(HISTORY).bounding_box()
    assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= width + 1


def test_many_sessions_keep_the_chart_readable_with_thinned_labels(backend, page):
    sessions = [{"days_ago": index / 4, "leaves": leaves(2)} for index in range(1, 26)]
    open_history(backend, page, *sessions, width=1440)
    segment(page, "Tout").click()
    wait_for(page, f"() => document.querySelectorAll('{HISTORY} rect.wl-chart-bar').length === 25")
    ticks = page.locator(f'{HISTORY} svg text.wl-chart-tick[text-anchor="middle"]')
    assert 0 < ticks.count() < 25  # des étiquettes d'abscisse en moins, jamais l'une sur l'autre
    boxes = ticks.evaluate_all("els => els.map((e) => e.getBoundingClientRect().toJSON())")
    boxes.sort(key=lambda box: box["x"])
    for left, right in zip(boxes, boxes[1:], strict=False):
        assert left["x"] + left["width"] <= right["x"] + 1, "deux étiquettes se chevauchent"


# --- Échelle des barres (fonctions pures de core/chart-scale.js) ------------------------------


def test_the_bar_scale_helpers(page, server):
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    got = page.evaluate(
        """async () => {
            const s = await import('/static/core/chart-scale.js');
            const few = s.barBands(4, 0, 400);
            const many = s.barBands(50, 0, 500);
            return {
                few: [few.step, few.width, few.center(0), few.center(3)],
                many: [many.step, many.width],
                heights: [
                    s.barHeight(0, 10, 100), s.barHeight(null, 10, 100), s.barHeight(-3, 10, 100),
                    s.barHeight(0.001, 10, 100), s.barHeight(5, 10, 100), s.barHeight(10, 10, 100),
                    s.barHeight(99, 10, 100), s.barHeight(5, 0, 100),
                ],
                strides: [s.labelStride(100, 90), s.labelStride(10, 90), s.labelStride(0, 90)],
            };
        }"""
    )
    assert got["few"] == [100, 56, 50, 350]  # une barre ne dépasse jamais 56 px
    assert got["many"] == [10, pytest.approx(7)]  # 70 % de la bande
    # Nulle, absente, négative ou axe nul : pas de barre ; une valeur non nulle garde 2 px.
    assert got["heights"] == [0, 0, 0, 2, 50, 100, 100, 0]
    assert got["strides"] == [1, 10, 1]
