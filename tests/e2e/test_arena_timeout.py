"""
Délai dépassé avec un vrai modèle : l'app est lancée avec un délai d'inférence très court pour
le seul petit modèle (WAVELOCALAI_E2E_MODEL_SMALL), par le lanceur (launch_app.py). L'appel à
Ollama est réel ; il est interrompu par le délai de l'application.

Constats couverts : F3 et CAP-3 (« Délai dépassé » au lieu d'une trace dans le chat, le banc
d'essai et l'Arène ; l'Arène continue et classe les autres modèles).
"""

import os
import re

import pytest

from src.app.modules import ARENA
from tests.e2e import helpers as h
from tests.e2e.launch_app import SHORT_TIMEOUT_S_ENV, TIMEOUT_TAGS_ENV
from tests.e2e.ollama_api import normalize_tag

pytestmark = pytest.mark.e2e

DEFAULT_SHORT_TIMEOUT_S = "0.05"
CHAT_PLACEHOLDER = "Écrivez votre message"


@pytest.fixture(scope="module")
def app_extra_env(e2e_models):
    """Délai court pour le seul petit modèle (qui ne doit être ni le modèle de chat ni le juge)."""
    small = e2e_models["small"]
    others = {normalize_tag(e2e_models["chat"]), normalize_tag(e2e_models["judge"])}
    if normalize_tag(small) in others:
        pytest.fail(
            "WAVELOCALAI_E2E_MODEL_SMALL doit différer du modèle de chat et du juge : son délai "
            "d'inférence est volontairement trop court dans ce module.",
            pytrace=False,
        )
    short = os.environ.get(SHORT_TIMEOUT_S_ENV) or DEFAULT_SHORT_TIMEOUT_S
    try:
        valid = float(short) > 0
    except ValueError:
        valid = False
    if not valid:
        pytest.fail(f"{SHORT_TIMEOUT_S_ENV} doit être un nombre de secondes > 0 (reçu « {short} »)")
    return {TIMEOUT_TAGS_ENV: small, SHORT_TIMEOUT_S_ENV: short}


def _assert_timeout_error(page, scope) -> None:
    """`alert-error` « Délai dépassé », détail replié, jamais une trace Python."""
    h.wait_text(scope, re.compile("Délai dépassé"), timeout_ms=h.PAGE_TIMEOUT_MS)
    h.settle(page)
    errors = [
        h.flat(t) for t in scope.locator('[data-testid="stAlertContentError"]').all_inner_texts()
    ]
    assert any("Délai dépassé" in e for e in errors), errors
    assert scope.get_by_text("Détails techniques").count() >= 1
    assert h.exceptions(page) == []
    assert "NoneType" not in h.flat(scope.inner_text())


def test_chat_timeout_is_readable(page, app, require_models):
    (small,) = require_models("small")
    h.goto(page, app.base_url, ARENA.url_path)
    panel = h.visible_panel(page)
    h.pick_model(page, panel.locator('[data-testid="stSelectbox"]').first, small)
    h.chat_send(page, CHAT_PLACEHOLDER, "Bonjour")
    _assert_timeout_error(page, h.main(page))


def test_lab_timeout_is_readable(page, app, require_models):
    (small,) = require_models("small")
    h.goto(page, app.base_url, ARENA.url_path)
    h.click_tab(page, "Banc d'essai")
    panel = h.visible_panel(page)
    h.pick_model(page, panel.locator('[data-testid="stSelectbox"]').first, small)
    panel.get_by_role("button", name="Lancer le test").click()
    _assert_timeout_error(page, panel)
    assert panel.locator('[data-testid="stMetric"]').count() == 0, "aucune métrique sans mesure"


def test_arena_timeout_does_not_block_others(page, app, require_models, generation_timeout_ms):
    """Le petit modèle dépasse le délai : sa ligne le dit, l'autre modèle est classé."""
    chat, small, judge = require_models("chat", "small", "judge")
    h.goto(page, app.base_url, ARENA.url_path)
    h.click_tab(page, "Arène")
    panel = h.visible_panel(page)
    multiselect = panel.locator('[data-testid="stMultiSelect"]').first
    h.multiselect_clear(page, multiselect)
    for tag in (chat, small):
        h.add_model(page, multiselect, tag)
    panel.get_by_text("Réglages du juge").click()
    h.pick_model(page, panel.locator('[data-testid="stSelectbox"]').first, judge)

    panel.get_by_role("button", name="Lancer la comparaison").click()
    status = h.wait_text(
        panel, re.compile(r"Comparaison (terminée|échouée)"), generation_timeout_ms
    )
    h.settle(page)
    label = h.flat(status.inner_text())
    assert "Comparaison terminée" in label and "1 modèle en échec" in label, label

    # Le suivi de la comparaison (replié) dit quel modèle a dépassé le délai.
    status.click()
    h.settle_after_action(page, until=panel.get_by_text("Les autres continuent").first)
    text = h.flat(panel.inner_text())
    small_name = h.model_query(small)[0]
    assert re.search(rf"{re.escape(small_name)}.{{0,40}}Délai dépassé", text), text[-2000:]
    assert "Les autres continuent" in text
    assert "Aucun modèle n'a répondu" not in text
    assert panel.get_by_role("heading", name="Verdict", exact=True).count() == 1
    assert h.exceptions(page) == []
