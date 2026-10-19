"""Base documentaire : supprimer un document, vider la base, régler (story 4.3), dans un vrai
navigateur sur le vrai serveur (embedding `fake`, voir `test_documents.py`).

Prouvés ici : `wl-confirm-dialog` (focus sur « Annuler », textes d'`epics.md`), « Annuler » qui ne
supprime rien, les messages de résultat au même verbe, un document en échec supprimable, aucun
bouton pour un document en cours d'indexation, le `409` affiché par `wl-error` pendant un import
(écart ouvert n° 13), un `expected_count` périmé, les réglages (persistés, relus après un
rechargement), le refus d'un changement d'embedding avec son bouton « Vider », axe-core clair et
sombre (dialogue ouvert compris) et 320 px.
"""

from __future__ import annotations

import json
import time

import pytest

from .test_documents import (  # noqa: F401 - `docs` est une fixture
    LONG,
    NBSP,
    URL,
    choose,
    docs,
    script_embedder,
    table_rows,
    txt,
    wait_summary,
)
from .test_shell import assert_no_axe_violations, wait_ready

DIALOG = "dialog.wl-dialog"


def until(page, condition, timeout_s: float = 20.0) -> None:
    """Attend qu'une condition Python devienne vraie ; l'attente passe par Playwright, qui sert
    pendant ce temps les gestionnaires de routes du test."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        page.wait_for_timeout(50)
    pytest.fail("condition jamais vraie")


def import_files(page, *files, summary: str) -> None:
    choose(page, *files)
    wait_summary(page, summary)
    page.locator("wl-data-table tbody tr").first.wait_for()


def status(page) -> str:
    return page.locator(".docs-manage-status").inner_text().strip()


def active_text(page) -> str:
    return page.evaluate("document.activeElement.textContent.trim()")


def api_documents(page, server) -> dict:
    return page.request.get(f"{server.base_url}/api/rag/documents").json()


def open_delete(page, name: str) -> None:
    page.get_by_role("button", name=f"Supprimer {name}").click()
    page.locator(f"{DIALOG}[open]").wait_for()


def fill_base(page) -> None:
    import_files(
        page, txt("notes.txt"), txt("court.md", "Un texte court."), summary="6 extraits ajoutés"
    )


@pytest.fixture
def base2(docs):
    """Une base de deux documents : `notes.txt` (5 extraits) et `court.md` (1 extrait)."""
    page, server = docs
    fill_base(page)
    return page, server


@pytest.fixture
def docs_409(backend, page_tolerating_failed_requests):
    """Comme `docs`, pour les tests qui provoquent un `409` (la console le signale)."""
    page = page_tolerating_failed_requests
    server = backend.start()
    page.goto(f"{server.base_url}/{URL}")
    wait_ready(page)
    page.locator(".docs-empty, .docs-card").first.wait_for()
    return page, server


@pytest.fixture
def base2_409(docs_409):
    page, server = docs_409
    fill_base(page)
    return page, server


# --- Supprimer un document ----------------------------------------------------------------------


def test_each_ready_document_has_a_delete_button_named_after_it(base2):
    page, _ = base2
    page.get_by_role("columnheader", name="Actions").wait_for()
    for name in ("notes.txt", "court.md"):
        assert page.get_by_role("button", name=f"Supprimer {name}").is_visible()
    assert page.locator(".docs-delete").first.inner_text() == "Supprimer"


def test_the_dialog_asks_with_the_numbered_consequence_and_focuses_cancel(base2):
    page, _ = base2
    open_delete(page, "notes.txt")
    assert page.locator(f"{DIALOG} h2").inner_text() == f"Supprimer «{NBSP}notes.txt{NBSP}»{NBSP}?"
    assert page.locator(f"{DIALOG} .wl-dialog-consequence").inner_text() == (
        "5 extraits seront retirés de la base. Cette action est irréversible."
    )
    assert active_text(page) == "Annuler"  # le focus n'est jamais sur l'action destructrice
    labels = page.locator(f"{DIALOG} button").all_inner_texts()
    assert labels == ["Annuler", "Supprimer"]
    assert page.locator(DIALOG).evaluate("d => d.matches(':modal')")  # `showModal`, pas `show`
    # Un document d'un seul extrait : le singulier.
    page.keyboard.press("Escape")
    open_delete(page, "court.md")
    assert page.locator(f"{DIALOG} .wl-dialog-consequence").inner_text() == (
        "1 extrait sera retiré de la base. Cette action est irréversible."
    )


def test_cancel_deletes_nothing_announces_it_and_returns_the_focus(base2):
    page, server = base2
    open_delete(page, "notes.txt")
    page.get_by_role("button", name="Annuler").click()
    page.locator(f"{DIALOG}[open]").wait_for(state="detached")
    assert status(page) == f"Suppression annulée{NBSP}: notes.txt reste dans la base."
    assert page.locator(".docs-manage-status").get_attribute("role") == "status"
    assert len(api_documents(page, server)["documents"]) == 2
    assert page.evaluate("document.activeElement.getAttribute('aria-label')") == (
        "Supprimer notes.txt"
    )


def test_escape_closes_the_dialog_like_cancel(base2):
    page, server = base2
    open_delete(page, "court.md")
    page.keyboard.press("Escape")
    page.locator(f"{DIALOG}[open]").wait_for(state="detached")
    assert status(page).startswith("Suppression annulée")
    assert len(api_documents(page, server)["documents"]) == 2


def test_confirming_deletes_the_document_and_says_how_many_chunks_went(base2):
    page, server = base2
    open_delete(page, "notes.txt")
    page.get_by_role("button", name="Supprimer", exact=True).last.click()
    until(page, lambda: "Document supprimé" in status(page))
    assert status(page) == f"Document supprimé{NBSP}: notes.txt. 5 extraits retirés de la base."
    assert [r[0] for r in table_rows(page)] == ["court.md"]
    listed = api_documents(page, server)
    assert [d["source"] for d in listed["documents"]] == ["court.md"]
    assert listed["totals"] == {"documents": 1, "chunks": 1}
    # Le focus reste dans la liste : le bouton de la ligne suivante.
    assert page.evaluate("document.activeElement.getAttribute('aria-label')") == (
        "Supprimer court.md"
    )


def test_deleting_the_last_document_brings_back_the_empty_base(base2):
    page, _ = base2
    for name in ("notes.txt", "court.md"):
        open_delete(page, name)
        page.locator(f"{DIALOG} .wl-dialog-confirm").click()
        until(page, lambda name=name: name in status(page))
    page.locator(".docs-card").wait_for()
    assert page.locator(".docs-card h2").inner_text() == "Votre base documentaire est vide"
    assert page.locator("wl-data-table").is_hidden()
    assert active_text(page) == "Choisir des fichiers"


def test_a_failed_document_can_be_deleted_and_nothing_is_retired(docs):
    page, server = docs
    choose(page, {"name": "vide.md", "mimeType": "text/markdown", "buffer": b""})
    page.locator("wl-data-table .docs-status[data-status=failed]").wait_for()
    open_delete(page, "vide.md")
    assert page.locator(f"{DIALOG} .wl-dialog-consequence").inner_text() == (
        f"Ce document n'a pas été indexé{NBSP}: aucun extrait n'est retiré."
    )
    page.locator(f"{DIALOG} .wl-dialog-confirm").click()
    until(page, lambda: "Document supprimé" in status(page))
    assert status(page) == (f"Document supprimé{NBSP}: vide.md. Aucun extrait retiré de la base.")
    assert api_documents(page, server)["documents"] == []


def test_a_document_being_indexed_has_no_delete_button(docs):
    page, server = docs
    import_files(page, txt("prete.txt", "Un texte court."), summary="1 extrait ajouté")
    script_embedder(server, page, {"sleep_s": 2})
    choose(page, txt("lente.txt"))
    page.locator("wl-data-table .docs-status[data-status=indexing]").wait_for()
    assert page.get_by_role("button", name="Supprimer prete.txt").is_visible()
    assert page.get_by_role("button", name="Supprimer lente.txt").count() == 0
    wait_summary(page, "5 extraits ajoutés")


# --- Vider la base ------------------------------------------------------------------------------


def test_clear_asks_with_the_numbered_consequence_then_cancel_deletes_nothing(base2):
    page, server = base2
    page.get_by_role("button", name="Vider la base documentaire").first.click()
    page.locator(f"{DIALOG}[open]").wait_for()
    assert page.locator(f"{DIALOG} h2").inner_text() == f"Vider la base documentaire{NBSP}?"
    assert page.locator(f"{DIALOG} .wl-dialog-consequence").inner_text() == (
        "6 extraits de 2 documents seront supprimés."
    )
    assert active_text(page) == "Annuler"
    page.get_by_role("button", name="Annuler").click()
    page.locator(f"{DIALOG}[open]").wait_for(state="detached")
    assert status(page) == (f"Opération annulée{NBSP}: la base documentaire est inchangée.")
    assert api_documents(page, server)["totals"] == {"documents": 2, "chunks": 6}
    assert active_text(page) == "Vider la base documentaire"  # le focus revient au bouton


def test_confirming_clears_the_base_and_says_so_with_the_same_verb(base2):
    page, server = base2
    page.locator(".docs-clear").click()
    page.locator(f"{DIALOG} .wl-dialog-confirm").click()
    until(page, lambda: "vidée" in status(page))
    assert status(page) == (f"Base documentaire vidée{NBSP}: 6 extraits de 2 documents supprimés.")
    page.locator(".docs-card").wait_for()
    listed = api_documents(page, server)
    assert listed["documents"] == [] and listed["totals"] == {"documents": 0, "chunks": 0}
    assert page.get_by_role("button", name="Vider la base documentaire").count() == 0


def test_a_stale_count_is_refused_and_the_base_is_read_again(base2_409):
    page, server = base2_409
    page.locator(".docs-clear").click()
    page.locator(f"{DIALOG}[open]").wait_for()
    # Pendant que la question est posée, un autre onglet ajoute un document : 6 devient 7.
    page.request.post(
        f"{server.base_url}/api/rag/documents",
        multipart={
            "files": {"name": "autre.txt", "mimeType": "text/plain", "buffer": b"Un de plus."}
        },
    )
    until(page, lambda: api_documents(page, server)["totals"]["chunks"] == 7)
    page.locator(f"{DIALOG} .wl-dialog-confirm").click()
    error = page.locator(".wl-error[data-code=base_count_stale]")
    error.wait_for()
    assert "rien n'a été supprimé" in error.inner_text()
    assert api_documents(page, server)["totals"] == {"documents": 3, "chunks": 7}
    until(page, lambda: len(table_rows(page)) == 3)  # le tableau a été relu


def test_clearing_during_an_import_shows_the_409_and_deletes_nothing(docs_409):
    page, server = docs_409
    import_files(page, txt("prete.txt", "Un texte court."), summary="1 extrait ajouté")
    script_embedder(server, page, {"sleep_s": 2})
    choose(page, txt("lente.txt"))
    page.locator("wl-data-table .docs-status[data-status=indexing]").wait_for()
    page.locator(".docs-clear").click()
    page.locator(f"{DIALOG} .wl-dialog-confirm").click()
    error = page.locator(".wl-error[data-code=base_in_use]")
    error.wait_for()
    assert error.locator(".wl-error-message").inner_text() == (
        "Un import ou une question utilise la base documentaire : rien n'a été modifié."
    )
    assert error.locator(".wl-error-action").inner_text()
    assert page.get_by_role("button", name="Supprimer prete.txt").is_visible()
    wait_summary(page, "5 extraits ajoutés")
    assert api_documents(page, server)["totals"]["documents"] == 2


# --- Réglages -----------------------------------------------------------------------------------


def open_settings(page):
    summary = page.locator("details.docs-settings > summary")
    until(page, lambda: summary.inner_text().startswith("Réglages"))  # lus du serveur
    summary.click()
    page.locator("details.docs-settings form").wait_for()


def test_the_settings_summary_and_form_come_from_the_server(docs):
    page, _ = docs
    summary = page.locator("details.docs-settings > summary")
    until(page, lambda: "Réglages" in summary.inner_text())
    assert summary.inner_text() == (
        f"Réglages{NBSP}: représentation Par défaut (le premier modèle installé) · "
        "4 extraits lus · Recherche directe"
    )
    open_settings(page)
    assert page.get_by_label("Taille des extraits (caractères)").input_value() == "800"
    assert page.get_by_label("Nombre d'extraits").input_value() == "4"
    assert page.get_by_label("Stratégie de recherche par défaut").input_value() == "naive"
    assert page.get_by_label("Modèle de représentation").input_value() == ""
    assert page.get_by_label("Nombre d'extraits").get_attribute("max") == "20"


def test_saved_settings_apply_to_the_next_import_and_survive_a_reload(docs):
    page, server = docs
    open_settings(page)
    page.get_by_label("Taille des extraits (caractères)").fill("200")
    page.get_by_label("Nombre d'extraits").fill("2")
    page.get_by_role("button", name="Enregistrer les réglages").click()
    until(page, lambda: "Réglages enregistrés." in status(page))
    summary = page.locator("details.docs-settings > summary")
    assert "2 extraits lus" in summary.inner_text()
    stored = page.request.get(f"{server.base_url}/api/rag/settings").json()
    assert (stored["chunk_size"], stored["top_k"]) == (200, 2)

    page.reload()
    until(page, lambda: "2 extraits lus" in summary.inner_text())
    open_settings(page)
    assert page.get_by_label("Taille des extraits (caractères)").input_value() == "200"
    choose(page, txt("long.txt", LONG))
    page.locator(".docs-summary").filter(has_text="extraits ajoutés depuis 1 document.").wait_for(
        timeout=60_000
    )
    assert "5 extraits ajoutés" not in page.locator(".docs-summary").inner_text()  # 200, pas 800


def test_an_out_of_range_value_is_stopped_by_the_form_before_any_request(docs):
    page, server = docs
    open_settings(page)
    page.get_by_label("Nombre d'extraits").fill("99")
    page.get_by_role("button", name="Enregistrer les réglages").click()
    assert page.get_by_label("Nombre d'extraits").evaluate("e => !e.validity.valid")
    assert page.request.get(f"{server.base_url}/api/rag/settings").json()["top_k"] == 4


def test_a_refused_embedding_change_says_to_clear_first_and_offers_the_button(base2_409):
    page, server = base2_409
    refused = {
        "code": "embedding_change_needs_clear",
        "message": "Changer de modèle d'embedding rendrait inutilisables les extraits déjà "
        "indexés.",
        "action": "Videz d'abord la base documentaire, puis enregistrez le nouveau modèle.",
        "detail": {"technical": None, "current": "fake-embed:16", "requested": "autre:1"},
    }
    calls: list[dict] = []

    def answer(route):
        calls.append(json.loads(route.request.post_data))
        if len(calls) == 1:  # le serveur n'a qu'un modèle ici : la première demande est refusée
            route.fulfill(status=409, content_type="application/json", body=json.dumps(refused))
        else:
            route.continue_()

    page.route(
        "**/api/rag/settings", lambda r: answer(r) if r.request.method == "PUT" else r.continue_()
    )
    open_settings(page)
    page.get_by_label("Modèle de représentation").select_option("")  # change par rapport à la base
    page.get_by_role("button", name="Enregistrer les réglages").click()
    error = page.locator("details.docs-settings .wl-error")
    error.wait_for()
    assert "rendrait inutilisables" in error.inner_text()
    clear = page.locator("details.docs-settings").get_by_role(
        "button", name="Vider la base documentaire"
    )
    assert clear.is_visible()
    assert api_documents(page, server)["totals"]["documents"] == 2  # rien n'a été supprimé
    clear.click()
    page.locator(f"{DIALOG}[open]").wait_for()
    assert (
        "6 extraits de 2 documents" in page.locator(f"{DIALOG} .wl-dialog-consequence").inner_text()
    )
    page.locator(f"{DIALOG} .wl-dialog-confirm").click()
    until(page, lambda: "vidée" in status(page))
    until(page, lambda: len(calls) == 2)  # le réglage refusé est rejoué sur la base vide
    until(page, lambda: status(page).endswith("Réglages enregistrés."))
    assert status(page) == (
        f"Base documentaire vidée{NBSP}: 6 extraits de 2 documents supprimés. "
        "Réglages enregistrés."
    )
    assert calls[0] == calls[1] == {"embedding_model": None}
    assert api_documents(page, server)["documents"] == []


# --- Charte et accessibilité --------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_nothing_with_the_delete_buttons_the_dialog_and_the_settings(base2, theme):
    page, _ = base2
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    open_settings(page)
    assert_no_axe_violations(page, f"tableau, réglages ouverts, thème {theme}")
    open_delete(page, "notes.txt")
    assert_no_axe_violations(page, f"dialogue de suppression, thème {theme}")
    page.keyboard.press("Escape")
    page.locator(".docs-clear").click()
    page.locator(f"{DIALOG}[open]").wait_for()
    assert_no_axe_violations(page, f"dialogue « Vider », thème {theme}")


def test_the_dialog_and_the_screen_fit_a_phone_width(base2):
    page, _ = base2
    page.set_viewport_size({"width": 320, "height": 800})

    def overflow() -> int:
        return page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )

    open_settings(page)
    assert overflow() <= 0
    open_delete(page, "notes.txt")
    assert overflow() <= 0
    box = page.locator(DIALOG).bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 320
    assert_no_axe_violations(page, "320 px, dialogue ouvert")
