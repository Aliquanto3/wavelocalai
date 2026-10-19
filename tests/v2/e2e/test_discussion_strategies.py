"""Écran Discussion, story 4.6 : stratégies de recherche (HyDE, Self-RAG), nombre d'extraits et
citations vérifiées, dans un vrai navigateur sur le vrai serveur.

Comme `test_discussion.py` : indexation, recherche, flux et mesures sont réels ; seuls l'embedding et
le modèle de réponse sont les `fake` scriptables du mode test. Le `fake` rend ici un script **par
appel** (`POST /api/test/chat-model {scripts}`) : réponse hypothétique, notation, reformulation, puis
réponse. Ollama n'est jamais sollicité.

Prouvés ici : les réglages avancés (trois stratégies, nombre d'extraits borné, noms techniques en aide
seulement), les étapes « Rédaction d'une réponse hypothétique… » et « Vérification de la pertinence… »,
l'effet réel de chaque réglage sur la question suivante, et les citations (seuls les marqueurs
vérifiés par le serveur deviennent des boutons, mise en évidence dans les deux sens, extrait ouvert
au clic, réponse rouverte).
"""

from __future__ import annotations

import json
import re

import pytest

from .test_chat import MODEL, install_models
from .test_discussion import (  # noqa: F401 - `docs` est une fixture
    ANSWER,
    CARS,
    CATS,
    NBSP,
    PASSAGE,
    ask,
    docs,
    field,
    import_docs,
    open_screen,
    plain,
    post,
    reload_screen,
    script_model,
    source_of,
    sources,
    stage,
    txt,
    wait_done,
)
from .test_shell import assert_no_axe_violations, wait_for

SCREEN = "[data-screen='documents-chat']"
GRADE_NONE = "1 : non\n2 : non\n3 : non"
GRADE_FIRST = "1 : oui\n2 : non\n3 : non"
CITED = [{"text": "Il dort sur le canapé [1] "}, {"text": "et ronronne [9]."}]


def script_calls(page, server, *scripts) -> None:
    """Un script par appel du modèle, dans l'ordre (le dernier se répète)."""
    post(page, server, "/api/test/chat-model", data={"scripts": [list(s) for s in scripts]})


def settings(page):
    advanced = page.locator(f"{SCREEN} details.docs-advanced")
    if advanced.get_attribute("open") is None:
        advanced.locator("summary").click()
    return advanced


def choose(page, label: str) -> None:
    settings(page).get_by_label("Stratégie de recherche").select_option(label=label)


def asked(page, text=None):
    """La commande `POST /api/rag/runs` que la question envoie."""
    with page.expect_request(
        lambda request: request.method == "POST" and request.url.endswith("/api/rag/runs")
    ) as sent:
        ask(page) if text is None else ask(page, text)
    return sent.value.post_data_json


def wait_stage(page, text: str) -> None:
    wait_for(
        page,
        f'() => document.querySelector("{SCREEN} .wl-run-stage")?.textContent === {text!r}',
    )


def test_self_rag_with_a_small_or_unmeasured_model_warns_that_the_check_is_unreliable(
    backend, page
):
    """8.1 (décision du 2026-10-19) : la stratégie vérifiée confie le contrôle des extraits au
    modèle ; sous le seuil du serveur (`verify_min_params_b`) ou sans taille connue, l'avertissement
    s'affiche, comme pour le juge de l'Arène. Rien de tel avec un modèle assez gros, ni sans Self-RAG.
    """
    server = backend.start()
    install_models(page)
    import_docs(page, server, **{"chats.txt": txt(CATS)})
    small = {**MODEL, "tag": "petit:1b", "name": "Petit 1B", "params_active_b": 1.0}
    big = {**MODEL, "tag": "grand:8b", "name": "Grand 8B", "params_active_b": 8.0}
    odd = {  # local sans digest : origine inconnue, signalé comme un local (`is_weak_judge`)
        **MODEL,
        "tag": "inconnu:8b",
        "name": "Inconnu 8B",
        "origin": "unknown",
        "params_active_b": None,
    }
    page.route(
        re.compile(r"/api/models\?"),
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "models": [MODEL, small, big, odd],
                    "ollama_up": True,
                    "refreshed_at": "2026-10-19T10:00:00Z",
                }
            ),
        ),
    )
    open_screen(page, server)
    assert (
        page.request.get(f"{server.base_url}/api/rag/settings").json()["verify_min_params_b"] == 3.0
    )
    note = page.locator(f"{SCREEN} .docs-verify-note")
    pick = lambda name: (  # noqa: E731
        page.locator(f"{SCREEN} .wl-picker-input").click(),
        page.get_by_role("option", name=re.compile(name)).click(),
    )
    assert note.is_hidden()  # recherche directe : rien à vérifier
    choose(page, "Recherche vérifiée")
    note.wait_for()  # Factice 1B : taille inconnue
    assert note.inner_text().strip() == (
        f"Vérification peu fiable avec Factice 1B{NBSP}: la recherche vérifiée confie le contrôle "
        "des extraits au modèle, et celui-ci a moins de 3 milliards de paramètres actifs (ou sa "
        "taille est inconnue). Choisissez un modèle plus gros pour une vérification plus sûre."
    )
    pick("Petit 1B")
    assert "Petit 1B" in note.inner_text()
    pick("Grand 8B")
    note.wait_for(state="hidden")
    pick("Inconnu 8B")
    note.wait_for()
    assert "Inconnu 8B" in note.inner_text()
    pick("Petit 1B")
    note.wait_for()
    choose(page, "Recherche directe")
    note.wait_for(state="hidden")


