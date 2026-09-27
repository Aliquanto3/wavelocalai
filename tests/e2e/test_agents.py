"""
Agents autonomes, dans l'app réelle avec un petit modèle Ollama qui appelle des outils.
L'envoi d'email vise un puits SMTP local (conftest.py) : aucun email ne part, et le test
vérifie qu'aucune connexion SMTP n'a lieu sans validation.

Constats couverts : F7 et CAP-8 (la réponse de l'agent seul et son CO₂ survivent au
changement de mode), F16 (le modèle choisi aussi), D2/U14 (« Envoi d'email » décoché ;
brouillon soumis à confirmation, « Annuler » n'envoie rien), équipe d'agents (schéma et
vérification avant lancement rendus, sans lancer la mission), F17 (garde-fou mémoire :
échec explicite s'il bloque, la question restant affichée).
"""

import re

import pytest

from src.app.modules import AGENTS
from tests.e2e import helpers as h

pytestmark = pytest.mark.e2e

INSTRUCTION_PLACEHOLDER = "Décrivez la tâche à confier à l'agent"
MODE_SOLO = "Agent seul"
MODE_CREW = "Équipe d'agents"
EMAIL_TOOL = "Envoi d'email"
EMAIL_TO = "e2e@example.com"
# Début du message du garde-fou mémoire (ResourceManager.check_resources, src/core) : src/
# n'en expose pas de constante, et ce test ne modifie pas src/.
MEMORY_GUARD_TEXT = "Mémoire vive insuffisante"
RAM_GUARD_HINT = (
    "Le garde-fou mémoire bloque l'agent sur cette machine : libérez de la mémoire ou choisissez "
    "un modèle plus petit avec WAVELOCALAI_E2E_MODEL_AGENT."
)


@pytest.fixture(scope="module")
def app_extra_env(smtp_sink):
    """SMTP configuré vers le puits local : « Envoi d'email » devient sélectionnable."""
    return smtp_sink.env


def _answers(page):
    """Réponses finales de l'agent : seules elles portent le bouton « Télécharger » (ni les
    journaux d'outils ni les tours en erreur)."""
    return (
        h.main(page)
        .locator('[data-testid="stChatMessage"]')
        .filter(has=page.get_by_role("button", name="Télécharger"))
    )


def _answer_caption(page) -> str:
    """Métadonnées de la dernière réponse : badge, modèle, CO₂."""
    captions = _answers(page).last.locator('[data-testid="stCaptionContainer"]')
    return h.flat(captions.last.inner_text())


def _switch_mode(page, mode: str) -> None:
    h.sidebar(page).get_by_text(mode, exact=True).click()
    radio = h.sidebar(page).get_by_role("radio", name=mode)
    h.settle_after_action(page, until=radio.is_checked)


def _send(page, text: str, timeout_ms: int) -> None:
    """Confie la tâche et attend la fin du tour ; échec explicite si le garde-fou mémoire
    bloque l'agent."""
    h.chat_send(page, INSTRUCTION_PLACEHOLDER, text)
    h.settle_after_action(page, timeout_ms)
    guard = (
        h.main(page)
        .locator('[data-testid="stAlertContentWarning"]')
        .filter(has_text=MEMORY_GUARD_TEXT)
    )
    if guard.count():
        warning = h.flat(guard.first.inner_text())
        # La question bloquée reste affichée (F17), mais le parcours ne peut pas continuer.
        assert h.main(page).get_by_text(text).count() >= 1, "question bloquée perdue"
        pytest.fail(f"{RAM_GUARD_HINT} Message : {warning}", pytrace=False)


def _tool_pills(page):
    return h.main(page).locator('[data-testid="stButtonGroup"] button[data-variant="pills"]')


