"""Écran Modèles, « Reclassement des extraits » (story 5.5 ; fastembed en dépendance de base depuis la
story 9.5, D-R6) dans un vrai navigateur, sur le vrai serveur.

Aucun vrai téléchargement : l'installation du reranker est factice (`POST /api/test/reranker-install` :
octets simulés, un `FakeReranker` une fois « installé »). Ollama est le faux de `test_models_install.py`.
Un vrai téléchargement du reranker est une recette d'Anaël.
"""

from __future__ import annotations

import pytest

from .test_models_install import (  # noqa: F401 - fixtures
    models_server,
    ollama,
    open_models,
    wait_notice,
)
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
SECTION = ".models-rerank"
STATUS = ".models-rerank-status"
BUTTON = ".models-install-reranker"
NOTICE_DONE = "Reranker installé. La recherche documentaire reclasse désormais les extraits."


def arrange(page, server, **body):
    """Règle l'installation factice, puis relit l'écran (l'état du reranker est lu à l'ouverture)."""
    response = page.request.post(f"{server.base_url}/api/test/reranker-install", data=body)
    assert response.ok, response.text()
    page.reload()
    wait_ready(page)
    wait_for(page, f"() => document.querySelector('{STATUS}')?.textContent.length > 0")


def downloads(page, server) -> int:
    return page.request.get(f"{server.base_url}/api/test/reranker-install").json()["downloads"]


@pytest.fixture
def screen(page, models_server, ollama):
    return open_models(page, models_server, ollama)


def wait_status(page, text: str) -> None:
    wait_for(page, f"() => document.querySelector('{STATUS}')?.textContent === '{text}'")


def status(page) -> str:
    return page.locator(STATUS).inner_text()


def test_a_missing_model_says_not_installed_with_the_servers_reason_and_downloads_nothing_unasked(
    screen, models_server
):
    arrange(screen, models_server)
    assert status(screen) == "Non installé"
    assert screen.locator("#models-rerank-reason").inner_text().startswith(f"Raison{NBSP}: ")
    assert screen.locator(BUTTON).get_attribute("aria-disabled") == "false"
    assert screen.get_by_role("button", name="Installer le reranker").count() == 1
    assert downloads(screen, models_server) == 0  # lire l'écran ne télécharge rien


def test_installing_shows_the_bytes_blocks_the_other_installs_then_says_installed(
    screen, models_server
):
    arrange(screen, models_server, total_bytes=2 * 1024**3, steps=4, step_delay_s=0.5)
    screen.locator(BUTTON).click()
    wait_for(
        screen,
        f"() => /Téléchargement/.test(document.querySelector('{SECTION} .wl-progress-text')?.textContent ?? '')",
    )
    assert status(screen) == "Installation en cours"
    bar = screen.locator(f"{SECTION} progress")
    assert bar.get_attribute("aria-label") == "Installation de Reclassement des extraits"
    assert screen.get_by_role(
        "button", name="Annuler l'installation de Reclassement des extraits"
    ).is_visible()
    # L'installation d'un modèle est refusée en attendant, avec sa raison.
    named = screen.locator(".models-install-named")
    assert named.get_attribute("aria-disabled") == "true"
    assert (
        screen.locator("#models-install-reason")
        .inner_text()
        .startswith("Une installation est en cours")
    )
    wait_notice(screen, NOTICE_DONE)
    wait_status(screen, "Installé")
    assert screen.locator(BUTTON).is_hidden()
    assert screen.locator("#models-rerank-reason").inner_text().startswith("Le reranker ")
    assert named.get_attribute("aria-disabled") == "false"
    assert downloads(screen, models_server) == 1


def test_cancelling_leaves_the_reranker_not_installed(screen, models_server):
    arrange(screen, models_server, mode="hang", step_delay_s=0.05)
    screen.locator(BUTTON).click()
    wait_for(
        screen,
        f"() => /Téléchargement/.test(document.querySelector('{SECTION} .wl-progress-text')?.textContent ?? '')",
    )
    screen.get_by_role("button", name="Annuler l'installation de Reclassement des extraits").click()
    wait_notice(screen, "Installation du reranker annulée. Il reste non installé.")
    assert status(screen) == "Non installé"
    assert screen.locator(BUTTON).is_visible()


def test_a_failed_download_shows_pull_failed_in_the_section_and_can_be_retried(
    screen, models_server
):
    arrange(screen, models_server, mode="fail", step_delay_s=0.05, reason="disque plein")
    screen.locator(BUTTON).click()
    screen.locator(f"{SECTION} wl-error").wait_for()
    assert status(screen) == "Non installé"
    assert "Le reranker" in screen.locator(f"{SECTION} wl-error").inner_text()
    assert screen.locator(BUTTON).is_visible()
    assert screen.locator(".models-pull-panel").is_hidden()  # rien sous la barre d'un modèle nommé


def test_leaving_the_screen_and_coming_back_resumes_the_reranker_progress(screen, models_server):
    arrange(screen, models_server, mode="hang", step_delay_s=0.05)
    screen.locator(BUTTON).click()
    wait_for(
        screen,
        f"() => /Téléchargement/.test(document.querySelector('{SECTION} .wl-progress-text')?.textContent ?? '')",
    )
    screen.reload()  # une page rechargée rejoint l'installation, dans la section du reranker
    wait_ready(screen)
    wait_for(
        screen,
        f"() => /Téléchargement/.test(document.querySelector('{SECTION} .wl-progress-text')?.textContent ?? '')",
    )
    wait_status(screen, "Installation en cours")
    screen.get_by_role("button", name="Annuler l'installation de Reclassement des extraits").click()
    wait_notice(screen, "Installation du reranker annulée. Il reste non installé.")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_nothing_in_the_section_not_installed_installing_and_failing(
    screen, models_server, theme
):
    screen.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    arrange(screen, models_server)
    screen.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(screen, f"reranker non installé, thème {theme}")
    arrange(screen, models_server, mode="hang", step_delay_s=0.05)
    screen.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    screen.locator(BUTTON).click()
    wait_for(
        screen,
        f"() => /Téléchargement/.test(document.querySelector('{SECTION} .wl-progress-text')?.textContent ?? '')",
    )
    assert_no_axe_violations(screen, f"reranker en cours, thème {theme}")
    screen.get_by_role("button", name="Annuler l'installation de Reclassement des extraits").click()
    wait_notice(screen, "Installation du reranker annulée. Il reste non installé.")
