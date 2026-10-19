"""Écran Agent seul (story 6.4) dans un vrai navigateur, sur le vrai serveur et le modèle `fake`.

Le serveur est le vrai (hub, boucle d'outils, outils réels, route d'approbation, envoi SMTP) ; Ollama
n'est jamais sollicité. La liste des modèles est simulée par le test (`page.route`), le modèle `fake`
suit un script **par appel de modèle** (`POST /api/test/chat-model`, appels d'outils compris). Le SMTP
est un faux serveur **local** en processus (`tests/v2/fake_smtp.py`) : aucun email réel ne part.

Les composants (`wl-run-status` piloté, `wl-step-trace`) sont aussi joués à la main dans la vraie page,
avec des enveloppes écrites par le test, pour les états que le serveur passe trop vite (« Appel de
l'outil… », focus d'une étape dépliée pendant que d'autres arrivent). axe-core, clair et sombre.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import shutil
import threading
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect

from ..fake_smtp import FakeSmtp
from .conftest import Backend
from .test_chat import MODEL as CHAT_MODEL
from .test_chat import forget_conversations
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

ROOT = Path(__file__).resolve().parents[3]
NBSP = "\N{NO-BREAK SPACE}"
MODEL = {**CHAT_MODEL, "tools_verified": True}
UNVERIFIED = {**CHAT_MODEL, "tag": "fake:sans-outils", "name": "Sans outils 1B"}
SMALL = {**MODEL, "tag": "fake:small", "name": "Petit 0,5B", "needed_gb": 0.6}
REASON = "Le plus capable des modèles à outils vérifiés qui tient en mémoire."
NO_DEFAULT = "Aucun modèle local ne réunit les conditions de l'Agent : aucun défaut n'est proposé."
TASK_FIELD = "Décrivez la tâche à confier à l'agent"
GUARD = {
    "fail": "ram_guard",
    "detail": {"needed_gb": 5.2, "free_gb": 2.8, "suggested_model": "fake:small"},
}
EMAIL = {
    "to": "client@example.org",
    "subject": "Synthèse du mardi",
    "body": "Bonjour,\nVoici la synthèse des ventes.\nCordialement",
}
RUNS: list[tuple[str, str]] = []  # (serveur, run_id) lancés par un test : annulés à sa fin


def call(name, call_id="c1", **arguments):
    return {"tool_call": {"id": call_id, "name": name, "arguments": arguments}}


def install_models(page, models=(MODEL,), default=("fake:1b",), reason=REASON):
    def on_models(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"models": list(models), "ollama_up": True, "refreshed_at": "2026-10-18T10:00:00Z"}
            ),
        )

    def on_defaults(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"purpose": "agent", "tags": list(default), "reason": reason, "source": "rule"}
            ),
        )

    page.route(re.compile(r"/api/models\?"), on_models)
    page.route(re.compile(r"/api/models/defaults\?"), on_defaults)


def script(page, server, *turns):
    """Un script du `fake` par appel de modèle, dans l'ordre (le dernier se répète)."""
    response = page.request.post(
        f"{server.base_url}/api/test/chat-model", data={"scripts": [list(t) for t in turns]}
    )
    assert response.ok, response.text()