def test_solo_answer_and_model_survive_mode_switch(
    page, app, require_models, generation_timeout_ms
):
    """Une tâche outillée (calculatrice) aboutit ; après un passage par l'équipe d'agents,
    la réponse, son CO₂ et le modèle choisi sont toujours là."""
    (tag,) = require_models("agent")
    h.goto(page, app.base_url, AGENTS.url_path)
    selectbox = h.main(page).locator('[data-testid="stSelectbox"]').first
    label = h.pick_model(page, selectbox, tag)
    assert "· Local" in label

    _send(
        page,
        "Combien font 1234 multiplié par 5678 ? Utilise la calculatrice.",
        generation_timeout_ms,
    )
    h.wait_count(page, _answers(page), 1, generation_timeout_ms, "Réponse de l'agent")
    answer = h.flat(_answers(page).last.inner_text())
    assert "7006652" in re.sub(r"[\s\u202f\u00a0.,']", "", answer), answer
    caption = _answer_caption(page)
    assert "Local" in caption and "CO₂" in caption, caption

    _switch_mode(page, MODE_CREW)
    _switch_mode(page, MODE_SOLO)
    assert _answers(page).count() == 1, "réponse perdue au changement de mode"
    kept = h.flat(_answers(page).last.inner_text())
    assert "7006652" in re.sub(r"[\s\u202f\u00a0.,']", "", kept), kept
    assert _answer_caption(page) == caption, "badge, modèle ou CO₂ perdus au changement de mode"
    selectbox = h.main(page).locator('[data-testid="stSelectbox"]').first
    assert h.selected_value(selectbox) == label, "modèle choisi perdu après l'équipe d'agents"
    assert h.exceptions(page) == []


def test_email_requires_confirmation(page, app, require_models, smtp_sink, generation_timeout_ms):
    """« Envoi d'email » est décoché par défaut ; coché, l'agent prépare un brouillon
    montré dans une confirmation (destinataire, objet, corps) ; « Annuler » n'envoie rien."""
    (tag,) = require_models("agent")
    connections_before = len(smtp_sink.connections)
    h.goto(page, app.base_url, AGENTS.url_path)
    h.pick_model(page, h.main(page).locator('[data-testid="stSelectbox"]').first, tag)

    email = _tool_pills(page).filter(has_text=EMAIL_TOOL)
    assert email.count() == 1 and email.is_enabled()
    assert email.get_attribute("aria-pressed") != "true", "email coché par défaut (D2)"
    email.click()
    h.settle_after_action(page, until=lambda: email.get_attribute("aria-pressed") == "true")

    _send(
        page,
        f"Envoie un email à {EMAIL_TO} avec l'objet « Test e2e » et le corps « Bonjour ». "
        "Utilise l'outil d'envoi d'email.",
        generation_timeout_ms,
    )
    dialog = page.get_by_role("dialog")
    try:
        dialog.wait_for(timeout=generation_timeout_ms)
    except Exception:  # noqa: BLE001
        pytest.fail(
            "L'agent n'a pas préparé d'email (aucune confirmation affichée). Choisissez avec "
            "WAVELOCALAI_E2E_MODEL_AGENT un modèle qui appelle les outils de façon fiable. "
            f"Conversation : {h.flat(h.main(page).inner_text())[-800:]}",
            pytrace=False,
        )
    h.settle(page)
    text = h.flat(dialog.inner_text())
    assert "Envoyer l'email ?" in text and EMAIL_TO in text, text
    for part in ("Destinataire", "Objet", "Corps du message"):
        assert part in text, text
    assert len(smtp_sink.connections) == connections_before, "connexion SMTP avant validation"

    dialog.get_by_role("button", name="Annuler").click()
    h.settle_after_action(page, until=lambda: page.get_by_role("dialog").count() == 0)
    assert h.main(page).get_by_text("Email envoyé").count() == 0
    page.wait_for_timeout(1_000)
    assert len(smtp_sink.connections) == connections_before, "un email est parti malgré « Annuler »"
    assert h.exceptions(page) == []


def test_crew_renders_without_launching(page, app, require_models):
    """Équipe d'agents : schéma de l'enchaînement et vérification mémoire rendus, bouton de
    lancement présent (la mission, longue, n'est pas lancée)."""
    require_models("agent")
    h.goto(page, app.base_url, AGENTS.url_path)
    _switch_mode(page, MODE_CREW)
    main = h.main(page)
    assert main.get_by_role("heading", name="Enchaînement des agents").count() == 1
    main.locator('[data-testid="stGraphVizChart"]').first.wait_for(timeout=h.PAGE_TIMEOUT_MS)
    assert main.get_by_text("Vérification avant lancement").count() == 1
    launch = main.get_by_role("button", name=re.compile(r"Lancer l'équipe|Lancer malgré le risque"))
    assert launch.count() == 1
    assert h.exceptions(page) == []
