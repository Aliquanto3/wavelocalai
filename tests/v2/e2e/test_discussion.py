"""Écran Discussion (story 4.5) dans un vrai navigateur, sur le vrai serveur.

L'indexation, la recherche, les sources, le flux et les mesures sont réels (extraction, découpe,
base sqlite-vec, `POST /api/rag/runs`) ; seuls l'embedding et le modèle de réponse sont les `fake`
scriptables du mode test (`POST /api/test/embedder`, `POST /api/test/chat-model`). La liste des
modèles est simulée par le test (`page.route`). Ollama n'est jamais sollicité, aucune requête ne
sort de 127.0.0.1 (fixture `context`).

Prouvés ici : l'état vide, l'en-tête et les réglages repliés, « Recherche des extraits… » puis
« Génération… », les sources avant la réponse, le passage surligné (emoji compris), « extrait
supprimé » (à l'ouverture et à la réouverture), « Afficher les sources » dès la deuxième réponse, le
panneau toujours ouvert dès 1 024 px et replié sous la réponse en deçà, la reprise par `?after=`,
l'avertissement du cloud, axe-core clair et sombre à 1 440, 1 024 et 320 px.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time

import pytest

from ..rag_files import make_pdf
from .test_chat import MODEL, REASON, install_models
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
URL = "#/documents"
QUESTION = "Où dort le chat domestique ?"
PASSAGE = "Le chat domestique dort sur le canapé du salon."
# L'emoji est avant le passage : ses positions sont en points de code, pas en unités UTF-16.
CATS = f"Un 🐈 passe. {PASSAGE} Il ronronne quand on le caresse."
CARS = "La voiture électrique recharge sa batterie. L'autonomie dépend de la vitesse."
ANSWER = [{"text": "Le chat dort"}, {"text": " sur le canapé [1]."}]
CLOUD = {**MODEL, "tag": "nuage:1", "name": "Nuage 1", "origin": "cloud", "provider": "openai"}


def post(page, server, path, **kwargs):
    response = page.request.post(f"{server.base_url}{path}", **kwargs)
    assert response.ok, response.text()
    return response.json()


def run_status(page, server, run_id) -> str:
    return page.request.get(f"{server.base_url}/api/runs/{run_id}").json()["status"]


def wait_run(page, server, run_id) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if run_status(page, server, run_id) != "running":
            return
        time.sleep(0.05)
    pytest.fail("le run ne se termine pas")


def import_docs(page, server, **docs) -> None:
    """Un import par document (le serveur n'en accepte qu'un à la fois), attendu jusqu'au bout."""
    for name, (mime, data) in docs.items():
        started = post(
            page,
            server,
            "/api/rag/documents",
            multipart={"files": {"name": name, "mimeType": mime, "buffer": data}},
        )
        wait_run(page, server, started["run_id"])


def script_model(page, server, *steps) -> None:
    post(page, server, "/api/test/chat-model", data={"script": list(steps)})


def delete_document(backend, source: str) -> None:
    """Retire le document comme le ferait « Supprimer » (5.x) : extraits et ligne, sans le serveur."""
    with sqlite3.connect(backend.data_dir / "wavelocalai.db", timeout=10) as conn:
        conn.execute(
            "DELETE FROM chunks WHERE document_id IN (SELECT id FROM documents WHERE source = ?)",
            (source,),
        )
        conn.execute("DELETE FROM documents WHERE source = ?", (source,))


def txt(text: str) -> tuple[str, bytes]:
    return "text/plain", text.encode()


def prepared(backend, page):
    """Une base de trois documents (deux TXT et un PDF d'une page), l'écran ouvert et prêt."""
    server = backend.start()
    install_models(page)
    import_docs(
        page,
        server,
        **{
            "chats.txt": txt(CATS),
            "voitures.txt": txt(CARS),
            "nuit.pdf": ("application/pdf", make_pdf(["La nuit le chat chasse les souris."])),
        },
    )
    script_model(page, server, *ANSWER)
    open_screen(page, server)
    return page, server, backend


@pytest.fixture
def docs(backend, page):
    return prepared(backend, page)


