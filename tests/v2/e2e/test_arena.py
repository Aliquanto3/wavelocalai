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

from .test_shell import (
    assert_no_axe_violations,
    assert_no_horizontal_scroll,
    wait_for,
    wait_ready,
)

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
JUDGE_DEFAULT = "fake:d"
JUDGE_REASON = "Le plus gros modèle local qui tient en mémoire."
DEFAULT_CRITERIA = ["exactitude", "pertinence", "clarté"]
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
    # L'annulation est asynchrone : on attend la fin de chaque run (sinon `409 run_busy` au suivant).
    deadline = time.monotonic() + 10
    for base_url, run_id in STARTED:
        url = f"{base_url}/api/runs/{run_id}"
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
                    if json.load(response).get("status") != "running":
                        break
            except OSError:
                break
            time.sleep(0.05)
    STARTED.clear()


def install_models(page, judge_tags=(JUDGE_DEFAULT,), cloud=()):
    """Simule la liste des modèles (`cloud` : seulement avec `allow_cloud=true`, comme le serveur)
    et les défauts : `arena` et `judge` (`judge_tags` : vide quand aucun juge ne convient)."""

    def on_models(route):
        listing = MODELS + (list(cloud) if "allow_cloud=true" in route.request.url else [])
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"models": listing, "ollama_up": True, "refreshed_at": "2026-10-18T10:00:00Z"}
            ),
        )

    def on_defaults(route):
        judge = "purpose=judge" in route.request.url
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "purpose": "judge" if judge else "arena",
                    "tags": list(judge_tags) if judge else ["fake:a", "fake:b"],
                    "reason": JUDGE_REASON if judge else REASON,
                    "source": "rule",
                }
            ),
        )

    page.route(re.compile(r"/api/models\?"), on_models)
    page.route(re.compile(r"/api/models/defaults\?"), on_defaults)


def verdict(score: int, reason: str = "Réponse claire et exacte.") -> list[dict]:
    """Le script d'un juge qui note `score` sur 100 (sortie structurée, texte JSON)."""
    return [{"text": json.dumps({"score": score, "reason": reason})}, {"done": DONE}]


def scripted(page, server, scripts, commands=None, judge=None):
    """Les commandes d'Arène de la page lancent des lanes scriptées (route de test).

    `judge` : `{"script": [...], "origin": "local" | "cloud"}`, le juge `fake` de la commande
    (son tag est celui que la page envoie) ; sans lui, aucune notation n'est câblée."""

    def on_arena(route):
        body = json.loads(route.request.post_data)
        if commands is not None:
            commands.append(body)
        lanes = [
            {"tag": tag, "script": scripts.get(tag, [{"text": "ok"}, {"done": DONE}])}
            for tag in body["models"]
        ]
        payload = {
            "prompt": body["prompt"],
            "criteria": body.get("criteria", []),
            "allow_cloud": body["allow_cloud"],
            "lanes": lanes,
        }
        if judge is not None and body.get("judge"):
            payload["judge"] = {"tag": body["judge"], **judge}
        response = page.request.post(f"{server.base_url}/api/test/arena", data=payload)
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
    wait_for(
        page,
        "() => document.querySelector('wl-model-picker[purpose=judge]')?.values.length === 1",
    )


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
    picker = page.locator("wl-model-picker[purpose=arena]")
    picker.get_by_role("combobox").click()
    picker.locator("[role=option]", has_text=name).click()
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
    assert button.is_disabled() and arena.get_by_text("Choisissez au plus 4 modèles").is_visible()
    arena.get_by_label("Question", exact=True).fill("")
    arena.get_by_role("button", name="Retirer Delta 4B").click()
    arena.get_by_role("button", name="Retirer Echo 5B").click()
    assert arena.get_by_text("Saisissez une question").is_visible() and button.is_disabled()


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
            "criteria": DEFAULT_CRITERIA,
            "judge": JUDGE_DEFAULT,  # le défaut `judge` du serveur, proposé par le sélecteur
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


# --- Notation (story 3.3) : panneau de critères, juge, note et « non évalué » ----------------------------------


def panel(page):
    return page.locator("details.arena-judge-panel")