def post_json(server, path, data):
    request = urllib.request.Request(
        f"{server.base_url}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def warm_up(server):
    """Un serveur neuf met une dizaine de secondes à mesurer son premier appel de modèle (compteur
    CodeCarbon) : on le fait une fois, hors du test, pour que les délais d'un test restent courts.
    """
    post_json(server, "/api/test/chat-model", {"scripts": [[{"text": "ok"}]]})
    started = post_json(
        server,
        "/api/agents/runs",
        {
            "mode": "solo",
            "model": "fake:1b",
            "prompt": "chauffe",
            "tools": [],
            "allow_cloud": False,
        },
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if get_json(server, f"/api/runs/{started['run_id']}")["status"] == "ok":
            return
        time.sleep(0.2)
    pytest.fail("le premier appel de modèle n'a pas fini")


def get_json(server, path):
    with urllib.request.urlopen(f"{server.base_url}{path}", timeout=5) as response:  # noqa: S310
        return json.load(response)


@pytest.fixture(autouse=True)
def leave_no_run(server):
    """Un seul run d'agent à la fois : chaque test finit le sien (annulé s'il tourne encore)."""
    yield
    for base_url, run_id in RUNS:
        cancel = urllib.request.Request(f"{base_url}/api/runs/{run_id}/cancel", method="POST")
        with contextlib.suppress(OSError):
            urllib.request.urlopen(cancel, timeout=5).close()  # noqa: S310
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with (
                contextlib.suppress(OSError),
                urllib.request.urlopen(  # noqa: S310
                    f"{base_url}/api/runs/{run_id}", timeout=5
                ) as response,
            ):
                if json.load(response)["status"] not in ("running", "awaiting_approval"):
                    break
            time.sleep(0.05)
    RUNS.clear()
    forget_conversations(server.base_url)


def watch_runs(page, base_url):
    def on_response(response):
        if response.url.endswith("/api/agents/runs") and response.request.method == "POST":
            with contextlib.suppress(Exception):
                RUNS.append((base_url, response.json()["run_id"]))

    page.on("response", on_response)


def open_agent(page, base_url, models=(MODEL,), default=("fake:1b",), reason=REASON):
    install_models(page, models, default, reason)
    watch_runs(page, base_url)
    page.goto(f"{base_url}/#/agents/seul")
    wait_ready(page)
    wait_for(page, "() => document.querySelectorAll('.agents-tool-list li').length > 0")
    if default:
        wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    return page


@pytest.fixture
def agent(page, server):
    return open_agent(page, server.base_url)


def field(page):
    return page.get_by_label(TASK_FIELD)


def ask(page, text):
    field(page).fill(text)
    field(page).press("Enter")


def steps(page):
    return page.locator("wl-step-trace li.wl-step")


def step_labels(page):
    return [li.locator(".wl-step-label").inner_text() for li in steps(page).all()]


def stage(page):
    return page.locator("wl-run-status .wl-run-stage").inner_text()


def tool_switch(page, label):
    return page.get_by_role("switch", name=label, exact=True)


# --- Réglages ---------------------------------------------------------------------------------


def test_the_screen_is_agent_seul_with_the_picker_the_tools_and_the_welcome(agent):
    assert agent.title() == "Agent seul · WaveLocalAI"
    assert agent.get_by_role("heading", level=1).inner_text() == "Agent seul"
    tabs = agent.get_by_role("navigation", name="Écrans du module Agents")
    assert tabs.get_by_role("link", name="Agent seul").get_attribute("aria-current") == "page"
    crew = tabs.get_by_role("link", name="Équipe d'agents")
    # L'écran Équipe d'agents est disponible depuis la story 6.6 : un lien actif.
    assert crew.get_attribute("aria-disabled") is None
    assert crew.get_attribute("href") == "#/agents/equipe"
    # Le sélecteur est sur le défaut `agent`, avec sa raison.
    assert agent.locator("wl-model-picker .wl-picker-help").inner_text().endswith(REASON)
    assert agent.locator("wl-model-picker").evaluate("el => el.getAttribute('purpose')") == "agent"
    # Accueil : « Bonjour ! », une phrase, des actions rapides qui remplissent sans envoyer.
    assert agent.locator(".agents-welcome-title").inner_text() == f"Bonjour{NBSP}!"
    assert agent.locator(".agents-welcome-text").inner_text().startswith("L'agent est prêt.")
    sent: list[str] = []
    agent.on("request", lambda r: sent.append(r.url) if r.url.endswith("/api/agents/runs") else 0)
    agent.get_by_role("button", name="Lancer l'audit").click()
    assert field(agent).input_value() == "Vérifie l'état du système (CPU/RAM) et fais un résumé."
    agent.get_by_role("button", name="Analyser les données").click()
    assert "ventes.csv" in field(agent).input_value()
    assert sent == []


def test_the_nine_tools_are_switches_all_on_but_the_sensitive_one_and_an_unavailable_one_stays_off(
    agent, server
):
    listed = get_json(server, "/api/agents/tools")["tools"]
    assert len(listed) == 9
    switches = agent.locator(".agents-tool-list").get_by_role("switch")
    assert switches.count() == 9
    for tool in listed:
        box = tool_switch(agent, tool["label"])
        assert box.get_attribute("type") == "checkbox"
        # Chaque outil a sa description, en aide reliée à l'interrupteur.
        described = box.get_attribute("aria-describedby").split()
        assert agent.locator(f"#{described[0]}").inner_text() == tool["description"]
        if tool["available"]:
            assert box.is_checked() == (not tool["sensitive"]), tool["id"]
            assert box.get_attribute("aria-disabled") is None
        else:
            assert box.get_attribute("aria-disabled") == "true" and not box.is_checked()
            assert agent.locator(f"#{described[1]}").inner_text() == tool["reason"]
    # Sans SMTP configuré, « Envoi d'email » est indisponible, focalisable, non activable.
    email = tool_switch(agent, "Envoi d'email")
    assert email.get_attribute("aria-disabled") == "true"
    assert agent.get_by_text("Configuration SMTP absente").first.is_visible()
    email.focus()
    assert email.evaluate("el => el === document.activeElement")
    email.press("Space")
    email.click(force=True)
    assert not email.is_checked()


def test_without_a_default_the_screen_says_why_asks_for_a_choice_and_cannot_launch(page, server):
    open_agent(page, server.base_url, models=(MODEL, UNVERIFIED), default=(), reason=NO_DEFAULT)
    assert page.locator("wl-model-picker .wl-picker-help").inner_text() == NO_DEFAULT
    assert page.locator(".agents-model-hint").inner_text() == (
        "Choisissez un modèle avec outils vérifiés."
    )
    assert page.get_by_role("button", name="Envoyer").is_disabled()
    # Un modèle choisi sans outils vérifiés : avertissement, lancement permis (D-32).
    picker = page.get_by_role("combobox", name="Modèle")
    picker.click()
    page.get_by_role("option", name=re.compile("Sans outils 1B")).click()
    warning = page.locator(".agents-warning")
    assert warning.inner_text() == (
        f"Ce modèle n'a pas d'outils vérifiés{NBSP}: l'agent risque de mal appeler ses outils. "
        f"Préférez un modèle marqué «{NBSP}Outils vérifiés{NBSP}»."
    )
    assert page.get_by_role("button", name="Envoyer").is_enabled()
    assert not page.locator(".agents-model-hint").is_visible()
    # Un modèle aux outils vérifiés : plus d'avertissement.
    picker.click()
    page.get_by_role("option", name=re.compile("Factice 1B")).click()
    assert not warning.is_visible()


# --- Étapes, statut, réponse ------------------------------------------------------------------------


def test_steps_arrive_in_order_with_their_detail_and_the_answer_is_one_block(agent, server):
    script(
        agent,
        server,
        [{"text": "Je calcule."}, call("calculator", expression="2+3")],
        [{"sleep_s": 1.2}, {"text": "Le résultat est **5**.\n\n---\n\n*Fin* du calcul."}],
    )
    ask(agent, "Combien font 2 + 3 ?")
    assert agent.locator(".wl-msg-user .wl-msg-text").inner_text() == "Combien font 2 + 3 ?"
    assert field(agent).input_value() == ""
    # Les trois premières étapes arrivent pendant que le modèle prépare sa réponse.
    expect(steps(agent)).to_have_count(3)
    assert step_labels(agent) == [
        "Réflexion",
        "Appel de l'outil Calculatrice",
        "Résultat de Calculatrice",
    ]
    assert agent.locator("wl-step-trace ol").evaluate("el => el.tagName") == "OL"
    assert agent.locator("wl-step-trace ol").get_attribute("aria-live") is None
    # La réponse n'est pas encore là : un bloc à la fin, dit par l'aide et par le statut.
    assert agent.locator(".wl-msg-assistant").count() == 0
    assert agent.locator(".agents-block-notice").inner_text() == (
        "La réponse de l'agent s'affiche d'un bloc, à la fin de sa dernière étape."
    )
    assert stage(agent) == "Réflexion…"
    # On déplie « Appel de l'outil » pendant que la suite arrive : arguments en JSON mis en forme.
    toggle = steps(agent).nth(1).get_by_role("button")
    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "true"
    detail = steps(agent).nth(1).locator(".wl-step-detail")
    assert json.loads(detail.locator("pre").inner_text()) == {"expression": "2+3"}
    assert detail.locator("pre").inner_text().startswith('{\n  "expression"')
    # L'étape de réponse arrive, le focus et l'étape dépliée restent.
    expect(steps(agent)).to_have_count(4)
    assert toggle.get_attribute("aria-expanded") == "true"
    assert toggle.evaluate("el => el === document.activeElement")
    assert step_labels(agent)[3] == "Réponse de l'agent"
    # Le résultat se déplie aussi (texte du serveur).
    steps(agent).nth(2).get_by_role("button").click()
    assert steps(agent).nth(2).locator(".wl-step-text").inner_text() == "5"
    # Réponse : un seul bloc, Markdown rendu sans astérisque visible (gras, séparateur, italique).
    agent.locator(".wl-msg-assistant .wl-md strong").wait_for()
    body = agent.locator(".wl-msg-assistant .wl-md")
    assert body.locator("strong").inner_text() == "5" and body.locator("em").inner_text() == "Fin"
    assert body.locator("hr").count() == 1 and "*" not in body.inner_text()
    assert agent.locator(".wl-msg-assistant").count() == 1
    # Fin de tâche : plus rien « en cours » dans la trace.
    wait_for(agent, "() => !document.querySelector('wl-step-trace [data-current]')")


def test_the_reduced_footer_and_the_download_come_from_the_server(agent, server):
    script(
        agent,
        server,
        [{"text": "Je calcule."}, call("calculator", expression="6*7")],
        [{"text": "C'est **42**."}],
    )
    ask(agent, "Combien font 6 fois 7 ?")
    foot = agent.locator(".wl-msg-assistant .wl-msg-foot")
    expect(foot.locator("wl-metric")).to_have_count(3)
    labels = [m.get_attribute("label") for m in foot.locator("wl-metric").all()]
    assert labels == ["CO₂", "Étapes", "Durée"]  # ni débit, ni tokens, ni chargement (D-31)
    steps_metric = foot.locator("wl-metric").nth(1)
    assert steps_metric.get_attribute("value") == "4"
    snapshot = get_json(server, f"/api/runs/{RUNS[-1][1]}")
    assert snapshot["totals"]["steps"] == 4 and snapshot["totals"]["turns"] == 2
    # « Télécharger » : la route d'export du serveur, un lien (jamais `blob:`), après le pied.
    link = agent.locator(".wl-msg-assistant").get_by_role("link", name="Télécharger")
    href = link.get_attribute("href")
    assert re.fullmatch(r"/api/conversations/[\w-]+\.md", href) and "blob:" not in href
    assert link.evaluate(
        "el => el.compareDocumentPosition(el.closest('.wl-msg').querySelector('.wl-msg-foot'))"
        " & Node.DOCUMENT_POSITION_PRECEDING"
    )
    exported = agent.request.get(f"{server.base_url}{href}")
    assert exported.ok and "42" in exported.text()
    assert "blob:" not in agent.content()


def test_a_tool_error_stays_a_step_and_the_agent_goes_on(agent, server):
    script(agent, server, [call("calculator", expression="1/0")], [{"text": "Impossible."}])
    ask(agent, "Divise 1 par 0")
    expect(steps(agent)).to_have_count(3)
    failed = steps(agent).nth(1)
    assert failed.get_attribute("data-kind") == "failed"
    assert (
        failed.locator(".wl-step-label").inner_text() == f"Résultat de Calculatrice{NBSP}: erreur"
    )
    failed.get_by_role("button").click()
    assert "Erreur" in failed.locator(".wl-step-text").inner_text()
    agent.locator(".wl-msg-assistant .wl-md").get_by_text("Impossible.").wait_for()


def test_a_file_produced_by_a_tool_is_offered_in_its_step(agent, server):
    report = call("generate_markdown_report", title="Ventes", sections='{"Résumé": "RAS"}')
    script(agent, server, [report], [{"text": "Rapport prêt."}])
    ask(agent, "Prépare un rapport")
    expect(steps(agent)).to_have_count(3)
    result = steps(agent).nth(1)
    result.get_by_role("button").click()
    link = result.get_by_role("link", name="Ouvrir le fichier")
    href = link.get_attribute("href")
    assert href.startswith("/api/outputs/") and "blob:" not in href
    assert agent.request.get(f"{server.base_url}{href}").ok


def test_only_a_same_site_path_becomes_an_open_file_link(agent):
    # Revue 6.4 : `artifact_url` vient du serveur ; une autre adresse n'est jamais un lien suivi.
    links = agent.evaluate(
        """() => {
          const trace = document.querySelector('wl-step-trace');
          const urls = ['javascript:alert(1)', '//evil.example/x', 'https://evil.example/x',
                        '/api/outputs/a.png'];
          for (const url of urls) {
            trace.add({ kind: 'tool_result', tool: 'calculator', summary: 'ok', artifact_url: url });
          }
          return [...trace.querySelectorAll('a.wl-step-file')].map((a) => a.getAttribute('href'));
        }"""
    )
    assert links == ["/api/outputs/a.png"]


def test_the_task_cannot_leave_before_the_tools_are_read(page_tolerating_failed_requests, server):
    # Revue 6.4 : sans la liste des outils, la tâche partirait sans outil et sans le dire.
    page = page_tolerating_failed_requests
    page.route(
        re.compile(r"/api/agents/tools$"),
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"code": "internal", "message": "Erreur.", "action": "", "detail": {}}),
        ),
    )
    posted = []
    page.on(
        "request",
        lambda request: (
            posted.append(request.url)
            if request.url.endswith("/api/agents/runs") and request.method == "POST"
            else None
        ),
    )
    install_models(page)
    page.goto(f"{server.base_url}/#/agents/seul")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    expect(page.locator(".agents-tools wl-error")).to_be_visible()
    expect(page.get_by_role("button", name="Envoyer")).to_be_disabled()
    ask(page, "Calcule 2 + 2")
    page.wait_for_timeout(300)
    assert posted == []


