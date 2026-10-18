"""Écran Base documentaire (story 4.2) dans un vrai navigateur, sur le vrai serveur.

L'indexation est réelle (extraction, découpe, base sqlite-vec) ; seul l'embedding est le `fake`
scriptable du mode test (`POST /api/test/embedder` règle ses pauses et ses pannes), Ollama n'est
jamais sollicité. Chaque test a son serveur (fixture `backend`) : la base commence vide.
Prouvés ici : la zone de dépôt sans serveur, l'état vide, la progression par fichier, l'échec
avec « Détails techniques », la fin annoncée, le tableau (tri au clavier, `indexing` pas prêt), le
retour sur l'écran et le rechargement pendant un import, l'annulation, le 409, les plafonds, axe-core
clair et sombre.
"""

from __future__ import annotations

import json
import re

import pytest
from axe_playwright_python.sync_playwright import Axe

from ..rag_files import make_blank_pdf, make_docx
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
LONG = " ".join(f"phrase{i:03d}" for i in range(300))  # 5 extraits
DROP_LINE = "Déposez des fichiers ici ou Choisir des fichiers · PDF, TXT, MD, DOCX"
URL = "#/documents/base"


def txt(name: str, text: str = LONG) -> dict:
    return {"name": name, "mimeType": "text/plain", "buffer": text.encode()}


def script_embedder(server, page, *steps) -> None:
    response = page.request.post(
        f"{server.base_url}/api/test/embedder", data={"script": list(steps)}
    )
    assert response.ok, response.text()


@pytest.fixture
def docs(backend, page):
    server = backend.start()
    page.goto(f"{server.base_url}/{URL}")
    wait_ready(page)
    page.locator(".docs-empty, .docs-card").first.wait_for()
    return page, server


def choose(page, *files) -> None:
    page.set_input_files("input.docs-file-input", list(files))


def summary(page) -> str:
    return page.locator(".docs-summary").inner_text().strip()


def wait_summary(page, text: str) -> None:
    page.locator(".docs-summary").filter(has_text=text).wait_for(timeout=60_000)


def row(page, name: str):
    return page.locator(".docs-import").filter(has=page.locator(".docs-import-name", has_text=name))


def table_rows(page) -> list[list[str]]:
    return page.evaluate(
        """() => [...document.querySelectorAll('wl-data-table tbody tr')]
            .map((tr) => [...tr.children].map((cell) => cell.innerText.trim()))"""
    )


# --- Écran : zone de dépôt, état vide, onglets -------------------------------------------------


def test_the_drop_zone_is_visible_before_the_server_answers_and_the_base_is_empty_afterwards(
    backend, page
):
    server = backend.start()
    held = []
    page.route(re.compile(r"/api/rag/documents$"), lambda route: held.append(route))
    page.goto(f"{server.base_url}/{URL}")
    wait_ready(page)
    page.locator(".docs-drop").wait_for()
    assert page.locator(".docs-drop-line").inner_text() == DROP_LINE
    assert page.get_by_text("Chargement de la base documentaire…").is_visible()
    assert page.locator(".docs-card").is_hidden()  # pas de « base vide » avant la réponse
    assert page.title() == "Base documentaire · WaveLocalAI"

    while not held:
        page.wait_for_timeout(20)
    held[0].continue_()
    page.locator(".docs-card").wait_for()
    assert page.locator(".docs-card h2").inner_text() == "Votre base documentaire est vide"
    assert page.get_by_role("button", name="Importer des documents").is_enabled()
    assert (
        page.locator("wl-data-table").is_hidden()
        or page.locator("wl-data-table table").count() == 0
    )
    # Les plafonds viennent du serveur, sous la zone.
    assert page.locator(".docs-drop .help").first.inner_text() == (
        f"50{NBSP}Mo au plus par fichier{NBSP}; 50 fichiers et 500{NBSP}Mo au plus par import."
    )


def test_the_module_tabs_name_the_screen_and_disable_the_others_with_their_reason(docs):
    page, _ = docs
    tabs = page.locator("nav.screen-tabs")
    assert (
        tabs.get_by_role("link", name="Base documentaire").get_attribute("aria-current") == "page"
    )
    for name in ("Discussion", "Évaluation de la qualité"):
        link = tabs.get_by_role("link", name=name)
        assert link.get_attribute("aria-disabled") == "true" and link.get_attribute("href") is None
        reason = link.evaluate(
            "el => document.getElementById(el.getAttribute('aria-describedby')).innerText"
        )
        assert reason == "Pas encore disponible dans cette préversion"


