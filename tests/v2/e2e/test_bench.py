"""Écran Banc d'essai (story 7.4) dans un vrai navigateur, sur le vrai serveur et le modèle `fake`.

Le serveur calcule le verdict de format : les essais ci-dessous passent par le vrai service (`POST
/api/bench/runs`), le `fake` rend le texte que le test lui a scripté (`POST /api/test/chat-model`), et
la page lit le flux et l'instantané du vrai serveur. Seule la liste des modèles est simulée (le
`structured_output` d'un second modèle est faux) ; le délai dépassé est un flux fixé par le test
(`page.route`), le serveur réel ayant un délai de 300 s. Aucune requête ne sort de 127.0.0.1 (fixture
`context`) ; Ollama n'est jamais sollicité.

Prouvés ici : le formulaire (consigne repliée, format attendu, « Format imposé » désactivé avec sa
raison), un format respecté, un format violé, une sortie illisible, les interrupteurs, « Relancer le
test » et « Modifier le test », la réouverture par l'adresse, la liste des essais passés, un
identifiant inconnu, le délai dépassé cité, axe-core clair et sombre.
"""

from __future__ import annotations

import contextlib
import json
import re
import urllib.request

import pytest

from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready

URL = "#/arene/banc"
NBSP = "\N{NO-BREAK SPACE}"
MODEL = {
    "tag": "fake:1b",
    "name": "Factice 1B",
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
    "structured_output": True,
    "reasoning": False,
    "throughput_tps": None,
    "accuracy": None,
    "co2_method": "codecarbon",
    "in_catalog": False,
}
PLAIN = {**MODEL, "tag": "fake:plain", "name": "Factice simple", "structured_output": False}
REASON = "Le plus capable qui tient en mémoire sur ce poste."
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
GOOD = '{"sentiment": "Neutre", "categorie": "formation"}'
BAD = '{"sentiment": "Super", "categorie": "formation"}'
RUN = "bbbbbbbb-2222-3333-4444-555555555555"


def install_models(page, models=(MODEL, PLAIN), default="fake:1b"):
    def on_models(route):
        body = {"models": list(models), "ollama_up": True, "refreshed_at": "2026-10-18T10:00:00Z"}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def on_defaults(route):
        body = {"purpose": "chat", "tags": [default], "reason": REASON, "source": "rule"}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route(re.compile(r"/api/models\?"), on_models)
    page.route(re.compile(r"/api/models/defaults\?"), on_defaults)


def script(page, server, *texts: str, done: dict | None = DONE) -> None:
    steps = [{"text": text} for text in texts]
    if done is not None:
        steps.append({"done": done})
    response = page.request.post(
        f"{server.base_url}/api/test/chat-model", data={"model": "fake:1b", "script": steps}
    )
    assert response.ok, response.text()


def open_bench(page, server, path: str = URL, models=(MODEL, PLAIN)):
    install_models(page, models)
    page.goto(f"{server.base_url}/{path}")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    wait_for(page, "() => !!document.querySelector('.bc-form')")


def launch(page):
    return page.get_by_role("button", name="Lancer le test")


def run_test(page, wire: list | None = None) -> str:
    """Lance l'essai et rend son identifiant, une fois le résultat affiché."""
    with page.expect_response(re.compile(r"/api/bench/runs$")) as posted:
        launch(page).click()
    run_id = posted.value.json()["run_id"]
    wait_for(
        page,
        "() => !!document.querySelector('.bc-actions') && !document.querySelector('.bc-actions').hidden",
    )
    return run_id


def verdict_text(page) -> str:
    return page.locator(".bc-verdict-line").inner_text().strip()


@pytest.fixture(autouse=True)
def finish_leftover_runs(server):
    """Un seul essai à la fois : un test n'en laisse aucun en cours au suivant."""
    yield
    with urllib.request.urlopen(
        f"{server.base_url}/api/bench/runs?limit=5", timeout=5
    ) as reply:  # noqa: S310
        listing = json.load(reply)["runs"]
    for item in listing:
        if item["status"] == "running":
            request = urllib.request.Request(
                f"{server.base_url}/api/runs/{item['run_id']}/cancel", method="POST"
            )
            with contextlib.suppress(OSError):
                urllib.request.urlopen(request, timeout=5).close()  # noqa: S310


