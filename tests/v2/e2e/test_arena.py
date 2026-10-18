"""Écran Arène (story 3.2) dans un vrai navigateur, sur le vrai serveur et des lanes `fake` scriptées.

Ollama n'est jamais sollicité (le serveur pointe sur un port fermé). La liste des modèles est
simulée par le test (`page.route`) ; la commande `POST /api/arena/runs` de la page est redirigée
vers la route de test `POST /api/test/arena`, qui lance le vrai service de l'Arène avec un script
par modèle (jetons, pauses, échecs, mesures). Les lanes locales passent donc par le vrai sémaphore.

Colonnes, statuts, mesures, arrêt, reprise `?after=`, `409 run_busy`, mise en page (deux colonnes
avec défilement, onglets, mode focus) et axe-core (clair, sombre, projection) sont prouvés ici.
"""

from __future__ import annotations

import contextlib
import json
import re
import time
import urllib.request

import pytest

from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
BASE_MODEL = {
    "provider": "fake",
    "editor": None,
    "origin": "local",
    "kind": "chat",
    "available": True,
    "digest": "abc",
    "params_total_b": None,
    "params_active_b": None,
    "size_gb": 1.0,
    "quantization": None,
    "context_length": None,
    "needed_gb": 1.5,
    "fits": True,
    "tools_verified": False,
    "reasoning": False,
    "throughput_tps": None,
    "accuracy": None,
    "co2_method": "codecarbon",
    "in_catalog": False,
}
NAMES = {
    "fake:a": "Alpha 1B",
    "fake:b": "Bravo 2B",
    "fake:c": "Charlie 3B",
    "fake:d": "Delta 4B",
    "fake:e": "Echo 5B",
}
MODELS = [{**BASE_MODEL, "tag": tag, "name": name} for tag, name in NAMES.items()]
REASON = "Les plus rapides qui tiennent en mémoire sur ce poste."
DONE = {
    "input_tokens": 4,
    "output_tokens": 12,
    "ttft_s": 0.1,
    "load_s": 0.42,
    "eval_s": 0.3,
    "total_s": 1.2,
    "tps": 38.4,
    "tps_source": "ollama_eval",
}
STARTED: list[tuple[str, str]] = []


@pytest.fixture(autouse=True)
def cancel_leftover_runs():
    """Une seule Arène à la fois : un test n'en laisse aucune en cours au suivant."""
    yield
    for base_url, run_id in STARTED:
        request = urllib.request.Request(f"{base_url}/api/runs/{run_id}/cancel", method="POST")
        with contextlib.suppress(OSError):  # déjà terminé
            urllib.request.urlopen(request, timeout=5).close()  # noqa: S310
    STARTED.clear()
    time.sleep(0.2)


def install_models(page, models=None, defaults=("fake:a", "fake:b")):
    listed = MODELS if models is None else models

    def on_models(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"models": listed, "ollama_up": True, "refreshed_at": "2026-10-18T10:00:00Z"}
            ),
        )

    def on_defaults(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "purpose": "arena",
                    "tags": list(defaults),
                    "reason": REASON,
                    "source": "rule",
                }
            ),
        )

    page.route(re.compile(r"/api/models\?"), on_models)
    page.route(re.compile(r"/api/models/defaults\?"), on_defaults)


def scripted(page, server, scripts, commands=None):
    """Les commandes d'Arène de la page lancent des lanes scriptées (route de test)."""

    def on_arena(route):
        body = json.loads(route.request.post_data)
        if commands is not None:
            commands.append(body)
        lanes = [
            {"tag": tag, "script": scripts.get(tag, [{"text": "ok"}, {"done": DONE}])}
            for tag in body["models"]
        ]
        response = page.request.post(
            f"{server.base_url}/api/test/arena",
            data={
                "prompt": body["prompt"],
                "criteria": body.get("criteria", []),
                "allow_cloud": body["allow_cloud"],
                "lanes": lanes,
            },
        )
        if response.ok:
            STARTED.append((server.base_url, response.json()["run_id"]))
        route.fulfill(status=response.status, content_type="application/json", body=response.text())

    page.route(re.compile(r"/api/arena/runs$"), on_arena)