def test_both_import_buttons_open_the_file_chooser(docs):
    page, _ = docs
    for name in ("Choisir des fichiers", "Importer des documents"):
        with page.expect_file_chooser() as chooser:
            page.get_by_role("button", name=name).click()
        assert chooser.value.is_multiple()


# --- Import : progression, réussite, échec -------------------------------------------------------


def test_each_file_has_its_line_with_the_vectorisation_progress_then_a_summary(docs):
    page, server = docs
    script_embedder(server, page, {"sleep_s": 1.5})
    choose(page, txt("notes.txt"), txt("autre.md", "Un autre texte court."))
    line = row(page, "notes.txt")
    line.locator(".docs-import-state").filter(has_text="Vectorisation 0/5 extraits").wait_for()
    assert line.locator(".docs-import-state").inner_text() == (
        "Envoi 100 % · Découpage · Vectorisation 0/5 extraits".replace(" %", f"{NBSP}%")
    )
    assert page.get_by_role("button", name="Annuler l'import").is_visible()
    assert (
        page.get_by_role("button", name="Annuler l'import").count() == 1
    )  # un seul, pas par ligne
    assert line.get_by_role("button").count() == 0
    assert line.locator("progress").is_visible()
    assert page.get_by_role("heading", name="Fichiers de cet import").is_visible()
    # Le second fichier attend son tour, puis est lu à son tour.
    assert "En attente" in row(page, "autre.md").locator(".docs-import-state").inner_text()

    wait_summary(page, "6 extraits ajoutés depuis 2 documents.")
    assert line.locator(".docs-import-state").inner_text() == "5 extraits ajoutés"
    assert row(page, "autre.md").locator(".docs-import-state").inner_text() == "1 extrait ajouté"
    assert line.get_by_role("button").count() == 0 or not line.get_by_role("button").is_visible()
    assert page.get_by_role("status").filter(has_text="6 extraits ajoutés").count() >= 1
    assert page.locator(".docs-card").is_hidden()
    assert page.locator("wl-data-table .docs-status[data-status=ready]").count() == 2
    assert page.locator(".docs-count").last.inner_text() == "2 documents prêts · 6 extraits"
    # Le champ de fichiers est vidé : le même fichier peut être choisi de nouveau.
    assert page.eval_on_selector("input.docs-file-input", "el => el.value") == ""


def test_an_indexing_document_is_never_shown_as_ready(docs):
    page, server = docs
    script_embedder(server, page, {"sleep_s": 1.5})
    choose(page, txt("lent.txt"))
    cell = page.locator("wl-data-table .docs-status[data-status=indexing]")
    cell.wait_for()
    assert cell.inner_text() == "Indexation en cours"
    assert page.locator("wl-data-table .docs-status[data-status=ready]").count() == 0
    assert (
        page.locator("wl-data-table tbody tr").first.locator("td").nth(0).inner_text() == "en cours"
    )
    assert page.locator(".docs-count").last.inner_text() == "0 document prêt · 0 extrait"
    wait_summary(page, "5 extraits ajoutés depuis 1 document.")
    page.locator("wl-data-table .docs-status[data-status=ready]").wait_for()


def test_a_failed_file_says_why_with_the_technical_details_folded_and_the_others_continue(docs):
    page, _ = docs
    choose(
        page,
        {"name": "vide.md", "mimeType": "text/markdown", "buffer": b""},
        {"name": "secret.pdf", "mimeType": "application/pdf", "buffer": make_blank_pdf("mdp")},
        txt("bon.txt", "Un texte qui passe."),
    )
    wait_summary(page, "1 extrait ajouté depuis 1 document. 2 fichiers n'ont pas pu être indexés.")
    empty = row(page, "vide.md")
    assert empty.locator("wl-error .wl-error-message").inner_text() == (
        f"Le fichier n'a pas pu être indexé{NBSP}: le fichier est vide."
    )
    assert empty.locator("wl-error .wl-error-action").inner_text()
    protected = row(page, "secret.pdf")
    assert "mot de passe" in protected.locator("wl-error .wl-error-message").inner_text()
    assert row(page, "bon.txt").locator(".docs-import-state").inner_text() == "1 extrait ajouté"
    # Un fichier en échec n'est jamais compté parmi les documents prêts.
    assert page.locator(".docs-count").last.inner_text() == "1 document prêt · 1 extrait"
    failed = page.locator("wl-data-table .docs-status[data-status=failed]")
    assert failed.count() == 2
    assert (
        "le fichier est vide" in failed.first.inner_text()
        or "mot de passe" in failed.first.inner_text()
    )
    # Les détails techniques sont repliés quand ils disent autre chose que la raison.
    details = protected.locator("wl-error details")
    if details.count():
        assert details.get_attribute("open") is None


