"""Rouvrir, exporter, relancer et effacer une Arène (story 3.6) dans un vrai navigateur, sur le vrai
serveur. Les lanes sont des `fake` scriptées (route de test), le juge note 70 partout.

Rouvrir par `#/arene/comparer/<run_id>` reconstruit l'écran depuis la base : le flux rejoué, puis
l'instantané du run (`GET /api/runs/{id}`) pour le verdict, les actions et le CO2 complété d'une lane
arrêtée. Aucun modèle n'est relancé : le test relève les requêtes de la page.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from pathlib import Path

import pytest

from .test_arena import (  # noqa: F401  (`cancel_leftover_runs` est une fixture automatique)
    DONE,
    JUDGE_DEFAULT,
    MODELS,
    NBSP,
    STARTED,
    cancel_leftover_runs,
    install_models,
    lane,
    launch,
    scripted,
    verdict,
    wait_banner,
)
from .test_arena_results import co2, ok_lane, wait_names
from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready

JUDGE = {"script": verdict(70), "origin": "local"}


def post_run(page, server, lanes, prompt="Que pèse un nuage ?", criteria=None) -> str:
    """Lance une Arène par la route de test, avec ses critères et son juge, et attend sa fin."""
    data = {
        "prompt": prompt,
        "criteria": criteria or [],
        "allow_cloud": False,
        "lanes": lanes,
        "judge": {"tag": JUDGE_DEFAULT, **JUDGE},
    }
    response = page.request.post(f"{server.base_url}/api/test/arena", data=data)
    assert response.ok, response.text()
    run_id = response.json()["run_id"]
    STARTED.append((server.base_url, run_id))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if page.request.get(f"{server.base_url}/api/runs/{run_id}").json()["status"] != "running":
            return run_id
        time.sleep(0.05)
    pytest.fail("la comparaison ne s'est pas terminée")


def reopen(page, server, run_id, models=None):
    install_models(page, models)
    page.goto(f"{server.base_url}/#/arene/comparer/{run_id}")
    wait_ready(page)
    wait_banner(page, "Comparaison terminée")
    page.locator(".arena-run-actions").wait_for(state="visible")
    wait_for(page, "() => !document.querySelector('.arena-run-actions button').disabled")
    wait_names(page)


def actions(page):
    return page.get_by_role("group", name="Actions sur cette comparaison")


@pytest.fixture
def requests_log(page):
    log: list[tuple[str, str]] = []
    page.on("request", lambda request: log.append((request.method, request.url)))
    return log


def test_a_finished_arena_is_rebuilt_from_the_database_without_running_a_model(
    page, server, requests_log
):
    run_id = post_run(page, server, [ok_lane("fake:a", "Alpha"), ok_lane("fake:b", "Bravo")])
    requests_log.clear()
    reopen(page, server, run_id)
    assert lane(page, "fake:a").locator(".wl-md").inner_text().strip() == "Alpha"
    assert lane(page, "fake:b").locator(".wl-md").inner_text().strip() == "Bravo"
    assert page.locator(".arena-rank-item").count() == 2  # classement, depuis les notes du juge
    assert page.locator(".arena-chart-body wl-chart-svg").count() == 1  # matrice
    assert page.locator(".arena-verdict").is_hidden()  # aucun modèle cloud : pas de verdict
    posts = [url for method, url in requests_log if method != "GET"]
    assert posts == [], posts  # rien n'est relancé : ni commande, ni route de test
    assert any(url.endswith(f"/api/runs/{run_id}") for _, url in requests_log)
    assert any(f"/api/runs/{run_id}/events" in url for _, url in requests_log)
    buttons = actions(page).get_by_role("button").all_inner_texts()
    assert "Relancer" in buttons and "Modifier la question" in buttons
    assert "Exporter en CSV" in buttons and "Exporter en Markdown" in buttons
    assert "Effacer la comparaison" in buttons


def test_a_reopened_arena_takes_the_display_names_when_the_model_list_arrives_late(page, server):
    run_id = post_run(page, server, [ok_lane("fake:a", "Alpha"), ok_lane("fake:b", "Bravo")])
    install_models(page)
    held = []
    page.route(re.compile(r"/api/models\?"), lambda route: held.append(route))  # liste retenue
    page.goto(f"{server.base_url}/#/arene/comparer/{run_id}")
    wait_ready(page)
    wait_banner(page, "Comparaison terminée")
    names = page.locator("wl-arena-lane .wl-lane-name")
    assert names.all_inner_texts() == ["fake:a", "fake:b"]  # pas de fiche : l'identifiant
    body = json.dumps({"models": MODELS, "ollama_up": True, "refreshed_at": "2026-10-18T10:00:00Z"})
    for route in held:
        route.fulfill(status=200, content_type="application/json", body=body)
    wait_names(page)
    assert names.all_inner_texts() == ["Alpha 1B", "Bravo 2B"]
    assert sorted(page.locator(".arena-rank-name").all_inner_texts()) == ["Alpha 1B", "Bravo 2B"]


def test_modify_the_question_takes_the_whole_configuration_back_into_the_form(page, server):
    run_id = post_run(
        page,
        server,
        [ok_lane("fake:a"), ok_lane("fake:c")],
        prompt="Question d'origine",
        criteria=["clarté", "ton"],
    )
    reopen(page, server, run_id)
    page.get_by_label("Question", exact=True).fill("Autre chose")  # le formulaire a dérivé
    actions(page).get_by_role("button", name="Modifier la question").click()
    question = page.get_by_label("Question", exact=True)
    assert question.input_value() == "Question d'origine"
    assert page.evaluate("document.activeElement.id") == page.evaluate(
        "document.querySelector('.arena-question').id"
    )
    chips = page.get_by_role("list", name="Modèles choisis").inner_text()
    assert "Alpha 1B" in chips and "Charlie 3B" in chips and "Bravo 2B" not in chips
    criteria = page.locator(".arena-criterion-input")
    assert criteria.evaluate_all("(nodes) => nodes.map((n) => n.value)") == ["clarté", "ton"]
    assert page.get_by_role("button", name="Lancer la comparaison").is_enabled()
    # La question modifiée ne lance rien : la comparaison rouverte reste affichée.
    assert lane(page, "fake:a").is_visible()


def test_rerun_launches_the_same_configuration_again(page, server):
    run_id = post_run(
        page,
        server,
        [ok_lane("fake:a"), ok_lane("fake:c")],
        prompt="Question d'origine",
        criteria=["clarté"],
    )
    install_models(page)
    commands: list[dict] = []
    scripted(page, server, {}, commands, judge=JUDGE)
    page.goto(f"{server.base_url}/#/arene/comparer/{run_id}")
    wait_ready(page)
    wait_banner(page, "Comparaison terminée")
    wait_for(page, "() => !document.querySelector('.arena-run-actions button').disabled")
    before = len(STARTED)
    actions(page).get_by_role("button", name="Relancer").click()
    deadline = time.monotonic() + 10
    while len(STARTED) == before and time.monotonic() < deadline:  # la commande est partie
        page.wait_for_timeout(
            50
        )  # le gestionnaire de route ne tourne que pendant un appel Playwright
    assert len(STARTED) == before + 1
    while time.monotonic() < deadline:  # la nouvelle comparaison se termine
        done = page.request.get(f"{server.base_url}/api/runs/{STARTED[-1][1]}").json()["status"]
        if done != "running":
            break
        time.sleep(0.05)
    wait_banner(page, "Comparaison terminée")
    assert len(commands) == 1
    assert commands[0]["models"] == ["fake:a", "fake:c"]
    assert commands[0]["prompt"] == "Question d'origine"
    assert commands[0]["criteria"] == ["clarté"] and commands[0]["judge"] == JUDGE_DEFAULT
    assert len(STARTED) == before + 1 and STARTED[-1][1] != run_id  # une nouvelle comparaison
    assert page.locator("wl-arena-lane").count() == 2


def test_an_unknown_id_says_result_not_found_with_a_link_to_a_new_comparison(
    page_tolerating_failed_requests, server
):
    page = page_tolerating_failed_requests
    install_models(page)
    page.goto(f"{server.base_url}/#/arene/comparer/inconnu")
    wait_ready(page)
    alert = page.get_by_role("alert").filter(has_text="Résultat introuvable")
    alert.wait_for()
    assert "aucune comparaison enregistrée" in alert.inner_text()
    assert page.locator("wl-arena-lane").count() == 0
    response = page.request.get(f"{server.base_url}/api/runs/inconnu")
    assert response.status == 404
    body = response.json()
    assert body["code"] == "run_not_found" and body["detail"]["run_id"] == "inconnu"
    alert.get_by_role("link", name="Lancer une nouvelle comparaison").click()
    wait_for(page, "() => location.hash === '#/arene/comparer'")
    page.get_by_role("button", name="Lancer la comparaison").wait_for()
    # Le routeur remonte l'écran en asynchrone : l'ancien (avec son alerte) reste visible un instant.
    wait_for(page, "() => !document.querySelector('.arena-missing:not([hidden])')")
    assert page.get_by_role("heading", name="Résultat introuvable").count() == 0


def test_the_csv_export_carries_each_model_and_the_proof_of_the_measure(page, server):
    run_id = post_run(
        page, server, [ok_lane("fake:a", "Alpha"), ok_lane("fake:b", "Bravo")], criteria=["clarté"]
    )
    reopen(page, server, run_id)
    with page.expect_download() as download:
        actions(page).get_by_role("button", name="Exporter en CSV").click()
    assert download.value.suggested_filename == f"arene-{run_id[:8]}.csv"
    text = Path(download.value.path()).read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert [row["model"] for row in rows] == ["fake:a", "fake:b"]
    first = rows[0]
    assert first["score"] == "70" and first["tps"] and first["tps_source"] == "ollama_eval"
    assert first["total_s"] and first["co2_method"] == "unmeasurable" and first["co2_mg"] == ""
    assert first["criteria"] == "clarté" and first["judge"] == JUDGE_DEFAULT
    assert first["machine_os"] and first["machine_cpu"] and first["app_version"]
    assert "model_digest" in first and "ollama_version" in first
    assert not any(
        url.startswith("blob:")
        for url in page.evaluate("performance.getEntries().map((e) => e.name)")
    )


def test_the_markdown_export_names_the_proof(page, server):
    run_id = post_run(page, server, [ok_lane("fake:a"), ok_lane("fake:b")])
    reopen(page, server, run_id)
    with page.expect_download() as download:
        actions(page).get_by_role("button", name="Exporter en Markdown").click()
    assert download.value.suggested_filename == f"arene-{run_id[:8]}.md"
    text = Path(download.value.path()).read_text(encoding="utf-8")
    for part in ("## Preuve de la mesure", "- Machine :", "- Ollama :", "- Digests des modèles :"):
        assert part in text, part
    assert "- Juge : fake:d" in text and "| fake:a |" in text


def test_under_768_px_a_single_export_button_opens_the_formats(page, server):
    run_id = post_run(page, server, [ok_lane("fake:a"), ok_lane("fake:b")])
    page.set_viewport_size({"width": 600, "height": 900})
    reopen(page, server, run_id)
    group = actions(page)
    assert group.get_by_role("button", name="Exporter en CSV").is_hidden()
    toggle = group.get_by_role("button", name="Exporter", exact=True)
    assert toggle.is_visible() and toggle.get_attribute("aria-expanded") == "false"
    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "true"
    with page.expect_download() as download:
        group.get_by_role("menuitem", name="Exporter en Markdown").click()
    assert download.value.suggested_filename.endswith(".md")
    assert_no_horizontal_scroll(page)


def test_erasing_asks_first_then_empties_the_screen_and_keeps_only_the_carbon(page, server):
    run_id = post_run(page, server, [ok_lane("fake:a", "Alpha"), ok_lane("fake:b", "Bravo")])
    other = post_run(page, server, [ok_lane("fake:a"), ok_lane("fake:b")], prompt="Autre")
    reopen(page, server, run_id)
    erase = actions(page).get_by_role("button", name="Effacer la comparaison")
    erase.click()
    dialog = page.get_by_role("dialog", name="Effacer cette comparaison ?")
    dialog.wait_for()
    assert "sans retour possible" in dialog.inner_text()
    assert page.evaluate("document.activeElement.textContent") == "Annuler"  # jamais l'action
    dialog.get_by_role("button", name="Annuler").click()
    dialog.wait_for(state="hidden")
    assert lane(page, "fake:a").is_visible() and erase.is_enabled()
    assert page.evaluate("document.activeElement.textContent") == "Effacer la comparaison"
    snapshot = page.request.get(f"{server.base_url}/api/runs/{run_id}").json()
    assert snapshot["erased"] is False

    erase.click()
    page.get_by_role("dialog").get_by_role("button", name="Effacer", exact=True).click()
    page.locator("wl-arena-lane").first.wait_for(state="detached")
    status = page.locator(".arena-history-status")
    status.wait_for(state="visible")
    assert "Comparaison effacée" in status.inner_text()
    assert page.locator(".arena-results").is_hidden() and page.locator(".arena-banner").is_hidden()
    # Côté serveur : le texte est parti, les lignes `runs` restent, la liste ne la montre plus.
    erased = page.request.get(f"{server.base_url}/api/runs/{run_id}").json()
    assert erased["erased"] is True and erased["config"] is None and erased["status"] == "ok"
    listed = page.request.get(f"{server.base_url}/api/arena/runs").json()["runs"]
    assert run_id not in [run["run_id"] for run in listed] and other in [
        r["run_id"] for r in listed
    ]
    assert page.locator(f'.arena-history-item[data-run-id="{run_id}"]').count() == 0
    # Rouverte par son adresse, elle dit qu'elle est effacée, sans erreur ni rejeu.
    page.goto(f"{server.base_url}/#/arene/comparer/{run_id}")
    page.reload()
    wait_ready(page)
    alert = page.get_by_role("alert").filter(has_text="Résultat introuvable")
    alert.wait_for()
    assert "effacée" in alert.inner_text() and "CO₂" in alert.inner_text()
    assert page.locator("wl-arena-lane").count() == 0


def test_erasing_also_forgets_the_question_left_in_the_form_and_its_draft(page, server):
    run_id = post_run(
        page, server, [ok_lane("fake:a"), ok_lane("fake:b")], prompt="Texte à oublier"
    )
    reopen(page, server, run_id)
    actions(page).get_by_role("button", name="Modifier la question").click()
    question = page.get_by_label("Question", exact=True)
    assert question.input_value() == "Texte à oublier"
    assert page.evaluate("localStorage.getItem('wavelocalai.draft.arena')") == "Texte à oublier"
    actions(page).get_by_role("button", name="Effacer la comparaison").click()
    page.get_by_role("dialog").get_by_role("button", name="Effacer", exact=True).click()
    page.locator("wl-arena-lane").first.wait_for(state="detached")
    assert question.input_value() == ""
    assert page.evaluate("localStorage.getItem('wavelocalai.draft.arena')") is None


def test_an_id_that_is_not_a_comparison_says_result_not_found_without_following_it(page, server):
    install_models(page)
    snapshot = {"run_id": "chat-1", "kind": "chat", "status": "ok", "children": [], "erased": False}
    page.route(re.compile(r"/api/runs/chat-1$"), lambda route: route.fulfill(json=snapshot))
    followed = []
    page.on("request", lambda r: followed.append(r.url) if "/chat-1/events" in r.url else None)
    page.goto(f"{server.base_url}/#/arene/comparer/chat-1")
    wait_ready(page)
    alert = page.get_by_role("alert").filter(has_text="Résultat introuvable")
    alert.wait_for()
    assert "aucune comparaison enregistrée" in alert.inner_text()
    assert (
        page.locator(".arena-notice, wl-arena-lane").filter(has_text="Un autre calcul").count() == 0
    )
    assert followed == []


def test_the_history_lists_previous_comparisons_and_each_one_reopens(page, server):
    first = post_run(
        page, server, [ok_lane("fake:a", "Alpha"), ok_lane("fake:b")], prompt="Première"
    )
    second = post_run(
        page, server, [ok_lane("fake:c", "Charlie"), ok_lane("fake:b")], prompt="Seconde"
    )
    reopen(page, server, first)
    items = page.locator(".arena-history-item")
    wait_for(page, "() => document.querySelectorAll('.arena-history-item').length >= 2")
    ids = items.evaluate_all("(nodes) => nodes.map((n) => n.dataset.runId)")
    assert ids.index(second) < ids.index(first)  # la plus récente d'abord
    row = page.locator(f'.arena-history-item[data-run-id="{second}"]')
    text = row.inner_text()
    assert "Charlie 3B" in text and "Bravo 2B" in text and "terminée" in text and "Seconde" in text
    link = row.get_by_role("link")
    assert link.get_attribute("href") == f"#/arene/comparer/{second}"
    link.click()
    wait_for(page, f"() => location.hash === '#/arene/comparer/{second}'")
    wait_banner(page, "Comparaison terminée")
    lane(page, "fake:c").locator(".wl-md").filter(has_text="Charlie").wait_for()
    assert lane(page, "fake:a").count() == 0


def test_a_new_comparison_appears_in_the_history_when_it_ends(page, server):
    install_models(page)
    scripted(page, server, {}, judge=JUDGE)
    page.goto(f"{server.base_url}/#/arene/comparer")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.values.length === 2")
    wait_for(
        page, "() => document.querySelector('wl-model-picker[purpose=judge]')?.values.length === 1"
    )
    before = page.locator(".arena-history-item").count()
    launch(page)
    wait_banner(page, "Comparaison terminée")
    run_id = STARTED[-1][1]
    page.locator(f'.arena-history-item[data-run-id="{run_id}"]').wait_for()
    assert page.locator(".arena-history-item").count() == before + 1


def test_the_co2_the_server_completed_for_a_stopped_lane_replaces_not_measured(page, server):
    """Une lane arrêtée n'a eu aucun `metrics` dans le flux ; le serveur peut avoir complété son CO2
    en base après coup : l'écran le lit dans l'instantané (rapport de la story 3.4)."""
    install_models(page)
    response = page.request.post(
        f"{server.base_url}/api/test/arena",
        data={
            "prompt": "Une question",
            "allow_cloud": False,
            "lanes": [
                ok_lane("fake:a"),
                {"tag": "fake:b", "script": [{"text": "B"}, {"sleep_s": 20}, {"done": DONE}]},
            ],
            "judge": {"tag": JUDGE_DEFAULT, **JUDGE},
        },
    )
    assert response.ok, response.text()
    run_id = response.json()["run_id"]
    STARTED.append((server.base_url, run_id))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:  # la lane locale `a` est notée (feuille du juge finie)
        children = page.request.get(f"{server.base_url}/api/runs/{run_id}").json()["children"]
        if any(c["kind"] == "judge" and c["status"] == "ok" for c in children):
            break
        time.sleep(0.1)
    page.request.post(f"{server.base_url}/api/runs/{run_id}/cancel")
    while time.monotonic() < deadline:
        if page.request.get(f"{server.base_url}/api/runs/{run_id}").json()["status"] != "running":
            break
        time.sleep(0.05)

    def complete(route):
        body = route.fetch().json()
        for child in body["children"]:
            if child["model"] == "fake:b" and child["metrics"]:
                child["metrics"]["co2"] = co2(0.9)
            elif child["model"] == "fake:b":
                child["metrics"] = {"origin": "local", "tps": None, "co2": co2(0.9)}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route(re.compile(rf"/api/runs/{run_id}$"), complete)
    page.goto(f"{server.base_url}/#/arene/comparer/{run_id}")
    wait_ready(page)
    wait_banner(page, "Comparaison arrêtée")
    page.get_by_role("radiogroup", name="Affichage des résultats").get_by_role(
        "radio", name="Tableau"
    ).click()
    row = page.locator(".arena-results .wl-table tbody tr", has_text="Bravo 2B")
    row.wait_for()
    wait_for(
        page, "() => document.querySelector('.arena-results .wl-table')?.innerText.includes('0,9')"
    )
    cells = [cell.replace(NBSP, " ") for cell in row.locator("th, td").all_inner_texts()]
    assert cells[4] == "0,9 mg"  # colonne CO₂ : la mesure du serveur, plus « non mesuré »


# --- Accessibilité -------------------------------------------------------------------------------


@pytest.mark.parametrize("width", [320, 1440])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_a_reopened_arena(page, server, theme, width):
    run_id = post_run(page, server, [ok_lane("fake:a", "Alpha"), ok_lane("fake:b", "Bravo")])
    page.set_viewport_size({"width": width, "height": 900})
    reopen(page, server, run_id)
    wait_for(page, "() => document.querySelectorAll('.arena-history-item').length >= 1")
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(page, f"Arène rouverte, {width} px, thème {theme}")
    assert_no_horizontal_scroll(page)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_result_not_found_and_on_the_erase_dialog(
    page_tolerating_failed_requests, server, theme
):
    page = page_tolerating_failed_requests
    install_models(page)
    page.goto(f"{server.base_url}/#/arene/comparer/inconnu")
    wait_ready(page)
    page.get_by_role("alert").filter(has_text="Résultat introuvable").wait_for()
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    page.set_viewport_size({"width": 320, "height": 900})
    assert_no_axe_violations(page, f"Résultat introuvable, 320 px, thème {theme}")
    assert_no_horizontal_scroll(page)

    run_id = post_run(page, server, [ok_lane("fake:a"), ok_lane("fake:b")])
    page.goto(f"{server.base_url}/#/arene/comparer/{run_id}")
    wait_banner(page, "Comparaison terminée")
    wait_for(page, "() => !document.querySelector('.arena-run-actions button').disabled")
    actions(page).get_by_role("button", name="Effacer la comparaison").click()
    page.get_by_role("dialog").wait_for()
    assert_no_axe_violations(page, f"dialogue d'effacement, 320 px, thème {theme}")