def start_run(page, server, scripts, models=("fake:a", "fake:b")):
    lanes = [{"tag": tag, "script": scripts.get(tag, [{"text": "ok"}])} for tag in models]
    response = page.request.post(
        f"{server.base_url}/api/test/arena", data={"prompt": "Question d'ailleurs", "lanes": lanes}
    )
    assert response.ok, response.text()
    run_id = response.json()["run_id"]
    STARTED.append((server.base_url, run_id))
    return run_id


def open_arena(page, server, path="#/arene/comparer"):
    install_models(page)
    page.goto(f"{server.base_url}/{path}")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.values.length === 2")


@pytest.fixture
def arena(page, server):
    open_arena(page, server)
    return page


@pytest.fixture
def arena_lenient(page_tolerating_failed_requests, server):
    """Comme `arena`, pour un test dont la commande échoue exprès (409 : le navigateur le dit)."""
    open_arena(page_tolerating_failed_requests, server)
    return page_tolerating_failed_requests


def launch(page):
    page.get_by_role("button", name="Lancer la comparaison").click()


def lane(page, tag):
    return page.locator(f'wl-arena-lane[data-tag="{tag}"]')


def status_of(page, tag):
    return lane(page, tag).locator(".wl-lane-status-text").inner_text()


def banner(page):
    return page.locator(".arena-banner-text")


def wait_banner(page, text):
    banner(page).filter(has_text=text).wait_for()


def pick(page, name):
    """Coche un modèle dans la liste du sélecteur (mode multi)."""
    page.get_by_role("combobox").click()
    page.locator("[role=option]", has_text=name).click()
    page.keyboard.press("Escape")


# --- Ouverture ------------------------------------------------------------------------------------


def test_the_screen_opens_with_the_form_the_scenarios_and_the_default_models(arena):
    assert arena.get_by_role("heading", level=1).inner_text() == "Arène"
    tabs = arena.get_by_role("navigation", name="Écrans du module Arène")
    assert (
        tabs.get_by_role("link", name="Arène", exact=True).get_attribute("aria-current") == "page"
    )
    question = arena.get_by_label("Question", exact=True)
    assert question.input_value().startswith("Explique la photosynthèse")  # défaut qui marche
    scenarios = arena.get_by_role("group", name="Scénarios")
    names = scenarios.get_by_role("button").all_inner_texts()
    assert names == ["Vulgarisation", "Extraction JSON", "Résumé", "Traduction"]
    scenarios.get_by_role("button", name="Traduction").click()
    assert question.input_value().startswith(f"Traduis en anglais{NBSP}:")
    scenarios.get_by_role("button", name="Extraction JSON").click()
    assert "JSON strict" in question.input_value()
    chips = arena.get_by_role("list", name="Modèles choisis")
    assert chips.inner_text().count("Alpha 1B") == 1 and "Bravo 2B" in chips.inner_text()
    assert arena.get_by_text(
        f"Les modèles locaux passent l'un après l'autre (mémoire){NBSP}; les modèles cloud en parallèle."
    ).is_visible()
    assert arena.get_by_role("button", name="Lancer la comparaison").is_enabled()
    assert (
        arena.locator(".arena-banner").is_hidden() and arena.locator("wl-arena-lane").count() == 0
    )


def test_under_two_models_the_launch_is_disabled_with_a_visible_reason(arena):
    button = arena.get_by_role("button", name="Lancer la comparaison")
    arena.get_by_role("button", name="Retirer Bravo 2B").click()
    assert button.is_disabled()
    reason = arena.get_by_text("Choisissez au moins 2 modèles")
    assert reason.is_visible()
    assert button.get_attribute("aria-describedby") == reason.get_attribute("id")
    pick(arena, "Charlie 3B")
    assert button.is_enabled() and arena.get_by_text("Choisissez au moins 2 modèles").is_hidden()
    for name in ("Delta 4B", "Bravo 2B", "Echo 5B"):
        pick(arena, name)
    assert button.is_disabled() and arena.get_by_text("Choisissez 4 modèles au plus").is_visible()
    arena.get_by_label("Question", exact=True).fill("")
    arena.get_by_role("button", name="Retirer Delta 4B").click()
    arena.get_by_role("button", name="Retirer Echo 5B").click()
    assert arena.get_by_text("Saisissez une question").is_visible() and button.is_disabled()