@pytest.fixture
def docs_lenient(backend, page_tolerating_failed_requests):
    """Comme `docs`, pour un test dont la commande échoue exprès (409 : le navigateur le dit)."""
    return prepared(backend, page_tolerating_failed_requests)


def open_screen(page, server) -> None:
    page.goto(f"{server.base_url}/{URL}")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    wait_restored(page)


def reload_screen(page) -> None:
    page.reload()
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    wait_restored(page)


def wait_restored(page) -> None:
    """La conversation d'avant est relue : un run lancé ensuite n'est plus pris pour elle."""
    wait_for(
        page, "() => document.querySelector(\"[data-screen='documents-chat'][data-restored]\")"
    )


def field(page):
    return page.get_by_label("Posez une question à vos documents")


def ask(page, text=QUESTION) -> None:
    field(page).fill(text)
    field(page).press("Enter")


def stage(page) -> str:
    return page.locator("[data-screen='documents-chat'] .wl-run-stage").inner_text()


def wait_done(page, count=1) -> None:
    wait_for(
        page,
        "() => [...document.querySelectorAll(\"[data-screen='documents-chat'] .wl-msg-assistant\")]"
        f".length >= {count} && document.querySelector(\"[data-screen='documents-chat'] "
        "wl-run-status\")?.dataset.stage === 'ok'",
        timeout_s=30,
    )


def sources(page):
    return page.locator("[data-screen='documents-chat'] .wl-source")


def metric(foot, label):
    return foot.locator("wl-metric").filter(
        has=foot.page.locator(".wl-metric-label", has_text=re.compile(f"^{label}$"))
    )


def source_of(page, document):
    return sources(page).filter(has=page.locator(".wl-source-doc", has_text=document))


# --- Écran : état vide, en-tête, réglages ------------------------------------------------------


def test_an_empty_base_leads_to_the_document_base(backend, page):
    server = backend.start()
    install_models(page)
    page.goto(f"{server.base_url}/{URL}")
    wait_ready(page)
    card = page.locator("[data-screen='documents-chat'] .docs-card")
    card.wait_for()
    assert card.locator("h2").inner_text() == "Votre base documentaire est vide"
    link = card.get_by_role("link", name="Importer des documents")
    assert link.get_attribute("href") == "#/documents/base"
    assert page.locator(".docs-chat-workspace").is_hidden()
    link.click()
    wait_for(page, "() => location.hash === '#/documents/base'")


def test_the_header_the_model_and_the_collapsed_settings(docs):
    page, _, _ = docs
    assert page.title() == "Discussion · WaveLocalAI"
    assert page.locator("h1").filter(has_text="Discussion").is_visible()
    tabs = page.locator("[data-screen='documents-chat'] nav.screen-tabs")
    assert tabs.get_by_role("link", name="Discussion").get_attribute("aria-current") == "page"
    summary = page.locator("[data-screen='documents-chat'] .docs-chat-summary")
    assert summary.locator(".docs-chat-count").inner_text() == "3 documents · 3 extraits"
    assert (
        summary.get_by_role("link", name="Gérer la base documentaire").get_attribute("href")
        == "#/documents/base"
    )
    assert field(page).is_visible()
    assert page.get_by_text(REASON).is_visible()
    advanced = page.locator("[data-screen='documents-chat'] details.docs-advanced")
    assert advanced.get_attribute("open") is None
    advanced.locator("summary").click()
    options = advanced.locator("select option")
    assert options.all_inner_texts() == ["Recherche directe"]
    assert "naive" in advanced.locator(".help").inner_text()


