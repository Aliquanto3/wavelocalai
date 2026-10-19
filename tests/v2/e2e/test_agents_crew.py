"""Écran Équipe d'agents (story 6.6) dans un vrai navigateur, sur le vrai serveur et le modèle `fake`.

Le serveur est le vrai (hub, missions, boucle d'outils, routes des équipes et d'approbation, envoi
SMTP) ; Ollama n'est jamais sollicité. La liste des modèles est simulée par le test (`page.route`), le
modèle `fake` suit un script **par appel de modèle**, tous agents confondus, dans l'ordre. Le SMTP est
le faux serveur **local** de l'écran Agent seul : aucun email réel ne part. Les équipes sont celles
livrées (`config/agent_crews.json`) ; un test qui les modifie les rétablit à sa fin.
"""

from __future__ import annotations

import json
import re
import urllib.request

import pytest
from playwright.sync_api import expect

from .test_agents_solo import (  # noqa: F401 - fixtures et aides de l'écran Agent seul
    EMAIL,
    MODEL,
    NBSP,
    call,
    get_json,
    install_models,
    leave_no_run,
    mail,
    script,
    smtp,
    warm_up,
    watch_runs,
)
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

CREW = "etude_concurrentielle"
ROLES = ["Chercheur", "Analyste", "Rédacteur"]
ORDER = "Chercheur, puis Analyste, puis Rédacteur, puis le rapport"
TOPIC = "Étudier le marché des petits modèles"
REPORT = "Rapport final de la mission."
TOTALS = re.compile(r"^Terminé · \d+ outils? · \d")


@pytest.fixture(scope="module", autouse=True)
def warmed(server):
    warm_up(server)


def open_crew(page, base_url, route="#/agents/equipe"):
    install_models(page)
    watch_runs(page, base_url)
    page.goto(f"{base_url}/{route}")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('.crew-select')?.options.length > 0")
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    return page


@pytest.fixture
def crew(page, server):
    return open_crew(page, server.base_url)


def launch(page):
    return page.get_by_role("button", name="Lancer la mission")


def rows(page):
    return page.locator(".crew-agent")


def statuses(page):
    return [row.locator(".crew-agent-status").inner_text() for row in rows(page).all()]


def node_states(page):
    return [
        node.locator(".wl-team-state").all_text_contents()
        for node in page.locator(".wl-team-node").all()
    ]


def mission(page, server, topic=TOPIC):
    """Une mission de trois agents : le premier appelle un outil, le dernier écrit le rapport."""
    script(
        page,
        server,
        [call("get_current_time")],
        [{"text": "Données collectées."}],
        [{"text": "Indicateurs calculés."}],
        [{"text": REPORT}],
    )
    page.get_by_label("Sujet de la mission").fill(topic)
    launch(page).click()


def put_agents(page, base_url, crew_id, agents):
    response = page.request.put(
        f"{base_url}/api/agents/crews/{crew_id}", data={"agents": agents, "allow_cloud": False}
    )
    assert response.ok, response.text()


def reset_crew(base_url, crew_id):
    request = urllib.request.Request(f"{base_url}/api/agents/crews/{crew_id}", method="DELETE")
    urllib.request.urlopen(request, timeout=5).close()  # noqa: S310


# --- Écran et schéma ---------------------------------------------------------------------------


def test_the_screen_is_equipe_d_agents_with_its_schema_and_the_topic_of_the_crew(crew):
    assert crew.title() == "Équipe d'agents · WaveLocalAI"
    assert crew.get_by_role("heading", level=1).inner_text() == "Équipe d'agents"
    tabs = crew.get_by_role("navigation", name="Écrans du module Agents")
    assert tabs.get_by_role("link", name="Équipe d'agents").get_attribute("aria-current") == "page"
    assert tabs.get_by_role("link", name="Agent seul").get_attribute("href") == "#/agents/seul"
    labels = crew.locator(".crew-select option").all_inner_texts()
    assert labels == ["Étude concurrentielle", "Audit des mesures", "Comparaison carbone"]
    assert crew.get_by_label("Sujet de la mission").input_value().startswith("Analyser le marché")
    # Le schéma : un `<title>`, un `<desc>` qui lit l'ordre, un nœud par agent puis « Rapport ».
    svg = crew.locator("wl-team-graph svg")
    assert svg.locator("title").first.text_content() == "Schéma de l'équipe"
    assert svg.locator("desc").text_content() == ORDER
    assert (
        svg.get_attribute("role") == "img" and svg.get_attribute("data-orientation") == "horizontal"
    )
    assert crew.locator(".wl-team-node > title").all_text_contents() == [*ROLES, "Rapport"]
    assert node_states(crew) == [[], [], [], []]  # rien n'est « en cours » avant le lancement
    # Pas de mission : ni suivi d'agents ni rapport.
    assert rows(crew).count() == 0 and not crew.locator(".crew-report").is_visible()


