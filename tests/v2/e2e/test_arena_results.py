"""Classement, matrice et tableau de l'Arène (story 3.4) dans un vrai navigateur, sur le vrai serveur.

Le serveur de test rejoue le même script de juge pour chaque lane, et ne mesure pas le CO2 d'une
lane locale (pas de CodeCarbon) : pour des notes, des débits et des CO2 différents d'une lane à
l'autre, le flux d'une comparaison terminée est relu puis réécrit (`replayed`) avant d'être donné
à la page, qui rouvre la comparaison par son adresse (c'est aussi le parcours « rouvrir »). Le flux
en direct (classement qui se construit, figé à `run_ended`) est prouvé avec le vrai flux.

Les calculs d'échelle (`core/chart-scale.js`) et l'unité commune du CO2 sont prouvés en important
les modules dans la page.
"""

from __future__ import annotations

import json
import re
import time

import pytest

from .test_arena import (  # noqa: F401  (`cancel_leftover_runs` est une fixture automatique)
    DONE,
    JUDGE_DEFAULT,
    NBSP,
    STARTED,
    arena,
    cancel_leftover_runs,
    install_models,
    lane,
    launch,
    open_arena,
    pick,
    scripted,
    verdict,
    wait_banner,
)
from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready

CODECARBON = {
    "method": "codecarbon",
    "estimated": False,
    "range_mg": None,
    "allocation": "direct",
    "reason": None,
}


def co2(mg: float, **extra) -> dict:
    return {"mg": mg, **CODECARBON, **extra}


def finished_run(page, server, lanes: list[dict], judge_script=None) -> str:
    """Lance une Arène (lanes `fake` scriptées et un juge) et attend sa fin."""
    judge = {"tag": JUDGE_DEFAULT, "script": judge_script or verdict(70), "origin": "local"}
    response = page.request.post(
        f"{server.base_url}/api/test/arena",
        data={"prompt": "Une question", "lanes": lanes, "judge": judge, "allow_cloud": False},
    )
    assert response.ok, response.text()
    run_id = response.json()["run_id"]
    STARTED.append((server.base_url, run_id))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if page.request.get(f"{server.base_url}/api/runs/{run_id}").json()["status"] != "running":
            return run_id
        time.sleep(0.05)
    pytest.fail("la comparaison ne s'est pas terminée")


def replayed(page, server, run_id: str, edit) -> None:
    """La page lira, pour `run_id`, le flux réel réécrit par `edit(enveloppe)`."""
    text = page.request.get(f"{server.base_url}/api/runs/{run_id}/events").text()
    lines = []
    for line in text.split("\n"):
        if line.startswith("data:"):
            envelope = json.loads(line[5:].strip())
            edit(envelope)
            line = f"data: {json.dumps(envelope, ensure_ascii=False)}"
        lines.append(line)
    body = "\n".join(lines)
    page.route(
        re.compile(rf"/api/runs/{run_id}/events"),
        lambda route: route.fulfill(status=200, content_type="text/event-stream", body=body),
    )


def tuned(scores: dict, rates: dict | None = None, co2s: dict | None = None):
    """Une réécriture : note par lane, débit par lane, `co2` par lane."""

    def edit(envelope):
        data = envelope["data"]
        lane_tag = data.get("lane") if isinstance(data, dict) else None
        if envelope["type"] == "judge_score" and lane_tag in scores and data["score"] is not None:
            data["score"] = scores[lane_tag]
        if envelope["type"] == "metrics":
            if rates and lane_tag in rates:
                data["tps"] = rates[lane_tag]
            if co2s and lane_tag in co2s:
                data["co2"] = co2s[lane_tag]

    return edit


def ok_lane(tag: str, text: str = "Réponse") -> dict:
    return {"tag": tag, "script": [{"text": text}, {"done": DONE}]}