# --- Formulaire -----------------------------------------------------------------------------------


def test_the_form_shows_the_scenario_its_folded_instruction_and_its_expected_format(page, server):
    open_bench(page, server)
    assert page.title() == "Banc d'essai · WaveLocalAI"
    select = page.get_by_label("Scénario prédéfini")
    assert select.locator("option").all_inner_texts()[:3] == [
        "Classification (JSON)",
        "Traduction technique",
        "Extraction (JSON)",
    ]
    instruction = page.locator("details.bc-instruction")
    assert instruction.evaluate("el => el.open") is False  # D-18 : repliée
    assert "sentiment" in instruction.locator(".bc-instruction-body").text_content()
    page.locator("details.bc-format-box summary").click()
    rows = page.locator(".bc-format tbody tr")
    assert rows.count() == 2
    assert "Positif, Neutre, Négatif" in rows.nth(0).inner_text()
    assert page.get_by_label("Entrée").input_value().startswith("Analyse ce feedback")
    assert launch(page).is_enabled()
    assert page.locator(".bc-legend").inner_text() == (
        f"Test de «{NBSP}Classification (JSON){NBSP}» avec Factice 1B."
    )


def test_a_scenario_without_format_has_no_format_and_disables_the_forced_format(page, server):
    open_bench(page, server)
    page.get_by_label("Scénario prédéfini").select_option(label="Résumé")
    page.locator("details.bc-format-box summary").click()
    assert "n'attend aucun format" in page.locator(".bc-format-body").inner_text()
    force = page.get_by_role("switch", name="Format imposé")
    assert force.is_disabled()
    reason = page.locator(".bc-switch-reason").first
    assert reason.is_visible() and "n'attend aucun format" in reason.inner_text()
    assert page.get_by_role("switch", name="Réponse concise").is_enabled()


def test_a_model_that_cannot_force_a_format_disables_the_switch_with_its_reason(page, server):
    open_bench(page, server)
    page.get_by_role("switch", name="Format imposé").locator("xpath=..").click()
    assert page.get_by_role("switch", name="Format imposé").is_checked()
    picker = page.locator("wl-model-picker")
    picker.get_by_role("combobox").click()
    picker.locator("[role=option]", has_text="Factice simple").click()
    page.keyboard.press("Escape")
    force = page.get_by_role("switch", name="Format imposé")
    wait_for(page, "() => document.querySelector('.bc-switch input').disabled")
    assert not force.is_checked()  # le choix précédent est retiré avec la raison
    assert (
        "Factice simple ne sait pas contraindre sa sortie"
        in page.locator(".bc-switch-reason").first.inner_text()
    )


def test_changing_the_scenario_keeps_an_edited_input_and_offers_to_replace_it(page, server):
    open_bench(page, server)
    field = page.get_by_label("Entrée")
    field.fill("Mon texte à moi")
    page.get_by_label("Scénario prédéfini").select_option(label="Traduction technique")
    assert field.input_value() == "Mon texte à moi"
    assert page.get_by_role("button", name="Remplacer par l'exemple du scénario").is_visible()
    page.get_by_role("button", name="Remplacer par l'exemple du scénario").click()
    assert field.input_value().startswith("L'inférence locale")


def test_an_empty_input_disables_the_launch_with_a_visible_reason(page, server):
    open_bench(page, server)
    page.get_by_label("Entrée").fill("   ")
    assert launch(page).is_disabled()
    assert page.locator(".bc-legend").inner_text() == "Saisissez une entrée"
    assert launch(page).get_attribute("aria-describedby") == page.locator(
        ".bc-legend"
    ).get_attribute("id")


# --- Essais ---------------------------------------------------------------------------------------


def test_a_respected_format_is_said_with_the_pretty_output_and_the_measures(page, server):
    script(page, server, GOOD[:20], GOOD[20:])
    open_bench(page, server)
    run_test(page)
    assert verdict_text(page) == "Format respecté"
    assert page.locator(".bc-json").inner_text() == (
        '{\n  "sentiment": "Neutre",\n  "categorie": "formation"\n}'
    )
    assert page.locator(".bc-stream").inner_text() == GOOD
    labels = page.locator(".bc-metrics .wl-metric-label").all_inner_texts()
    assert labels[0] == "Débit" and "CO₂" in labels and "Durée totale" in labels
    assert "38,4" in page.locator(".bc-metrics").inner_text()
    assert page.get_by_role("button", name="Relancer le test").is_enabled()
    assert page.get_by_role("button", name="Modifier le test").is_enabled()