def test_the_schema_is_vertical_below_768px_and_the_launch_needs_a_topic(crew):
    crew.set_viewport_size({"width": 600, "height": 900})
    svg = crew.locator("wl-team-graph svg")
    expect(svg).to_have_attribute("data-orientation", "vertical")
    crew.set_viewport_size({"width": 1280, "height": 900})
    expect(svg).to_have_attribute("data-orientation", "horizontal")
    crew.get_by_label("Sujet de la mission").fill("")
    button = launch(crew)
    assert button.is_disabled()
    reason = crew.locator(".crew-launch-reason")
    assert reason.inner_text() == "Saisissez un sujet"
    assert button.get_attribute("aria-describedby") == reason.get_attribute("id")


def test_changing_the_crew_changes_the_schema_and_proposes_its_topic(crew):
    crew.locator(".crew-select").select_option("audit_des_mesures")
    assert crew.locator(".wl-team-node > title").all_text_contents() == [
        "Analyste de données",
        "Expert en visualisation",
        "Rédacteur technique",
        "Rapport",
    ]
    assert "fichier CSV" in crew.get_by_label("Sujet de la mission").input_value()


# --- Mission -----------------------------------------------------------------------------------


def test_a_mission_goes_agent_by_agent_and_ends_with_its_report_and_its_address(crew, server):
    mission(crew, server)
    # Les trois agents finissent, chacun avec ses outils et sa durée lus du serveur (D-34).
    expect(crew.locator(".crew-agent[data-state=done]")).to_have_count(3, timeout=20000)
    status = statuses(crew)
    assert all(TOTALS.match(text) for text in status), status
    assert status[0].startswith("Terminé · 1 outil · ")
    assert status[1].startswith("Terminé · 0 outil · ")
    assert node_states(crew)[:3] == [["terminé"]] * 3
    # Le rapport est le dernier agent ; son pied vient du serveur (badge, CO₂, mémoire, durée).
    crew.locator(".wl-msg-assistant .wl-md").get_by_text(REPORT).wait_for()
    footer = crew.locator(".crew-report .wl-msg-foot")
    labels = footer.locator("wl-metric").evaluate_all(
        "els => els.map((e) => e.getAttribute('label'))"
    )
    assert labels[-3:] == ["Étapes", "Durée", "Pic de mémoire"]
    link = crew.get_by_role("link", name="Télécharger en Markdown")
    assert re.fullmatch(r"/api/conversations/[\w-]+\.md", link.get_attribute("href"))
    # L'adresse est réécrite à la fin du run, sans nouvelle entrée d'historique.
    wait_for(crew, "() => /^#\\/agents\\/equipe\\/[\\w-]+$/.test(location.hash)")
    assert crew.evaluate("history.length") == 2  # about:blank puis la page, pas d'entrée de plus
    # Une ligne dépliée montre la trace de l'agent ; le journal brut est replié, en lignes horaires.
    first = rows(crew).first
    first.get_by_role("button").click()
    labels = first.locator(".wl-step-label").all_inner_texts()
    assert "Appel de l'outil Heure actuelle" in labels or any(
        "Appel de l'outil" in x for x in labels
    )
    journal = crew.locator("details.crew-journal")
    assert journal.get_attribute("open") is None
    journal.locator("summary").click()
    lines = journal.locator(".crew-journal-line").all_inner_texts()
    assert re.match(r"^\d\d:\d\d:\d\d Mission lancée$", lines[0])
    assert any(re.match(r"^\d\d:\d\d:\d\d Chercheur · Appel de l'outil ", x) for x in lines)
    assert re.match(r"^\d\d:\d\d:\d\d Mission terminée$", lines[-1])
    assert not any("{" in x for x in lines)  # jamais du JSON brut (D-33)