def test_a_content_already_in_the_base_is_not_indexed_twice(docs):
    page, _ = docs
    choose(page, txt("a.txt"))
    wait_summary(page, "5 extraits ajoutés depuis 1 document.")
    choose(page, txt("copie.txt"))  # même contenu, autre nom
    row(page, "copie.txt").locator(".docs-import-state").filter(has_text="Déjà indexé").wait_for()
    wait_for(page, "() => !document.querySelector('.docs-import-progress:not([hidden])')")
    wait_summary(page, "1 fichier était déjà dans la base.")  # la fin est annoncée quand même
    assert len(table_rows(page)) == 1


def test_an_unreachable_embedding_model_fails_the_file_with_its_reason(docs):
    page, server = docs
    script_embedder(server, page, {"fail": "ollama_down"})
    choose(page, txt("a.txt"))
    wait_summary(page, "1 fichier n'a pas pu être indexé.")
    assert (
        "Le fichier n'a pas pu être indexé" in row(page, "a.txt").locator("wl-error").inner_text()
    )
    assert page.locator("wl-data-table .docs-status[data-status=failed]").count() == 1


# --- Annulation, retour sur l'écran, rechargement, 409 --------------------------------------------


def test_cancelling_stops_the_import_and_removes_the_document_in_progress(docs):
    page, server = docs
    script_embedder(server, page, {"sleep_s": 30})
    choose(page, txt("a.txt"), txt("b.txt", "Un autre."))
    row(page, "a.txt").locator(".docs-import-state").filter(has_text="Vectorisation 0/5").wait_for()
    page.get_by_role("button", name="Annuler l'import").click()
    wait_summary(page, "Import annulé. Les documents déjà indexés sont conservés.")
    for name in ("a.txt", "b.txt"):
        assert row(page, name).locator(".docs-import-state").inner_text() == "Annulé"
    page.locator(".docs-card").wait_for()  # rien n'a été gardé : la base est vide de nouveau
    assert page.get_by_role("button", name="Choisir des fichiers").is_enabled()


def test_the_single_cancel_button_sits_above_the_rows_and_only_shows_during_an_import(docs):
    page, server = docs
    cancel = page.get_by_role("button", name="Annuler l'import")
    assert page.locator(".docs-imports-cancel").is_hidden()  # rien à annuler au repos
    script_embedder(server, page, {"sleep_s": 1.5})
    choose(page, txt("a.txt"), txt("b.txt", "Un autre."))
    row(page, "a.txt").locator(".docs-import-state").filter(has_text="Vectorisation 0/5").wait_for()
    assert cancel.is_visible()
    above = page.evaluate(
        """() => {
          const button = document.querySelector('.docs-imports-cancel').getBoundingClientRect();
          const list = document.querySelector('.docs-imports').getBoundingClientRect();
          return button.bottom <= list.top;
        }"""
    )
    assert above
    wait_summary(page, "6 extraits ajoutés depuis 2 documents.")
    assert not cancel.is_visible()  # le lot est fini
    assert page.evaluate("document.activeElement === document.body") is True


def test_cancelling_keeps_the_documents_that_are_already_ready(docs):
    page, server = docs
    choose(page, txt("prete.txt"))
    wait_summary(page, "5 extraits ajoutés depuis 1 document.")
    script_embedder(server, page, {"sleep_s": 30})
    choose(page, txt("lente.txt", LONG + " fin"))
    row(page, "lente.txt").locator(".docs-import-state").filter(
        has_text="Vectorisation 0/"
    ).wait_for()
    page.get_by_role("button", name="Annuler l'import").click()
    wait_summary(page, "Import annulé. Les documents déjà indexés sont conservés.")
    wait_for(page, "() => document.querySelectorAll('wl-data-table tbody tr').length === 1")
    assert [r[0] for r in table_rows(page)] == ["prete.txt"]
    assert page.locator(".docs-section .docs-count").inner_text() == "1 document prêt · 5 extraits"


