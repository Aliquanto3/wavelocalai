"""Encart « La représentation vectorielle n'est pas installée », Base documentaire (story 9.4) dans
un vrai navigateur, sur le vrai serveur.

Le modèle proposé est installé par le même faux Ollama HTTP (`ThreadedOllama`, `/api/pull` en flux
scripté) que l'installation d'un modèle de l'écran Modèles (`test_models_install.py`) : aucun vrai
téléchargement. Le tag réel (`nomic-embed-text`, 274 Mo) a été vérifié par une installation réelle
pendant le développement de la story (voir `story-9-4.md`) ; ici seul le comportement de l'écran est
prouvé, avec des octets scriptés.
"""

from __future__ import annotations

import json
import threading

import pytest

from ..conftest import closed_port
from ..pull_fake import GB, ThreadedOllama, layer, manifest
from .conftest import Backend
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
URL = "#/documents/base"
TAG = "nomic-embed-text"


def alert(page):
    return page.locator(".docs-embedding-alert")


def install_button(page):
    return alert(page).get_by_role("button", name="Installer nomic-embed-text")


@pytest.fixture
def ollama():
    fake = ThreadedOllama(closed_port())
    fake.start()
    yield fake
    fake.stop()


NO_FAKE_EMBEDDER = {"WAVELOCALAI_TESTING_NO_FAKE_EMBEDDER": "1"}  # aucun embedding, même `fake`


@pytest.fixture
def backend_with_ollama(tmp_path, ollama):
    created = Backend(tmp_path, ollama_port=ollama.port, env=NO_FAKE_EMBEDDER)
    yield created
    created.stop()


def test_the_alert_precedes_the_screen_and_disables_the_drop_zone(backend_with_ollama, page):
    server = backend_with_ollama.start()
    page.goto(f"{server.base_url}/{URL}")
    wait_ready(page)
    alert(page).wait_for()
    assert (
        alert(page).locator("h2").inner_text()
        == "La représentation vectorielle n’est pas installée"
    )
    assert f"nomic-embed-text (274{NBSP}Mo)" in alert(page).locator("p").first.inner_text()
    # Ollama est connu « debout » par le flux système un instant après l'ouverture de l'écran.
    wait_for(
        page,
        "() => document.querySelector('.docs-embedding-alert-install')"
        "?.getAttribute('aria-disabled') === 'false'",
    )
    drop = page.locator(".docs-drop")
    assert drop.get_attribute("data-blocked") == "true"
    assert page.get_by_role("button", name="Choisir des fichiers").is_disabled()
    assert page.get_by_role("button", name="Importer des documents").is_disabled()
    assert page.locator("#docs-drop-embedding-reason").inner_text() == (
        f"Aucun modèle de représentation n'est installé{NBSP}: utilisez "
        f"«{NBSP}Installer nomic-embed-text{NBSP}» ci-dessus."
    )
    assert_no_axe_violations(page, "encart sans modèle de représentation")


def test_clicking_installs_through_the_models_pull_route_and_the_alert_disappears(
    backend_with_ollama, page, ollama
):
    server = backend_with_ollama.start()
    page.goto(f"{server.base_url}/{URL}")
    wait_ready(page)
    alert(page).wait_for()

    # Octets scriptés (ronds, pour une mise en forme prévisible) : le tag et la taille réels
    # (274 Mo) sont vérifiés par ailleurs (installation réelle, voir `story-9-4.md`), prouvés ici
    # dans le texte fixe de l'encart (test précédent) ; ce test prouve le mécanisme du run `pull`.
    resume = threading.Event()
    total = 4 * GB
    ollama.scripts.append(
        [
            manifest(),
            layer("sha256:nomicaaaa", total, 0),
            layer("sha256:nomicaaaa", total, total // 2),
            resume,
            layer("sha256:nomicaaaa", total, total),
            {"status": "verifying sha256 digest"},
            {"status": "success"},
        ]
    )
    install_button(page).click()
    expected = f"Téléchargement 2{NBSP}Go sur 4{NBSP}Go · 50{NBSP}%"
    wait_for(
        page,
        f"() => document.querySelector('.docs-embedding-alert .wl-progress-text')?.textContent"
        f" === {json.dumps(expected)}",
    )
    cancel = alert(page).get_by_role("button", name="Annuler l'installation de nomic-embed-text")
    assert cancel.is_visible()
    assert ollama.pull_requests == [TAG]

    resume.set()
    wait_for(
        page,
        "() => document.querySelector('.docs-notice')?.textContent === "
        f"{json.dumps('nomic-embed-text installé.')}",
    )
    alert(page).wait_for(state="hidden")
    wait_for(page, "() => document.querySelector('.docs-drop')?.dataset.blocked === 'false'")
    assert page.get_by_role("button", name="Choisir des fichiers").is_enabled()

    settings = page.evaluate(
        f"() => fetch('{server.base_url}/api/rag/settings').then(r => r.json())"
    )
    assert settings["embedding_models"] == [{"tag": TAG, "name": TAG}]
    # Le modèle installé devient le défaut enregistré (préférence), pas un « premier installé »
    # implicite (AC epics 9.4).
    assert settings["embedding_model"] == TAG


def test_without_ollama_the_install_button_is_disabled_with_the_reason(tmp_path, page):
    backend = Backend(tmp_path, env=NO_FAKE_EMBEDDER)  # Ollama sur un port fermé (par défaut)
    server = backend.start()
    try:
        page.goto(f"{server.base_url}/{URL}")
        wait_ready(page)
        alert(page).wait_for()
        wait_for(
            page,
            "() => document.querySelector('.docs-embedding-alert-install')"
            "?.getAttribute('aria-disabled') === 'true'",
        )
        assert alert(page).locator("#docs-embedding-alert-reason").inner_text() == (
            f"Ollama ne répond pas{NBSP}: démarrez-le pour installer un modèle."
        )
    finally:
        backend.stop()