def test_without_a_ready_local_model_an_info_alert_says_what_to_do_and_the_launch_stays_disabled(
    page, server
):
    install_models(page, models=[], defaults=())
    page.goto(f"{server.base_url}/#/arene/comparer")
    wait_ready(page)
    alert = page.locator(".wl-notice-info")
    alert.wait_for(state="visible")
    text = alert.inner_text()
    assert "Aucun modèle local n'est prêt." in text
    assert "depuis l'écran Modèles" in text and "Autoriser le cloud" in text
    button = page.get_by_role("button", name="Lancer la comparaison")
    assert button.is_disabled()
    reason = page.get_by_text("Aucun modèle local prêt, installez un modèle ou autorisez le cloud")
    assert reason.is_visible()
    assert button.get_attribute("aria-describedby") == reason.get_attribute("id")
    # Le cloud autorisé : la phrase ne le propose plus, la raison redevient celle du nombre de modèles.
    page.get_by_label("Autoriser le cloud").check()
    page.locator(".wl-notice-info").filter(has_text="restent utilisables").wait_for()
    assert "Autoriser le cloud" not in page.locator(".wl-notice-info").inner_text()
    assert page.get_by_text("Choisissez au moins 2 modèles").is_visible()
    assert_no_axe_violations(page, "Arène sans modèle local")


def test_with_a_ready_local_model_there_is_no_info_alert(arena):
    assert arena.locator(".wl-notice-info").is_hidden()


def test_the_configuration_is_replaced_by_a_summary_until_the_run_ends(arena, server):
    pick(arena, "Charlie 3B")
    question = arena.get_by_label("Question", exact=True)
    asked = question.input_value()
    scripted(
        arena,
        server,
        {
            "fake:a": [{"text": "A"}, {"sleep_s": 1.5}, {"done": DONE}],
            "fake:b": [{"text": "B"}, {"done": DONE}],
            "fake:c": [{"text": "C"}, {"done": DONE}],
        },
    )
    assert arena.locator(".arena-summary").is_hidden()
    launch(arena)
    summary = arena.locator(".arena-summary")
    summary.wait_for(state="visible")
    assert arena.locator(".arena-form").is_hidden()  # configuration retirée
    assert arena.get_by_role("button", name="Lancer la comparaison").count() == 0  # masqué
    assert summary.get_by_role("heading", name="Comparaison", exact=True).is_visible()
    assert summary.locator("dd").first.inner_text() == asked
    models = summary.locator(".arena-summary-model")
    assert [m.inner_text().split("\n")[0] for m in models.all()] == [
        "Alpha 1B",
        "Bravo 2B",
        "Charlie 3B",
    ]
    assert "Local" in models.first.inner_text()
    assert arena.evaluate("document.activeElement.className") == "arena-summary-title"
    wait_banner(arena, "Comparaison en cours")
    assert arena.locator(".arena-banner").get_by_role("button", name="Arrêter").is_visible()
    wait_banner(arena, "Comparaison terminée")
    summary.wait_for(state="hidden")  # `run_ended` : la configuration revient
    assert arena.locator(".arena-form").is_visible()
    assert question.input_value() == asked
    assert arena.get_by_role("list", name="Modèles choisis").inner_text().count("Charlie 3B") == 1
    assert arena.get_by_role("button", name="Lancer la comparaison").is_enabled()


# --- Colonnes en flux ---------------------------------------------------------------------------------


def test_a_comparison_fills_one_column_per_model_with_status_and_final_measures(arena, server):
    commands: list[dict] = []
    pick(arena, "Charlie 3B")
    scripted(
        arena,
        server,
        {
            "fake:a": [{"text": "Réponse **alpha**"}, {"done": DONE}],
            "fake:b": [{"text": "Réponse bravo"}, {"done": {**DONE, "tps": 21.5}}],
            "fake:c": [{"text": "Réponse charlie"}, {"done": DONE}],
        },
        commands,
    )
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert commands == [
        {
            "models": ["fake:a", "fake:b", "fake:c"],
            "prompt": arena.get_by_label("Question", exact=True).input_value(),
            "allow_cloud": False,
        }
    ]
    assert arena.locator("wl-arena-lane").count() == 3
    assert banner(arena).inner_text().startswith("Comparaison terminée · 3 sur 3 · ")
    assert re.search(r"· \d+:\d\d$", banner(arena).inner_text())
    assert arena.locator(".arena-banner").get_by_role("button", name="Arrêter").is_hidden()
    for tag, name, text in (
        ("fake:a", "Alpha 1B", "Réponse alpha"),
        ("fake:b", "Bravo 2B", "Réponse bravo"),
        ("fake:c", "Charlie 3B", "Réponse charlie"),
    ):
        column = lane(arena, tag)
        assert column.get_by_role("heading", level=2).inner_text() == name
        assert "Local" in column.locator("wl-badge").first.inner_text()
        assert status_of(arena, tag) == "Terminé"
        assert column.locator(".wl-md").inner_text().strip() == text
        foot = column.locator(".wl-msg-foot").inner_text()
        for label in ("Débit", "Premier token", "Tokens", "Chargement", "Durée totale"):
            assert label in foot, (tag, label, foot)
    assert "21,5" in lane(arena, "fake:b").locator(".wl-msg-foot").inner_text()
    assert lane(arena, "fake:a").locator(".wl-md strong").inner_text() == "alpha"  # Markdown
    assert arena.get_by_text("Afficher toute la réponse").count() == 3
    # Annonce unique de fin (UX-DR10) : une seule région polie, l'écran parle, pas les fils.
    wait_for(
        arena,
        "() => [...document.querySelectorAll('[role=status]')].some("
        "(n) => n.textContent === 'Comparaison terminée : 3 réponses sur 3.')",
    )
    assert arena.locator("wl-chat-thread[silent]").count() == 3