def mixed_lanes() -> list[dict]:
    """Deux lanes notées, une en délai (sans mesure), une à réponse vide (non évaluée, mesurée)."""
    return [
        ok_lane("fake:a"),
        ok_lane("fake:b"),
        {"tag": "fake:c", "script": [{"text": "Début"}, {"fail": "timeout"}]},
        {"tag": "fake:e", "script": [{"done": DONE}]},
    ]


def open_replayed(page, server, scores, rates=None, co2s=None, lanes=None, viewport=None):
    install_models(page)
    run_id = finished_run(page, server, lanes or mixed_lanes())
    replayed(page, server, run_id, tuned(scores, rates, co2s))
    if viewport:
        page.set_viewport_size(viewport)
    page.goto(f"{server.base_url}/#/arene/comparer/{run_id}")
    wait_ready(page)
    wait_banner(page, "Comparaison terminée")
    page.locator(".arena-results").wait_for(state="visible")
    return run_id


SCORES = {"fake:a": 64, "fake:b": 88}
RATES = {"fake:a": 30.0, "fake:b": 12.5}
CO2S = {"fake:a": co2(1.8), "fake:b": co2(0.45)}


def ranked_names(page) -> list[str]:
    return page.locator(".arena-rank-item .arena-rank-name").all_inner_texts()


def table_rows(page) -> list[list[str]]:
    rows = page.locator(".arena-results .wl-table tbody tr")
    return [
        [cell.replace(NBSP, " ") for cell in rows.nth(i).locator("th, td").all_inner_texts()]
        for i in range(rows.count())
    ]


# --- Classement -----------------------------------------------------------------------------------


def test_the_ranking_builds_as_results_arrive_and_freezes_at_the_end(arena, server):
    scripted(
        arena,
        server,
        {
            "fake:a": [{"text": "Alpha"}, {"done": DONE}],
            "fake:b": [{"text": "Bravo"}, {"sleep_s": 2.0}, {"done": DONE}],
        },
        judge={"script": verdict(72), "origin": "local"},
    )
    assert arena.locator(".arena-results").is_hidden()  # rien avant le premier résultat
    launch(arena)
    results = arena.locator(".arena-results")
    results.wait_for(state="visible")  # dès les premières mesures, la comparaison court encore
    assert "en cours" in arena.locator(".arena-banner-text").inner_text()
    box = results.locator(".arena-results-block").first
    assert box.get_attribute("data-frozen") == "false"
    assert "se construit au fil des notes" in box.locator(".help").first.inner_text()
    wait_banner(arena, "Comparaison terminée")
    assert box.get_attribute("data-frozen") == "true"
    assert box.locator(".help").first.inner_text() == "Classement figé."
    # Deux notes égales : le même rang, dit en texte ; l'ordre est celui du lancement.
    assert ranked_names(arena) == ["Alpha 1B", "Bravo 2B"]
    items = arena.locator(".arena-rank-item")
    assert items.evaluate_all("(nodes) => nodes.map((n) => n.dataset.rank)") == ["1", "1"]
    assert items.locator(".arena-rank-tie").all_inner_texts() == ["ex æquo", "ex æquo"]
    first = items.first
    assert (
        first.locator(".arena-rank-n").inner_text().replace(NBSP, " ").replace("\n", "") == "Rang 1"
    )
    assert first.locator("wl-badge[kind=local]").count() == 1
    facts = [
        f.replace("\n", " ").replace(NBSP, " ")
        for f in first.locator(".arena-fact").all_inner_texts()
    ]
    assert facts[0] == "Note 72/100"
    assert facts[1].startswith("Débit 38,4")
    assert facts[2] == "CO₂ non mesurable"  # le serveur de test ne mesure rien
    assert arena.locator(".arena-unranked").count() == 0