def test_a_cloud_model_warns_that_the_extracts_leave_the_machine(backend, page):
    server = backend.start()
    install_models(page)
    import_docs(page, server, **{"chats.txt": txt(CATS)})
    page.route(
        re.compile(r"/api/models\?"),
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "models": [
                        MODEL,
                        *([CLOUD] if "allow_cloud=true" in route.request.url else []),
                    ],
                    "ollama_up": True,
                    "refreshed_at": "2026-10-19T10:00:00Z",
                }
            ),
        ),
    )
    open_screen(page, server)
    note = page.locator("[data-screen='documents-chat'] .docs-cloud-note")
    assert note.is_hidden()
    page.get_by_label("Autoriser le cloud").check()
    page.locator("[data-screen='documents-chat'] .wl-picker-input").click()
    page.get_by_role("option", name=re.compile("Nuage 1")).click()
    note.wait_for()
    assert note.inner_text().strip() == (
        f"Nuage 1 est un modèle cloud{NBSP}: les extraits retrouvés dans vos documents lui sont "
        "envoyés, hors de ce poste."
    )
    page.locator("[data-screen='documents-chat'] .wl-picker-input").click()
    page.get_by_role("option", name=re.compile("Factice 1B")).click()
    note.wait_for(state="hidden")


def test_a_reopened_conversation_with_a_cloud_model_warns_too(backend, page):
    """Le modèle de la conversation rouverte est posé sans `wl-model-change` : l'avertissement du
    cloud (AD-9) doit apparaître quand même, alors que le modèle par défaut est local."""
    server = backend.start()
    import_docs(page, server, **{"chats.txt": txt(CATS)})
    script_model(page, server, *ANSWER)
    started = post(
        page,
        server,
        "/api/rag/runs",
        data={"question": QUESTION, "model": "fake:1b", "strategy": "naive"},
    )
    wait_run(page, server, started["run_id"])
    local = {**MODEL, "tag": "local:1b", "name": "Local 1B"}
    as_cloud = {**MODEL, "origin": "cloud", "provider": "openai"}  # le front le croit cloud

    def on_models(route):
        listed = [local, *([as_cloud] if "allow_cloud=true" in route.request.url else [])]
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"models": listed, "ollama_up": True, "refreshed_at": "2026-10-19T10:00:00Z"}
            ),
        )

    def on_defaults(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"purpose": "rag", "tags": ["local:1b"], "reason": REASON, "source": "rule"}
            ),
        )

    page.route(re.compile(r"/api/models\?"), on_models)
    page.route(re.compile(r"/api/models/defaults\?"), on_defaults)
    page.goto(f"{server.base_url}/#/")
    wait_ready(page)
    page.get_by_label("Autoriser le cloud").check()
    page.evaluate("location.hash = '#/documents'")
    wait_for(page, "() => document.querySelector('wl-model-picker')?.selected?.tag === 'fake:1b'")
    note = page.locator("[data-screen='documents-chat'] .docs-cloud-note")
    note.wait_for()
    assert "les extraits retrouvés dans vos documents lui sont envoyés" in note.inner_text()


# --- Une question : étapes, sources avant la réponse, passage, pied ----------------------------


