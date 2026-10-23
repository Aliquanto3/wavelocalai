"""Flow 2 d'`EXPERIENCE.md` (atelier de formation) joué de bout en bout, puis l'accessibilité de tous
les écrans du MVP (story 4.9), dans un vrai navigateur, sur le vrai serveur.

La base est celle du test, en dossier temporaire (jamais `data/`). L'extraction du `.docx`, la
découpe, l'indexation, la recherche, les sources et le flux sont réels ; seuls l'embedding et le
modèle de réponse sont les `fake` scriptables du mode test, et la liste des modèles est simulée par
le test (`page.route`). Le garde-fou mémoire est celui de la route de test (`ram_guard` et ses clés).

Prouvés ici : l'Accueil et la carte « Documents » (nom court, nom long, résumé de la base), la base
vide, l'import suivi par fichier, « 14 extraits ajoutés depuis 1 document », la question, les sources
avant la réponse, l'extrait retrouvé mot pour mot avec son passage surligné (D-21), « Vider » cliqué
par erreur puis « Annuler » qui ne supprime rien, le garde-fou qui garde la question et chiffre le
besoin, aucune requête hors de 127.0.0.1, et axe-core sans violation sur chaque écran disponible du
registre, thème clair puis sombre.
"""

from __future__ import annotations

import re

import pytest

from ..workshop_note import ANSWER_PARAGRAPH, ANSWER_SENTENCE, FILE_NAME, QUESTION, make_note
from .parcours import assert_never_reloaded, mark_no_reload
from .test_arena import install_models as install_arena_models
from .test_discussion import (
    ANSWER,
    ask,
    field,
    import_docs,
    plain,
    script_model,
    source_of,
    stage,
    wait_done,
)
from .test_documents import choose, script_embedder, wait_summary
from .test_memory_guard import GUARD, MESSAGE, button, guard_alert, install_chat_models
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCUMENTS = '[data-screen="home"] a.home-module-link[href="#/documents"]'


def wait_home_summary(page, text: str) -> None:
    wait_for(
        page,
        '() => document.querySelector(\'[data-screen="home"] a.home-module-link[href="#/documents"]'
        f" .home-module-summary')?.textContent === {text!r}",
    )


def go(page, hash_: str, screen: str) -> None:
    page.evaluate("(hash) => { location.hash = hash; }", hash_)
    wait_for(page, f"() => document.querySelector('[data-screen=\"{screen}\"]:not([hidden])')")


def wait_discussion(page) -> None:
    wait_for(page, "() => document.querySelector('wl-model-picker')?.value === 'fake:1b'")
    wait_for(
        page, "() => document.querySelector(\"[data-screen='documents-chat'][data-restored]\")"
    )