def test_the_turn_limit_is_a_last_step_that_says_so(page, tmp_path_factory):
    folder = tmp_path_factory.mktemp("e2e-agent-turns")
    config = folder / "wavelocalai.toml"
    config.write_text("[agents]\nmax_turns = 2\n", encoding="utf-8")
    (folder / "data").mkdir()
    backend = Backend(folder / "data", config=config)
    server = backend.start()
    try:
        warm_up(server)
        open_agent(page, server.base_url)
        script(page, server, [call("calculator", expression="1+1")])  # il ne s'arrête jamais
        ask(page, "Boucle")
        last = page.locator("wl-step-trace li.wl-step").last
        expect(last).to_contain_text("Arrêt")
        assert step_labels(page)[-1] == f"Arrêt{NBSP}: nombre d'étapes maximal atteint (2)"
        page.locator("wl-step-trace li:last-child").get_by_role("button").click()
        assert "2" in page.locator("wl-step-trace li:last-child .wl-step-text").inner_text()
    finally:
        backend.stop()


# --- Composants joués à la main (états trop brefs pour un vrai run) --------------------------------


def envelope(kind, data, seq=1):
    return {"seq": seq, "run_id": "probe", "type": kind, "ts": "2026-10-19T10:00:00Z", "data": data}


def test_the_status_follows_the_steps_the_validation_and_the_answer(agent):
    agent.evaluate(
        """() => {
            const status = document.createElement('wl-run-status');
            status.id = 'probe-status';
            status.setAttribute('driven', '');
            status.setAttribute('first-stage', 'thinking');
            status.toolLabel = (id) => ({ calculator: 'Calculatrice' })[id] ?? id;
            status.runId = 'probe';
            document.body.append(status);
        }"""
    )

    def feed(kind, data):
        agent.evaluate(
            "([e]) => document.getElementById('probe-status').feed(e)", [envelope(kind, data)]
        )
        return agent.locator("#probe-status .wl-run-stage").inner_text()

    assert agent.locator("#probe-status .wl-run-stage").inner_text() == "Réflexion…"
    assert feed("run_started", {}) == "Réflexion…"
    assert feed("model_loading", {}) == "Chargement du modèle en mémoire…"
    assert feed("model_loaded", {}) == "Réflexion…"  # un appel de modèle est en cours
    assert feed("step", {"kind": "think"}) == "Réflexion…"
    assert feed("step", {"kind": "tool_call", "tool": "calculator"}) == (
        "Appel de l'outil Calculatrice…"
    )
    assert feed("approval_required", {"approval_id": "a"}) == "En attente de votre validation"
    assert feed("approval_resolved", {"decision": "approved"}) == "Appel de l'outil Calculatrice…"
    assert feed("step", {"kind": "tool_result", "tool": "calculator"}) == "Réflexion…"
    assert feed("step", {"kind": "answer"}) == "Génération…"
    assert feed("token", {"text": "x"}) == "Génération…"
    assert feed("run_ended", {"status": "ok"}) == "Terminé"
    assert agent.locator("#probe-status .wl-run-stage").get_attribute("aria-live") == "off"