def test_the_ranking_updates_with_each_score_before_the_comparison_ends(arena, server):
    slow_judge = [{"sleep_s": 0.7}, *verdict(55)]
    scripted(
        arena,
        server,
        {"fake:a": [{"text": "A"}, {"done": DONE}], "fake:b": [{"text": "B"}, {"done": DONE}]},
        judge={"script": slow_judge, "origin": "local"},
    )
    launch(arena)
    wait_for(arena, "() => document.querySelectorAll('.arena-rank-item').length === 1")
    wait_for(arena, "() => document.querySelectorAll('.arena-rank-item').length === 2")
    wait_banner(arena, "Comparaison terminée")
    assert arena.locator(".arena-rank-pending").count() == 0


def test_a_lane_not_evaluated_is_listed_with_its_reason_below_the_ranked_ones_without_a_rank(
    page, server
):
    open_replayed(page, server, SCORES, RATES, CO2S)
    assert ranked_names(page) == ["Bravo 2B", "Alpha 1B"]  # la meilleure note d'abord
    items = page.locator(".arena-rank-item")
    assert items.evaluate_all("(nodes) => nodes.map((n) => n.dataset.rank)") == ["1", "2"]
    assert page.locator(".arena-rank-tie").count() == 0
    best = items.first.locator(".arena-fact").all_inner_texts()
    assert [fact.replace("\n", " ").replace(NBSP, " ") for fact in best] == [
        "Note 88/100",
        "Débit 12,5 tokens/s",
        "CO₂ 0,45 mg",  # une seule unité pour toute la comparaison
    ]
    assert "1,8 mg" in items.nth(1).inner_text().replace(NBSP, " ")
    unranked = page.locator(".arena-unranked-item")
    assert unranked.locator("strong").all_inner_texts() == ["Charlie 3B", "Echo 5B"]
    texts = [
        text.replace(NBSP, " ")
        for text in unranked.locator(".arena-unranked-reason").all_inner_texts()
    ]
    assert texts == ["Non évalué : délai dépassé", "Non évalué : réponse vide"]
    assert page.locator(".arena-unranked .arena-rank-n").count() == 0  # aucun rang de podium
    assert "0/100" not in page.locator(".arena-ranking").inner_text()
    assert page.get_by_role("heading", name="Non évalués, sans rang").is_visible()
    # Au-dessus de la liste des non évalués, jamais mêlés aux lanes notées.
    order = page.locator(".arena-ranking").evaluate(
        "(box) => [...box.querySelectorAll('.arena-rank, .arena-unranked')].map((n) => n.className)"
    )
    assert order == ["arena-rank", "arena-unranked"]


def test_a_partial_comparison_says_the_ranking_only_holds_for_the_scored_models(page, server):
    # Une lane cloud lente tourne sans la place Ollama : la lane locale est notée pendant ce temps.
    install_models(page)
    response = page.request.post(
        f"{server.base_url}/api/test/arena",
        data={
            "prompt": "Une question",
            "allow_cloud": True,
            "lanes": [
                ok_lane("fake:a"),
                {
                    "tag": "fake:b",
                    "origin": "cloud",
                    "script": [{"text": "B"}, {"sleep_s": 20}, {"done": DONE}],
                },
            ],
            "judge": {"tag": JUDGE_DEFAULT, "script": verdict(61), "origin": "local"},
        },
    )
    assert response.ok, response.text()
    STARTED.append((server.base_url, response.json()["run_id"]))
    page.goto(f"{server.base_url}/#/arene/comparer/{response.json()['run_id']}")
    wait_ready(page)
    wait_for(page, "() => document.querySelectorAll('.arena-rank-item').length === 1")
    assert page.locator(".arena-rank-pending").inner_text() == "1 modèle n'est pas encore noté."
    page.get_by_role("button", name="Arrêter").click()
    wait_banner(page, "Comparaison arrêtée")
    partial = page.locator(".arena-results-partial")
    assert partial.inner_text().replace(NBSP, " ") == (
        "Comparaison arrêtée : le classement ne vaut que pour les modèles déjà notés."
    )
    assert ranked_names(page) == ["Alpha 1B"]
    unranked = page.locator(".arena-unranked-item")
    assert unranked.locator("strong").all_inner_texts() == ["Bravo 2B"]
    assert unranked.inner_text().replace(NBSP, " ").endswith("Non évalué : comparaison arrêtée")
    assert page.locator(".arena-rank-pending").count() == 0