def test_stopping_with_escape_keeps_the_partial_report_and_marks_the_agents(crew, server):
    script(
        crew,
        server,
        [{"text": "Premier travail terminé."}],
        [{"sleep_s": 30}],
    )
    crew.get_by_label("Sujet de la mission").fill(TOPIC)
    launch(crew).click()
    expect(rows(crew).first).to_have_attribute("data-state", "done", timeout=20000)
    expect(rows(crew).nth(1)).to_have_attribute("data-state", "current")
    assert statuses(crew)[1] == "En cours · Réflexion…"
    assert statuses(crew)[2] == "En attente"
    # Le schéma marque l'agent en cours par un libellé, jamais par la couleur seule.
    assert node_states(crew)[1] == ["en cours"]
    crew.keyboard.press("Escape")
    expect(rows(crew).nth(1)).to_have_attribute("data-state", "stopped", timeout=10000)
    assert statuses(crew) == [statuses(crew)[0], "Arrêté", "Non lancé"]
    assert statuses(crew)[0].startswith("Terminé")
    assert node_states(crew)[1:3] == [["arrêté"], ["non lancé"]]
    # Rapport partiel : la réponse du dernier agent terminé est gardée.
    expect(crew.get_by_role("heading", name="Rapport partiel (mission arrêtée)")).to_be_visible()
    crew.locator(".wl-msg-assistant .wl-md").get_by_text("Premier travail terminé.").wait_for()
    assert crew.get_by_role("link", name="Télécharger en Markdown").is_visible()
    wait_for(crew, "() => /^#\\/agents\\/equipe\\/[\\w-]+$/.test(location.hash)")


def test_stopping_before_the_first_agent_ends_says_there_is_no_report(crew, server):
    script(crew, server, [{"sleep_s": 30}])
    crew.get_by_label("Sujet de la mission").fill(TOPIC)
    launch(crew).click()
    expect(rows(crew).first).to_have_attribute("data-state", "current", timeout=20000)
    crew.locator("wl-run-status").get_by_role("button", name="Arrêter").click()
    expect(rows(crew).first).to_have_attribute("data-state", "stopped", timeout=10000)
    assert statuses(crew) == ["Arrêté", "Non lancé", "Non lancé"]
    expect(crew.locator(".crew-report-note")).to_have_text(
        f"Aucun rapport{NBSP}: la mission a été arrêtée avant la fin du premier agent."
    )


def test_a_finished_mission_reopens_by_its_address_and_an_unknown_one_is_said(crew, server, page):
    mission(crew, server)
    expect(crew.locator(".crew-agent[data-state=done]")).to_have_count(3, timeout=20000)
    wait_for(crew, "() => /^#\\/agents\\/equipe\\/[\\w-]+$/.test(location.hash)")
    address = crew.evaluate("location.hash")
    run_id = address.rsplit("/", 1)[1]
    first_report = crew.locator(".wl-msg-assistant .wl-md").inner_text()
    # Rechargement de la page sur l'adresse : le suivi et le rapport reviennent, sans relancer.
    page.goto(f"{server.base_url}/{address}")
    wait_ready(page)
    expect(page.locator(".crew-agent[data-state=done]")).to_have_count(3, timeout=20000)
    assert page.locator(".crew-select").input_value() == CREW
    assert page.locator(".wl-msg-user .wl-msg-text").inner_text() == TOPIC
    assert page.locator(".wl-msg-assistant .wl-md").inner_text() == first_report
    assert get_json(server, f"/api/runs/{run_id}")["status"] == "ok"


def test_an_unknown_mission_address_says_so_and_offers_a_new_mission(
    page_tolerating_failed_requests, server
):
    page = page_tolerating_failed_requests
    install_models(page)
    page.goto(f"{server.base_url}/#/agents/equipe/inconnu")
    wait_ready(page)
    alert = page.get_by_role("alert").filter(has_text="Mission introuvable")
    alert.wait_for()
    assert page.get_by_role("link", name="Lancer une nouvelle mission").get_attribute("href") == (
        "#/agents/equipe"
    )
    assert page.locator(".crew-agent").count() == 0


# --- Configurer --------------------------------------------------------------------------------