def test_an_open_step_keeps_its_state_and_the_focus_while_new_steps_arrive(agent):
    agent.evaluate(
        """() => {
            const trace = document.createElement('wl-step-trace');
            trace.id = 'probe-trace';
            trace.labelOf = (id) => ({ calculator: 'Calculatrice' })[id] ?? id;
            document.body.append(trace);
            trace.setCurrent('running');
            trace.add({ kind: 'think', agent: 'Chercheur', summary: 'Je calcule.', duration_s: 0.4 });
            trace.add({ kind: 'tool_call', tool: 'calculator', arguments: { expression: '2+3' } });
        }"""
    )
    trace = agent.locator("#probe-trace")
    # La dernière étape (un appel d'outil) est « en cours » : contour, libellé, jamais la couleur seule.
    last = trace.locator("li").nth(1)
    assert last.get_attribute("data-current") == "running"
    assert last.locator(".wl-step-state").inner_text() == "en cours"
    first = trace.locator("li").nth(0)
    assert first.locator(".wl-step-agent").inner_text() == "Chercheur"  # champ `agent` (6.6)
    assert first.get_attribute("data-current") is None
    toggle = trace.locator("li").nth(0).get_by_role("button")
    toggle.focus()
    toggle.press("Enter")
    assert toggle.get_attribute("aria-expanded") == "true"
    assert toggle.get_attribute("aria-controls") == toggle.evaluate(
        "el => el.parentElement.querySelector('.wl-step-detail').id"
    )
    agent.evaluate(
        """() => {
            const trace = document.getElementById('probe-trace');
            trace.add({ kind: 'tool_result', tool: 'calculator', summary: '5', duration_s: 0.01 });
            trace.add({ kind: 'tool_call', tool: 'calculator', arguments: {} });
            trace.add({ kind: 'tool_call', tool: 'calculator', arguments: {} });
            trace.setCurrent('approval');
        }"""
    )
    assert toggle.get_attribute("aria-expanded") == "true"
    assert toggle.evaluate("el => el === document.activeElement")
    assert trace.locator("li").count() == 5
    # Une seule étape porte la marque, et c'est la dernière.
    assert trace.locator("[data-current]").count() == 1
    assert trace.locator("li").nth(4).locator(".wl-step-state").inner_text() == (
        "En attente de votre validation"
    )
    assert trace.locator("li").nth(1).locator(".wl-step-state").is_hidden()
    toggle.press("Space")
    assert toggle.get_attribute("aria-expanded") == "false"


