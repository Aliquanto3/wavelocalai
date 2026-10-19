"""Garde-fou mémoire (story 4.8) dans un vrai navigateur, sur le vrai serveur.

Le serveur de test ne charge aucun vrai modèle : la réponse refusée est celle que le service
produirait (`ram_guard` et ses clés machine), jouée par la route de test (`{"fail": "ram_guard",
"detail": {...}}`), avec le vrai rendu de l'enveloppe. Le calcul du besoin et de la mémoire libre est
prouvé côté serveur (`tests/v2/unit/test_memory_guard.py`, `tests/v2/web/test_memory_guard_api.py`) ;
ici, on prouve ce que l'écran en fait : le message chiffré, les deux actions, la question gardée,
le modèle proposé choisi sans relancer, le déchargement par la vraie route (face à un Ollama simulé
qui perd son modèle) et la mémoire libre qui suit le flux système. axe-core, clair et sombre.
"""

from __future__ import annotations

import json
import re

import pytest

from .test_arena import DONE
from .test_arena import MODELS as ARENA_MODELS
from .test_arena import install_models as install_arena_models
from .test_arena import lane, launch
from .test_arena import scripted as scripted_arena
from .test_arena import status_of, wait_banner
from .test_chat import MODEL, REASON, ask, field, forget_conversations, scripted
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
SMALL = {**MODEL, "tag": "fake:small", "name": "Petit 0,5B", "needed_gb": 0.6}
MESSAGE = "Mémoire insuffisante : 5,2 Go nécessaires, 2,8 Go libres."
GUARD = {
    "fail": "ram_guard",
    "detail": {"needed_gb": 5.2, "free_gb": 2.8, "suggested_model": "fake:small"},
}
NO_SUGGESTION = {
    "fail": "ram_guard",
    "detail": {"needed_gb": 5.2, "free_gb": 2.8, "suggested_model": None},
}


def install_chat_models(page):
    def on_models(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "models": [MODEL, SMALL],
                    "ollama_up": True,
                    "refreshed_at": "2026-10-18T10:00:00Z",
                }
            ),
        )

    def on_defaults(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"purpose": "chat", "tags": ["fake:1b"], "reason": REASON, "source": "rule"}
            ),
        )

    page.route(re.compile(r"/api/models\?"), on_models)
    page.route(re.compile(r"/api/models/defaults\?"), on_defaults)