def test_cancelling_during_the_upload_sends_nothing_to_the_run(docs):
    page, server = docs
    page.route(
        re.compile(r"/api/rag/documents$"),
        lambda route: None if route.request.method == "POST" else route.fallback(),
    )  # l'envoi reste en attente : on peut l'annuler
    choose(page, txt("a.txt"))
    line = row(page, "a.txt")
    line.locator(".docs-import-state").filter(has_text="Envoi").wait_for()
    page.get_by_role("button", name="Annuler l'import").click()
    wait_summary(page, "Import annulé.")
    assert line.locator(".docs-import-state").inner_text() == "Annulé"
    runs = json.loads(page.request.get(f"{server.base_url}/api/rag/documents").text())
    assert runs["documents"] == []


def test_cancelling_once_the_files_are_sent_stops_the_run_the_server_started(docs):
    # Le corps est parti, le serveur a créé le run, la réponse n'est pas encore traitée : Annuler
    # ne peut plus abandonner la requête (le run indexerait quand même), il arrête le run. La
    # réponse est retenue dans la page (le `load` de la requête attend), pas dans le réseau : une
    # interception Playwright couperait la progression d'envoi.
    page, server = docs
    script_embedder(server, page, {"sleep_s": 30})
    page.evaluate(
        """() => {
          window.__hold = new Promise((resolve) => { window.__release = resolve; });
          const base = Object.getOwnPropertyDescriptor(XMLHttpRequestEventTarget.prototype, "onload");
          Object.defineProperty(XMLHttpRequest.prototype, "onload", {
            configurable: true,
            get() { return base.get.call(this); },
            set(handler) {
              base.set.call(this, handler && ((event) => window.__hold.then(() => handler.call(this, event))));
            },
          });
        }"""
    )
    choose(page, txt("a.txt"), txt("b.txt", "Un autre."))
    line = row(page, "a.txt")
    line.locator(".docs-import-state").filter(has_text="Envoi 100").wait_for()
    listed = f"{server.base_url}/api/rag/documents"
    for _ in range(200):  # le serveur a répondu : le run indexe le premier fichier
        documents = page.request.get(listed).json()["documents"]
        if documents:
            break
        page.wait_for_timeout(50)
    assert documents and documents[0]["status"] == "indexing"
    run_id = documents[0]["run_id"]
    page.get_by_role("button", name="Annuler l'import").click()
    page.evaluate("window.__release()")
    wait_summary(page, "Import annulé. Les documents déjà indexés sont conservés.")
    for name in ("a.txt", "b.txt"):
        assert row(page, name).locator(".docs-import-state").inner_text() == "Annulé"
    page.locator(".docs-card").wait_for()  # le run a été arrêté : rien n'est gardé
    assert page.request.get(f"{server.base_url}/api/runs/{run_id}").json()["status"] == "cancelled"


def test_leaving_the_screen_during_an_import_and_coming_back_resumes_the_progress(docs):
    page, server = docs
    script_embedder(server, page, {"sleep_s": 2.5})
    choose(page, txt("a.txt"))
    row(page, "a.txt").locator(".docs-import-state").filter(has_text="Vectorisation 0/5").wait_for()
    page.evaluate("location.hash = '#/'")
    page.locator('[data-screen="home"]').wait_for(state="visible")
    assert page.locator('[data-screen="documents-base"]').is_hidden()
    page.evaluate("location.hash = '#/documents/base'")
    page.locator('[data-screen="documents-base"]').wait_for(state="visible")
    wait_summary(page, "5 extraits ajoutés depuis 1 document.")
    assert row(page, "a.txt").locator(".docs-import-state").inner_text() == "5 extraits ajoutés"
    assert page.locator("wl-data-table .docs-status[data-status=ready]").count() == 1


def test_reloading_the_page_during_an_import_rejoins_it(docs):
    page, server = docs
    script_embedder(server, page, {"sleep_s": 2.5})
    choose(page, txt("a.txt"))
    row(page, "a.txt").locator(".docs-import-state").filter(has_text="Vectorisation 0/5").wait_for()
    page.reload()
    wait_ready(page)
    line = row(page, "a.txt")
    line.wait_for()
    assert page.get_by_role("button", name="Choisir des fichiers").is_disabled()
    wait_summary(page, "5 extraits ajoutés depuis 1 document.")
    assert page.get_by_role("button", name="Choisir des fichiers").is_enabled()