# --- Validation de l'email ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def smtp():
    """Un faux serveur SMTP local, dans un fil à lui (aucun vrai serveur n'est joint)."""
    ready = threading.Event()
    box: dict = {}

    def run():
        async def main():
            async with FakeSmtp() as fake:
                box["fake"] = fake
                box["stop"] = asyncio.Event()
                box["loop"] = asyncio.get_running_loop()
                ready.set()
                await box["stop"].wait()

        asyncio.run(main())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(10)
    yield box["fake"]
    box["loop"].call_soon_threadsafe(box["stop"].set)
    thread.join(10)


@pytest.fixture(scope="module")
def mail(tmp_path_factory, smtp):
    """Le serveur dont le SMTP est le faux serveur local ; l'attente d'une validation y dure 3 s."""
    folder = tmp_path_factory.mktemp("e2e-agent-mail")
    config = folder / "wavelocalai.toml"
    config.write_text("[delays]\napproval_expiry_s = 4\n", encoding="utf-8")
    (folder / "data").mkdir()
    # Les équipes livrées, pour l'écran Équipe (story 6.6) : la bibliothèque se lit à côté du `.toml`.
    (folder / "config").mkdir()
    shutil.copy(ROOT / "config" / "agent_crews.json", folder / "config" / "agent_crews.json")
    env = {
        "SMTP_SERVER": "127.0.0.1",
        "SMTP_PORT": str(smtp.port),
        "SMTP_USER": smtp.user,
        "SMTP_PASSWORD": smtp.password,
    }
    backend = Backend(folder / "data", config=config, env=env)
    try:
        server = backend.start()
        warm_up(server)
        yield server
    finally:
        backend.stop()