def test_the_sources_fill_the_panel_before_the_answer_with_the_stages_the_passage_and_the_foot(
    docs,
):
    page, server, _ = docs
    post(page, server, "/api/test/embedder", data={"script": [{"sleep_s": 1.2}]})
    script_model(page, server, {"sleep_s": 4}, *ANSWER)
    ask(page)
    wait_for(
        page,
        "() => document.querySelector(\"[data-screen='documents-chat'] .wl-run-stage\")"
        "?.textContent === 'Recherche des extraits…'",
    )
    assert sources(page).count() == 0  # rien avant la recherche
    wait_for(
        page,
        "() => document.querySelectorAll(\"[data-screen='documents-chat'] .wl-source\").length === 3",
    )
    # Les sources sont là, la réponse n'a pas commencé : l'étape est « Génération… ».
    assert stage(page) == "Génération…"
    assert page.locator(".wl-msg-assistant .wl-md").inner_text().strip() == ""
    wait_done(page)

    assert page.locator(".wl-msg-assistant .wl-md").inner_text().strip() == (
        "Le chat dort sur le canapé [1]."  # le marqueur reste du texte, tel que le modèle l'écrit
    )
    panel = page.locator("[data-screen='documents-chat'] wl-source-panel")
    assert panel.locator(".wl-sources-title").inner_text() == "3 sources utilisées"
    numbers = sources(page).locator(".wl-source-num").all_inner_texts()
    assert numbers == ["[1]", "[2]", "[3]"]
    first = sources(page).first
    assert first.locator(".wl-source-rel").inner_text() in {"Très proche", "Proche", "Éloignée"}
    assert first.locator(".wl-source-relevance .help").inner_text() == "n° 1"
    first.get_by_role("button", name="Aide sur score brut").click()
    assert "Score brut de similarité" in first.locator(".wl-metric-help").inner_text()
    assert source_of(page, "nuit.pdf").locator(".wl-source-page").inner_text() == "page 1"
    assert source_of(page, "chats.txt").locator(".wl-source-page").count() == 0

    # « Ouvrir l'extrait » : l'extrait entier, le passage du serveur surligné (emoji compris).
    cats = source_of(page, "chats.txt")
    assert cats.locator("mark").count() == 0
    cats.get_by_role("button", name=re.compile("^Ouvrir l'extrait de la source")).click()
    cats.locator("mark").wait_for()
    assert cats.locator("mark").inner_text() == PASSAGE
    assert cats.locator("blockquote").inner_text() == CATS
    cats.get_by_role("button", name=re.compile("^Fermer l'extrait")).click()
    assert cats.locator("mark").count() == 0

    # Pied : durées de recherche et de génération à part.
    foot = page.locator(".wl-msg-assistant .wl-msg-foot")
    for label in ("Recherche", "Génération"):
        value = metric(foot, label).locator(".wl-metric-value").inner_text()
        assert re.fullmatch(rf"[\d,]+{NBSP}s", value.strip()), (label, value)
    assert metric(foot, "Durée totale").count() == 0
    # Une seule réponse : pas de « Afficher les sources ».
    assert page.get_by_role("button", name=re.compile("^Afficher les sources")).count() == 0


# --- Plusieurs réponses, un seul panneau -------------------------------------------------------


def test_each_answer_shows_its_sources_in_the_single_panel_from_the_second_answer_on(
    backend, page_tolerating_failed_requests
):
    page = page_tolerating_failed_requests
    server = backend.start()
    install_models(page)
    import_docs(
        page,
        server,
        **{
            "chats.txt": txt(CATS),
            "voitures.txt": txt(CARS),
            "nuit.pdf": ("application/pdf", make_pdf(["La nuit le chat chasse les souris."])),
        },
    )
    script_model(page, server, *ANSWER)
    open_screen(page, server)
    ask(page)
    wait_done(page, 1)
    assert sources(page).count() == 3
    assert page.get_by_role("button", name=re.compile("^Afficher les sources")).count() == 0

    delete_document(backend, "nuit.pdf")
    ask(page, "Que fait la voiture électrique ?")
    wait_done(page, 2)
    assert sources(page).count() == 2  # la dernière réponse : le panneau montre ses sources
    buttons = page.get_by_role("button", name=re.compile("^Afficher les sources"))
    assert buttons.count() == 2
    assert [b.get_attribute("aria-pressed") for b in buttons.all()] == ["false", "true"]

    buttons.first.click()
    assert sources(page).count() == 3  # les sources de la première réponse, dans le même panneau
    assert [b.get_attribute("aria-pressed") for b in buttons.all()] == ["true", "false"]
    assert page.locator("[data-screen='documents-chat'] wl-source-panel").count() == 1

    # Le document a disparu depuis : l'ouvrir dit « extrait supprimé ».
    pdf = source_of(page, "nuit.pdf")
    pdf.get_by_role("button", name=re.compile("^Ouvrir l'extrait")).click()
    pdf.locator(".wl-source-gone").wait_for()
    assert pdf.locator(".wl-source-gone").inner_text().strip() == "extrait supprimé"
    assert pdf.get_by_role("button", name=re.compile("^Ouvrir l'extrait")).count() == 0