def test_a_violated_format_names_its_first_violation(page, server):
    script(page, server, BAD)
    open_bench(page, server)
    run_test(page)
    assert verdict_text(page) == f"« sentiment »{NBSP}: valeur hors de la liste permise"
    assert page.locator(".bc-verdict-line").get_attribute("data-ok") == "false"
    assert '"Super"' in page.locator(".bc-json").inner_text()  # lisible : mis en forme quand même


def test_an_unreadable_output_is_shown_as_the_model_returned_it(page, server):
    script(page, server, "Voici le JSON : {oups")
    open_bench(page, server)
    run_test(page)
    assert verdict_text(page).startswith("La sortie n'est pas du JSON valide")
    assert "telle que le modèle l'a rendue" in page.locator(".bc-formatted").inner_text()
    assert page.locator(".bc-json").inner_text() == "Voici le JSON : {oups"


def test_a_scenario_without_format_shows_no_verdict(page, server):
    script(page, server, "- Projet en retard\n", "- Livraison décalée de deux semaines")
    open_bench(page, server)
    page.get_by_label("Scénario prédéfini").select_option(label="Résumé")
    run_test(page)
    assert page.locator(".bc-verdict-line").count() == 0
    assert "pas de verdict de format" in page.locator(".bc-verdict").inner_text()
    assert "Livraison décalée" in page.locator(".bc-md").inner_text()


def test_the_switches_go_to_the_server_with_the_command(page, server):
    script(page, server, GOOD)
    open_bench(page, server)
    page.get_by_role("switch", name="Format imposé").locator("xpath=..").click()
    page.get_by_role("switch", name="Réponse concise").locator("xpath=..").click()
    with page.expect_request(re.compile(r"/api/bench/runs$")) as sent:
        launch(page).click()
    body = json.loads(sent.value.post_data)
    assert body == {
        "scenario": "classification",
        "model": "fake:1b",
        "input": body["input"],
        "force_format": True,
        "concise": True,
        "allow_cloud": False,
    }
    wait_for(page, "() => !!document.querySelector('.bc-verdict-line')")
    assert "Le format était imposé au modèle." in page.locator(".bc-verdict").inner_text()


def test_rerun_and_edit_reuse_the_configuration_of_the_test(page, server):
    script(page, server, GOOD)
    open_bench(page, server)
    page.get_by_label("Entrée").fill("Le café était froid")
    first = run_test(page)
    page.get_by_label("Entrée").fill("autre chose")
    page.get_by_role("button", name="Modifier le test").click()
    assert page.get_by_label("Entrée").input_value() == "Le café était froid"
    assert page.evaluate("document.activeElement.id").endswith("-input")
    with page.expect_response(re.compile(r"/api/bench/runs$")) as again:
        page.get_by_role("button", name="Relancer le test").click()
    assert again.value.json()["run_id"] != first


# --- Rouvrir et lister ----------------------------------------------------------------------------


def test_the_result_is_kept_reopens_by_its_address_and_is_listed_newest_first(page, server):
    script(page, server, BAD)
    open_bench(page, server)
    older = run_test(page)
    script(page, server, GOOD)
    page.get_by_role("button", name="Relancer le test").click()
    wait_for(page, "() => document.querySelector('.bc-verdict-line')?.dataset.ok === 'true'")
    wait_for(page, "() => document.querySelectorAll('.bc-history-item').length >= 2")
    items = page.locator(".bc-history-item")
    newest = items.first.get_attribute("data-run-id")
    assert newest != older
    assert "Format respecté" in items.first.inner_text()
    assert (
        "Format non respecté"
        in page.locator(f'.bc-history-item[data-run-id="{older}"]').inner_text()
    )
    page.locator(f'.bc-history-item[data-run-id="{older}"] a').click()
    wait_for(page, "() => document.querySelector('.bc-verdict-line')?.dataset.ok === 'false'")
    assert page.evaluate("location.hash") == f"#/arene/banc/{older}"
    assert "aucun modèle n'a été relancé" in page.locator(".chat-notice").inner_text()
    assert page.get_by_label("Entrée").input_value().startswith("Analyse ce feedback")
    assert '"Super"' in page.locator(".bc-json").inner_text()


