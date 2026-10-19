"""Écran Modèles, décharger, supprimer et choisir ses défauts (story 5.4) dans un vrai navigateur,
sur le vrai serveur (vrai registre, vrais défauts, vraies préférences dans un store de test).

Aucun modèle du poste n'est touché : le serveur de l'application parle à un faux Ollama HTTP local
(`ThreadedOllama`, qui sait `/api/tags`, `/api/show`, `/api/ps`, `/api/delete` et le déchargement) ;
la suppression passe par lui, jamais par `DELETE` contre le vrai Ollama. Un modèle « employé par un
run » est un `pull` qui ne finit pas (le run `pull` emploie le tag, comme une réponse emploie son
modèle : c'est la même table du hub que lit `GET /api/system/stream`).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

import pytest

from ..conftest import closed_port
from ..pull_fake import GB, ThreadedOllama
from .conftest import Backend
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
AGENT = "agentmodel:7b"  # outils vérifiés et 7 B : éligible à l'Agent et aux Documents
DOCS = "docmodel:4b"  # 4 B sans outils : éligible aux Documents seulement
SMALL = "smallmodel:1b"  # 1 B : éligible ni à l'Agent ni aux Documents
INSTALLED = {AGENT: 4 * GB, DOCS: 2 * GB, SMALL: GB}
PURPOSES = ("chat", "arena", "judge", "agent", "rag")


@pytest.fixture(scope="module")
def ollama():
    fake = ThreadedOllama(closed_port())
    fake.start()
    yield fake
    fake.stop()


@pytest.fixture(scope="module")
def manage_server(tmp_path_factory, ollama):
    root = tmp_path_factory.mktemp("e2e-manage")
    config = root / "reglages.toml"
    config.write_text("[ollama]\nprobe_cache_s = 0.2\n", encoding="utf-8")  # liste relue vite
    ollama.reset(INSTALLED)
    ollama.params = {AGENT: "7B", DOCS: "4B", SMALL: "1B"}
    ollama.tools = {AGENT}
    backend = Backend(root / "data", ollama_port=ollama.port, config=config)
    (root / "data").mkdir()
    try:
        yield backend.start()
    finally:
        backend.stop()


def call(server, method: str, path: str, body=None):
    """Un appel à l'API du serveur de test (l'`Origin` des écritures est celui de la page)."""
    request = urllib.request.Request(  # noqa: S310
        f"{server.base_url}{path}",
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Origin": server.base_url, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def reset(server, ollama: ThreadedOllama) -> None:
    """Le faux Ollama rendu à ses trois modèles, aucun choix enregistré, aucun run actif."""
    ollama.reset(INSTALLED)
    ollama.params = {AGENT: "7B", DOCS: "4B", SMALL: "1B"}
    ollama.tools = {AGENT}
    for purpose in PURPOSES:
        call(server, "DELETE", f"/api/models/defaults/{purpose}")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:  # le registre relit Ollama (cache de 0,2 s)
        tags = [m["tag"] for m in call(server, "GET", "/api/models")[1]["models"]]
        if sorted(tags) == sorted(INSTALLED):
            return
        time.sleep(0.15)
    pytest.fail(f"le registre n'a pas relu les trois modèles : {tags}")


@pytest.fixture
def models(page, manage_server, ollama):
    reset(manage_server, ollama)
    page.goto(f"{manage_server.base_url}/#/modeles")
    wait_ready(page)
    wait_for(page, "() => document.querySelectorAll('.models-installed tbody tr').length === 3")
    wait_for(page, "() => document.querySelectorAll('.models-defaults tbody tr').length === 5")
    return page


@pytest.fixture
def models_lenient(page_tolerating_failed_requests, manage_server, ollama):
    """Pour un test dont une requête échoue exprès (le `409` de `model_in_use`)."""
    reset(manage_server, ollama)
    page = page_tolerating_failed_requests
    page.goto(f"{manage_server.base_url}/#/modeles")
    wait_ready(page)
    wait_for(page, "() => document.querySelectorAll('.models-installed tbody tr').length === 3")
    wait_for(page, "() => document.querySelectorAll('.models-defaults tbody tr').length === 5")
    return page


def installed_row(page, tag: str):
    return page.locator(".models-installed tbody tr").filter(has_text=tag)


def default_row(page, usage: str):
    return page.locator(".models-defaults tbody tr").filter(
        has=page.get_by_role("rowheader", name=usage)
    )


def delete_button(page, tag: str):
    return page.locator(f'.models-delete[data-tag="{tag}"]')


def wait_notice(page, text: str) -> None:
    wait_for(
        page,
        f"() => document.querySelector('.models-notice').textContent === {json.dumps(text)}",
    )


def hold_in_use(server, ollama, tag: str) -> str:
    """Un run `pull` sur ce tag, qui ne finit pas : le modèle est « employé par un run »."""
    ollama.scripts.append(["hang"])
    status, body = call(server, "POST", "/api/models/pull", {"tag": tag})
    assert status == 200, body
    return body["run_id"]


def release(server, run_id: str) -> None:
    call(server, "POST", f"/api/runs/{run_id}/cancel")


# --- Défauts --------------------------------------------------------------------------------------


def test_the_defaults_section_lists_the_five_purposes_with_their_reason(models):
    rows = models.locator(".models-defaults tbody tr")
    assert rows.count() == 5
    usages = [rows.nth(i).locator("th").inner_text() for i in range(5)]
    assert usages == ["Conversation", "Arène", "Juge", "Agent", "Documents"]
    headers = models.locator(".models-defaults thead th").all_inner_texts()
    assert headers == ["Usage", "Modèle", "Raison", "Actions"]
    agent = default_row(models, "Agent")
    assert AGENT in agent.inner_text()  # le seul modèle éligible à l'Agent qui tient en mémoire
    assert "Choisi par vous" not in models.locator(".models-defaults").inner_text()
    assert (
        default_row(models, "Agent")
        .get_by_role("button", name="Changer le modèle de l'usage Agent")
        .is_visible()
    )
    assert (
        models.locator(".models-defaults").get_by_role("button", name=re.compile("Revenir")).count()
        == 0
    )


def test_the_picker_proposes_only_the_models_eligible_to_the_purpose(models):
    def options(usage: str) -> list[str]:
        default_row(models, usage).get_by_role("button", name=re.compile("^Changer")).click()
        picker = default_row(models, usage).locator("wl-model-picker")
        picker.get_by_role("combobox").click()
        picker.locator('[role="option"]').first.wait_for()  # la liste arrive du serveur
        names = picker.locator('[role="option"] .wl-picker-option-name').all_inner_texts()
        default_row(models, usage).get_by_role("button", name=re.compile("^Annuler")).click()
        return sorted(names)

    assert options("Agent") == [
        AGENT
    ]  # outils vérifiés et 3 B actifs : ni le 4 B sans outils, ni le 1 B
    assert options("Documents") == [AGENT, DOCS]  # 3 B actifs
    assert options("Conversation") == [AGENT, DOCS, SMALL]


def test_choosing_a_default_writes_it_and_reverting_clears_it(models, manage_server):
    row = default_row(models, "Documents")
    row.get_by_role("button", name=re.compile("^Changer")).click()
    picker = row.locator("wl-model-picker")
    picker.get_by_role("combobox").click()
    picker.get_by_role("option", name=re.compile(DOCS)).click()
    row.get_by_role("button", name=re.compile("^Enregistrer")).click()
    wait_notice(models, f"Modèle par défaut enregistré pour l'usage Documents{NBSP}: {DOCS}.")
    row = default_row(models, "Documents")
    assert DOCS in row.locator("td").nth(0).inner_text()
    assert row.locator("td").nth(1).inner_text() == "Choisi par vous"
    stored = call(manage_server, "GET", "/api/models/defaults?purpose=rag")[1]
    assert (stored["tags"], stored["source"]) == ([DOCS], "preference")
    # Un autre usage garde la règle ; « Revenir » n'existe que pour le choix de la personne.
    assert (
        default_row(models, "Conversation").locator("td").nth(1).inner_text() != "Choisi par vous"
    )
    assert (
        models.locator(".models-defaults")
        .get_by_role("button", name=re.compile("^Revenir"))
        .count()
        == 1
    )
    row.get_by_role("button", name=re.compile("^Revenir au choix automatique")).click()
    wait_notice(models, "Choix automatique rétabli pour l'usage Documents.")
    assert "Choisi par vous" not in models.locator(".models-defaults").inner_text()
    assert call(manage_server, "GET", "/api/models/defaults?purpose=rag")[1]["source"] == "rule"
    assert (
        default_row(models, "Documents")
        .get_by_role("button", name=re.compile("^Changer"))
        .evaluate("(button) => document.activeElement === button")
    )  # le focus revient au bouton « Changer »


def test_cancelling_a_change_writes_nothing(models, manage_server):
    row = default_row(models, "Documents")
    row.get_by_role("button", name=re.compile("^Changer")).click()
    row.locator("wl-model-picker").get_by_role("combobox").click()
    row.locator("wl-model-picker").get_by_role("option", name=re.compile(DOCS)).click()
    row.get_by_role("button", name=re.compile("^Annuler")).click()
    assert row.locator("wl-model-picker").count() == 0
    assert call(manage_server, "GET", "/api/models/defaults?purpose=rag")[1]["source"] == "rule"


def test_the_arena_asks_for_two_or_three_models(models, manage_server):
    row = default_row(models, "Arène")
    row.get_by_role("button", name=re.compile("^Changer")).click()
    picker = row.locator("wl-model-picker")
    while picker.locator(".wl-picker-chip-remove").count():
        picker.locator(".wl-picker-chip-remove").first.click()  # on repart de zéro, puis un seul
    picker.get_by_role("combobox").click()
    picker.get_by_role("option", name=re.compile(AGENT)).click()
    row.get_by_role("button", name=re.compile("^Enregistrer")).click()
    warning = row.locator(".models-default-editor > wl-error")
    warning.wait_for()
    assert warning.inner_text().startswith("Choisissez 2 ou 3 modèles avant d'enregistrer.")
    assert call(manage_server, "GET", "/api/models/defaults?purpose=arena")[1]["source"] == "rule"
    picker.get_by_role("combobox").click()  # la liste s'est refermée avec le focus
    picker.get_by_role("option", name=re.compile(DOCS)).click()
    row.get_by_role("button", name=re.compile("^Enregistrer")).click()
    wait_for(models, "() => !document.querySelector('.models-defaults wl-model-picker')")
    stored = call(manage_server, "GET", "/api/models/defaults?purpose=arena")[1]
    assert (sorted(stored["tags"]), stored["source"]) == ([AGENT, DOCS], "preference")


# --- Supprimer ------------------------------------------------------------------------------------


def test_deleting_asks_first_with_the_focus_on_cancel_then_removes_the_model(
    models, manage_server, ollama
):
    delete_button(models, SMALL).click()
    dialog = models.locator("wl-confirm-dialog dialog[open]")
    dialog.wait_for()
    assert dialog.locator("h2").inner_text() == f"Supprimer {SMALL}{NBSP}?"
    assert dialog.locator(".wl-dialog-consequence").inner_text() == (
        f"{SMALL} sera supprimé de ce poste (1{NBSP}Go libérés)."
    )
    assert models.evaluate("() => document.activeElement.textContent") == "Annuler"
    dialog.get_by_role("button", name="Annuler").click()
    assert (
        ollama.deleted == [] and installed_row(models, SMALL).count() == 1
    )  # « Annuler » ne supprime rien
    assert delete_button(models, SMALL).evaluate("(button) => document.activeElement === button")
    delete_button(models, SMALL).click()
    dialog.wait_for()
    dialog.get_by_role("button", name="Supprimer le modèle").click()
    wait_notice(models, f"Modèle supprimé{NBSP}: {SMALL} (1{NBSP}Go libérés).")
    assert ollama.deleted == [SMALL]
    wait_for(models, f"() => !document.querySelector('.models-delete[data-tag=\"{SMALL}\"]')")
    assert installed_row(models, SMALL).count() == 0 and installed_row(models, AGENT).count() == 1
    tags = [m["tag"] for m in call(manage_server, "GET", "/api/models")[1]["models"]]
    assert SMALL not in tags
    assert models.evaluate("() => document.activeElement.id") == "models-installed-title"


def test_the_dialog_names_the_purposes_whose_default_is_the_model(models, manage_server):
    call(manage_server, "PUT", "/api/models/defaults/agent", {"tags": [AGENT]})
    call(manage_server, "PUT", "/api/models/defaults/rag", {"tags": [AGENT]})
    models.reload()
    wait_ready(models)
    wait_for(models, "() => document.querySelectorAll('.models-defaults tbody tr').length === 5")
    wait_for(models, "() => document.body.innerText.includes('Choisi par vous')")
    delete_button(models, AGENT).click()
    dialog = models.locator("wl-confirm-dialog dialog[open]")
    dialog.wait_for()
    consequence = dialog.locator(".wl-dialog-consequence").inner_text()
    assert consequence == (
        f"{AGENT} sera supprimé de ce poste (4{NBSP}Go libérés). "
        f"C'est le modèle par défaut pour{NBSP}: Agent et Documents. "
        "Ces usages reviendront à la règle automatique."
    )
    dialog.get_by_role("button", name="Annuler").click()
    # Un modèle qui n'est pas un défaut choisi ne porte pas cette phrase.
    delete_button(models, DOCS).click()
    dialog.wait_for()
    assert "par défaut" not in dialog.locator(".wl-dialog-consequence").inner_text()
    dialog.get_by_role("button", name="Annuler").click()


def test_a_chosen_default_that_is_deleted_falls_back_to_the_rule(models, manage_server, ollama):
    call(manage_server, "PUT", "/api/models/defaults/agent", {"tags": [AGENT]})
    models.reload()
    wait_ready(models)
    wait_for(models, "() => document.body.innerText.includes('Choisi par vous')")
    delete_button(models, AGENT).click()
    dialog = models.locator("wl-confirm-dialog dialog[open]")
    dialog.wait_for()
    dialog.get_by_role("button", name="Supprimer le modèle").click()
    wait_for(models, "() => !document.body.innerText.includes('Choisi par vous')")
    assert ollama.deleted == [AGENT]
    agent = call(manage_server, "GET", "/api/models/defaults?purpose=agent")[1]
    assert agent["source"] == "rule" and AGENT not in agent["tags"] and agent["reason"]
    row = default_row(models, "Agent")
    assert agent["reason"] in row.inner_text()  # la raison de la règle est dite à l'écran
    assert row.get_by_role("button", name=re.compile("^Revenir")).count() == 0


def test_a_model_used_by_a_run_cannot_be_deleted_and_says_why(models, manage_server, ollama):
    run_id = hold_in_use(manage_server, ollama, AGENT)
    try:
        wait_for(
            models,
            f"() => document.querySelector('.models-delete[data-tag=\"{AGENT}\"]').getAttribute('aria-disabled') === 'true'",
        )
        row = installed_row(models, AGENT)
        assert row.locator(".models-legend").inner_text() == "Utilisé par une réponse en cours"
        button = delete_button(models, AGENT)
        assert button.get_attribute("aria-describedby") == row.locator(
            ".models-legend"
        ).get_attribute("id")
        button.click(force=True)  # `aria-disabled` : le clic ne fait rien, ni dialogue ni appel
        assert models.locator("wl-confirm-dialog dialog[open]").count() == 0
        assert call(manage_server, "DELETE", f"/api/models/{AGENT}")[0] == 409
        # Un autre modèle reste supprimable pendant ce run.
        assert delete_button(models, DOCS).get_attribute("aria-disabled") == "false"
    finally:
        release(manage_server, run_id)
    wait_for(
        models,
        f"() => document.querySelector('.models-delete[data-tag=\"{AGENT}\"]').getAttribute('aria-disabled') === 'false'",
    )
    assert models.locator(".models-installed .models-legend").count() == 0


def test_a_run_that_starts_while_the_dialog_is_open_is_refused_by_the_server(
    models_lenient, manage_server, ollama
):
    models = models_lenient
    delete_button(models, AGENT).click()
    dialog = models.locator("wl-confirm-dialog dialog[open]")
    dialog.wait_for()
    run_id = hold_in_use(manage_server, ollama, AGENT)  # le run démarre après l'ouverture
    try:
        dialog.get_by_role("button", name="Supprimer le modèle").click()
        models.locator("wl-error:not([hidden])").first.wait_for()
        wait_for(
            models, "() => document.body.innerText.includes('est employé par une réponse en cours')"
        )
        assert ollama.deleted == []
        assert installed_row(models, AGENT).count() == 1  # la liste est inchangée
    finally:
        release(manage_server, run_id)


# --- Décharger ------------------------------------------------------------------------------------


def test_unload_frees_the_idle_models_and_the_column_and_memory_follow_the_stream(
    models, manage_server, ollama
):
    ollama.loaded = [AGENT, DOCS]
    wait_for(
        models,
        "() => [...document.querySelectorAll('.models-installed tbody tr')].filter((r) => r.cells[6]?.textContent === 'Oui').length === 2",
    )
    button = models.get_by_role("button", name="Décharger les modèles inactifs")
    assert button.get_attribute("aria-disabled") == "false"
    button.click()
    wait_notice(models, "2 modèles déchargés.")
    assert sorted(ollama.unloaded) == sorted([AGENT, DOCS]) and ollama.loaded == []
    wait_for(
        models,
        "() => [...document.querySelectorAll('.models-installed tbody tr')].every((r) => r.cells[6]?.textContent === 'Non')",
    )
    assert button.get_attribute("aria-disabled") == "true"
    assert (
        models.locator("#models-unload-reason").inner_text()
        == "Aucun modèle n'est chargé en mémoire."
    )
    assert button.get_attribute("aria-describedby") == "models-unload-reason"


def test_unload_keeps_a_model_a_run_uses_and_is_disabled_when_all_are_in_use(
    models_lenient, manage_server, ollama
):
    models = models_lenient
    ollama.loaded = [AGENT]
    run_id = hold_in_use(manage_server, ollama, AGENT)
    try:
        button = models.get_by_role("button", name="Décharger les modèles inactifs")
        wait_for(
            models,
            "() => document.getElementById('models-unload-reason').textContent === 'Tous les modèles chargés servent à une réponse en cours.'",
        )
        assert button.get_attribute("aria-disabled") == "true"
        ollama.loaded = [AGENT, DOCS]  # un second modèle chargé, lui inactif
        wait_for(
            models,
            "() => document.querySelector('.models-unload-box button').getAttribute('aria-disabled') === 'false'",
        )
        button.click()
        wait_notice(
            models,
            f"1 modèle déchargé. Gardé en mémoire, une réponse en cours l'emploie{NBSP}: {AGENT}.",
        )
        assert ollama.unloaded == [DOCS] and ollama.loaded == [AGENT]
    finally:
        release(manage_server, run_id)


# --- Accessibilité --------------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_nothing_on_the_lists_the_editor_and_the_dialog(models, theme):
    models.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(models, f"écran Modèles, thème {theme}")
    row = default_row(models, "Agent")
    row.get_by_role("button", name=re.compile("^Changer")).click()
    row.locator("wl-model-picker").get_by_role("combobox").click()
    assert_no_axe_violations(models, f"sélecteur d'un défaut, thème {theme}")
    row.get_by_role("button", name=re.compile("^Annuler")).click()
    delete_button(models, SMALL).click()
    models.locator("wl-confirm-dialog dialog[open]").wait_for()
    assert_no_axe_violations(models, f"dialogue de suppression, thème {theme}")
    models.get_by_role("button", name="Annuler").click()


def test_the_new_actions_stay_in_reach_at_320_px(models):
    models.set_viewport_size({"width": 320, "height": 800})
    overflow = models.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, f"défilement horizontal de {overflow} px"
    assert models.get_by_role("button", name="Décharger les modèles inactifs").is_visible()


def test_reading_the_screen_never_deletes_anything(models, manage_server, ollama):
    calls = []
    models.on("request", lambda request: calls.append((request.method, request.url)))
    models.reload()
    wait_ready(models)
    wait_for(models, "() => document.querySelectorAll('.models-defaults tbody tr').length === 5")
    writes = [(m, u) for m, u in calls if m not in {"GET", "HEAD"} and "/api/" in u]
    assert writes == [] and ollama.deleted == [] and ollama.unloaded == []
