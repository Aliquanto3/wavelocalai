"""Retrouver, exporter et effacer une conversation (story 2.6) : l'écran Chat dans un vrai
navigateur, sur le vrai serveur et l'adaptateur `fake`.

Les conversations sont préparées par la route de test (`POST /api/test/runs`, avec
`conversation_id` pour les échanges suivants) ; le navigateur les rouvre. Ollama n'est jamais
sollicité. Aucune requête ne sort de 127.0.0.1 (fixture `context`).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from .test_chat import (  # noqa: F401 - fixtures et aides du chat
    DONE,
    MODEL,
    REASON,
    STARTED,
    cancel_leftover_runs,
    field,
    install_models,
)
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

CO2 = {"mg": 2.5, "method": "codecarbon", "estimated": False}
OTHER = {**MODEL, "tag": "autre:7b", "name": "Autre 7B"}


def call(base_url, path, body=None, method=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method or ("GET" if data is None else "POST"),
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def wait_run(base_url, run_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if call(base_url, f"/api/runs/{run_id}")[1]["status"] != "running":
            return
        time.sleep(0.05)
    pytest.fail("le run ne se termine pas")


def exchange(server, message, script, conversation_id=None, wait=True):
    status, body = call(
        server.base_url,
        "/api/test/runs",
        {
            "kind": "chat",
            "model": "fake:1b",
            "message": message,
            "conversation_id": conversation_id,
            "script": script,
            "co2": CO2,
        },
    )
    assert status == 200, body
    STARTED.append((server.base_url, body["run_id"]))
    if wait:
        wait_run(server.base_url, body["run_id"])
    return body["run_id"], body["conversation_id"]


FIRST = [
    {"load": "loaded"},
    {"text": "Je compare les deux.", "channel": "thought"},
    {"text": "Réponse **un** du modèle."},
    {"done": DONE},
]
SECOND = [{"text": "Réponse deux."}, {"done": {**DONE, "tps": 25.5, "output_tokens": 7}}]


@pytest.fixture
def conversation(server):
    """Une conversation de deux échanges, écrite avant l'ouverture de la page."""
    _, conv = exchange(server, "Première question", FIRST)
    exchange(server, "Seconde question", SECOND, conv)
    return conv


@pytest.fixture
def screen(page, server, conversation):
    """L'écran Chat ouvert sur une conversation existante, dont il a relu le contenu."""
    return open_screen(page, server)


def open_screen(page, server):
    install_models(page)
    page.goto(f"{server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value")
    return page


def install_list(page, models, default):
    def on_models(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"models": models, "ollama_up": True, "refreshed_at": "2026-10-18T10:00:00Z"}
            ),
        )

    def on_defaults(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"purpose": "chat", "tags": [default], "reason": REASON, "source": "rule"}
            ),
        )

    page.route(re.compile(r"/api/models\?"), on_models)
    page.route(re.compile(r"/api/models/defaults\?"), on_defaults)


def texts(page, selector):
    return [node.strip() for node in page.locator(selector).all_inner_texts()]


def squash(text):
    return re.sub(r"\s+", " ", text)


# --- Retrouver ---------------------------------------------------------------------------------


def test_reopening_the_screen_shows_messages_reasoning_and_metrics_as_displayed(screen):
    page = screen
    page.locator(".wl-msg-assistant").nth(1).wait_for()
    assert texts(page, ".wl-msg-user .wl-msg-text") == ["Première question", "Seconde question"]
    answers = page.locator(".wl-msg-assistant")
    assert answers.count() == 2
    assert answers.nth(0).locator(".wl-md strong").inner_text() == "un"
    assert answers.nth(1).locator(".wl-md").inner_text().strip() == "Réponse deux."
    # Raisonnement replié, présent.
    thought = answers.nth(0).locator("details.wl-thought")
    assert thought.evaluate("node => node.open") is False
    assert "Je compare les deux." in thought.text_content()
    assert answers.nth(1).locator("details.wl-thought:visible").count() == 0
    # Mesures du serveur, pas un pied provisoire.
    first = squash(answers.nth(0).locator(".wl-msg-foot").inner_text())
    assert "Débit 38,4 tokens/s" in first and "(provisoire)" not in first
    assert "Tokens 12" in first and "Chargement 0,42 s" in first and "Durée totale 1,2 s" in first
    assert answers.nth(0).locator(".wl-badge").inner_text() == "Local"
    second = squash(answers.nth(1).locator(".wl-msg-foot").inner_text())
    assert "Débit 25,5 tokens/s" in second and "Tokens 7" in second
    # Rien n'est annoncé à la réouverture, et l'écran n'est plus « vide ».
    assert page.locator("wl-chat-thread [role=status]").inner_text() == ""
    assert page.locator(".chat-empty").is_hidden()
    assert page.get_by_role("button", name="Télécharger (JSON)").is_enabled()
    assert page.get_by_role("button", name="Effacer la conversation").is_enabled()