def open_panel(page):
    panel(page).get_by_text("Critères de notation", exact=True).click()
    assert panel(page).get_attribute("open") is not None


def criteria_inputs(page):
    return panel(page).locator(".arena-criterion-input")


def criteria_values(page):
    return criteria_inputs(page).evaluate_all("(nodes) => nodes.map((n) => n.value)")


def score_of(page, tag):
    return lane(page, tag).locator(".wl-lane-score")


def test_the_criteria_panel_is_folded_and_proposes_the_default_judge_and_criteria(arena):
    box_ = panel(arena)
    assert box_.get_attribute("open") is None  # replié
    assert box_.locator("summary").inner_text() == "Critères de notation"
    assert not box_.locator(".arena-judge-body").is_visible()
    open_panel(arena)
    judge = box_.locator("wl-model-picker[purpose=judge]")
    assert judge.get_by_role("combobox", name="Juge", exact=True).input_value() == "Delta 4B"
    current = box_.locator(".arena-judge-current")
    assert (
        " ".join(current.inner_text().replace(NBSP, " ").split()) == "Juge retenu : Delta 4B Local"
    )
    assert "Local" in current.locator("wl-badge").inner_text()
    assert criteria_values(arena) == DEFAULT_CRITERIA
    help_ = box_.get_by_text("Au plus 8 critères de 64 caractères.")
    assert help_.is_visible() and "exactitude, pertinence, clarté." in help_.inner_text()
    assert "moins de 4 milliards de paramètres actifs" in box_.inner_text()  # note peu fiable


def test_criteria_are_edited_added_up_to_eight_removed_reset_and_sent_cleaned(arena, server):
    commands: list[dict] = []
    scripted(arena, server, {}, commands)
    open_panel(arena)
    inputs = criteria_inputs(arena)
    assert inputs.first.get_attribute("maxlength") == "64"
    assert inputs.nth(1).get_attribute("aria-label") == "Critère 2"
    add = panel(arena).get_by_role("button", name="Ajouter un critère")
    for _ in range(5):
        add.click()
    assert inputs.count() == 8 and add.is_disabled()
    assert panel(arena).get_by_text(f"Huit critères au plus{NBSP}: retirez-en un").is_visible()
    # Le focus suit le nouveau critère, qui se remplit au clavier ; Entrée ajoute, n'envoie pas.
    arena.keyboard.type("concision")
    assert criteria_values(arena)[-1] == "concision"
    panel(arena).get_by_role("button", name="Retirer le critère 8").click()
    assert inputs.count() == 7 and add.is_enabled()
    inputs.nth(6).fill("")  # un critère vide n'est pas envoyé
    inputs.nth(5).fill("  Clarté ")  # un doublon (casse et espaces ignorés) non plus
    inputs.nth(4).fill("ton" * 30)
    assert inputs.nth(4).input_value() == ("ton" * 30)[:64]
    inputs.nth(3).fill("style")
    inputs.nth(3).press("Enter")
    assert inputs.count() == 8 and commands == []  # Entrée a ajouté un critère, rien n'est parti
    assert arena.evaluate("document.activeElement.classList.contains('arena-criterion-input')")
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert commands[0]["criteria"] == [
        "exactitude",
        "pertinence",
        "clarté",
        "style",
        ("ton" * 30)[:64],
    ]
    # Rétablir les critères par défaut ; sans aucun critère, rien n'est envoyé (le serveur décide).
    panel(arena).get_by_role("button", name="Rétablir les critères par défaut").click()
    assert criteria_values(arena) == DEFAULT_CRITERIA
    for _ in range(3):
        panel(arena).get_by_role("button", name="Retirer le critère 1").click()
    assert inputs.count() == 0
    assert arena.evaluate("document.activeElement.textContent") == "Ajouter un critère"
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert commands[1]["criteria"] == []