def test_a_reopened_conversation_says_deleted_extract_for_a_document_deleted_since(backend, page):
    server = backend.start()
    install_models(page)
    import_docs(page, server, **{"chats.txt": txt(CATS), "voitures.txt": txt(CARS)})
    script_model(page, server, *ANSWER)
    open_screen(page, server)
    ask(page)
    wait_done(page)
    assert sources(page).count() == 2

    delete_document(backend, "chats.txt")
    reload_screen(page)  # rechargée : la conversation est relue au serveur
    wait_for(
        page,
        "() => document.querySelectorAll(\"[data-screen='documents-chat'] .wl-source\").length === 2",
    )
    answer = page.locator("[data-screen='documents-chat'] .wl-msg-assistant")
    assert answer.locator(".wl-md").inner_text().strip() == "Le chat dort sur le canapé [1]."
    assert source_of(page, "chats.txt").locator(".wl-source-gone").inner_text().strip() == (
        "extrait supprimé"
    )
    assert (
        source_of(page, "voitures.txt").get_by_role("button", name=re.compile("^Ouvrir")).count()
        == 1
    )
    # Les mesures reviennent du flux rejoué : pied avec recherche et génération.
    foot = answer.locator(".wl-msg-foot")
    assert metric(foot, "Recherche").count() == 1
    assert metric(foot, "Génération").count() == 1
    summary = page.locator("[data-screen='documents-chat'] .docs-chat-count")
    assert summary.inner_text() == "1 document · 1 extrait"


# --- Positions du passage : points de code, pas unités UTF-16 ----------------------------------

SPLIT = """async () => {
    const { splitPassage } = await import('/static/components/wl-source-panel.js');
    return [
        splitPassage('Un 🐈 passe. Le chat.', { start: 12, end: 20 }),
        splitPassage('abc', { start: 2, end: 9 }),
        splitPassage('abc', null),
        splitPassage('abc', { start: 1, end: 1 }),
        splitPassage('abc', { start: -1, end: 2 }),
    ];
}"""


def test_the_passage_positions_count_code_points_and_an_invalid_passage_is_not_highlighted(
    server, page
):
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    cut = page.evaluate(SPLIT)
    # Le serveur compte en points de code Python : l'emoji (deux unités UTF-16) n'en vaut qu'un.
    assert cut == [["Un 🐈 passe. ", "Le chat.", ""], None, None, None, None]


# --- Mise en page : panneau toujours ouvert en large, sous la réponse et replié en deçà --------


def box(locator) -> dict:
    return locator.bounding_box()


def test_the_panel_is_always_open_beside_the_answer_from_1024px_and_collapsed_below_it(docs):
    page, _, _ = docs
    ask(page)
    wait_done(page)
    panel = page.locator("[data-screen='documents-chat'] details.wl-sources")
    thread = page.locator("[data-screen='documents-chat'] wl-chat-thread")

    page.set_viewport_size({"width": 1024, "height": 800})
    wait_for(
        page,
        "() => document.querySelector(\"[data-screen='documents-chat'] details.wl-sources\").open",
    )
    assert box(panel)["x"] > box(thread)["x"] + box(thread)["width"] - 1  # à droite
    # La classe de l'écran survit à celle du composant : le panneau couvre les deux rangées.
    host = page.locator("[data-screen='documents-chat'] wl-source-panel")
    assert host.evaluate("el => getComputedStyle(el).gridRowEnd") == "span 2"
    panel.locator("summary").click(force=True)  # aucun bouton de repli
    assert panel.evaluate("el => el.open") is True
    assert panel.locator("summary").get_attribute("tabindex") == "-1"

    page.set_viewport_size({"width": 1023, "height": 800})
    wait_for(
        page,
        "() => !document.querySelector(\"[data-screen='documents-chat'] details.wl-sources\").open",
    )
    assert box(panel)["y"] >= box(thread)["y"] + box(thread)["height"] - 1  # sous la réponse
    assert sources(page).first.is_hidden()
    panel.locator("summary").click()
    assert sources(page).first.is_visible()  # se déplie par son titre

    page.set_viewport_size({"width": 320, "height": 800})
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, f"défilement horizontal de {overflow} px"


# --- Reprise du flux ---------------------------------------------------------------------------