def test_a_second_import_joins_the_running_one_without_an_error(
    backend, page_tolerating_failed_requests
):
    page = page_tolerating_failed_requests
    server = backend.start()
    page.goto(f"{server.base_url}/{URL}")
    wait_ready(page)
    page.locator(".docs-card").wait_for()
    script_embedder(server, page, {"sleep_s": 2.5})
    started = page.request.post(
        f"{server.base_url}/api/rag/documents",
        multipart={
            "files": {"name": "dehors.txt", "mimeType": "text/plain", "buffer": LONG.encode()}
        },
    )
    assert started.ok
    choose(page, txt("ici.txt", "Autre contenu."))  # 409 run_busy : le run actif est rejoint
    page.get_by_text("Un import est déjà en cours").wait_for()
    assert page.locator("wl-error").filter(has_text="run").count() == 0
    wait_summary(page, "5 extraits ajoutés depuis 1 document.")
    assert row(page, "dehors.txt").count() == 1 and row(page, "ici.txt").count() == 0


# --- Plafonds ------------------------------------------------------------------------------------


def test_too_many_files_are_refused_before_anything_is_sent(docs):
    page, _ = docs
    posts = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    choose(page, *[txt(f"f{i}.txt", f"texte {i}") for i in range(51)])
    page.locator("wl-error").filter(
        has_text=f"Trop de fichiers{NBSP}: 50 au plus par import."
    ).wait_for()
    assert page.locator(".docs-import").count() == 0 and posts == []
    assert page.get_by_role("button", name="Choisir des fichiers").is_enabled()


# --- Tableau -------------------------------------------------------------------------------------


def test_the_table_lists_name_chunks_date_model_and_status_and_sorts_from_the_keyboard(docs):
    page, _ = docs
    choose(page, txt("b.txt", "Bravo " * 10), txt("a.txt", LONG), txt("c.txt", "Charlie " * 10))
    wait_summary(page, "7 extraits ajoutés depuis 3 documents.")
    headers = page.locator("wl-data-table thead th").all_inner_texts()
    assert [h.strip() for h in headers] == [
        "Nom", "Extraits", "Ajouté le", "Modèle de représentation", "Statut",
    ]  # fmt: skip
    first = table_rows(page)[0]
    assert re.fullmatch(r"\d{1,2} [^\s]+ \d{4}", first[2]), first  # date fr-FR, jamais ISO
    assert first[3] == "fake-embed:16" and first[4] == "Prêt"
    assert page.locator("wl-data-table table").get_attribute("class") == "wl-table"
    assert page.locator("wl-data-table th[scope=col]").count() == 5
    assert page.locator("wl-data-table tbody th[scope=row]").count() == 3

    name = page.locator("wl-data-table .wl-table-sort[data-key=source]")
    name.focus()
    page.keyboard.press("Enter")
    assert [r[0] for r in table_rows(page)] == ["a.txt", "b.txt", "c.txt"]
    header = page.locator("wl-data-table th").first
    assert header.get_attribute("aria-sort") == "ascending"
    assert page.evaluate("document.activeElement.dataset.key") == "source"  # le focus reste
    page.keyboard.press("Space")
    assert [r[0] for r in table_rows(page)] == ["c.txt", "b.txt", "a.txt"]
    assert header.get_attribute("aria-sort") == "descending"
    assert "ordre décroissant" in page.locator("wl-data-table [role=status]").inner_text()
    page.locator("wl-data-table .wl-table-sort[data-key=chunks]").click()
    assert table_rows(page)[0][0] in ("b.txt", "c.txt")  # 1 extrait avant 3
    assert table_rows(page)[-1][0] == "a.txt"
    assert header.get_attribute("aria-sort") == "none"


def test_a_sort_header_keeps_the_focus_while_an_import_updates_the_table(docs):
    page, server = docs
    choose(page, txt("a.txt"))
    wait_summary(page, "5 extraits ajoutés depuis 1 document.")
    script_embedder(server, page, {"sleep_s": 1.5})
    page.locator("wl-data-table .wl-table-sort[data-key=source]").focus()
    choose(page, txt("b.txt", "Un autre."))
    wait_for(page, "() => document.querySelectorAll('wl-data-table tbody tr').length === 2")
    assert page.evaluate("document.activeElement.dataset.key") == "source"  # tableau reconstruit
    wait_summary(page, "1 extrait ajouté depuis 1 document.")
    assert page.evaluate("document.activeElement.dataset.key") == "source"