def open_chat(page, server):
    forget_conversations(server.base_url)
    install_chat_models(page)
    page.goto(f"{server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    return page


@pytest.fixture
def chat(page, server):
    return open_chat(page, server)


@pytest.fixture
def chat_lenient(page_tolerating_failed_requests, server):
    """Comme `chat`, pour un test dont le déchargement échoue exprès (le navigateur le dit)."""
    return open_chat(page_tolerating_failed_requests, server)


def guard_alert(page):
    return page.locator("wl-run-status wl-error[data-code=ram_guard]")


def button(alert, name):
    return alert.get_by_role("button", name=name, exact=True)


# --- Chat : message chiffré, deux actions, question gardée ---------------------------------------------


def test_a_refused_chat_says_the_real_need_and_offers_the_two_actions(chat, server):
    scripted(chat, server, [GUARD])
    ask(chat, "Où dort le chat ?")
    alert = guard_alert(chat)
    alert.wait_for()
    assert alert.locator(".wl-error-message").inner_text() == MESSAGE
    assert "modèle plus petit" in alert.locator(".wl-error-action").inner_text()
    assert alert.get_by_role("button").all_inner_texts() == [
        "Prendre un modèle plus petit",
        "Décharger les modèles inactifs",
    ]
    assert (
        alert.locator(".wl-error-help").inner_text().startswith(f"Modèle proposé{NBSP}: fake:small")
    )
    # Le modèle n'a rien dit : la réponse est marquée en échec, sans texte.
    assert chat.locator(".wl-msg-assistant .wl-md").inner_text().strip() == ""


def test_the_question_stays_in_the_field_and_in_the_history(chat, server):
    scripted(chat, server, [GUARD])
    ask(chat, "Où dort le chat ?")
    guard_alert(chat).wait_for()
    assert field(chat).input_value() == "Où dort le chat ?"  # prête à être renvoyée
    assert chat.locator(".wl-msg-user .wl-msg-text").inner_text() == "Où dort le chat ?"
    # Aussi dans l'historique du serveur : un rechargement la retrouve.
    chat.reload()
    wait_ready(chat)
    chat.locator(".wl-msg-user .wl-msg-text").wait_for()
    assert chat.locator(".wl-msg-user .wl-msg-text").inner_text() == "Où dort le chat ?"


def test_a_question_typed_in_the_meantime_is_never_overwritten(chat, server):
    scripted(chat, server, [{"sleep_s": 0.6}, GUARD])
    ask(chat, "Première question")
    field(chat).fill("Autre idée, tapée entre-temps")
    guard_alert(chat).wait_for()
    assert field(chat).input_value() == "Autre idée, tapée entre-temps"


def test_take_a_smaller_model_selects_the_proposal_without_relaunching(chat, server):
    commands: list[dict] = []
    scripted(chat, server, [GUARD], commands)
    ask(chat, "Où dort le chat ?")
    alert = guard_alert(chat)
    alert.wait_for()
    button(alert, "Prendre un modèle plus petit").click()
    wait_for(chat, "() => document.querySelector('wl-model-picker').value === 'fake:small'")
    assert chat.locator(".chat-notice").inner_text() == (
        f"Modèle choisi{NBSP}: Petit 0,5B. Renvoyez votre question, elle est restée dans le champ."
    )
    assert len(commands) == 1  # aucune relance
    assert field(chat).input_value() == "Où dort le chat ?"
    assert chat.evaluate("() => document.activeElement === document.querySelector('textarea')")


def test_without_a_proposal_only_the_unload_action_is_offered_and_the_server_says_why(chat, server):
    scripted(chat, server, [NO_SUGGESTION])
    ask(chat, "Où dort le chat ?")
    alert = guard_alert(chat)
    alert.wait_for()
    assert alert.get_by_role("button").all_inner_texts() == ["Décharger les modèles inactifs"]
    assert alert.locator(".wl-error-help").inner_text() == (
        "Aucun modèle installé ne tient dans la mémoire libre."
    )


def test_unload_inactive_models_calls_the_server_and_reports_the_result(chat, server):
    calls: list[str] = []

    def on_unload(route):
        calls.append(route.request.method)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "unloaded": ["qwen3:8b"],
                    "kept": [{"tag": "fake:1b", "run_id": "r1"}],
                    "failed": [],
                    "free_gb": 6.3,
                }
            ),
        )

    chat.route(re.compile(r"/api/models/unload$"), on_unload)
    scripted(chat, server, [GUARD])
    ask(chat, "Où dort le chat ?")
    alert = guard_alert(chat)
    alert.wait_for()
    unload = button(alert, "Décharger les modèles inactifs")
    unload.click()
    result = alert.locator(".wl-error-result")
    result.filter(has_text="Modèles déchargés").wait_for()
    assert calls == ["POST"]
    assert result.inner_text() == (
        f"Modèles déchargés{NBSP}: qwen3:8b. Mémoire libre{NBSP}: 6,3{NBSP}Go. "
        f"Gardés, car une réponse les utilise{NBSP}: fake:1b."
    )
    assert result.get_attribute("role") == "status"
    assert unload.is_enabled()  # on peut recommencer
    assert chat.evaluate("() => document.activeElement?.textContent") == (
        "Décharger les modèles inactifs"
    )  # le focus reste sur le bouton


def test_an_unload_that_fails_says_the_server_message(chat_lenient, server):
    chat = chat_lenient
    chat.route(
        re.compile(r"/api/models/unload$"),
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps(
                {
                    "code": "ollama_down",
                    "message": "Ollama ne répond pas sur ce poste.",
                    "action": "Lancez Ollama.",
                    "detail": {"technical": None},
                }
            ),
        ),
    )
    scripted(chat, server, [GUARD])
    ask(chat, "Où dort le chat ?")
    alert = guard_alert(chat)
    alert.wait_for()
    button(alert, "Décharger les modèles inactifs").click()
    alert.locator(".wl-error-result").filter(has_text="Ollama ne répond pas").wait_for()