def test_configure_opens_a_non_modal_panel_beside_the_schema_and_saves_the_change(crew, server):
    try:
        crew.get_by_role("button", name="Configurer").click()
        panel = crew.locator(".crew-config")
        expect(panel).to_be_visible()
        assert crew.evaluate("document.activeElement.textContent") == "Configurer l'équipe"
        assert crew.locator("dialog[open]").count() == 0  # non modal
        # Colonne de droite dès 1 024 px : le schéma reste visible, le volet est à sa droite.
        graph_box = crew.locator("wl-team-graph").bounding_box()
        panel_box = panel.bounding_box()
        assert panel_box["x"] >= graph_box["x"] + graph_box["width"] - 1
        assert crew.locator("wl-team-graph").is_visible()
        fieldsets = panel.locator(".crew-config-agent")
        assert fieldsets.count() == 3
        assert fieldsets.first.locator("[data-field=role]").input_value() == "Chercheur"
        # Retirer le dernier agent, puis enregistrer.
        fieldsets.nth(2).get_by_role("button", name="Retirer cet agent").click()
        assert panel.locator(".crew-config-agent").count() == 2
        panel.get_by_role("button", name="Enregistrer").click()
        expect(panel).to_be_hidden()
        assert crew.locator(".wl-team-node > title").all_text_contents() == [
            "Chercheur",
            "Analyste",
            "Rapport",
        ]
        expect(crew.locator(".crew-modified")).to_have_text("Modifiée")
        assert (
            crew.evaluate("document.activeElement.textContent") == "Configurer"
        )  # le focus revient au bouton
        # La modification est dans les préférences du serveur : elle survit à un rechargement.
        crew.reload()
        wait_ready(crew)
        wait_for(crew, "() => document.querySelector('.crew-select')?.options.length > 0")
        assert crew.locator(".wl-team-node > title").all_text_contents() == [
            "Chercheur",
            "Analyste",
            "Rapport",
        ]
        # « Revenir à l'équipe d'origine » : sans confirmation, avec son annonce.
        crew.get_by_role("button", name="Revenir à l'équipe d'origine").click()
        expect(crew.locator("p.chat-notice")).to_have_text("Équipe d'origine rétablie.")
        assert crew.locator(".wl-team-node > title").all_text_contents() == [*ROLES, "Rapport"]
        assert crew.locator(".crew-modified").is_hidden()
    finally:
        reset_crew(server.base_url, CREW)


def test_the_fifth_agent_is_the_last_and_the_add_button_says_why(crew):
    crew.get_by_role("button", name="Configurer").click()
    panel = crew.locator(".crew-config")
    add = panel.get_by_role("button", name="Ajouter un agent")
    for _ in range(2):
        add.click()
    assert panel.locator(".crew-config-agent").count() == 5
    assert add.is_disabled()
    reason = panel.locator(".crew-config-reason")
    assert reason.inner_text() == (
        f"Une équipe compte 5 agents au plus{NBSP}: retirez un agent pour en ajouter un autre."
    )
    assert add.get_attribute("aria-describedby") == reason.get_attribute("id")
    # À 5 agents, le schéma est vertical, même en large (D-36) — une fois enregistré ; ici le brouillon
    # n'a rien changé au schéma.
    assert crew.locator("wl-team-graph svg").get_attribute("data-orientation") == "horizontal"
    panel.get_by_role("button", name="Retirer cet agent").last.click()
    assert add.is_enabled()


def test_the_server_errors_appear_under_their_field_and_the_focus_goes_to_the_first(crew, server):
    crew.get_by_role("button", name="Configurer").click()
    panel = crew.locator(".crew-config")
    panel.get_by_role("button", name="Ajouter un agent").click()
    new = panel.locator(".crew-config-agent").last
    new.locator("[data-field=goal]").fill("Un objectif")
    panel.get_by_role("button", name="Enregistrer").click()
    role = new.locator("[data-field=role]")
    error = new.locator("[data-error-for$='.role']")
    expect(error).to_be_visible()
    assert role.get_attribute("aria-invalid") == "true"
    assert role.get_attribute("aria-describedby") == error.get_attribute("id")
    assert crew.evaluate("document.activeElement.dataset.field") == "role"
    assert panel.is_visible()  # rien n'est enregistré
    panel.get_by_role("button", name="Annuler").click()
    expect(panel).to_be_hidden()
    assert crew.locator(".wl-team-node > title").all_text_contents() == [*ROLES, "Rapport"]
    assert crew.locator(".crew-modified").is_hidden()


def test_a_crew_without_agent_cannot_launch_and_the_panel_says_to_add_one(page, server):
    empty = {
        "crews": [
            {"id": "vide", "label": "Vide", "category": "Test", "description": "", "topic": "Un sujet",
             "modified": False, "agents": [], "tasks": []},
        ],
        "max_agents": 5,
    }  # fmt: skip
    page.route(
        re.compile(r"/api/agents/crews$"),
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(empty)
        ),
    )
    open_crew(page, server.base_url)
    assert launch(page).is_disabled()
    assert page.locator(".crew-launch-reason").inner_text() == "Ajoutez au moins un agent"
    assert page.locator("wl-team-graph").is_hidden()  # rien à dessiner
    page.get_by_role("button", name="Configurer").click()
    assert (
        page.locator(".crew-config")
        .get_by_text("Aucun agent. Ajoutez-en au moins un.")
        .is_visible()
    )