def open_mailer(page, mail, smtp):
    smtp.messages.clear()
    smtp.connections = 0
    return open_agent(page, mail.base_url)


@pytest.fixture
def mailer(page, mail, smtp):
    return open_mailer(page, mail, smtp)


def propose_email(page, server, final="Voilà."):
    script(page, server, [call("send_email", **EMAIL)], [{"text": final}])
    tool_switch(page, "Envoi d'email").check()
    ask(page, "Écris à mon client.")
    dialog = page.get_by_role("dialog")
    dialog.wait_for()
    return dialog


def test_the_email_switch_is_available_and_off_by_default_when_smtp_is_configured(mailer):
    email = tool_switch(mailer, "Envoi d'email")
    assert email.get_attribute("aria-disabled") is None and not email.is_checked()
    assert tool_switch(mailer, "Calculatrice").is_checked()


def test_nothing_is_sent_before_the_approval_and_approving_sends_exactly_what_was_shown(
    mailer, mail, smtp
):
    dialog = propose_email(mailer, mail)
    assert dialog.get_by_role("heading", name="Envoyer cet email ?").is_visible()
    terms = dialog.locator(".wl-dialog-term").all_inner_texts()
    values = dialog.locator(".wl-dialog-value").all_inner_texts()
    assert terms == ["Destinataire", "Objet", "Corps"]
    assert values == [EMAIL["to"], EMAIL["subject"], EMAIL["body"]]
    body = dialog.locator(".wl-dialog-value").nth(2)
    assert body.get_attribute("tabindex") == "0"  # défilable au clavier
    assert body.get_attribute("aria-labelledby") == (
        dialog.locator(".wl-dialog-term").nth(2).get_attribute("id")
    )
    assert dialog.locator(".wl-dialog-consequence").inner_text() == (
        f"Sans réponse dans 4{NBSP}s, l'envoi est refusé."
    )
    # Le focus est sur « Annuler », jamais sur l'action.
    assert mailer.evaluate("document.activeElement.textContent") == "Annuler"
    # L'étape passe à « En attente de votre validation », dans le statut et dans la trace.
    assert stage(mailer) == "En attente de votre validation"
    waiting = steps(mailer).last
    assert waiting.locator(".wl-step-state").inner_text() == "En attente de votre validation"
    assert waiting.get_attribute("data-current") == "approval"
    time.sleep(0.5)
    assert smtp.connections == 0 and smtp.messages == []
    dialog.get_by_role("button", name="Envoyer l'email").click()
    expect(dialog).to_be_hidden()
    mailer.locator("wl-step-trace li.wl-step-note").get_by_text("Email envoyé.").wait_for()
    assert mailer.locator("p.chat-notice").inner_text() == "Email envoyé."
    (message,) = smtp.messages
    assert message.recipients == [EMAIL["to"]] and message.subject == EMAIL["subject"]
    assert message.text == EMAIL["body"]
    mailer.locator(".wl-msg-assistant .wl-md").get_by_text("Voilà.").wait_for()


def test_cancelling_sends_nothing_and_the_agent_is_told(mailer, mail, smtp):
    dialog = propose_email(mailer, mail, final="Je n'ai rien envoyé.")
    dialog.get_by_role("button", name="Annuler").click()
    expect(dialog).to_be_hidden()
    note = mailer.locator("wl-step-trace li.wl-step-note")
    expect(note).to_have_text("Envoi annulé : l'agent en est informé.".replace(" :", f"{NBSP}:"))
    mailer.locator(".wl-msg-assistant .wl-md").get_by_text("Je n'ai rien envoyé.").wait_for()
    assert smtp.connections == 0 and smtp.messages == []
    # Le refus est un résultat d'outil en échec que la trace montre.
    assert any("erreur" in label for label in step_labels(mailer))