def test_a_run_without_any_score_gives_no_ranking_and_every_lane_not_evaluated(page, server):
    install_models(page, judge_tags=())
    run_id = finished_run(
        page,
        server,
        [ok_lane("fake:a"), ok_lane("fake:b")],
        judge_script=[{"fail": "ollama_error"}],
    )
    page.goto(f"{server.base_url}/#/arene/comparer/{run_id}")
    wait_ready(page)
    wait_banner(page, "Comparaison terminée")
    assert page.locator(".arena-rank-item").count() == 0
    assert page.locator(".arena-rank-none").inner_text() == "Aucune note pour l'instant."
    reasons = page.locator(".arena-unranked-reason").all_inner_texts()
    assert [r.replace(NBSP, " ") for r in reasons] == ["Non évalué : juge indisponible"] * 2


# --- Matrice --------------------------------------------------------------------------------------


def test_the_matrix_is_shown_first_with_a_title_a_description_a_size_legend_and_full_names(
    page, server
):
    open_replayed(page, server, SCORES, RATES, CO2S)
    seg = page.get_by_role("radiogroup", name="Affichage des résultats")
    assert seg.get_by_role("radio", name="Matrice").get_attribute("aria-checked") == "true"
    assert seg.get_by_role("radio", name="Tableau").get_attribute("aria-checked") == "false"
    assert [t.strip() for t in seg.get_by_role("radio").all_inner_texts()] == ["Matrice", "Tableau"]
    assert page.locator(".arena-results wl-data-table").count() == 0  # le tableau est derrière
    svg = page.locator("wl-chart-svg svg[role=img]")
    title = svg.locator("title").text_content()
    desc = svg.locator("desc").text_content().replace(NBSP, " ")
    assert title.startswith("Note du juge et débit de chaque modèle")
    assert "En abscisse, le débit en tokens par seconde" in desc
    assert "Alpha 1B : 64/100, 30 tokens/s, 1,8 mg." in desc
    assert "Bravo 2B : 88/100, 12,5 tokens/s, 0,45 mg." in desc
    assert svg.get_attribute("aria-labelledby") and svg.locator("circle.wl-chart-dot").count() == 2
    labels = svg.locator("text.wl-chart-label").evaluate_all("(n) => n.map((x) => x.textContent)")
    assert sorted(labels) == ["Alpha 1B", "Bravo 2B"]  # noms complets
    ticks = svg.locator("text.wl-chart-tick").evaluate_all("(n) => n.map((x) => x.textContent)")
    assert "0" in ticks and "100" in ticks
    # La légende de taille, en texte : le plus petit et le plus grand CO2, dans la même unité.
    legend = page.locator(".wl-chart-legend")
    assert legend.locator(".wl-chart-legend-title").inner_text().replace(NBSP, " ") == (
        "Taille du point : CO₂ de la réponse"
    )
    sizes = [t.replace(NBSP, " ") for t in legend.locator(".wl-chart-size").all_inner_texts()]
    assert sizes == ["0,45 mg", "1,8 mg"]
    assert "Tous les CO₂ de cette comparaison sont exprimés en mg." in legend.inner_text()
    # Les lanes que la matrice ne peut pas placer sont nommées, jamais oubliées en silence.
    missing = page.locator(".wl-chart-missing").inner_text().replace(NBSP, " ")
    assert missing == "Non placés sur la matrice : Charlie 3B, Echo 5B."
    # Aucune couleur seule : chaque point a son nom écrit et un contour d'encre.
    assert (
        page.locator("wl-chart-svg .wl-chart-dot").first.evaluate(
            "(n) => getComputedStyle(n).strokeWidth"
        )
        == "1.5px"
    )