def test_leaving_and_coming_back_resumes_the_stream_by_after(docs, traffic):
    page, server, _ = docs
    script_model(
        page,
        server,
        {"text": "Un"},
        {"sleep_s": 1.0},
        {"text": " deux"},
        {"sleep_s": 4},
        {"text": " trois"},
    )
    ask(page)
    wait_for(
        page,
        "() => document.querySelector(\"[data-screen='documents-chat'] .wl-msg-assistant .wl-md\")"
        "?.textContent.includes('Un')",
    )
    run_id = page.evaluate(
        "() => document.querySelector(\"[data-screen='documents-chat'] wl-run-status\").runId"
    )
    page.evaluate("location.hash = '#/documents/base'")
    page.locator('[data-screen="documents-base"]').wait_for(state="visible")
    page.wait_for_timeout(1800)  # « deux » est émis pendant que l'écran est masqué
    page.evaluate("location.hash = '#/documents'")
    # Reprise EN COURS de flux : « deux » (manqué, masqué) revient alors que le run tourne encore.
    wait_for(
        page,
        "() => document.querySelector(\"[data-screen='documents-chat'] .wl-msg-assistant .wl-md\")"
        "?.textContent.includes('deux')",
    )
    assert run_status(page, server, run_id) == "running"
    assert any(re.search(r"/events\?after=\d+", url) for url in traffic.api_calls())
    wait_done(page)
    text = page.locator(".wl-msg-assistant .wl-md").inner_text().strip()
    assert text == "Un deux trois"  # rien de perdu, rien de répété


# --- Refus du serveur : base vidée entre-temps, question déjà en cours ---------------------------


def test_a_base_emptied_meanwhile_leads_to_the_document_base_instead_of_an_answer(docs_lenient):
    page, _, backend = docs_lenient
    for name in ("chats.txt", "voitures.txt", "nuit.pdf"):
        delete_document(backend, name)
    ask(page)
    card = page.locator("[data-screen='documents-chat'] .docs-card")
    card.wait_for()  # la base relue est vide : le message mène à la Base documentaire
    assert card.get_by_role("link", name="Importer des documents").get_attribute("href") == (
        "#/documents/base"
    )
    assert page.locator(".wl-msg-assistant").count() == 0  # aucun run, aucune réponse vide


def test_a_question_already_running_is_joined_without_an_error(docs_lenient):
    page, server, _ = docs_lenient
    script_model(page, server, {"sleep_s": 4}, *ANSWER)
    started = post(
        page,
        server,
        "/api/rag/runs",
        data={"question": QUESTION, "model": "fake:1b", "strategy": "naive"},
    )
    ask(page, "Une autre question ?")
    wait_done(page)
    assert page.locator("[data-screen='documents-chat'] .chat-notice").inner_text() == (
        f"Une réponse est déjà en cours{NBSP}: vous la suivez. Votre question est restée dans le champ."
    )
    assert page.locator("[data-screen='documents-chat'] wl-error:not([hidden])").count() == 0
    assert field(page).input_value() == "Une autre question ?"
    wait_run(page, server, started["run_id"])
    assert sources(page).count() == 3


# --- axe-core ---------------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 1024, 320])
def test_axe_finds_no_violation_with_sources_an_open_extract_and_the_source_deleted(
    docs, theme, width
):
    page, server, backend = docs
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    page.set_viewport_size({"width": width, "height": 900})
    assert_no_axe_violations(page, f"écran prêt, {width} px, thème {theme}")
    ask(page)
    wait_done(page)
    panel = page.locator("[data-screen='documents-chat'] details.wl-sources")
    if not panel.evaluate("el => el.open"):
        panel.locator("summary").click()
    cats = source_of(page, "chats.txt")
    cats.get_by_role("button", name=re.compile("^Ouvrir l'extrait")).click()
    cats.locator("mark").wait_for()
    cats.get_by_role("button", name=re.compile("^Aide sur score brut")).click()
    assert_no_axe_violations(page, f"sources, extrait ouvert, {width} px, thème {theme}")
    delete_document(backend, "voitures.txt")
    reload_screen(page)
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    page.set_viewport_size({"width": width, "height": 900})
    source_of(page, "voitures.txt").locator(".wl-source-gone").wait_for(state="attached")
    assert_no_axe_violations(page, f"extrait supprimé, {width} px, thème {theme}")