def test_escape_is_cancel_and_does_not_stop_the_whole_task(mailer, mail, smtp):
    dialog = propose_email(mailer, mail, final="Annulé.")
    mailer.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    mailer.locator("wl-step-trace li.wl-step-note").get_by_text("Envoi annulé").wait_for()
    # Échap n'a pas arrêté la tâche : elle va jusqu'à sa réponse, sans état « Arrêté ».
    mailer.locator(".wl-msg-assistant .wl-md").get_by_text("Annulé.").wait_for()
    assert mailer.locator(".wl-msg-flag:visible").count() == 0
    assert smtp.messages == []


def test_an_expired_validation_closes_the_dialog_and_says_so(mailer, mail, smtp):
    dialog = propose_email(mailer, mail, final="Pas de réponse.")
    expect(dialog).to_be_hidden(timeout=10_000)  # le serveur le ferme à l'expiration (4 s)
    mailer.locator("wl-step-trace li.wl-step-note").get_by_text(
        "Validation expirée : email non envoyé.".replace(" :", f"{NBSP}:")
    ).wait_for()
    mailer.locator(".wl-msg-assistant .wl-md").get_by_text("Pas de réponse.").wait_for()
    assert smtp.connections == 0 and smtp.messages == []


def test_stopping_the_task_during_the_wait_closes_the_dialog_as_a_refusal(mailer, mail, smtp):
    dialog = propose_email(mailer, mail)
    run_id = RUNS[-1][1]
    mailer.request.post(f"{mail.base_url}/api/runs/{run_id}/cancel")
    expect(dialog).to_be_hidden()
    mailer.locator("wl-step-trace li.wl-step-note").get_by_text("Envoi annulé").wait_for()
    assert smtp.connections == 0 and smtp.messages == []
    assert mailer.locator(".wl-msg-flag").inner_text() == "Arrêté"


def test_a_late_answer_is_said_without_a_technical_error(
    page_tolerating_failed_requests, mail, smtp
):
    mailer = open_mailer(page_tolerating_failed_requests, mail, smtp)
    mailer.route(
        re.compile(r"/api/runs/[^/]+/approvals/"),
        lambda route: route.fulfill(
            status=409,
            content_type="application/json",
            body=json.dumps(
                {
                    "code": "approval_not_pending",
                    "message": "Cette demande n'attend plus de réponse.",
                    "action": "Relancez la tâche si besoin.",
                    "detail": {},
                }
            ),
        ),
    )
    dialog = propose_email(mailer, mail)
    dialog.get_by_role("button", name="Envoyer l'email").click()
    expect(dialog).to_be_hidden()
    expect(mailer.locator("p.chat-notice")).to_have_text(
        f"Cette validation n'est plus attendue{NBSP}: votre réponse n'a pas été prise en compte."
    )
    assert mailer.locator("wl-error:visible").count() == 0
    assert smtp.messages == []


def test_an_answered_validation_is_not_asked_again_when_coming_back(mailer, mail, smtp):
    # Revue 6.4 : réponse partie, `approval_resolved` pas encore arrivé (ici, jamais : la réponse
    # est interceptée) ; revenir sur l'écran ne rouvre pas le dialogue, l'expiration le clôt.
    mailer.route(
        re.compile(r"/api/runs/[^/]+/approvals/"),
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"run_id": "x", "approval_id": "y", "decision": "rejected"}),
        ),
    )
    dialog = propose_email(mailer, mail)
    dialog.get_by_role("button", name="Annuler").click()
    expect(dialog).to_be_hidden()
    mailer.evaluate("location.hash = '#/'")
    mailer.evaluate("location.hash = '#/agents/seul'")
    mailer.wait_for_timeout(500)
    expect(mailer.get_by_role("dialog")).to_be_hidden()
    mailer.locator("wl-step-trace li.wl-step-note").get_by_text("Validation expirée").wait_for()
    assert smtp.messages == []


def test_leaving_the_screen_closes_the_dialog_and_coming_back_reopens_it(mailer, mail, smtp):
    dialog = propose_email(mailer, mail)
    mailer.evaluate("location.hash = '#/'")
    expect(dialog).to_be_hidden()
    time.sleep(0.5)
    assert smtp.messages == []  # sortir n'est pas répondre
    mailer.evaluate("location.hash = '#/agents/seul'")
    expect(mailer.get_by_role("dialog")).to_be_visible()
    assert mailer.evaluate("document.activeElement.textContent") == "Annuler"
    mailer.get_by_role("dialog").get_by_role("button", name="Annuler").click()
    mailer.locator("wl-step-trace li.wl-step-note").get_by_text("Envoi annulé").wait_for()


# --- Garde-fou mémoire, reprise, mise en page ---------------------------------------------------------