def test_local_lanes_wait_for_their_turn_and_the_banner_counts_finished_lanes(arena, server):
    scripted(
        arena,
        server,
        {
            "fake:a": [
                {"load": "loading", "duration_s": 0.05},
                {"load": "loaded"},
                {"text": "A"},
                {"sleep_s": 1.5},
            ],
            "fake:b": [{"text": "B"}],
        },
    )
    launch(arena)
    wait_for(arena, "() => document.querySelectorAll('wl-arena-lane').length === 2")
    lane(arena, "fake:a").locator(".wl-md").filter(has_text="A").wait_for()
    assert status_of(arena, "fake:a") == "Génération"
    assert status_of(arena, "fake:b") == "En attente"
    assert (
        lane(arena, "fake:b").locator(".wl-msg").count() == 0
    )  # pas de durée qui court en attente
    assert banner(arena).inner_text().startswith("Comparaison en cours · 0 sur 2 · ")
    assert arena.locator(".arena-banner").get_by_role("button", name="Arrêter").is_visible()
    wait_banner(arena, "Comparaison terminée")
    assert status_of(arena, "fake:a") == status_of(arena, "fake:b") == "Terminé"


def test_a_notation_status_is_shown_as_a_status_only(arena, server):
    scripted(arena, server, {"fake:a": [{"text": "A"}], "fake:b": [{"text": "B"}]})
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    arena.evaluate("document.querySelector('wl-arena-lane').setStatus('judging')")
    assert status_of(arena, "fake:a") == "Notation"
    assert arena.get_by_text("/100").count() == 0  # ni note ni panneau de critères (story 3.3)


def test_a_lane_in_timeout_and_a_lane_in_failure_do_not_stop_the_others(arena, server):
    pick(arena, "Charlie 3B")
    scripted(
        arena,
        server,
        {
            "fake:a": [{"text": "Début"}, {"fail": "timeout"}],
            "fake:b": [{"text": "Partiel"}, {"fail": "ollama_error", "technical": "boum"}],
            "fake:c": [{"text": "Complet"}, {"done": DONE}],
        },
    )
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert status_of(arena, "fake:a") == "Délai dépassé"
    assert (
        lane(arena, "fake:a").locator(".wl-lane-note").inner_text()
        == "Délai dépassé pour ce modèle. Les autres continuent."
    )
    assert status_of(arena, "fake:b") == "Échec"
    assert lane(arena, "fake:b").locator("wl-error").inner_text().strip()  # message et action
    assert status_of(arena, "fake:c") == "Terminé"
    assert lane(arena, "fake:c").locator(".wl-lane-note").is_hidden()
    assert lane(arena, "fake:c").locator(".wl-md").inner_text().strip() == "Complet"
    assert lane(arena, "fake:a").locator(".wl-md").inner_text().strip() == "Début"  # partiel gardé
    assert banner(arena).inner_text().startswith("Comparaison terminée · 3 sur 3")


# --- Arrêt, reprise, run déjà actif ----------------------------------------------------------------------------