# --- Validation d'un email par un agent d'équipe ------------------------------------------------


def email_crew(page, base_url):
    """Le dernier agent peut envoyer un email (outil sensible) : l'approbation de la 6.3 s'applique."""
    agents = [
        {"role": "Rédacteur", "goal": "Écrire au client", "backstory": "", "tools": ["send_email"],
         "model": None},
    ]  # fmt: skip
    put_agents(page, base_url, CREW, agents)
    page.reload()
    wait_ready(page)
    wait_for(page, "() => document.querySelector('.crew-select')?.options.length > 0")
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")


def test_an_email_asked_by_a_team_agent_is_sent_only_after_approval(page, mail, smtp):
    smtp.messages.clear()
    smtp.connections = 0
    open_crew(page, mail.base_url)
    try:
        email_crew(page, mail.base_url)
        script(
            page, mail, [call("send_email", **EMAIL)], [{"text": "Email envoyé, mission faite."}]
        )
        page.get_by_label("Sujet de la mission").fill(TOPIC)
        launch(page).click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        assert dialog.get_by_role("heading", name="Envoyer cet email ?").is_visible()
        assert dialog.locator(".wl-dialog-value").all_inner_texts() == [
            EMAIL["to"], EMAIL["subject"], EMAIL["body"],
        ]  # fmt: skip
        assert (
            page.locator(".crew-agent-status").inner_text()
            == "En cours · En attente de votre validation"
        )
        assert smtp.connections == 0 and smtp.messages == []
        dialog.get_by_role("button", name="Envoyer l'email").click()
        expect(dialog).to_be_hidden()
        page.locator(".wl-msg-assistant .wl-md").get_by_text(
            "Email envoyé, mission faite."
        ).wait_for()
        (message,) = smtp.messages
        assert message.recipients == [EMAIL["to"]] and message.text == EMAIL["body"]
        # L'issue est inscrite dans la trace de l'agent qui l'a demandée.
        page.locator(".crew-agent").first.get_by_role("button").click()
        expect(page.locator("wl-step-trace li.wl-step-note")).to_have_text("Email envoyé.")
    finally:
        reset_crew(mail.base_url, CREW)


def test_a_refused_email_sends_nothing_and_the_mission_goes_on(page, mail, smtp):
    smtp.messages.clear()
    smtp.connections = 0
    open_crew(page, mail.base_url)
    try:
        email_crew(page, mail.base_url)
        script(page, mail, [call("send_email", **EMAIL)], [{"text": "Je n'ai rien envoyé."}])
        page.get_by_label("Sujet de la mission").fill(TOPIC)
        launch(page).click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for()
        dialog.get_by_role("button", name="Annuler").click()
        expect(dialog).to_be_hidden()
        page.locator(".wl-msg-assistant .wl-md").get_by_text("Je n'ai rien envoyé.").wait_for()
        assert smtp.connections == 0 and smtp.messages == []
        expect(page.locator(".crew-agent[data-state=done]")).to_have_count(1)
    finally:
        reset_crew(mail.base_url, CREW)


# --- Accessibilité -----------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_idle_configuring_running_and_finished(crew, server, theme):
    crew.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(crew, f"Équipe au repos, thème {theme}")
    crew.get_by_role("button", name="Configurer").click()
    assert_no_axe_violations(crew, f"Équipe, volet Configurer ouvert, thème {theme}")
    crew.get_by_role("button", name="Annuler").click()
    script(crew, server, [{"text": "Un."}], [{"sleep_s": 3}, {"text": "Deux."}], [{"text": REPORT}])
    crew.get_by_label("Sujet de la mission").fill(TOPIC)
    launch(crew).click()
    expect(rows(crew).nth(1)).to_have_attribute("data-state", "current", timeout=20000)
    assert_no_axe_violations(crew, f"Équipe, mission en cours, thème {theme}")
    expect(crew.locator(".crew-agent[data-state=done]")).to_have_count(3, timeout=20000)
    crew.locator(".wl-msg-assistant .wl-md").get_by_text(REPORT).wait_for()
    rows(crew).first.get_by_role("button").click()
    crew.locator("details.crew-journal summary").click()
    assert_no_axe_violations(crew, f"Équipe, mission finie, thème {theme}")
    crew.set_viewport_size({"width": 320, "height": 800})
    assert_no_axe_violations(crew, f"Équipe à 320 px, thème {theme}")