def test_the_axes_start_at_zero_and_one_point_does_not_squeeze_them(page, server):
    open_replayed(
        page,
        server,
        {"fake:a": 40},
        {"fake:a": 38.4},
        {"fake:a": co2(0.9)},
        lanes=[ok_lane("fake:a"), {"tag": "fake:c", "script": [{"fail": "timeout"}]}],
    )
    svg = page.locator("wl-chart-svg svg.wl-chart-svg")
    assert svg.locator("circle.wl-chart-dot").count() == 1
    y_ticks = svg.locator("text.wl-chart-tick").evaluate_all("(n) => n.map((x) => x.textContent)")
    assert "0" in y_ticks and "100" in y_ticks  # la note garde 0 à 100
    x_ticks = [float(t.replace(",", ".")) for t in y_ticks if t not in ("20", "40", "60", "80")]
    assert (
        min(x_ticks) == 0 and max(x_ticks) >= 38.4
    )  # le débit part de 0, il n'entoure pas le point
    assert len(page.locator(".wl-chart-size").all_inner_texts()) == 1  # une seule taille, légendée


def test_an_estimated_and_an_unmeasurable_co2_are_said_in_text(page, server):
    open_replayed(
        page,
        server,
        SCORES,
        RATES,
        {"fake:a": co2(2.4, method="ecologits", estimated=True, allocation="direct")},
    )
    items = page.locator(".arena-rank-item")
    by_name = {
        items.nth(i)
        .locator(".arena-rank-name")
        .inner_text(): items.nth(i)
        .inner_text()
        .replace(NBSP, " ")
        for i in range(items.count())
    }
    assert "2,4 mg (estimé)" in by_name["Alpha 1B"]
    assert "non mesurable" in by_name["Bravo 2B"]
    # Le point sans CO2 mesuré a un contour en pointillés, expliqué dans la légende en texte.
    assert page.locator(".wl-chart-plot circle.is-unknown").count() == 1
    legend = page.locator(".wl-chart-legend").inner_text().replace(NBSP, " ")
    assert "Contour en pointillés : CO₂ non mesurable" in legend


# --- Tableau --------------------------------------------------------------------------------------


def see_table(page):
    page.get_by_role("button", name="Voir le tableau").click()


def test_see_the_table_leads_to_the_table_and_the_segments_switch_with_the_arrow_keys(page, server):
    open_replayed(page, server, SCORES, RATES, CO2S)
    see_table(page)
    seg = page.get_by_role("radiogroup", name="Affichage des résultats")
    assert seg.get_by_role("radio", name="Tableau").get_attribute("aria-checked") == "true"
    page.locator(".arena-results .wl-table").wait_for()
    assert page.locator("wl-chart-svg").count() == 0
    focused = page.evaluate("() => document.activeElement.className")
    assert "wl-table-wrap" in focused  # le focus suit le lien
    seg.get_by_role("radio", name="Tableau").focus()
    page.keyboard.press("ArrowLeft")
    assert seg.get_by_role("radio", name="Matrice").get_attribute("aria-checked") == "true"
    page.locator("wl-chart-svg svg.wl-chart-svg").wait_for()
    page.keyboard.press("ArrowRight")
    assert seg.get_by_role("radio", name="Tableau").get_attribute("aria-checked") == "true"


