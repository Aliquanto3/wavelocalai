"""Écran Discussion, story 4.7 : reclassement des extraits par un reranker local, s'il est là, dans
un vrai navigateur sur le vrai serveur.

Comme `test_discussion_strategies.py` : indexation, recherche et flux sont réels ; l'embedding, le
modèle de réponse et le reranker sont factices (`POST /api/test/reranker`). Aucun modèle de reranker
n'est présent ni téléchargé : sans lui, l'écran dit pourquoi et la recherche garde l'ordre trouvé.
"""

from __future__ import annotations

import re

import pytest

from .test_discussion import (  # noqa: F401 - fixture
    ANSWER,
    docs,
    post,
    reload_screen,
    sources,
    wait_done,
)
from .test_discussion_strategies import (
    GRADE_FIRST,
    SCREEN,
    asked,
    choose,
    script_calls,
    settings,
    wait_stage,
)
from .test_shell import assert_no_axe_violations

NOTE = f"{SCREEN} .docs-rerank"


def first_document(page) -> str:
    return sources(page).first.locator(".wl-source-doc").inner_text()


def test_without_a_reranker_the_screen_says_why_and_the_search_keeps_its_order(docs):
    page, _, _ = docs
    settings(page)
    note = page.locator(NOTE)
    assert note.get_attribute("data-reranker") == "off"
    text = note.inner_text()
    assert re.match(r"Reclassement indisponible\xa0: .+\.", text)  # la raison vient du serveur
    assert "extra" in text or "cache" in text

    asked(page)
    wait_done(page)
    assert first_document(page) == "chats.txt"  # l'ordre des vecteurs, sans reclassement
    assert page.locator(f"{SCREEN} wl-run-status").get_attribute("data-stage") == "ok"


def test_a_present_reranker_says_reclassement_and_reorders_the_excerpts(docs):
    page, server, _ = docs
    post(page, server, "/api/test/reranker", data={"mode": "reverse", "delay_s": 1.5})
    reload_screen(page)  # l'état du reranker est relu avec les réglages
    settings(page)
    note = page.locator(NOTE)
    assert note.get_attribute("data-reranker") == "on"
    assert note.inner_text().startswith("Reclassement actif (")

    body = asked(page)
    assert body["strategy"] == "naive"
    wait_stage(page, "Reclassement…")
    wait_done(page)
    # `reverse` met le candidat le plus éloigné en tête : la réponse suit le reclassement.
    assert first_document(page) != "chats.txt"
    assert sources(page).count() == 3  # trois documents, tous gardés sous `top_k` = 4


def test_the_reranking_keeps_only_top_k_excerpts(docs):
    page, server, _ = docs
    post(page, server, "/api/test/reranker", data={"mode": "reverse"})
    reload_screen(page)
    top_k = settings(page).get_by_label("Nombre d'extraits")
    top_k.fill("1")
    asked(page)
    wait_done(page)
    assert sources(page).count() == 1
    assert first_document(page) != "chats.txt"


def test_the_stage_after_the_reranking_is_the_one_of_the_strategy(docs):
    page, server, _ = docs
    post(page, server, "/api/test/reranker", data={"mode": "lexical"})
    reload_screen(page)
    script_calls(page, server, [{"sleep_s": 1.5}, {"text": GRADE_FIRST}], ANSWER)
    choose(page, "Recherche vérifiée")
    assert asked(page)["strategy"] == "self_rag"
    wait_stage(
        page, "Vérification de la pertinence…"
    )  # le reclassement est fini, la notation tourne
    wait_done(page)
    calls = page.request.get(f"{server.base_url}/api/test/reranker").json()["calls"]
    assert [call["texts"] for call in calls] == [3]  # une recherche, trois candidats


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 320])
def test_axe_finds_no_violation_with_the_reranker_note_in_both_states(docs, theme, width):
    page, server, _ = docs
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    page.set_viewport_size({"width": width, "height": 900})
    settings(page)
    assert_no_axe_violations(page, f"reclassement indisponible, {width} px, thème {theme}")
    post(page, server, "/api/test/reranker", data={"mode": "lexical"})
    reload_screen(page)
    page.set_viewport_size({"width": width, "height": 900})
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    settings(page)
    assert page.locator(NOTE).get_attribute("data-reranker") == "on"
    assert_no_axe_violations(page, f"reclassement actif, {width} px, thème {theme}")