def test_stop_cancels_every_lane_and_keeps_the_partial_answers(arena, server):
    scripted(
        arena,
        server,
        {"fake:a": [{"text": "Partiel"}, {"sleep_s": 30}], "fake:b": [{"text": "Jamais"}]},
    )
    launch(arena)
    lane(arena, "fake:a").locator(".wl-md").filter(has_text="Partiel").wait_for()
    arena.get_by_role("button", name="Arrêter").click()
    wait_banner(arena, "Comparaison arrêtée")
    assert status_of(arena, "fake:a") == status_of(arena, "fake:b") == "Arrêté"
    assert lane(arena, "fake:a").locator(".wl-md").inner_text().strip() == "Partiel"
    assert lane(arena, "fake:b").locator(".wl-md").count() == 0  # jamais démarrée : pas de réponse
    assert arena.get_by_role("button", name="Lancer la comparaison").is_enabled()


def test_escape_stops_the_comparison(arena, server):
    scripted(arena, server, {"fake:a": [{"text": "Partiel"}, {"sleep_s": 30}]})
    launch(arena)
    lane(arena, "fake:a").locator(".wl-md").filter(has_text="Partiel").wait_for()
    arena.keyboard.press("Escape")
    wait_banner(arena, "Comparaison arrêtée")
    assert status_of(arena, "fake:a") == "Arrêté"


def test_the_stream_resumes_by_after_without_loss_or_duplicate_after_a_visit_to_home(
    arena, server, traffic
):
    words = ["un ", "deux ", "trois ", "quatre "]
    slow = [step for word in words for step in ({"text": word}, {"sleep_s": 0.6})]
    scripted(arena, server, {"fake:a": slow, "fake:b": [{"text": "bravo"}]})
    launch(arena)
    lane(arena, "fake:a").locator(".wl-md").filter(has_text="un").wait_for()
    run_id = STARTED[-1][1]

    arena.evaluate("location.hash = '#/'")
    arena.locator("section[data-screen=arena-compare]").wait_for(state="hidden")
    time.sleep(1.5)  # la génération continue pendant l'absence
    arena.evaluate("location.hash = '#/arene/comparer'")
    wait_banner(arena, "Comparaison terminée")

    assert lane(arena, "fake:a").locator(".wl-md").inner_text().strip() == "un deux trois quatre"
    assert lane(arena, "fake:b").locator(".wl-md").inner_text().strip() == "bravo"
    streams = [url for url in traffic.urls if f"/api/runs/{run_id}/events" in url]
    assert len(streams) == 2 and "?after=" not in streams[0] and "?after=" in streams[1]
    assert arena.locator("wl-arena-lane").count() == 2


def test_a_running_arena_is_joined_on_run_busy_and_by_its_url(arena_lenient, server):
    page = arena_lenient
    run_id = start_run(page, server, {"fake:a": [{"text": "En cours"}, {"sleep_s": 1.5}]})
    scripted(page, server, {})
    launch(page)  # 409 run_busy : la comparaison active est rejointe, sans erreur
    lane(page, "fake:a").locator(".wl-md").filter(has_text="En cours").wait_for()
    assert page.get_by_text(
        f"Une comparaison est déjà en cours{NBSP}: vous la suivez."
    ).is_visible()
    assert page.locator("wl-error:visible").count() == 0
    assert (
        page.locator(".arena-summary").get_by_text("Question d'ailleurs").is_visible()
    )  # la question vient du flux
    wait_banner(page, "Comparaison terminée")

    # Une URL avec un run_id suit ce run (rejoué depuis le début).
    page.goto(f"{server.base_url}/#/arene/comparer/{run_id}")
    page.reload()
    wait_ready(page)
    wait_banner(page, "Comparaison terminée")
    assert lane(page, "fake:a").locator(".wl-md").inner_text().strip() == "En cours"


def test_an_unknown_run_in_the_url_is_said(page_tolerating_failed_requests, server):
    page = page_tolerating_failed_requests
    open_arena(page, server, "#/arene/comparer/inconnu")
    page.get_by_text("Cette comparaison est introuvable.").wait_for()
    assert page.locator("wl-arena-lane").count() == 0