def test_a_real_unload_empties_ollama_and_the_free_memory_follows_the_stream(
    backend, fake_ollama, page
):
    """Bout en bout : la vraie route décharge le modèle chez un Ollama simulé ; la barre haute, nourrie
    par le flux système, ne le liste plus et affiche la mémoire libre."""
    fake_ollama.start()
    backend.ollama_port = fake_ollama.port
    server = backend.start()
    install_chat_models(page)
    page.goto(f"{server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    page.locator("#ollama-button").click()
    panel = page.locator("#ollama-panel")
    panel.wait_for(state="visible")
    wait_for(page, "() => document.getElementById('ollama-loaded').textContent.includes('qwen2.5')")
    wait_for(page, "() => /Go/.test(document.getElementById('ollama-memory-free').textContent)")
    assert re.fullmatch(r"[\d  ,]+\sGo", panel.locator("#ollama-memory-free").inner_text())

    scripted(page, server, [GUARD])
    ask(page, "Où dort le chat ?")
    alert = guard_alert(page)
    alert.wait_for()
    button(alert, "Décharger les modèles inactifs").click()
    alert.locator(".wl-error-result").filter(has_text="Modèles déchargés").wait_for()
    assert "qwen2.5:1.5b" in alert.locator(".wl-error-result").inner_text()
    assert fake_ollama.unloaded == ["qwen2.5:1.5b"]
    wait_for(
        page,
        "() => document.getElementById('ollama-loaded').textContent.includes('Aucun modèle chargé')",
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_chat_refusal(chat, server, theme):
    scripted(chat, server, [GUARD])
    chat.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    ask(chat, "Où dort le chat ?")
    guard_alert(chat).wait_for()
    assert_no_axe_violations(chat, f"refus du garde-fou dans le chat, thème {theme}")
    chat.set_viewport_size({"width": 320, "height": 800})
    assert_no_axe_violations(chat, f"refus du garde-fou à 320 px, thème {theme}")
    overflow = chat.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0


# --- Arène : la colonne refusée, les autres continuent ---------------------------------------------------------


@pytest.fixture
def arena(page, server):
    models = [*ARENA_MODELS]
    install_arena_models(page, models)
    page.goto(f"{server.base_url}/#/arene/comparer")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.values.length === 2")
    return page


ARENA_GUARD = {
    "fail": "ram_guard",
    "detail": {"needed_gb": 5.2, "free_gb": 2.8, "suggested_model": "fake:c"},
}


def run_with_refused_lane(arena, server, commands):
    scripted_arena(
        arena,
        server,
        {"fake:a": [ARENA_GUARD], "fake:b": [{"text": "Réponse bravo"}, {"done": DONE}]},
        commands,
    )
    arena.get_by_label("Question", exact=True).fill("Où dort le chat ?")
    launch(arena)
    wait_banner(arena, "Comparaison terminée")


def test_an_arena_lane_refused_for_memory_offers_the_actions_and_the_others_go_on(arena, server):
    commands: list[dict] = []
    run_with_refused_lane(arena, server, commands)
    assert status_of(arena, "fake:a") == "Échec"
    assert status_of(arena, "fake:b") == "Terminé"
    alert = lane(arena, "fake:a").locator("wl-error[data-code=ram_guard]")
    assert alert.locator(".wl-error-message").inner_text() == MESSAGE
    assert alert.get_by_role("button").all_inner_texts() == [
        "Prendre un modèle plus petit",
        "Décharger les modèles inactifs",
    ]
    assert lane(arena, "fake:b").locator(".wl-md").inner_text().strip() == "Réponse bravo"
    # La question reste dans le champ (formulaire de retour à la fin de la comparaison).
    assert arena.get_by_label("Question", exact=True).input_value() == "Où dort le chat ?"


def test_in_the_arena_the_proposal_replaces_the_refused_model_without_relaunching(arena, server):
    commands: list[dict] = []
    run_with_refused_lane(arena, server, commands)
    alert = lane(arena, "fake:a").locator("wl-error[data-code=ram_guard]")
    button(alert, "Prendre un modèle plus petit").click()
    wait_for(
        arena,
        "() => JSON.stringify(document.querySelector('wl-model-picker').values) === "
        '\'["fake:c","fake:b"]\'',
    )
    assert len(commands) == 1  # aucune relance : la personne relance elle-même
    assert arena.get_by_label("Question", exact=True).input_value() == "Où dort le chat ?"
    assert arena.get_by_role("button", name="Lancer la comparaison").is_enabled()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_arena_refusal(arena, server, theme):
    arena.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    run_with_refused_lane(arena, server, [])
    lane(arena, "fake:a").locator("wl-error[data-code=ram_guard]").wait_for()
    assert_no_axe_violations(arena, f"refus du garde-fou dans l'Arène, thème {theme}")