def test_flow_2_from_the_home_to_the_source_the_mistaken_clear_and_the_memory_guard(
    backend, page, traffic
):
    server = backend.start()
    install_chat_models(page)
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    mark_no_reload(page)  # un rechargement l'effacerait (story 8.3)

    # 1. L'Accueil : la carte « Documents », avec le nom court, le nom long et le résumé de la base.
    link = page.locator(DOCUMENTS)
    assert link.locator(".home-module-name").inner_text() == "Documents"
    assert link.locator(".home-module-long").inner_text() == "Assistant documentaire"
    wait_home_summary(page, "0 document indexé · 0 extrait")
    link.click()

    # 2. Base vide, un seul geste pour importer.
    empty = page.locator("[data-screen='documents-chat'] .docs-card")
    empty.wait_for()
    assert empty.locator("h2").inner_text() == "Votre base documentaire est vide"
    empty.get_by_role("link", name="Importer des documents").click()
    wait_for(page, "() => location.hash === '#/documents/base'")
    base_empty = page.locator("[data-screen='documents-base'] .docs-card")
    base_empty.wait_for()
    assert base_empty.locator("h2").inner_text() == "Votre base documentaire est vide"
    assert base_empty.get_by_role("button", name="Importer des documents").is_enabled()

    # 3. L'import du `.docx`, suivi par fichier, puis « 14 extraits ajoutés depuis 1 document ».
    script_embedder(server, page, {"sleep_s": 1.5})
    choose(page, {"name": FILE_NAME, "mimeType": DOCX, "buffer": make_note()})
    line = page.locator(".docs-import").filter(
        has=page.locator(".docs-import-name", has_text=FILE_NAME)
    )
    line.locator(".docs-import-state").filter(
        has_text=re.compile(r"Vectorisation \d+/14 extraits")
    ).wait_for()
    wait_summary(page, "14 extraits ajoutés depuis 1 document.")
    assert line.locator(".docs-import-state").inner_text() == "14 extraits ajoutés"
    assert page.locator(".docs-count").last.inner_text() == "1 document prêt · 14 extraits"

    # Le résumé de la carte de l'Accueil suit la base.
    go(page, "#/", "home")
    wait_home_summary(page, "1 document indexé · 14 extraits")

    # 4. La question : les sources arrivent avant la réponse.
    go(page, "#/documents", "documents-chat")
    wait_discussion(page)
    wait_for(
        page,
        "() => document.querySelector(\"[data-screen='documents-chat'] .docs-chat-count\")"
        "?.textContent === '1 document · 14 extraits'",
    )
    script_model(page, server, {"sleep_s": 3}, *ANSWER)
    ask(page, QUESTION)
    sources = page.locator("[data-screen='documents-chat'] .wl-source")
    wait_for(
        page,
        "() => document.querySelectorAll(\"[data-screen='documents-chat'] .wl-source\").length > 0",
    )
    assert stage(page) == "Génération…"
    assert page.locator(".wl-msg-assistant .wl-md").inner_text().strip() == ""
    wait_done(page)
    assert plain(page.locator(".wl-msg-assistant .wl-md")) == "Le chat dort sur le canapé [1]."

    # 5. Le climax : l'extrait retrouvé mot pour mot, son passage surligné (D-21).
    cited = source_of(page, FILE_NAME).filter(has_text=ANSWER_SENTENCE).first
    assert sources.count() >= 1
    cited.get_by_role("button", name=re.compile("^Ouvrir l'extrait")).click()
    cited.locator("mark").wait_for()
    assert cited.locator("mark").inner_text() == ANSWER_SENTENCE
    assert cited.locator("blockquote").inner_text() == ANSWER_PARAGRAPH

    # 6. « Vider » cliqué par erreur : le dialogue annonce les 14 extraits, « Annuler » ne
    # supprime rien.
    go(page, "#/documents/base", "documents-base")
    page.locator("wl-data-table tbody tr").first.wait_for()
    page.get_by_role("button", name="Vider la base documentaire").first.click()
    dialog = page.locator("dialog.wl-dialog[open]")
    dialog.wait_for()
    assert dialog.locator(".wl-dialog-consequence").inner_text() == (
        "14 extraits de 1 document seront supprimés."
    )
    page.get_by_role("button", name="Annuler").click()
    page.locator("dialog.wl-dialog[open]").wait_for(state="detached")
    assert page.locator(".docs-manage-status").inner_text().strip() == (
        f"Opération annulée{NBSP}: la base documentaire est inchangée."
    )
    totals = page.request.get(f"{server.base_url}/api/rag/documents").json()["totals"]
    assert totals == {"documents": 1, "chunks": 14}

    # 7. Le garde-fou mémoire (simulé) : la question reste, l'alerte chiffre le besoin.
    go(page, "#/documents", "documents-chat")
    wait_discussion(page)
    script_model(page, server, GUARD)
    ask(page, "Quelle est la durée de la pause de midi ?")
    alert = guard_alert(page)
    alert.wait_for()
    assert alert.locator(".wl-error-message").inner_text() == MESSAGE
    assert button(alert, "Prendre un modèle plus petit").is_visible()
    assert field(page).input_value() == "Quelle est la durée de la pause de midi ?"

    # La page n'a jamais été rechargée, et rien n'est sorti de la machine pendant tout le parcours.
    assert_never_reloaded(page)
    assert traffic.urls
    assert all(url.startswith(server.base_url) for url in traffic.urls), traffic.urls
    assert not traffic.blocked


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_every_screen_of_the_mvp(backend, page, theme):
    """Chaque écran `available` du registre (sans paramètre), base vide puis avec un document."""
    server = backend.start()
    install_arena_models(page)
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    screens = page.evaluate(
        """async () => {
            const { SCREENS } = await import('/static/core/registry.js');
            return SCREENS.filter((screen) => screen.status === 'available')
                .map((screen) => ({ id: screen.id, path: screen.path }));
        }"""
    )
    # Le MVP : l'Accueil, le Chat, l'Arène, la Discussion et la Base documentaire.
    assert {screen["id"] for screen in screens} >= {
        "home",
        "arena-chat",
        "arena-compare",
        "documents-chat",
        "documents-base",
    }

    def check(state: str) -> None:
        for screen in screens:
            go(page, f"#{screen['path']}", screen["id"])
            page.wait_for_timeout(600)  # les cartes, la liste de modèles et la base se remplissent
            assert_no_axe_violations(page, f"{screen['id']}, {state}, thème {theme}")

    check("base vide")
    import_docs(page, server, **{FILE_NAME: (DOCX, make_note())})
    check("base de 14 extraits")