def markers(page):
    return page.locator(f"{SCREEN} .wl-msg-assistant .docs-cite")


def linked(locator) -> bool:
    return locator.evaluate("el => el.classList.contains('is-linked')")


# --- Réglages avancés --------------------------------------------------------------------------


def test_the_advanced_settings_offer_three_strategies_and_a_bounded_number_of_excerpts(docs):
    page, _, _ = docs
    advanced = settings(page)
    select = advanced.get_by_label("Stratégie de recherche")
    assert select.locator("option").all_inner_texts() == [
        "Recherche directe",
        "Réponse imaginée d'abord",
        "Recherche vérifiée",
    ]
    # Les noms techniques ne sont qu'en aide, jamais dans un libellé.
    labels = " ".join(
        [
            *select.locator("option").all_inner_texts(),
            *advanced.locator("label").all_inner_texts(),
            advanced.locator("summary").inner_text(),
        ]
    )
    assert not re.search(r"HyDE|Self-RAG|Top-K|naive", labels)
    help_of = lambda: advanced.locator(".help").all_inner_texts()  # noqa: E731
    assert "naive" in help_of()[0]
    select.select_option(label="Réponse imaginée d'abord")
    assert "HyDE" in help_of()[0] and "naive" not in help_of()[0]
    select.select_option(label="Recherche vérifiée")
    assert "Self-RAG" in help_of()[0]
    assert "Top-K" in " ".join(help_of())

    top_k = advanced.get_by_label("Nombre d'extraits")
    assert top_k.input_value() == "4"  # le défaut du serveur
    assert top_k.get_attribute("max") == "20"  # son plafond
    top_k.fill("50")
    top_k.press("Tab")
    assert top_k.input_value() == "20"  # ramené dans les bornes, le champ le montre
    top_k.fill("0")
    top_k.press("Tab")
    assert top_k.input_value() == "1"


def test_the_number_of_excerpts_acts_on_the_next_question(docs):
    page, _, _ = docs
    top_k = settings(page).get_by_label("Nombre d'extraits")
    top_k.fill("1")
    body = asked(page)
    assert body["top_k"] == 1 and body["strategy"] == "naive"
    wait_done(page)
    assert sources(page).count() == 1
    top_k.fill("2")
    assert asked(page)["top_k"] == 2
    wait_done(page, 2)
    assert sources(page).count() == 2  # le panneau montre les sources de la dernière réponse


# --- HyDE --------------------------------------------------------------------------------------


def test_hyde_writes_a_hypothetical_answer_and_searches_with_it(docs):
    page, server, _ = docs
    ask(page)  # d'abord la recherche directe : la question parle du chat
    wait_done(page)
    assert sources(page).first.locator(".wl-source-doc").inner_text() == "chats.txt"

    script_calls(page, server, [{"sleep_s": 1.5}, {"text": CARS}], ANSWER)
    choose(page, "Réponse imaginée d'abord")
    body = asked(page)
    assert body["strategy"] == "hyde"
    wait_stage(page, "Rédaction d'une réponse hypothétique…")
    wait_done(page, 2)
    # La recherche s'est appuyée sur l'hypothèse (sur les voitures), non sur la question (le chat).
    assert sources(page).first.locator(".wl-source-doc").inner_text() == "voitures.txt"
    assert plain(page.locator(".wl-msg-assistant .wl-md").last) == "Le chat dort sur le canapé [1]."


# --- Self-RAG ----------------------------------------------------------------------------------


