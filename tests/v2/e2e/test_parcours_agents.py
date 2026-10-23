"""Parcours « Agents » de bout en bout (story 8.3), sans recharger la page.

Un seul chargement de page, sur le vrai serveur et le modèle `fake` : l'Agent seul appelle un outil
et publie ses étapes, propose un email que rien n'envoie avant la validation (faux SMTP **local**),
puis l'onglet « Équipe d'agents » mène une mission agent par agent jusqu'à son rapport, et l'onglet
« Agent seul » se remonte sans perte de ses réglages. La navigation passe par les onglets du module.

Doublures de `test_agents_solo.py` et `test_agents_crew.py` : liste des modèles simulée par le test,
script du `fake` par appel de modèle, faux SMTP en processus. Ollama n'est jamais sollicité, aucun
email réel ne part, aucune requête ne sort de 127.0.0.1 (fixture `context` et bilan de la suite).
"""

from __future__ import annotations

import re

from playwright.sync_api import expect

from .parcours import assert_never_reloaded, mark_no_reload, open_tab, wait_screen
from .test_agents_crew import (  # noqa: F401  (fixtures et aides de l'écran Équipe d'agents)
    REPORT,
    TOTALS,
    leave_no_run,
    mission,
    rows,
    statuses,
)
from .test_agents_solo import (  # noqa: F401  (fixtures et aides de l'écran Agent seul)
    EMAIL,
    MODEL,
    NBSP,
    RUNS,
    ask,
    call,
    mail,
    open_mailer,
    script,
    smtp,
    stage,
    step_labels,
    steps,
    tool_switch,
)
from .test_shell import wait_for


def test_parcours_agent_seul_puis_equipe_sans_recharger_la_page(page, mail, smtp):
    open_mailer(page, mail, smtp)
    mark_no_reload(page)
    assert page.get_by_role("heading", level=1).inner_text() == "Agent seul"

    # 1. Une tâche outillée : réflexion, appel de l'outil, résultat, réponse d'un bloc.
    script(
        page,
        mail,
        [{"text": "Je calcule."}, call("calculator", expression="2+3")],
        [{"text": "Le résultat est **5**."}],
    )
    ask(page, "Combien font 2 + 3 ?")
    expect(steps(page)).to_have_count(4)
    assert step_labels(page) == [
        "Réflexion",
        "Appel de l'outil Calculatrice",
        "Résultat de Calculatrice",
        "Réponse de l'agent",
    ]
    page.locator(".wl-msg-assistant .wl-md strong").wait_for()
    assert page.locator(".wl-msg-assistant .wl-md strong").inner_text() == "5"

    # 2. Un email proposé : rien ne part avant la validation, puis exactement ce qui était montré.
    smtp.messages.clear()
    script(page, mail, [call("send_email", **EMAIL)], [{"text": "L'email est parti."}])
    tool_switch(page, "Envoi d'email").check()
    ask(page, "Écris à mon client.")
    dialog = page.get_by_role("dialog")
    dialog.wait_for()
    assert dialog.get_by_role("heading", name="Envoyer cet email ?").is_visible()
    assert dialog.locator(".wl-dialog-value").all_inner_texts() == [
        EMAIL["to"],
        EMAIL["subject"],
        EMAIL["body"],
    ]
    assert stage(page) == "En attente de votre validation"
    assert smtp.messages == []
    dialog.get_by_role("button", name="Envoyer l'email").click()
    expect(dialog).to_be_hidden()
    page.locator("wl-step-trace li.wl-step-note").get_by_text("Email envoyé.").wait_for()
    (message,) = smtp.messages
    assert message.recipients == [EMAIL["to"]] and message.subject == EMAIL["subject"]
    page.locator(".wl-msg-assistant .wl-md").get_by_text("L'email est parti.").wait_for()

    # 3. L'Équipe d'agents, par l'onglet du module : une mission, trois agents, un rapport.
    open_tab(page, "Agents", "Équipe d'agents", "agents-crew")
    wait_for(page, "() => document.querySelector('.crew-select')?.options.length > 0")
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    assert page.get_by_role("heading", level=1).inner_text() == "Équipe d'agents"
    mission(page, mail)
    expect(page.locator(".crew-agent[data-state=done]")).to_have_count(3, timeout=20_000)
    assert all(TOTALS.match(text) for text in statuses(page)), statuses(page)
    page.locator(".wl-msg-assistant .wl-md").get_by_text(REPORT).wait_for()
    assert rows(page).count() == 3
    # Le rapport se télécharge par la route du serveur, jamais par un `blob:`.
    link = page.get_by_role("link", name="Télécharger en Markdown")
    assert re.fullmatch(r"/api/conversations/[\w-]+\.md", link.get_attribute("href"))

    # 4. Retour à l'Agent seul : l'écran se remonte, ses outils sont relus, rien n'est envoyé.
    open_tab(page, "Agents", "Agent seul", "agents-solo")
    wait_screen(page, "agents-solo")
    wait_for(page, "() => document.querySelectorAll('.agents-tool-list li').length === 9")
    assert len(smtp.messages) == 1  # l'email du parcours, et aucun autre

    # 5. Le tout sans recharger la page.
    assert_never_reloaded(page)