def test_the_panel_opens_and_works_from_the_keyboard(arena):
    summary = panel(arena).locator("summary")
    summary.focus()
    arena.keyboard.press("Enter")
    assert panel(arena).get_attribute("open") is not None
    ring = summary.evaluate("(n) => getComputedStyle(n).outlineStyle")
    assert ring != "none"  # focus visible
    arena.keyboard.press("Tab")  # le sélecteur du juge
    assert arena.evaluate("document.activeElement.getAttribute('role')") == "combobox"
    for _ in range(5):  # le sélecteur puis, sans piège, le premier critère
        arena.keyboard.press("Tab")
        if arena.evaluate("document.activeElement.getAttribute('aria-label')") == "Critère 1":
            break
    assert arena.evaluate("document.activeElement.getAttribute('aria-label')") == "Critère 1"
    arena.keyboard.press("Enter")  # ajoute un critère après celui-ci, sans envoyer
    assert criteria_inputs(arena).count() == 4
    assert arena.evaluate("document.activeElement.getAttribute('aria-label')") == "Critère 2"


def test_a_column_shows_notation_then_its_score_its_reason_and_the_one_judge_label(arena, server):
    commands: list[dict] = []
    scripted(
        arena,
        server,
        {
            "fake:a": [{"text": "Alpha"}, {"done": DONE}],
            "fake:b": [{"text": "Bravo"}, {"done": DONE}],
        },
        commands,
        judge={"script": [{"sleep_s": 0.8}, *verdict(72)], "origin": "local"},
    )
    launch(arena)
    wait_for(arena, "() => document.querySelectorAll('wl-arena-lane').length === 2")
    wait_for(
        arena,
        "() => [...document.querySelectorAll('.wl-lane-status-text')].some((n) => n.textContent === 'Notation')",
    )
    assert score_of(arena, "fake:a").is_hidden()  # pas de note avant l'arrivée de `judge_score`
    wait_banner(arena, "Comparaison terminée")
    assert commands[0]["judge"] == JUDGE_DEFAULT
    for tag in ("fake:a", "fake:b"):
        score = score_of(arena, tag)
        assert score.locator(".wl-score-line").inner_text() == "72/100"
        assert score.locator(".wl-score-reason").inner_text() == "Réponse claire et exacte."
        assert score.locator("wl-badge[kind=single-judge]").inner_text().strip() == "un seul juge"
        # Un juge local de taille inconnue : note peu fiable, dite en texte, avec son icône.
        weak = score.locator("wl-badge[kind=unreliable]")
        assert weak.inner_text().strip() == "note peu fiable" and weak.locator("use").count() == 1
        assert status_of(arena, tag) == "Terminé"
        assert "0/100" not in score.inner_text().replace("72/100", "")
    info = arena.locator(".arena-judge-info")
    assert (
        info.locator(".arena-judge-who")
        .inner_text()
        .replace(NBSP, " ")
        .startswith("Juge : Delta 4B")
    )
    assert "Local" in info.locator(".arena-judge-who wl-badge[kind=local]").inner_text()
    assert info.locator("wl-badge[kind=single-judge]").count() == 1
    alert = info.locator(".arena-judge-alert")
    assert alert.get_attribute("role") == "status"
    assert "Note peu fiable" in alert.inner_text() and "moins de 4 milliards" in alert.inner_text()
    used = info.locator(".help").inner_text().replace(NBSP, " ")
    assert used == "Critères : exactitude, pertinence, clarté"
    # Chaque note est annoncée poliment, l'une après l'autre.
    wait_for(
        arena,
        "() => document.querySelectorAll('[aria-live=polite][aria-atomic=false] p').length === 2",
    )
    announced = arena.locator("[aria-live=polite][aria-atomic=false] p").all_inner_texts()
    assert sorted(a.replace(NBSP, " ") for a in announced) == [  # l'ordre dépend de la place Ollama
        "Alpha 1B : note 72 sur 100, peu fiable.",
        "Bravo 2B : note 72 sur 100, peu fiable.",
    ]