def test_an_orchestration_failure_is_said_with_its_cause(page, server):
    """`run_ended` en `error` (échec de l'orchestration, AD-5) : « en échec » et la cause, pas
    « interrompue ». Le flux est simulé : le vrai service ne casse pas sur commande."""

    def frame(seq, kind, data):
        envelope = {
            "seq": seq,
            "run_id": "casse",
            "type": kind,
            "ts": "2026-10-18T10:00:00Z",
            "data": data,
        }
        return f"id: {seq}\ndata: {json.dumps(envelope)}\n\n"

    body = "".join(
        [
            frame(1, "run_started", {"kind": "arena", "models": ["fake:a", "fake:b"]}),
            frame(2, "lane_status", {"lane": "fake:a", "status": "cancelled"}),
            frame(3, "lane_status", {"lane": "fake:b", "status": "cancelled"}),
            frame(
                4,
                "run_ended",
                {
                    "status": "error",
                    "error": {"code": "internal", "message": "Orchestration cassée"},
                },
            ),
        ]
    )
    page.route(
        re.compile(r"/api/runs/casse/events"),
        lambda route: route.fulfill(status=200, content_type="text/event-stream", body=body),
    )
    open_arena(page, server, "#/arene/comparer/casse")
    wait_banner(page, "Comparaison en échec")
    assert page.locator("wl-error:visible").filter(has_text="Orchestration cassée").count() == 1
    assert status_of(page, "fake:a") == "Arrêté"


# --- Mise en page ---------------------------------------------------------------------------------------------


def three_columns(page, server):
    pick(page, "Charlie 3B")
    long_text = "mot " * 400
    scripted(
        page,
        server,
        {
            "fake:a": [{"text": long_text}, {"done": DONE}],
            "fake:b": [{"text": "Bravo"}, {"done": DONE}],
            "fake:c": [{"text": "Charlie"}, {"done": DONE}],
        },
    )
    launch(page)
    wait_banner(page, "Comparaison terminée")


def box(page, selector):
    return page.locator(selector).first.bounding_box()


def four_columns(page, server, texts=None):
    for name in ("Charlie 3B", "Delta 4B"):
        pick(page, name)
    long_text = "mot " * 400
    scripted(
        page,
        server,
        {
            "fake:a": [{"text": long_text}, {"done": DONE}],
            "fake:b": [{"text": long_text}, {"done": DONE}],
            "fake:c": [{"text": "Court"}, {"done": DONE}],
            "fake:d": [{"text": long_text}, {"done": DONE}],
        },
    )
    launch(page)
    wait_banner(page, "Comparaison terminée")


def test_from_1440_px_four_models_make_four_columns_with_the_answer_folded_on_four_lines(
    arena, server
):
    four_columns(arena, server)
    lanes = arena.locator(".arena-lanes")
    sizes = lanes.evaluate("(n) => [n.clientWidth, n.scrollWidth]")
    assert sizes[1] <= sizes[0]  # aucune colonne hors de la vue
    container = lanes.bounding_box()
    boxes = [lane(arena, tag).bounding_box() for tag in ("fake:a", "fake:b", "fake:c", "fake:d")]
    assert len({round(b["y"]) for b in boxes}) == 1  # une seule rangée de quatre colonnes
    assert boxes[-1]["x"] + boxes[-1]["width"] <= container["x"] + container["width"] + 1
    text = lane(arena, "fake:a").locator(".wl-msg-text")
    metrics = text.evaluate(
        "(n) => [n.clientHeight, n.scrollHeight, parseFloat(getComputedStyle(n).lineHeight)]"
    )
    assert metrics[1] > metrics[0]  # la réponse est plus longue que son repli
    assert metrics[0] <= 4 * metrics[2] + 1  # 4 lignes
    short = lane(arena, "fake:c").locator(".wl-msg-text")
    assert short.evaluate(
        "(n) => n.scrollHeight <= n.clientHeight"
    )  # une réponse courte reste entière
    button = lane(arena, "fake:a").get_by_role("button", name="Afficher toute la réponse")
    assert button.is_visible()
    button.click()
    assert text.evaluate("(n) => n.clientHeight") > 4 * metrics[2] * 2
    assert lane(arena, "fake:b").locator(".wl-msg-text").evaluate("(n) => n.clientHeight") <= (
        4 * metrics[2] + 1
    )  # les autres colonnes restent repliées
    lane(arena, "fake:a").get_by_role("button", name="Réduire la réponse").click()
    assert text.evaluate("(n) => n.clientHeight") <= 4 * metrics[2] + 1


def test_below_1440_px_four_models_keep_the_two_column_layout(arena, server):
    arena.set_viewport_size({"width": 1200, "height": 900})
    four_columns(arena, server)
    sizes = arena.locator(".arena-lanes").evaluate("(n) => [n.clientWidth, n.scrollWidth]")
    assert sizes[1] > sizes[0]  # défilement horizontal, comme à 3 modèles
    text = lane(arena, "fake:a").locator(".wl-msg-text")
    assert text.evaluate("(n) => n.clientHeight") > 6 * 24  # pas de repli à 4 lignes