def test_a_failed_document_keeps_its_reason_in_the_table_after_a_reload(docs):
    page, server = docs
    choose(page, {"name": "vide.md", "mimeType": "text/markdown", "buffer": b""})
    wait_summary(page, "1 fichier n'a pas pu être indexé.")
    page.reload()
    wait_ready(page)
    cell = page.locator("wl-data-table .docs-status[data-status=failed]")
    cell.wait_for()
    assert cell.inner_text().replace("\n", " ") == "Échec le fichier est vide"
    assert page.locator(".docs-import").count() == 0  # le suivi d'un import fini n'est pas rejoué


def test_a_failed_document_is_in_the_table_but_not_in_the_ready_count(docs):
    page, server = docs
    choose(page, txt("bon.txt"), {"name": "vide.md", "mimeType": "text/markdown", "buffer": b""})
    wait_summary(page, "5 extraits ajoutés depuis 1 document. 1 fichier n'a pas pu être indexé.")
    for _ in range(2):  # puis après un rechargement
        wait_for(page, "() => document.querySelectorAll('wl-data-table tbody tr').length === 2")
        statuses = {r[0]: r[-1].replace("\n", " ") for r in table_rows(page)}
        assert statuses == {"bon.txt": "Prêt", "vide.md": "Échec le fichier est vide"}
        assert (
            page.locator(".docs-section .docs-count").inner_text() == "1 document prêt · 5 extraits"
        )
        assert page.locator("wl-data-table button").filter(has_text="Supprimer").count() == 0
        page.reload()
        wait_ready(page)


# --- Charte et accessibilité ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("theme", "fill"), [("light", "rgb(69, 29, 199)"), ("dark", "rgb(106, 77, 230)")]
)
def test_the_filled_button_uses_primary_fill_with_white_text(docs, theme, fill):
    page, _ = docs
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    style = page.get_by_role("button", name="Importer des documents").evaluate(
        "n => { const s = getComputedStyle(n); return [s.backgroundColor, s.color]; }"
    )
    assert style == [fill, "rgb(255, 255, 255)"]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_nothing_on_the_empty_screen_the_import_and_the_table(docs, theme):
    page, server = docs
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(page, f"écran vide, thème {theme}")

    script_embedder(server, page, {"sleep_s": 1.5})
    choose(page, txt("a.txt"), {"name": "vide.md", "mimeType": "text/markdown", "buffer": b""})
    row(page, "a.txt").locator(".docs-import-state").filter(has_text="Vectorisation 0/5").wait_for()
    assert_no_axe_violations(page, f"import en cours, thème {theme}")

    wait_summary(page, "5 extraits ajoutés depuis 1 document.")
    assert_no_axe_violations(page, f"import terminé et tableau, thème {theme}")


def test_the_screen_fits_a_phone_width_without_horizontal_scroll(docs):
    page, server = docs
    page.set_viewport_size({"width": 320, "height": 800})

    def overflow() -> int:
        return page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )

    script_embedder(server, page, {"sleep_s": 1.5})
    long_name = "un-nom-de-fichier-vraiment-tres-long-pour-le-test-de-largeur.txt"
    choose(page, txt(long_name), {"name": "vide.md", "mimeType": "text/markdown", "buffer": b""})
    page.get_by_role("button", name="Annuler l'import").wait_for()
    assert overflow() <= 0  # import en cours, bouton d'annulation compris
    assert Axe().run(page).violations_count == 0
    wait_summary(page, "5 extraits ajoutés depuis 1 document. 1 fichier n'a pas pu être indexé.")
    page.locator("wl-data-table .docs-status[data-status=failed]").wait_for()
    assert overflow() <= 0  # tableau avec un document en échec
    assert Axe().run(page).violations_count == 0


def test_a_docx_file_is_indexed_from_the_screen(docs):
    page, _ = docs
    choose(
        page,
        {
            "name": "note.docx",
            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "buffer": make_docx(["Une note de cadrage.", "Deuxième paragraphe."]),
        },
    )
    wait_summary(page, "1 extrait ajouté depuis 1 document.")
