"""Créativité du modèle, export sur écran étroit, premier chargement lent, 409 (story 2.7) : l'écran
Chat dans un vrai navigateur, sur le vrai serveur et l'adaptateur `fake`.

La liste des modèles est simulée par le test (`default_temperature` comprise) ; les conversations
viennent de la route de test. Aucune requête ne sort de 127.0.0.1 (fixture `context`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from .test_chat import (  # noqa: F401 - fixtures et aides du chat
    DONE,
    MODEL,
    STARTED,
    answer_text,
    ask,
    cancel_leftover_runs,
    chat,
    chat_lenient,
    field,
    scripted,
    start_run,
)
from .test_conversations import (  # noqa: F401 - fixtures de conversation
    SECOND,
    call,
    conversation,
    install_list,
    open_screen,
    screen,
    wait_run,
)
from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
WARM = {**MODEL, "default_temperature": 0.7}
COOL = {**MODEL, "tag": "autre:7b", "name": "Autre 7B", "default_temperature": 1.2}
SILENT = {**MODEL, "tag": "muet:3b", "name": "Muet 3B", "default_temperature": None}
FIRST_LOAD = "Le premier appel charge le modèle en mémoire" + NBSP + ": de 8 à 26 secondes."


def slider(page):
    return page.get_by_label("Créativité")


def shown(page) -> str:
    return page.locator("output.chat-slider-value").inner_text()


def scripted_fake(page, server, script, commands):
    """Comme `scripted`, mais le run est celui du modèle `fake:1b` : les autres tags de la liste
    simulée n'existent pas côté serveur. `commands` garde la commande telle que la page l'a envoyée.
    """

    def on_chat(route):
        body = json.loads(route.request.post_data)
        commands.append(body)
        response = page.request.post(
            f"{server.base_url}/api/test/runs",
            data={"kind": "chat", "model": "fake:1b", "message": body["message"], "script": script},
        )
        assert response.ok, response.text()
        STARTED.append((server.base_url, response.json()["run_id"]))
        route.fulfill(status=response.status, content_type="application/json", body=response.text())

    page.route(re.compile(r"/api/chat/runs$"), on_chat)


def choose(page, name):
    page.get_by_role("combobox", name="Modèle", exact=True).click()
    page.locator("wl-model-picker [role=option]", has_text=name).click()


@pytest.fixture
def three_models(page, server):
    install_list(page, [WARM, COOL, SILENT], default="fake:1b")
    page.goto(f"{server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    return page


# --- Créativité : le défaut du modèle (D-12) ----------------------------------------------------


def test_the_slider_takes_the_default_of_the_chosen_model_and_the_fallback_when_unknown(
    three_models,
):
    page = three_models
    assert slider(page).input_value() == "0.7" and shown(page) == "0,7"
    help_text = page.locator(".chat-creativity-default")
    assert help_text.inner_text() == f"Valeur conseillée pour Factice 1B{NBSP}: 0,7."
    choose(page, "Autre 7B")
    assert slider(page).input_value() == "1.2" and shown(page) == "1,2"
    assert "Autre 7B" in help_text.inner_text()
    choose(page, "Muet 3B")  # `default_temperature: null` : repli à 0,2
    assert slider(page).input_value() == "0.2" and shown(page) == "0,2"
    assert help_text.inner_text() == f"Valeur par défaut{NBSP}: 0,2 (ce modèle n'en conseille pas)."


def test_a_moved_slider_stays_while_the_model_changes_and_the_sent_value_is_the_shown_one(
    three_models, server
):
    page = three_models
    commands: list[dict] = []
    scripted_fake(page, server, [{"text": "ok"}, {"done": DONE}], commands)
    slider(page).focus()
    page.keyboard.press("ArrowRight")  # 0,7 -> 0,75 (pas de 0,05)
    assert shown(page) == "0,75"
    choose(page, "Autre 7B")
    assert slider(page).input_value() == "0.75" and shown(page) == "0,75"  # déplacé : il reste
    ask(page, "Bonjour")
    page.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    assert [(c["model"], c["temperature"]) for c in commands] == [("autre:7b", 0.75)]


def test_an_untouched_slider_sends_the_model_default(three_models, server):
    page = three_models
    commands: list[dict] = []
    scripted_fake(page, server, [{"text": "ok"}, {"done": DONE}], commands)
    choose(page, "Autre 7B")
    assert shown(page) == "1,2"
    ask(page, "Bonjour")
    page.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    assert [(c["model"], c["temperature"]) for c in commands] == [("autre:7b", 1.2)]


def test_an_off_tenth_default_is_shown_and_sent_as_published(page, server):
    """0,15 (valeur publiée par Mistral) : ni arrondie par le curseur, ni différente de l'aide."""
    precise = {**MODEL, "default_temperature": 0.15}
    install_list(page, [precise], default="fake:1b")
    commands: list[dict] = []
    scripted_fake(page, server, [{"text": "ok"}, {"done": DONE}], commands)
    page.goto(f"{server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    assert slider(page).input_value() == "0.15" and shown(page) == "0,15"
    assert page.locator(".chat-creativity-default").inner_text().endswith(f"{NBSP}: 0,15.")
    ask(page, "Bonjour")
    page.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    assert [c["temperature"] for c in commands] == [0.15]


def test_clearing_the_conversation_gives_the_slider_back_to_the_model(three_models, server):
    page = three_models
    scripted(page, server, [{"text": "ok"}, {"done": DONE}])
    slider(page).focus()
    page.keyboard.press("ArrowRight")
    ask(page, "Bonjour")
    page.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    assert shown(page) == "0,75"
    page.get_by_role("button", name="Effacer la conversation").click()
    page.locator(".chat-notice").wait_for()
    assert slider(page).input_value() == "0.7" and shown(page) == "0,7"  # nouvelle conversation


def test_a_reopened_conversation_keeps_its_own_creativity(page, server):
    install_list(page, [WARM, COOL], default="autre:7b")
    status, started = call(
        server.base_url,
        "/api/chat/runs",
        {"model": "fake:1b", "message": "Avant", "temperature": 1.4, "allow_cloud": False},
    )
    assert status == 200, started
    wait_run(server.base_url, started["run_id"])
    page.goto(f"{server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    page.locator(".wl-msg-assistant").wait_for()
    assert slider(page).input_value() == "1.4" and shown(page) == "1,4"
    assert "0,7" in page.locator(".chat-creativity-default").inner_text()  # le conseil du modèle


# --- Menu « Exporter » sous 768 px (D-3) ---------------------------------------------------------


def exporter(page):
    return page.get_by_role("button", name="Exporter", exact=True)


def test_two_buttons_from_768_px_and_one_export_menu_below(screen):
    page = screen
    for width, narrow in ((1440, False), (768, False), (767, True), (320, True)):
        page.set_viewport_size({"width": width, "height": 900})
        assert page.get_by_role("button", name="Télécharger (JSON)").is_visible() is not narrow
        assert page.get_by_role("button", name="Télécharger (Markdown)").is_visible() is not narrow
        assert exporter(page).is_visible() is narrow, width


def test_the_export_menu_is_driven_by_keyboard_and_gives_the_focus_back(screen):
    page = screen
    page.set_viewport_size({"width": 500, "height": 900})
    toggle = exporter(page)
    assert toggle.get_attribute("aria-expanded") == "false"
    toggle.focus()
    page.keyboard.press("Enter")
    assert toggle.get_attribute("aria-expanded") == "true"
    items = page.get_by_role("menuitem")
    assert items.all_inner_texts() == ["Télécharger (JSON)", "Télécharger (Markdown)"]
    assert page.evaluate("document.activeElement.textContent") == "Télécharger (JSON)"
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.textContent") == "Télécharger (Markdown)"
    page.keyboard.press("ArrowDown")  # en boucle
    assert page.evaluate("document.activeElement.textContent") == "Télécharger (JSON)"
    page.keyboard.press("ArrowUp")
    assert page.evaluate("document.activeElement.textContent") == "Télécharger (Markdown)"
    page.keyboard.press("Escape")
    assert toggle.get_attribute("aria-expanded") == "false"
    assert page.evaluate("document.activeElement.textContent") == "Exporter"
    assert page.get_by_role("menuitem").count() == 0  # liste fermée : plus dans l'arbre


def test_escape_closes_the_menu_without_stopping_a_running_answer(page, server, conversation):
    open_screen(page, server)
    page.locator(".wl-msg-assistant").first.wait_for()
    page.set_viewport_size({"width": 500, "height": 900})
    scripted(page, server, [{"text": "Début"}, {"sleep_s": 3}, {"text": " fin"}])
    ask(page, "Encore")
    page.locator(".wl-run-stage").filter(has_text="Génération").wait_for()
    exporter(page).click()
    page.keyboard.press("Escape")
    assert exporter(page).get_attribute("aria-expanded") == "false"
    assert page.locator(".wl-run-stage").inner_text() == "Génération…"  # pas arrêtée
    page.locator(".wl-run-stage").filter(has_text="Terminé").wait_for(timeout=10_000)


@pytest.mark.parametrize(
    ("entry", "extension"), [("Télécharger (JSON)", "json"), ("Télécharger (Markdown)", "md")]
)
def test_a_menu_entry_downloads_from_the_server_route_without_blob(
    screen, conversation, traffic, entry, extension
):
    page = screen
    page.set_viewport_size({"width": 500, "height": 900})
    exporter(page).click()
    with page.expect_download() as download:
        page.get_by_role("menuitem", name=entry).click()
    url = download.value.url
    assert url.endswith(f"/api/conversations/{conversation}.{extension}"), url
    assert not url.startswith("blob:") and not any(u.startswith("blob:") for u in traffic.urls)
    assert re.fullmatch(
        rf"conversation-[0-9a-f]{{8}}\.{extension}", download.value.suggested_filename
    )
    text = Path(download.value.path()).read_text(encoding="utf-8")
    assert "Première question" in text
    assert page.evaluate("document.activeElement.textContent") == "Exporter"  # focus rendu
    assert exporter(page).get_attribute("aria-expanded") == "false"  # menu refermé après le choix


def test_a_click_elsewhere_closes_the_menu(screen):
    page = screen
    page.set_viewport_size({"width": 500, "height": 900})
    exporter(page).click()
    assert exporter(page).get_attribute("aria-expanded") == "true"
    page.locator("h1").click()
    assert exporter(page).get_attribute("aria-expanded") == "false"


def test_the_narrow_export_is_disabled_without_a_conversation(chat):
    chat.set_viewport_size({"width": 500, "height": 900})
    assert exporter(chat).is_visible() and exporter(chat).is_disabled()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_export_menu_at_320_px(screen, theme):
    page = screen
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    page.set_viewport_size({"width": 320, "height": 800})
    assert_no_axe_violations(page, f"écran étroit, menu fermé, thème {theme}")
    exporter(page).click()
    assert page.get_by_role("menuitem").count() == 2
    assert_no_axe_violations(page, f"écran étroit, menu ouvert, thème {theme}")
    assert_no_horizontal_scroll(page)
    page.keyboard.press("Escape")
    page.set_viewport_size({"width": 1440, "height": 900})
    assert_no_axe_violations(page, f"écran large, deux boutons, thème {theme}")
    page.evaluate("document.documentElement.setAttribute('data-projection', 'true')")
    assert_no_axe_violations(page, f"écran large en projection, thème {theme}")
    page.set_viewport_size({"width": 500, "height": 900})
    exporter(page).click()
    assert_no_axe_violations(page, f"écran étroit en projection, menu ouvert, thème {theme}")


# --- Premier chargement lent (UX-DR17) -----------------------------------------------------------

LOADING = [
    {"load": "loading", "duration_s": 0.5},
    {"sleep_s": 1.5},
    {"load": "loaded"},
    {"text": "Bonjour"},
    {"sleep_s": 1.5},
    {"done": DONE},
]


def first_load(page):
    return page.locator(".wl-run-first-load")


def test_the_first_load_message_shows_during_model_loading_only(chat, server):
    assert first_load(chat).is_hidden()
    scripted(chat, server, LOADING)
    ask(chat, "Bonjour")
    chat.locator(".wl-run-stage").filter(has_text="Chargement du modèle en mémoire…").wait_for()
    assert first_load(chat).is_visible()
    assert first_load(chat).inner_text() == FIRST_LOAD
    chat.locator(".wl-run-stage").filter(has_text="Génération…").wait_for()
    assert first_load(chat).is_hidden()
    chat.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    assert first_load(chat).is_hidden()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_slow_first_load_state(chat, server, theme):
    chat.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    scripted(chat, server, [{"load": "loading", "duration_s": 0.5}, {"sleep_s": 60}])
    ask(chat, "Bonjour")
    first_load(chat).wait_for(state="visible")
    assert_no_axe_violations(chat, f"premier chargement lent, thème {theme}")
    chat.get_by_role("button", name="Arrêter").click()
    chat.locator(".wl-run-stage").filter(has_text="Arrêté").wait_for()


def test_the_first_load_message_goes_away_when_the_run_is_stopped(chat, server):
    scripted(chat, server, [{"load": "loading", "duration_s": 0.5}, {"sleep_s": 30}])
    ask(chat, "Bonjour")
    first_load(chat).wait_for(state="visible")
    chat.get_by_role("button", name="Arrêter").click()
    chat.locator(".wl-run-stage").filter(has_text="Arrêté").wait_for()
    assert first_load(chat).is_hidden()


# --- 409 : le message tapé reste dans le champ (D-13) -------------------------------------------


def test_the_typed_message_stays_in_the_field_after_a_409_run_busy(chat_lenient, server):
    page = chat_lenient
    script = [{"text": "Réponse "}, {"sleep_s": 1.0}, {"text": "en cours"}, {"done": DONE}]
    start_run(page, server, script)  # un autre onglet a un run actif
    scripted(page, server, script)  # la commande de cette page : 409 run_busy
    ask(page, "Ma question à ne pas perdre")
    page.locator(".chat-notice").filter(has_text="Une réponse est déjà en cours").wait_for()
    assert field(page).input_value() == "Ma question à ne pas perdre"
    assert page.locator(".wl-msg-user").count() == 0  # rien n'est parti
    page.locator(".wl-run-stage").filter(has_text="Terminé").wait_for()
    assert answer_text(page) == "Réponse en cours"
    assert field(page).input_value() == "Ma question à ne pas perdre"  # toujours là, après le run
    stored = page.evaluate("Object.values(localStorage).join('|')")
    assert "Ma question à ne pas perdre" in stored  # le brouillon survit aussi à un rechargement
    assert page.get_by_role("button", name="Envoyer").is_enabled()