def test_between_1024_and_1439_px_two_columns_are_visible_with_a_horizontal_scroll(arena, server):
    arena.set_viewport_size({"width": 1200, "height": 900})
    three_columns(arena, server)
    lanes = arena.locator(".arena-lanes")
    sizes = lanes.evaluate("(n) => [n.clientWidth, n.scrollWidth]")
    assert sizes[1] > sizes[0]  # défilement horizontal
    first = lane(arena, "fake:a").bounding_box()
    second = lane(arena, "fake:b").bounding_box()
    container = lanes.bounding_box()
    assert first["x"] >= container["x"] - 1
    assert second["x"] + second["width"] <= container["x"] + container["width"] + 1  # visible
    assert lane(arena, "fake:c").bounding_box()["x"] >= container["x"] + container["width"] - 1
    head = lane(arena, "fake:a").locator(".wl-lane-head")
    assert head.evaluate("(n) => getComputedStyle(n).position") == "sticky"
    assert lanes.get_attribute("tabindex") == "0"


def test_from_1440_px_every_column_is_visible_without_horizontal_scroll(arena, server):
    three_columns(arena, server)
    sizes = arena.locator(".arena-lanes").evaluate("(n) => [n.clientWidth, n.scrollWidth]")
    assert sizes[1] <= sizes[0]
    container = arena.locator(".arena-lanes").bounding_box()
    for tag in ("fake:a", "fake:b", "fake:c"):
        item = lane(arena, tag).bounding_box()
        assert item["x"] + item["width"] <= container["x"] + container["width"] + 1
    assert arena.get_by_role("tablist").is_hidden()


def test_under_768_px_the_arena_becomes_tabs_by_model(arena, server):
    three_columns(arena, server)
    arena.set_viewport_size({"width": 600, "height": 900})
    tablist = arena.get_by_role("tablist", name="Modèles comparés")
    tablist.wait_for(state="visible")
    tabs = tablist.get_by_role("tab")
    assert tabs.all_inner_texts() == [
        "Alpha 1B · Terminé",
        "Bravo 2B · Terminé",
        "Charlie 3B · Terminé",
    ]
    assert arena.locator("wl-arena-lane:visible").count() == 1
    assert lane(arena, "fake:a").is_visible()
    assert tabs.nth(0).get_attribute("aria-selected") == "true"
    assert lane(arena, "fake:a").get_attribute("role") == "tabpanel"
    tabs.nth(0).focus()
    arena.keyboard.press("ArrowRight")
    assert lane(arena, "fake:b").is_visible() and lane(arena, "fake:a").is_hidden()
    assert tabs.nth(1).get_attribute("aria-selected") == "true"
    assert arena.evaluate("document.activeElement.textContent") == "Bravo 2B · Terminé"
    arena.keyboard.press("End")
    assert lane(arena, "fake:c").is_visible()
    assert arena.locator(".wl-lane-focus:visible").count() == 0  # le mode focus n'a pas de sens ici
    # De retour en large : toutes les colonnes, en groupes.
    arena.set_viewport_size({"width": 1440, "height": 900})
    tablist.wait_for(state="hidden")
    assert arena.locator("wl-arena-lane:visible").count() == 3
    assert lane(arena, "fake:a").get_attribute("role") == "group"


def test_the_focus_mode_enlarges_one_column_and_hides_the_others(arena, server):
    three_columns(arena, server)
    button = lane(arena, "fake:b").get_by_role("button", name="Mode focus")
    assert button.get_attribute("aria-pressed") == "false"
    button.click()
    assert button.get_attribute("aria-pressed") == "true"
    assert lane(arena, "fake:b").is_visible()
    assert lane(arena, "fake:a").is_hidden() and lane(arena, "fake:c").is_hidden()
    width = lane(arena, "fake:b").bounding_box()["width"]
    assert width > arena.locator(".arena-lanes").bounding_box()["width"] * 0.9
    button.click()
    assert button.get_attribute("aria-pressed") == "false"
    assert arena.locator("wl-arena-lane:visible").count() == 3