def test_self_rag_verifies_the_relevance_then_reformulates_and_keeps_the_relevant_excerpt(docs):
    page, server, _ = docs
    script_calls(
        page,
        server,
        [{"sleep_s": 1.5}, {"text": GRADE_NONE}],  # notation du premier tour
        [{"text": CARS}],  # reformulation : elle parle des voitures
        [{"text": GRADE_FIRST}],  # notation du second tour
        ANSWER,
    )
    choose(page, "Recherche vérifiée")
    assert asked(page)["strategy"] == "self_rag"
    wait_stage(page, "Vérification de la pertinence…")
    assert sources(page).count() == 0  # rien n'est montré avant la fin de la vérification
    wait_done(page)
    assert sources(page).count() == 1  # seul l'extrait jugé pertinent reste
    assert sources(page).first.locator(".wl-source-doc").inner_text() == "voitures.txt"
    foot = page.locator(f"{SCREEN} .wl-msg-foot")
    assert "Recherche" in foot.inner_text() and "Génération" in foot.inner_text()


def test_the_stage_of_a_naive_search_is_unchanged_and_never_names_the_other_strategies(docs):
    page, server, _ = docs
    post(page, server, "/api/test/embedder", data={"script": [{"sleep_s": 1.2}]})
    script_model(page, server, {"sleep_s": 2}, *ANSWER)
    ask(page)
    wait_stage(page, "Recherche des extraits…")
    wait_stage(page, "Génération…")
    wait_done(page)


# --- Citations ---------------------------------------------------------------------------------


def test_only_the_markers_the_server_verified_become_buttons_that_link_to_the_sources(docs):
    page, server, _ = docs
    script_model(page, server, *CITED)
    ask(page)
    wait_done(page)
    answer = page.locator(f"{SCREEN} .wl-msg-assistant .wl-md")
    assert plain(answer) == "Il dort sur le canapé [1] et ronronne [9]."  # le texte du modèle
    assert markers(page).count() == 1  # [9] ne désigne aucune source : du texte, pas un bouton
    marker = page.get_by_role("button", name=re.compile(r"^\[1\] source 1, chats\.txt"))
    assert marker.count() == 1 and marker.inner_text().startswith("[1]")
    assert "[9]" in answer.inner_text() and answer.get_by_role("button", name="[9]").count() == 0
    first = sources(page).first

    marker.hover()  # survoler [1] met la source 1 en évidence
    assert linked(first) and not linked(sources(page).nth(1))
    page.mouse.move(0, 0)
    assert not linked(first)
    first.hover()  # et inversement
    assert linked(marker)
    page.mouse.move(0, 0)
    assert not linked(marker)
    marker.focus()  # au clavier aussi
    assert linked(first)
    marker.blur()
    assert not linked(first)

    marker.click()  # un clic ouvre l'extrait et surligne son passage
    source_of(page, "chats.txt").locator("mark").wait_for()
    assert source_of(page, "chats.txt").locator("mark").inner_text() == PASSAGE


def test_a_marker_of_another_answer_shows_that_answers_sources_in_the_single_panel(docs):
    page, server, _ = docs
    script_model(page, server, *CITED)
    ask(page)
    wait_done(page)
    script_model(page, server, {"text": "Aucune citation ici."})
    ask(page)
    wait_done(page, 2)
    buttons = page.get_by_role("button", name=re.compile("^Afficher les sources"))
    assert buttons.nth(1).get_attribute("aria-pressed") == "true"  # la dernière réponse
    markers(page).first.hover()
    assert buttons.nth(0).get_attribute("aria-pressed") == "true"  # la première, par son marqueur
    assert buttons.nth(1).get_attribute("aria-pressed") == "false"


@pytest.mark.parametrize(
    "answer",
    ["Il dort sur le canapé.", "Un marqueur inventé [9] et un autre [0]."],
)
def test_without_a_verified_marker_the_front_makes_no_button(docs, answer):
    page, server, _ = docs
    script_model(page, server, {"text": answer})
    ask(page)
    wait_done(page)
    assert plain(page.locator(f"{SCREEN} .wl-msg-assistant .wl-md")) == answer
    assert markers(page).count() == 0


def test_a_reopened_conversation_keeps_its_verified_markers(docs):
    page, server, _ = docs
    script_model(page, server, *CITED)
    ask(page)
    wait_done(page)
    reload_screen(page)
    wait_for(page, f'() => document.querySelectorAll("{SCREEN} .wl-source").length === 3')
    assert markers(page).count() == 1
    markers(page).first.hover()
    assert linked(sources(page).first)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [1440, 320])
def test_axe_finds_no_violation_with_citations_and_the_strategy_settings(docs, theme, width):
    page, server, _ = docs
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    page.set_viewport_size({"width": width, "height": 900})
    settings(page)
    assert_no_axe_violations(page, f"réglages avancés ouverts, {width} px, thème {theme}")
    script_model(page, server, *CITED)
    ask(page)
    wait_done(page)
    markers(page).first.focus()
    assert_no_axe_violations(page, f"citation focalisée, {width} px, thème {theme}")
    assert field(page).is_visible()