def test_the_table_lists_every_model_in_a_semantic_table_with_one_co2_unit(page, server):
    open_replayed(page, server, SCORES, RATES, CO2S)
    see_table(page)
    table = page.locator(".arena-results table.wl-table")
    assert (
        table.locator("caption").inner_text() == "Résultats de la comparaison, une ligne par modèle"
    )
    headers = table.locator("thead th")
    assert headers.all_inner_texts() == [
        "Modèle",
        "Origine",
        "Note",
        "Débit",
        "CO₂",
        "Chargement",
        "Durée totale",
    ]
    assert headers.evaluate_all("(n) => n.map((th) => th.scope)") == ["col"] * 7
    assert table.locator("tbody th").evaluate_all("(n) => n.map((th) => th.scope)") == ["row"] * 4
    rows = table_rows(page)
    assert [row[0] for row in rows] == ["Bravo 2B", "Alpha 1B", "Charlie 3B", "Echo 5B"]
    bravo, alpha, charlie, delta = rows
    assert bravo[2:5] == ["88/100", "12,5 tokens/s", "0,45 mg"]
    assert alpha[2:5] == ["64/100", "30 tokens/s", "1,8 mg"]  # mg pour tous
    assert bravo[5] == "0,42 s" and bravo[6] == "1,2 s"
    # Jamais 0 ni « — » : un texte qui dit pourquoi.
    assert charlie[2:] == [
        "non évalué : délai dépassé",
        "non mesuré",
        "non mesuré",
        "non mesuré",
        "non mesuré",
    ]
    assert delta[2] == "non évalué : réponse vide"
    assert delta[4] == "non mesurable"  # le CO2 de cette lane n'a pas pu être mesuré
    flat = [cell for row in rows for cell in row]
    assert not any(cell in ("0", "—", "-", "0/100", "0 mg") for cell in flat)
    assert table.locator("tbody td wl-badge").count() == 4


def test_the_table_sorts_with_the_keyboard_and_puts_the_unknown_last(page, server):
    open_replayed(page, server, SCORES, RATES, CO2S)
    see_table(page)
    sort = page.locator(".arena-results .wl-table-sort", has_text="Note")
    sort.focus()
    page.keyboard.press("Enter")
    assert page.locator(".arena-results th[aria-sort=ascending]").inner_text().strip() == "Note"
    assert [row[0] for row in table_rows(page)][:2] == ["Alpha 1B", "Bravo 2B"]  # 64 puis 88
    assert [row[0] for row in table_rows(page)][2:] == ["Charlie 3B", "Echo 5B"]
    page.keyboard.press("Space")
    assert [row[0] for row in table_rows(page)][:2] == ["Bravo 2B", "Alpha 1B"]
    assert page.locator(".arena-results th[aria-sort=descending]").count() == 1
    announced = page.locator(".arena-results [role=status]").inner_text()
    assert announced == "Trié par Note, ordre décroissant"
    # Le tri du CO2 compare des mg, pas des textes.
    page.locator(".arena-results .wl-table-sort", has_text="CO₂").focus()
    page.keyboard.press("Enter")
    assert [row[0] for row in table_rows(page)][:2] == ["Bravo 2B", "Alpha 1B"]  # 0,45 puis 1,8


def test_the_segment_choice_holds_for_the_page_session(page, server):
    run_id = open_replayed(page, server, SCORES, RATES, CO2S)
    see_table(page)
    page.evaluate("location.hash = '#/'")
    page.locator("section[data-screen=arena-compare]").wait_for(state="hidden")
    page.evaluate(f"location.hash = '#/arene/comparer/{run_id}'")
    page.locator("section[data-screen=arena-compare]").wait_for(state="visible")
    assert page.locator(".arena-results table.wl-table").is_visible()


# --- Calculs --------------------------------------------------------------------------------------


def evaluate_module(page, server, body: str):
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    return page.evaluate(
        "async () => {"
        "const scale = await import('/static/core/chart-scale.js');"
        "const format = await import('/static/core/format.js');"
        "const data = await import('/static/screens/arena-results-data.js');"
        f"{body} }}"
    )


def test_a_linear_axis_always_starts_at_zero_and_never_collapses_on_one_point(page, server):
    axes = evaluate_module(
        page,
        server,
        "return {"
        "one: scale.linearAxis([38.4]), same: scale.linearAxis([12, 12, 12]),"
        "none: scale.linearAxis([]), zero: scale.linearAxis([0, null]),"
        "wide: scale.linearAxis([3, 4200]), tiny: scale.linearAxis([0.004]) };",
    )
    for name, axis in axes.items():
        assert axis["min"] == 0, name
        assert axis["max"] > 0 and len(axis["ticks"]) >= 2, name
        assert axis["ticks"][0] == 0 and axis["ticks"][-1] == axis["max"], name
        steps = {round(b - a, 9) for a, b in zip(axis["ticks"], axis["ticks"][1:], strict=False)}
        assert len(steps) == 1, (name, axis["ticks"])  # graduations régulières
    assert axes["one"]["max"] >= 38.4 * 1.1 and axes["tiny"]["max"] >= 0.004
    assert axes["wide"]["max"] >= 4200 and axes["same"]["max"] >= 12