def test_a_column_in_notation_when_the_stream_is_lost_says_not_evaluated_interrupted(arena):
    # Flux perdu (`finish("interrupted")`) pendant la notation : la colonne ne reste pas « Notation »
    # sans note ; une colonne déjà notée garde sa note et passe à « Terminé ».
    result = arena.evaluate(
        """() => {
          const make = (tag) => {
            const el = document.createElement('wl-arena-lane');
            document.body.append(el);
            el.setup({ tag, name: tag, origin: 'local' });
            el.setStatus('generating');
            el.setStatus('judging');
            return el;
          };
          const lost = make('perdu');
          const scored = make('note');
          scored.setScore({ score: 64, reason: 'Correct.' });
          lost.interrupt();
          scored.interrupt();
          const read = (el) => ({
            status: el.querySelector('.wl-lane-status-text').textContent,
            score: el.querySelector('.wl-lane-score').innerText,
          });
          const out = { lost: read(lost), scored: read(scored) };
          lost.remove();
          scored.remove();
          return out;
        }"""
    )
    assert result["lost"]["status"] == "Interrompu"
    assert (
        "Non évalué" in result["lost"]["score"]
        and "Comparaison interrompue" in result["lost"]["score"]
    )
    assert "64" in result["scored"]["score"] and result["scored"]["status"] == "Terminé"


def test_a_cloud_judge_wears_the_cloud_badge_is_not_unreliable_and_needs_the_cloud_switch(
    arena, server
):
    commands: list[dict] = []
    nuage = {**BASE_MODEL, "tag": "fake:nuage", "name": "Nuage 70B", "origin": "cloud"}
    install_models(arena, cloud=[nuage])
    open_panel(arena)
    judge = panel(arena).locator("wl-model-picker[purpose=judge]")
    judge.get_by_role("combobox").click()
    assert judge.locator("[role=option]", has_text="Nuage 70B").count() == 0  # cloud coupé
    arena.keyboard.press("Escape")
    arena.evaluate(
        """async () => {
            const { store } = await import('/static/core/store.js');
            store.set({ allowCloud: true });
        }"""
    )
    judge.get_by_role("combobox").click()
    judge.locator("[role=option]", has_text="Nuage 70B").click()
    current = panel(arena).locator(".arena-judge-current")
    assert "Cloud" in current.locator("wl-badge").inner_text()
    scripted(
        arena, server, {}, commands, judge={"script": verdict(88, "Excellent."), "origin": "cloud"}
    )
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert commands[0]["judge"] == "fake:nuage" and commands[0]["allow_cloud"] is True
    info = arena.locator(".arena-judge-info")
    assert "Cloud" in info.locator(".arena-judge-who wl-badge").first.inner_text()
    assert info.locator(".arena-judge-alert").count() == 0  # un juge cloud n'est pas « peu fiable »
    assert score_of(arena, "fake:a").locator(".wl-score-line").inner_text() == "88/100"
    assert score_of(arena, "fake:a").locator("wl-badge[kind=unreliable]").count() == 0
    assert score_of(arena, "fake:a").locator("wl-badge[kind=single-judge]").count() == 1


def test_not_evaluated_is_said_with_its_reason_and_is_never_zero(arena, server):
    pick(arena, "Charlie 3B")
    pick(arena, "Delta 4B")
    scripted(
        arena,
        server,
        {
            "fake:a": [{"done": DONE}],  # aucune réponse
            "fake:b": [{"text": "Partiel"}, {"fail": "ollama_error", "technical": "boum"}],
            "fake:c": [{"text": "Début"}, {"fail": "timeout"}],
            "fake:d": [{"text": "Complet"}, {"done": DONE}],
        },
        judge={"script": verdict(64), "origin": "local"},
    )
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    expected = {
        "fake:a": "Réponse vide",
        "fake:b": "Échec du modèle",
        "fake:c": "Délai dépassé",
    }
    for tag, reason in expected.items():
        score = score_of(arena, tag)
        assert score.locator(".wl-score-none").inner_text() == "Non évalué", tag
        assert score.locator(".wl-score-reason").inner_text() == reason, tag
        assert "/100" not in score.inner_text() and "0" not in score.inner_text(), tag
        assert score.locator("wl-badge").count() == 0, tag  # pas de « un seul juge » sans note
    assert score_of(arena, "fake:d").locator(".wl-score-line").inner_text() == "64/100"
    texts = arena.locator("[aria-live=polite][aria-atomic=false] p").all_inner_texts()
    assert f"Alpha 1B{NBSP}: non évalué, réponse vide." in texts