def test_the_focus_mode_is_left_when_the_arena_becomes_tabs(arena, server):
    three_columns(arena, server)
    lane(arena, "fake:b").get_by_role("button", name="Mode focus").click()
    arena.set_viewport_size({"width": 600, "height": 900})
    arena.get_by_role("tablist", name="Modèles comparés").wait_for(state="visible")
    assert lane(arena, "fake:a").is_visible()  # l'onglet choisi reste lisible
    assert arena.locator(".arena-lanes").get_attribute("data-focus") is None
    arena.set_viewport_size({"width": 1440, "height": 900})
    arena.get_by_role("tablist", name="Modèles comparés").wait_for(state="hidden")
    assert arena.locator("wl-arena-lane:visible").count() == 3


def test_show_the_whole_answer_lifts_the_height_limit(arena, server):
    three_columns(arena, server)
    column = lane(arena, "fake:a")
    log = column.get_by_role("log")
    limited = log.evaluate("(n) => n.clientHeight")
    assert (
        log.evaluate("(n) => n.scrollHeight") > limited
    )  # la réponse est plus longue que la colonne
    column.get_by_role("button", name="Afficher toute la réponse").click()
    assert log.evaluate("(n) => n.clientHeight") > limited
    column.get_by_role("button", name="Réduire la réponse").click()
    assert log.evaluate("(n) => n.clientHeight") == limited


# --- Accessibilité et trafic ---------------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_arena_screen(arena, server, theme):
    pick(arena, "Charlie 3B")
    scripted(
        arena,
        server,
        {
            "fake:a": [{"text": "Lent **en cours**"}, {"sleep_s": 2.5}, {"done": DONE}],
            "fake:b": [{"text": "Partiel"}, {"fail": "ollama_error", "technical": "boum"}],
            "fake:c": [{"text": "Début"}, {"fail": "timeout"}],
        },
    )
    arena.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(arena, f"formulaire, thème {theme}")
    launch(arena)
    lane(arena, "fake:a").locator(".wl-md strong").wait_for()
    assert_no_axe_violations(arena, f"comparaison en cours, thème {theme}")
    wait_banner(arena, "Comparaison terminée")
    assert_no_axe_violations(arena, f"comparaison terminée, thème {theme}")
    arena.set_viewport_size({"width": 600, "height": 900})
    arena.get_by_role("tablist").wait_for(state="visible")
    assert_no_axe_violations(arena, f"onglets, thème {theme}")
    arena.set_viewport_size({"width": 1440, "height": 900})
    arena.get_by_role("tablist").wait_for(state="hidden")
    lane(arena, "fake:a").get_by_role("button", name="Mode focus").click()
    assert_no_axe_violations(arena, f"mode focus, thème {theme}")


@pytest.mark.parametrize("width", [320, 1440])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_with_four_models_the_summary_and_the_folded_answers(
    arena, server, theme, width
):
    arena.set_viewport_size({"width": width, "height": 900})
    arena.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    for name in ("Charlie 3B", "Delta 4B"):
        pick(arena, name)
    long_text = "mot " * 400
    scripted(
        arena,
        server,
        {
            "fake:a": [{"text": long_text}, {"sleep_s": 2.5}, {"done": DONE}],
            "fake:b": [{"text": long_text}, {"done": DONE}],
            "fake:c": [{"text": "Court"}, {"done": DONE}],
            "fake:d": [{"text": long_text}, {"done": DONE}],
        },
    )
    launch(arena)
    arena.locator(".arena-summary").wait_for(state="visible")
    lane(arena, "fake:a").locator(".wl-md").wait_for()
    assert_no_axe_violations(arena, f"résumé et colonnes repliées, {width} px, thème {theme}")
    wait_banner(arena, "Comparaison terminée")
    assert_no_axe_violations(arena, f"configuration revenue, {width} px, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_in_projection_mode(arena, server, theme):
    scripted(arena, server, {"fake:a": [{"text": "A"}, {"done": DONE}], "fake:b": [{"text": "B"}]})
    arena.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    arena.evaluate("document.documentElement.setAttribute('data-projection', 'true')")
    assert_no_axe_violations(arena, f"projection, formulaire, thème {theme}")
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert_no_axe_violations(arena, f"projection, colonnes, thème {theme}")


def test_every_request_stays_on_127_0_0_1(arena, server, traffic):
    scripted(arena, server, {})
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert traffic.urls and all(url.startswith("http://127.0.0.1") for url in traffic.urls)