def test_an_unknown_run_says_run_not_found_with_a_link_to_a_new_test(
    page_tolerating_failed_requests, server
):
    page = page_tolerating_failed_requests  # le 404 de l'instantané est le comportement prouvé
    open_bench(page, server, path=f"{URL}/inconnu")
    wait_for(page, "() => !document.querySelector('.bc-missing').hidden")
    missing = page.locator(".bc-missing")
    assert missing.get_attribute("data-code") == "run_not_found"
    assert "Essai introuvable" in missing.inner_text()
    assert missing.get_by_role("link", name="Lancer un test").get_attribute("href") == URL


# --- Délai dépassé --------------------------------------------------------------------------------


def stub_timeout_run(page) -> None:
    started = {
        "kind": "bench",
        "models": ["fake:1b"],
        "params": {"scenario": "classification", "force_format": False, "concise": False},
    }
    error = {
        "code": "timeout",
        "message": "Le modèle n'a pas fini de répondre dans le délai prévu.",
        "action": "Réessayez avec un modèle plus petit.",
        "detail": {"technical": "Aucune fin de réponse après 120 s.", "timeout_s": 120},
    }
    events = [
        ("run_started", started),
        ("bench_input", {"scenario": "classification", "text": "Entrée"}),
        ("token", {"lane": "fake:1b", "text": '{"sentiment": ', "channel": "answer"}),
        ("run_ended", {"status": "error", "error": error}),
    ]
    lines = "".join(
        "id: {}\ndata: {}\n\n".format(
            seq,
            json.dumps(
                {
                    "seq": seq,
                    "run_id": RUN,
                    "type": kind,
                    "ts": f"2026-10-19T10:00:0{seq}+00:00",
                    "data": data,
                }
            ),
        )
        for seq, (kind, data) in enumerate(events, start=1)
    )
    snapshot = {
        "run_id": RUN,
        "kind": "bench",
        "status": "error",
        "model": "fake:1b",
        "error": error,
        "metrics": None,
        "bench": {
            "scenario": "classification",
            "force_format": False,
            "concise": False,
            "input": "Entrée",
            "output": '{"sentiment": ',
        },
        "children": [],
    }
    page.route(
        re.compile(r"/api/bench/runs$"),
        lambda route: (
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"run_id": RUN})
            )
            if route.request.method == "POST"
            else route.continue_()
        ),
    )
    page.route(
        re.compile(rf"/api/runs/{RUN}/events"),
        lambda route: route.fulfill(status=200, content_type="text/event-stream", body=lines),
    )
    page.route(
        re.compile(rf"/api/runs/{RUN}$"),
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(snapshot)
        ),
    )


def test_a_timeout_cites_the_real_delay_and_keeps_the_partial_output(page, server):
    stub_timeout_run(page)
    open_bench(page, server)
    launch(page).click()
    wait_for(
        page,
        "() => !!document.querySelector('.bc-actions') && !document.querySelector('.bc-actions').hidden",
    )
    message = page.locator(".bc-result wl-error[data-code=timeout] .wl-error-message")
    assert message.inner_text() == f"Délai dépassé (120{NBSP}s)"
    assert page.locator(".bc-stream").inner_text() == '{"sentiment": '
    assert page.locator(".bc-verdict-line").count() == 0  # pas de verdict sur une sortie coupée


# --- Accessibilité --------------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 390])
def test_axe_finds_no_violation_on_the_form_the_result_and_the_missing_screen(
    page_tolerating_failed_requests, server, theme, width
):
    page = page_tolerating_failed_requests  # l'essai introuvable lit un 404
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(color_scheme=theme)
    script(page, server, BAD)
    open_bench(page, server)
    assert_no_axe_violations(page, f"formulaire ({theme}, {width})")
    page.locator("details.bc-instruction summary").click()
    page.locator("details.bc-format-box summary").click()
    run_test(page)
    assert_no_axe_violations(page, f"résultat ({theme}, {width})")
    assert_no_horizontal_scroll(page)
    page.goto(f"{server.base_url}/{URL}/inconnu")
    wait_for(page, "() => !document.querySelector('.bc-missing').hidden")
    assert_no_axe_violations(page, f"essai introuvable ({theme}, {width})")