def test_the_point_size_grows_with_the_co2_and_an_unknown_co2_has_its_own_size(page, server):
    sizes = evaluate_module(
        page,
        server,
        "const r = (mg) => scale.bubbleRadius(mg, 4);"
        "return { zero: r(0), small: r(1), big: r(4), over: r(9), unknown: r(null),"
        " flat: scale.bubbleRadius(2, 0),"
        " legend: scale.legendSizes([null, 4, 0.5, 4]), one: scale.legendSizes([2, 2]),"
        " empty: scale.legendSizes([null]) };",
    )
    assert sizes["zero"] < sizes["small"] < sizes["big"]
    assert sizes["unknown"] == 9 and sizes["flat"] == 7
    assert sizes["legend"] == [0.5, 4] and sizes["one"] == [2] and sizes["empty"] == []


def test_the_labels_stay_inside_the_plot_and_do_not_overlap(page, server):
    placed = evaluate_module(
        page,
        server,
        "const items = ['Alpha 1B', 'Bravo 2B', 'Qwen 2.5 Coder 7B Instruct', 'Charlie 3B']"
        ".map((name, i) => ({ name, cx: 120 + i * 18, cy: 60 + (i % 2) * 8, r: 12 }));"
        "const bounds = { left: 52, right: 288, top: 14, bottom: 210 };"
        "return { placed: scale.layoutLabels(items, bounds), bounds,"
        " wrapped: scale.wrapLabel('Qwen 2.5 Coder 7B Instruct', 12) };",
    )
    assert placed["wrapped"] == ["Qwen 2.5", "Coder 7B", "Instruct"]
    boxes = []
    for label in placed["placed"]:
        width = max(len(line) for line in label["lines"]) * 6.6
        x0 = label["x"] if label["anchor"] == "start" else label["x"] - width
        y0 = label["y"] - 11
        boxes.append((x0, x0 + width, y0, y0 + 14 * len(label["lines"])))
        assert y0 >= placed["bounds"]["top"] - 0.01
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            assert not (a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]), (a, b)


def test_the_co2_of_one_comparison_is_in_one_unit_and_a_tie_shares_its_rank(page, server):
    out = evaluate_module(
        page,
        server,
        "const lane = (tag, score, mg) => ({ tag, name: tag, origin: 'local', status: 'done',"
        " score: score === null ? null : { score, reason: '' },"
        " result: mg === undefined ? null : { co2: { mg } } });"
        "const lanes = [lane('a', 70, 0.9), lane('b', 70, 1500), lane('c', 90, 20), lane('d', null, null)];"
        "const group = data.co2GroupOf(lanes);"
        "return { unit: group.unit, texts: lanes.map((l) => data.co2Text(l, group, true)),"
        " ranks: data.rankLanes(lanes).map((r) => [r.lane.tag, r.rank, r.tied]),"
        " small: data.co2GroupOf([lane('x', 1, 0.3)]).unit,"
        " none: data.co2GroupOf([lane('x', 1, null)]).unit,"
        " plain: format.co2Group([999.6, 3]).unit };",
    )
    assert out["unit"] == "g"  # 1 500 mg : le plus grand, donc le gramme pour tous
    assert [t.replace(NBSP, " ") for t in out["texts"]] == [
        "0,0009 g",
        "1,5 g",
        "0,02 g",
        "non mesurable",
    ]
    assert out["ranks"] == [["c", 1, False], ["a", 2, True], ["b", 2, True]]  # 1, 2, 2
    assert out["small"] == "mg" and out["none"] == "mg" and out["plain"] == "g"