@pytest.mark.parametrize(
    ("script", "reason"),
    [
        ([{"fail": "ollama_error", "technical": "boum"}], "Juge indisponible"),
        ([{"text": "pas du JSON"}, {"done": DONE}], "Sortie du juge invalide"),
    ],
    ids=["juge en panne", "sortie invalide"],
)
def test_an_unavailable_or_invalid_judge_gives_not_evaluated_with_the_reason(
    arena, server, script, reason
):
    scripted(arena, server, {}, judge={"script": script, "origin": "local"})
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    for tag in ("fake:a", "fake:b"):
        score = score_of(arena, tag)
        assert score.locator(".wl-score-none").inner_text() == "Non évalué"
        assert score.locator(".wl-score-reason").inner_text() == reason
        assert status_of(arena, tag) == "Terminé"  # la lane finit : seule la note manque


def test_without_any_judge_the_screen_says_so_and_scores_are_not_evaluated(page, server):
    commands: list[dict] = []
    install_models(page, judge_tags=())
    page.goto(f"{server.base_url}/#/arene/comparer")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.values.length === 2")
    scripted(page, server, {}, commands)
    launch(page)
    wait_banner(page, "Comparaison terminée")
    assert "judge" not in commands[0]  # le serveur décide : ici, aucun juge
    info = page.locator(".arena-judge-info")
    assert "Aucun juge n'est disponible" in info.inner_text()
    assert "ne vaut jamais 0" in info.inner_text()
    for tag in ("fake:a", "fake:b"):
        assert score_of(page, tag).locator(".wl-score-none").inner_text() == "Non évalué"
        assert score_of(page, tag).locator(".wl-score-reason").inner_text() == "Juge indisponible"


def test_scores_survive_a_visit_elsewhere_without_loss_or_duplicate(arena, server):
    slow = [step for word in ("un ", "deux ") for step in ({"text": word}, {"sleep_s": 0.7})]
    scripted(
        arena,
        server,
        {"fake:a": slow, "fake:b": [{"text": "bravo"}]},
        judge={"script": verdict(55), "origin": "local"},
    )
    launch(arena)
    lane(arena, "fake:a").locator(".wl-md").filter(has_text="un").wait_for()
    arena.evaluate("location.hash = '#/'")
    arena.locator("section[data-screen=arena-compare]").wait_for(state="hidden")
    time.sleep(2.5)  # génération et notation continuent pendant l'absence
    arena.evaluate("location.hash = '#/arene/comparer'")
    wait_banner(arena, "Comparaison terminée")
    assert arena.locator(".wl-score-value").all_inner_texts() == ["55", "55"]
    assert arena.locator("[aria-live=polite][aria-atomic=false] p").count() == 2


def test_the_arena_with_scores_fits_320_px_without_horizontal_scroll(arena, server):
    arena.set_viewport_size({"width": 320, "height": 800})
    scripted(arena, server, {}, judge={"script": verdict(41), "origin": "local"})
    open_panel(arena)
    assert_no_horizontal_scroll(arena)
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    arena.get_by_role("tablist").wait_for(state="visible")
    assert score_of(arena, "fake:a").locator(".wl-score-line").inner_text() == "41/100"
    assert_no_horizontal_scroll(arena)
    assert_no_axe_violations(arena, "320 px, notes")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_with_the_criteria_panel_and_the_scores(arena, server, theme):
    pick(arena, "Charlie 3B")
    scripted(
        arena,
        server,
        {
            "fake:a": [{"done": DONE}],
            "fake:b": [{"text": "Partiel"}, {"fail": "ollama_error", "technical": "boum"}],
            "fake:c": [{"text": "Complet"}, {"done": DONE}],
        },
        judge={"script": verdict(72), "origin": "local"},
    )
    arena.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    open_panel(arena)
    panel(arena).get_by_role("button", name="Ajouter un critère").click()
    assert_no_axe_violations(arena, f"panneau ouvert, thème {theme}")
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert_no_axe_violations(arena, f"notes et non évalué, thème {theme}")
    arena.set_viewport_size({"width": 600, "height": 900})
    arena.get_by_role("tablist").wait_for(state="visible")
    assert_no_axe_violations(arena, f"onglets avec notes, thème {theme}")


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
    assert page.get_by_text("Question d'ailleurs").is_visible()  # la question vient du flux
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