def test_the_conversation_is_continued_by_the_next_message(screen, server, conversation):
    page = screen
    page.locator(".wl-msg-assistant").nth(1).wait_for()
    sent: list[dict] = []
    page.on(
        "request",
        lambda r: (
            sent.append(json.loads(r.post_data))
            if r.method == "POST" and r.url.endswith("/api/chat/runs")
            else None
        ),
    )
    field(page).fill("Et une troisième ?")
    field(page).press("Enter")
    page.locator(".wl-msg-user").nth(2).wait_for()
    assert sent and sent[0]["conversation_id"] == conversation


def test_the_chosen_model_and_creativity_are_kept_with_the_conversation(page, server):
    # La conversation a été tenue avec `fake:1b` à 1,4 de créativité (vraie route de chat).
    status, started = call(
        server.base_url,
        "/api/chat/runs",
        {"model": "fake:1b", "message": "Question", "temperature": 1.4, "allow_cloud": False},
    )
    assert status == 200, started
    wait_run(server.base_url, started["run_id"])
    # Le défaut de l'usage, lui, est un autre modèle : celui de la conversation l'emporte.
    install_list(page, [OTHER, MODEL], default="autre:7b")
    page.goto(f"{server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    assert page.get_by_label("Créativité").input_value() == "1.4"
    assert page.locator("output.chat-slider-value").inner_text() == "1,4"
    # Une réponse sans texte écrit reste visible, avec ses mesures.
    assert page.locator(".wl-msg-user").count() == 1
    assert page.locator(".wl-msg-assistant").count() == 1


def test_an_empty_store_opens_an_empty_screen_without_error(page, server):
    open_screen(page, server)
    assert page.locator(".chat-empty").is_visible()
    assert page.locator(".wl-msg").count() == 0
    assert page.get_by_role("button", name="Télécharger (JSON)").is_disabled()
    assert page.get_by_role("button", name="Télécharger (Markdown)").is_disabled()


def test_a_run_still_active_is_followed_after_a_reload(page, server):
    _, conv = exchange(server, "Avant", [{"text": "Fait."}])
    exchange(
        server,
        "Pendant",
        [{"text": "Début"}, {"sleep_s": 1.5}, {"text": " et fin."}, {"done": DONE}],
        conv,
        wait=False,
    )
    open_screen(page, server)
    # La question en cours est dans le fil ; la réponse arrive par le flux, rejouée en entier.
    page.locator(".wl-msg-assistant").filter(has_text="Début et fin.").wait_for()
    assert texts(page, ".wl-msg-user .wl-msg-text") == ["Avant", "Pendant"]
    assert page.locator(".wl-msg-assistant").count() == 2
    page.locator(".wl-msg-foot").nth(1).filter(has_text="Durée totale").wait_for()


def test_a_stopped_answer_comes_back_marked_stopped_with_its_partial(page, server):
    run_id, conv = exchange(server, "Long", [{"text": "Partiel"}, {"sleep_s": 30}], wait=False)
    time.sleep(0.4)
    call(server.base_url, f"/api/runs/{run_id}/cancel", {})
    wait_run(server.base_url, run_id)
    open_screen(page, server)
    page.locator(".wl-msg-flag").filter(has_text="Arrêté").wait_for()
    assert page.locator(".wl-msg-assistant .wl-md").inner_text().strip() == "Partiel"
    assert page.locator(".wl-msg-assistant .wl-msg-foot").count() == 0  # aucune mesure à montrer


# --- Exporter ----------------------------------------------------------------------------------


def test_download_json_gives_messages_model_origin_rate_and_co2_with_method(screen):
    page = screen
    page.locator(".wl-msg-assistant").nth(1).wait_for()
    with page.expect_download() as download:
        page.get_by_role("button", name="Télécharger (JSON)").click()
    assert re.fullmatch(r"conversation-[0-9a-f]{8}\.json", download.value.suggested_filename)
    document = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
    assert document["format"] == "wavelocalai.conversation/1"
    assert [m["role"] for m in document["messages"]] == ["user", "assistant"] * 2
    first = document["messages"][1]
    assert first["content"] == "Réponse **un** du modèle."
    assert first["reasoning"] == "Je compare les deux."
    assert first["model"] == "fake:1b" and first["origin"] == "local"
    assert first["tps"] == 38.4 and first["tps_source"] == "ollama_eval"
    assert first["co2"]["method"] == "codecarbon" and first["co2"]["mg"] == 2.5
    assert "sk-" not in json.dumps(document) and "api_key" not in json.dumps(document).lower()


def test_download_markdown_reads_as_a_transcript(screen):
    page = screen
    page.locator(".wl-msg-assistant").nth(1).wait_for()
    with page.expect_download() as download:
        page.get_by_role("button", name="Télécharger (Markdown)").click()
    assert re.fullmatch(r"conversation-[0-9a-f]{8}\.md", download.value.suggested_filename)
    text = Path(download.value.path()).read_text(encoding="utf-8")
    assert text.startswith("# Conversation wavelocalai")
    assert "## Vous\n\nPremière question" in text and "## Modèle\n\nRéponse deux." in text
    assert "origine : local" in text and "(mesuré par Ollama (D3))" in text
    assert "CO2 : 2,5 mg (codecarbon, mesuré)" in text


# --- Effacer -----------------------------------------------------------------------------------


def test_clear_deletes_the_conversation_without_confirmation_and_keeps_the_co2(
    screen, server, conversation
):
    page = screen
    page.locator(".wl-msg-assistant").nth(1).wait_for()
    dialogs: list[str] = []
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    before = call(server.base_url, "/api/carbon/session")[1]
    assert before["total_mg"] >= 5.0  # au moins ces deux réponses de 2,5 mg

    page.get_by_role("button", name="Effacer la conversation").click()
    page.locator(".chat-empty").wait_for(state="visible")
    assert dialogs == []  # aucune confirmation (UX-DR21)
    assert page.locator(".wl-msg").count() == 0
    notice = page.locator(".chat-notice")
    assert notice.is_visible() and "Conversation effacée" in notice.inner_text()
    assert page.get_by_role("button", name="Télécharger (JSON)").is_disabled()
    # Le serveur l'a oubliée ; son texte aussi ; le CO2 de la session n'a pas baissé.
    assert call(server.base_url, f"/api/conversations/{conversation}")[0] == 404
    assert call(server.base_url, "/api/conversations")[1] == {"conversations": []}
    assert call(server.base_url, "/api/carbon/session")[1] == before
    # Rechargée, la page est vide : rien à rouvrir.
    page.reload()
    wait_ready(page)
    page.locator(".chat-empty").wait_for(state="visible")
    assert page.locator(".wl-msg").count() == 0


def test_clear_while_a_run_is_active_shows_the_409_message_and_action(
    page_tolerating_failed_requests, server
):
    page = page_tolerating_failed_requests
    exchange(server, "Avant", [{"text": "Fait."}])
    open_screen(page, server)
    page.locator(".wl-msg-assistant").wait_for()
    # Un autre onglet relance la conversation : l'écran ne le sait pas, le serveur si.
    conv = call(server.base_url, "/api/conversations")[1]["conversations"][0]["id"]
    exchange(server, "Ailleurs", [{"text": "En cours"}, {"sleep_s": 30}], conv, wait=False)
    page.get_by_role("button", name="Effacer la conversation").click()
    alert = page.get_by_role("alert")
    alert.wait_for()
    assert "réponse en cours" in alert.inner_text()
    assert "Arrêtez la réponse" in alert.inner_text()
    assert page.locator(".wl-msg-user").count() == 1  # rien n'a bougé à l'écran
    assert call(server.base_url, f"/api/conversations/{conv}")[0] == 200


# --- Accessibilité, réseau ---------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_a_reopened_conversation(screen, theme):
    page = screen
    page.locator(".wl-msg-assistant").nth(1).wait_for()
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(page, f"conversation rouverte, thème {theme}")
    page.locator("details.wl-thought:visible summary").click()
    page.locator(".wl-msg-foot wl-metric", has_text="Débit").first.get_by_role("button").click()
    assert_no_axe_violations(page, f"conversation rouverte, aide ouverte, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_after_clearing_and_with_the_conflict_message(
    page_tolerating_failed_requests, server, theme
):
    page = page_tolerating_failed_requests
    exchange(server, "Avant", [{"text": "Fait."}])
    open_screen(page, server)
    page.locator(".wl-msg-assistant").wait_for()
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    conv = call(server.base_url, "/api/conversations")[1]["conversations"][0]["id"]
    exchange(server, "Ailleurs", [{"text": "En cours"}, {"sleep_s": 30}], conv, wait=False)
    page.get_by_role("button", name="Effacer la conversation").click()
    page.get_by_role("alert").wait_for()
    assert_no_axe_violations(page, f"effacement refusé (409), thème {theme}")
    run_id = STARTED[-1][1]
    call(server.base_url, f"/api/runs/{run_id}/cancel", {})
    wait_run(server.base_url, run_id)
    page.get_by_role("button", name="Effacer la conversation").click()
    page.locator(".chat-notice").filter(has_text="Conversation effacée").wait_for()
    assert_no_axe_violations(page, f"conversation effacée, thème {theme}")


def test_every_request_stays_on_127_0_0_1(screen, traffic):
    screen.locator(".wl-msg-assistant").nth(1).wait_for()
    with screen.expect_download():
        screen.get_by_role("button", name="Télécharger (JSON)").click()
    assert traffic.urls and all(url.startswith("http://127.0.0.1") for url in traffic.urls)
    assert any("/api/conversations" in url for url in traffic.urls)