# --- Accessibilité, mise en page, projection -----------------------------------------------------


@pytest.mark.parametrize("width", [320, 1440])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_ranking_the_matrix_and_the_table(page, server, theme, width):
    open_replayed(page, server, SCORES, RATES, CO2S, viewport={"width": width, "height": 900})
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(page, f"classement et matrice, {width} px, thème {theme}")
    assert_no_horizontal_scroll(page)
    see_table(page)
    assert_no_axe_violations(page, f"tableau, {width} px, thème {theme}")
    assert_no_horizontal_scroll(page)
    page.locator(".arena-results .wl-table-sort", has_text="Débit").click()
    assert_no_axe_violations(page, f"tableau trié, {width} px, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_results_in_projection_mode(page, server, theme):
    open_replayed(page, server, SCORES, RATES, CO2S)
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    page.evaluate("document.documentElement.setAttribute('data-projection', 'true')")
    page.locator("wl-chart-svg svg.wl-chart-svg").wait_for()
    assert_no_axe_violations(page, f"projection, matrice, thème {theme}")
    assert_no_horizontal_scroll(page)
    see_table(page)
    assert_no_axe_violations(page, f"projection, tableau, thème {theme}")


def test_the_matrix_labels_stay_inside_the_picture_at_320_px_and_in_projection(page, server):
    lanes = [ok_lane("fake:a"), ok_lane("fake:b")]
    open_replayed(
        page,
        server,
        {"fake:a": 64, "fake:b": 66},
        {"fake:a": 30.0, "fake:b": 31.0},
        {"fake:a": co2(1.8), "fake:b": co2(0.9)},
        lanes=lanes,
        viewport={"width": 320, "height": 900},
    )
    check = """() => {
        const svg = document.querySelector('wl-chart-svg svg');
        const frame = svg.getBoundingClientRect();
        return [...svg.querySelectorAll('text.wl-chart-label')].map((text) => {
            const box = text.getBoundingClientRect();
            return box.left >= frame.left - 1 && box.right <= frame.right + 1
                && box.top >= frame.top - 1 && box.bottom <= frame.bottom + 1;
        });
    }"""
    assert all(page.evaluate(check))
    page.evaluate("document.documentElement.setAttribute('data-projection', 'true')")
    page.wait_for_timeout(200)
    assert all(page.evaluate(check))
    font = page.locator("wl-chart-svg text.wl-chart-label").first.evaluate(
        "(n) => parseFloat(getComputedStyle(n).fontSize)"
    )
    assert font > 12  # le texte du graphique suit le mode projection


def test_the_chart_redraws_when_the_width_changes_and_keeps_its_text_size(page, server):
    open_replayed(page, server, SCORES, RATES, CO2S)
    wide = page.locator("wl-chart-svg svg.wl-chart-svg").get_attribute("width")
    page.set_viewport_size({"width": 420, "height": 900})
    wait_for(
        page,
        f"() => document.querySelector('wl-chart-svg svg').getAttribute('width') !== '{wide}'",
    )
    narrow = int(page.locator("wl-chart-svg svg.wl-chart-svg").get_attribute("width"))
    assert narrow < int(wide)
    # Redessiné à la taille réelle : le texte ne rétrécit pas avec l'image.
    scale = page.locator("wl-chart-svg svg.wl-chart-svg").evaluate(
        "(svg) => svg.getBoundingClientRect().width / svg.viewBox.baseVal.width"
    )
    assert abs(scale - 1) < 0.02


def test_the_front_scripts_never_build_the_results_from_html_strings(page, server):
    install_models(page)
    assert (
        "innerHTML"
        not in page.request.get(f"{server.base_url}/static/screens/arena-results.js").text()
    )
    assert (
        "innerHTML"
        not in page.request.get(f"{server.base_url}/static/components/wl-chart-svg.js").text()
    )