def test_the_memory_guard_keeps_the_task_and_offers_the_two_actions(page, server):
    open_agent(page, server.base_url, models=(MODEL, SMALL))
    script(page, server, [GUARD])
    sent: list[str] = []
    page.on("request", lambda r: sent.append(r.url) if r.url.endswith("/api/agents/runs") else 0)
    ask(page, "Analyse mes ventes")
    alert = page.locator("wl-run-status wl-error[data-code=ram_guard]")
    alert.wait_for()
    assert "5,2" in alert.inner_text() and "2,8" in alert.inner_text()
    assert alert.get_by_role("button", name="Prendre un modèle plus petit").is_visible()
    assert alert.get_by_role("button", name="Décharger les modèles inactifs").is_visible()
    assert "Libérer la mémoire" not in alert.inner_text()  # le bouton de la v1 n'existe plus
    # La tâche est dans l'historique du fil et revient dans le champ.
    assert page.locator(".wl-msg-user .wl-msg-text").inner_text() == "Analyse mes ventes"
    assert field(page).input_value() == "Analyse mes ventes"
    alert.get_by_role("button", name="Prendre un modèle plus petit").click()
    assert page.locator("wl-model-picker").evaluate("el => el.value") == "fake:small"
    assert len(sent) == 1  # le modèle est choisi, la tâche n'est pas relancée


def test_leaving_and_coming_back_resumes_the_trace_after_the_last_event(agent, server):
    script(
        agent,
        server,
        [call("calculator", expression="2+3")],
        [{"sleep_s": 2.0}, {"text": "Reprise réussie."}],
    )
    urls: list[str] = []
    agent.on("request", lambda r: urls.append(r.url) if "/events" in r.url else 0)
    ask(agent, "Calcule")
    expect(steps(agent)).to_have_count(2)
    agent.evaluate("location.hash = '#/'")
    wait_for(agent, "() => document.querySelector('[data-screen=agents-solo]').hidden")
    agent.evaluate("location.hash = '#/agents/seul'")
    agent.locator(".wl-msg-assistant .wl-md").get_by_text("Reprise réussie.").wait_for()
    assert any("after=" in url for url in urls), urls  # reprise, pas de rejeu depuis le début
    assert step_labels(agent) == [
        "Appel de l'outil Calculatrice",
        "Résultat de Calculatrice",
        "Réponse de l'agent",
    ]


def test_a_task_already_running_elsewhere_is_joined_without_an_error(
    page_tolerating_failed_requests, server
):
    agent = open_agent(page_tolerating_failed_requests, server.base_url)
    script(
        agent, server, [call("calculator", expression="2+3")], [{"sleep_s": 3.0}, {"text": "Fini."}]
    )
    # Un autre onglet a déjà lancé une tâche : la commande de l'écran rend `409 run_busy`.
    other = agent.request.post(
        f"{server.base_url}/api/agents/runs",
        data={
            "mode": "solo",
            "model": "fake:1b",
            "prompt": "Autre onglet",
            "tools": ["calculator"],
            "allow_cloud": False,
        },
    )
    assert other.ok
    RUNS.append((server.base_url, other.json()["run_id"]))
    ask(agent, "Ma tâche")
    expect(agent.locator("p.chat-notice")).to_have_text(
        f"Une tâche est déjà en cours{NBSP}: vous la suivez. Votre texte est resté dans le champ."
    )
    assert agent.locator("wl-error:visible").count() == 0
    assert field(agent).input_value() == "Ma tâche"
    # La tâche rejointe est rejouée depuis son début : sa trace et sa réponse arrivent.
    agent.locator(".wl-msg-assistant .wl-md").get_by_text("Fini.").wait_for()
    assert step_labels(agent)[0] == "Appel de l'outil Calculatrice"


def test_the_steps_panel_is_on_the_right_from_1024px_and_always_open_below(agent):
    agent.set_viewport_size({"width": 1440, "height": 900})
    panel = agent.get_by_role("complementary", name="Étapes")
    main = agent.locator(".agents-main")
    assert panel.bounding_box()["x"] >= main.bounding_box()["x"] + main.bounding_box()["width"] - 1
    assert panel.get_by_role("button").count() == 0  # aucun bouton de repli (D-30)
    agent.set_viewport_size({"width": 800, "height": 900})
    assert panel.bounding_box()["y"] >= main.bounding_box()["y"] + main.bounding_box()["height"] - 1
    assert panel.is_visible() and panel.get_by_role("button").count() == 0
    assert panel.get_by_text("Les étapes de l'agent apparaissent ici").is_visible()
    agent.set_viewport_size({"width": 320, "height": 800})
    overflow = agent.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0


# --- Accessibilité -----------------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_idle_running_and_asking_for_validation(mailer, mail, theme):
    mailer.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(mailer, f"Agent seul au repos, thème {theme}")
    dialog = propose_email(mailer, mail)
    assert_no_axe_violations(mailer, f"Agent seul, validation d'un email, thème {theme}")
    dialog.get_by_role("button", name="Annuler").click()
    mailer.locator(".wl-msg-assistant .wl-md").get_by_text("Voilà.").wait_for()
    steps(mailer).nth(0).get_by_role("button").click()
    assert_no_axe_violations(mailer, f"Agent seul, tâche finie et étape dépliée, thème {theme}")
    mailer.set_viewport_size({"width": 320, "height": 800})
    assert_no_axe_violations(mailer, f"Agent seul à 320 px, thème {theme}")
