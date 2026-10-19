"""Écran Modèles, installation (story 5.3) dans un vrai navigateur, sur le vrai serveur.

Aucun vrai téléchargement : le serveur de l'application parle à un faux Ollama HTTP local
(`ThreadedOllama`), qui joue `/api/pull` pas à pas sous la main du test. Les listes `GET /api/models`
et `GET /api/models/catalog` sont simulées dans le navigateur (la mémoire du poste ferait varier
`fits` d'une machine à l'autre) ; leur calcul est prouvé côté serveur
(`tests/v2/web/test_models_install_api.py`). Ce qu'on prouve ici : ce que l'écran en fait.
"""

from __future__ import annotations

import json
import re
import threading

import pytest

from ..conftest import closed_port
from ..pull_fake import GB, ThreadedOllama, layer, manifest
from .conftest import Backend
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
CATALOG = [
    {"tag": "small:1b", "name": "Petit 1B", "params_total_b": 1.0, "params_active_b": 1.0,
     "needed_gb": 1.0, "required_gb": 1.6, "fits": True, "short_gb": None},
    {"tag": "mid:7b", "name": "Moyen 7B", "params_total_b": 7.0, "params_active_b": 7.0,
     "needed_gb": 5.0, "required_gb": 6.0, "fits": True, "short_gb": None},
    {"tag": "moe:30b", "name": "MoE 30B", "params_total_b": 30.0, "params_active_b": 3.0,
     "needed_gb": 20.0, "required_gb": 22.5, "fits": False, "short_gb": 17.7},
]  # fmt: skip
NAMES = {row["tag"]: row["name"] for row in CATALOG}  # le registre nomme un modèle du catalogue
FREE_GB = 4.8


@pytest.fixture(scope="module")
def ollama():
    fake = ThreadedOllama(closed_port())
    fake.start()
    yield fake
    fake.stop()


@pytest.fixture(scope="module")
def models_server(tmp_path_factory, ollama):
    backend = Backend(tmp_path_factory.mktemp("e2e-models"), ollama_port=ollama.port)
    try:
        yield backend.start()
    finally:
        backend.stop()


def installed_listing(ollama: ThreadedOllama) -> dict:
    models = [
        {
            "tag": tag, "name": NAMES.get(tag, tag), "provider": "ollama", "origin": "local", "kind": "chat",
            "available": True, "params_total_b": 1.5, "params_active_b": 1.5,
            "size_gb": round(size / GB, 3), "fits": True, "short_gb": None, "required_gb": 2.0,
            "throughput_tps": None, "co2_method": "codecarbon",
        }
        for tag, size in sorted(ollama.sizes.items())
    ]  # fmt: skip
    return {"models": models, "ollama_up": True, "refreshed_at": "2026-10-19T10:00:00Z"}


def catalog_listing(ollama: ThreadedOllama) -> dict:
    rows = [row for row in CATALOG if row["tag"] not in ollama.sizes]
    return {"models": rows, "ollama_up": True, "free_gb": FREE_GB}


def open_models(page, models_server, ollama):
    """L'écran Modèles ouvert, Ollama simulé avec un seul modèle installé."""
    ollama.reset({"here:2b": GB * 2})
    page.route(
        re.compile(r"/api/models\?"),
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(installed_listing(ollama))
        ),
    )
    page.route(
        re.compile(r"/api/models/defaults\?"),
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "purpose": "chat",
                    "tags": ["here:2b"],
                    "reason": "Règle.",
                    "source": "rule",
                    "eligible": ["here:2b"],
                    "inactive": [],
                }
            ),
        ),
    )
    page.route(
        re.compile(r"/api/models/catalog$"),
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(catalog_listing(ollama))
        ),
    )
    page.goto(f"{models_server.base_url}/#/modeles")
    wait_ready(page)
    page.locator("wl-data-table").nth(1).wait_for()
    wait_for(page, "() => document.querySelectorAll('.models-catalog tbody tr').length > 0")
    return page


@pytest.fixture
def models(page, models_server, ollama):
    return open_models(page, models_server, ollama)


@pytest.fixture
def models_lenient(page_tolerating_failed_requests, models_server, ollama):
    """Comme `models`, pour un test dont une requête échoue exprès (le `409` de `run_busy` : le
    navigateur le dit en console)."""
    return open_models(page_tolerating_failed_requests, models_server, ollama)


def catalog_row(page, tag: str):
    return page.locator(".models-catalog tbody tr").filter(
        has=page.locator(f'code:text-is("{tag}")')
    )


def install_button(page, tag: str):
    return page.locator(f'.models-install[data-tag="{tag}"]')


def progress_text(page, tag: str) -> str:
    return catalog_row(page, tag).locator(".wl-progress-text").inner_text()


def wait_notice(page, text: str) -> None:
    wait_for(
        page,
        f"() => document.querySelector('.models-notice').textContent === {json.dumps(text)}",
    )


# --- Écran ----------------------------------------------------------------------------------------


def test_the_screen_lists_what_is_installed_and_what_can_be_installed(models):
    assert models.get_by_role("heading", level=1).inner_text() == "Modèles"
    assert models.title() == "Modèles · WaveLocalAI"
    assert [h.inner_text() for h in models.locator("h2:not(.wl-dialog-title)").all()] == [
        "Sur ce poste",
        "Modèles proposés par défaut",
        "Reclassement des extraits",
        "Catalogue installable",
    ]
    installed = models.locator(".models-installed tbody tr")
    assert installed.count() == 1 and "here:2b" in installed.first.inner_text()
    headers = models.locator(".models-installed thead th").all_inner_texts()
    assert headers == [
        "Nom", "Origine", "Usage", "Paramètres", "Taille", "Tient en mémoire", "Chargé",
        "Débit sur ce poste", "Actions",
    ]  # fmt: skip
    cells = installed.first.locator("td").all_inner_texts()
    assert cells[2] == f"1,5{NBSP}B" and cells[3] == f"2{NBSP}Go"
    assert cells[4] == "Oui" and cells[5] == "Non" and cells[6] == "non mesuré"

    assert models.locator(".models-catalog thead th").all_inner_texts() == [
        "Nom", "Paramètres", "Mémoire nécessaire", "Tient en mémoire", "Installation",
    ]  # fmt: skip
    rows = models.locator(".models-catalog tbody tr")
    assert rows.count() == len(CATALOG)
    moe = catalog_row(models, "moe:30b").locator("td").all_inner_texts()
    assert moe[0] == f"30{NBSP}B · 3{NBSP}B actifs"
    assert moe[1] == f"22,5{NBSP}Go"
    assert moe[2] == f"Ne tient pas{NBSP}: 22,5{NBSP}Go nécessaires, 4,8{NBSP}Go libres"
    assert catalog_row(models, "mid:7b").locator("td").all_inner_texts()[2] == "Oui"


def test_a_model_that_does_not_fit_stays_installable_with_an_install_anyway_button(models):
    button = install_button(models, "moe:30b")
    assert button.inner_text() == "Installer quand même"
    assert (
        button.get_attribute("aria-label")
        == f"Installer moe:30b quand même{NBSP}: il ne tient pas dans la mémoire libre"
    )
    assert button.get_attribute("aria-disabled") == "false"
    fits = install_button(models, "mid:7b")
    assert fits.inner_text() == "Installer"
    assert fits.get_attribute("aria-label") == "Installer mid:7b"


def test_installing_from_the_catalog_shows_the_bytes_then_installed_and_moves_the_row(
    models, ollama
):
    resume = threading.Event()
    ollama.scripts.append(
        [
            manifest(),
            layer("sha256:aaaa1111bbbb", 4 * GB, 0),
            layer("sha256:aaaa1111bbbb", 4 * GB, 2 * GB),
            resume,
            layer("sha256:aaaa1111bbbb", 4 * GB, 4 * GB),
            {"status": "verifying sha256 digest"},
            {"status": "success"},
        ]
    )
    install_button(models, "mid:7b").click()
    expected = f"Téléchargement 2{NBSP}Go sur 4{NBSP}Go · 50{NBSP}%"
    wait_for(
        models,
        f"() => document.querySelector('.models-catalog .wl-progress-text')?.textContent === {json.dumps(expected)}",
    )
    bar = catalog_row(models, "mid:7b").locator("progress")
    assert bar.get_attribute("value") == "50"
    assert bar.get_attribute("aria-label") == "Installation de Moyen 7B"
    cancel = catalog_row(models, "mid:7b").get_by_role(
        "button", name="Annuler l'installation de Moyen 7B"
    )
    assert cancel.is_visible()

    # Les autres « Installer » sont désactivés avec leur raison visible, mais focalisables.
    other = install_button(models, "small:1b")
    assert other.get_attribute("aria-disabled") == "true"
    other.focus()
    assert other.evaluate("el => el === document.activeElement")
    reason = models.locator("#models-catalog-reason")
    assert reason.inner_text() == "Une installation est en cours (mid:7b)."
    assert other.get_attribute("aria-describedby") == "models-catalog-reason"
    other.dispatch_event("click")  # sans effet (Playwright ne clique pas un `aria-disabled`)
    assert ollama.pull_requests == ["mid:7b"]
    assert (
        models.locator("#models-install-reason").inner_text()
        == "Une installation est en cours (mid:7b)."
    )
    assert models.locator(".models-install-named").get_attribute("aria-disabled") == "true"

    resume.set()
    wait_notice(models, "Moyen 7B installé.")
    wait_for(models, "() => document.querySelectorAll('.models-installed tbody tr').length === 2")
    assert catalog_row(models, "mid:7b").count() == 0  # la ligne a rejoint « Sur ce poste »
    assert "mid:7b" in models.locator(".models-installed tbody").inner_text()
    assert install_button(models, "small:1b").get_attribute("aria-disabled") == "false"
    assert models.locator("#models-catalog-reason").is_hidden()


def test_installing_by_name_follows_a_model_outside_the_catalog(models, ollama):
    resume = threading.Event()
    ollama.scripts.append(
        [manifest(), layer("sha256:cccc", 1 * GB, GB // 2), resume, {"status": "success"}]
    )
    models.get_by_label("Installer un modèle par son nom").fill("  perso:3b ")
    models.get_by_role("button", name="Installer le modèle saisi").click()
    panel = models.locator(".models-pull-panel")
    wait_for(
        models,
        "() => /Téléchargement/.test(document.querySelector('.models-pull-panel .wl-progress-text')?.textContent ?? '')",
    )
    assert panel.locator(".wl-progress-text").inner_text() == (
        f"Téléchargement 0,5{NBSP}Go sur 1{NBSP}Go · 50{NBSP}%"
    )
    assert ollama.pull_requests == ["perso:3b"]
    resume.set()
    wait_notice(models, "perso:3b installé.")
    assert panel.inner_text() == "Installé"
    wait_for(models, "() => document.querySelectorAll('.models-installed tbody tr').length === 2")


def test_an_empty_name_is_not_sent(models, ollama):
    models.get_by_role("button", name="Installer le modèle saisi").click()
    wait_notice(models, "Saisissez le nom d'un modèle pour l'installer.")
    assert ollama.pull_requests == []


def test_an_installed_name_is_not_downloaded_again(models, ollama):
    models.get_by_label("Installer un modèle par son nom").fill("here:2b")
    models.get_by_role("button", name="Installer le modèle saisi").click()
    wait_notice(models, "here:2b est déjà installé sur ce poste.")
    assert ollama.pull_requests == []


# --- Annulation, échecs, reprise ------------------------------------------------------------------


def test_cancelling_stops_the_download_and_leaves_the_list_unchanged(models, ollama):
    ollama.scripts.append([manifest(), layer("sha256:dddd", 4 * GB, GB), "hang"])
    install_button(models, "mid:7b").click()
    wait_for(
        models,
        "() => /Téléchargement/.test(document.querySelector('.models-catalog .wl-progress-text')?.textContent ?? '')",
    )
    catalog_row(models, "mid:7b").get_by_role(
        "button", name="Annuler l'installation de Moyen 7B"
    ).click()
    wait_notice(models, "Installation de Moyen 7B annulée. La liste des modèles est inchangée.")
    assert install_button(models, "mid:7b").get_attribute("aria-disabled") == "false"
    assert models.locator(".models-installed tbody tr").count() == 1
    wait_for_dropped(ollama)


def wait_for_dropped(ollama, timeout_s: float = 5.0) -> None:
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if ollama.pull_dropped >= 1:
            return
        time.sleep(0.05)
    pytest.fail("Ollama n'a pas vu le flux se fermer")


def test_a_name_that_does_not_exist_ends_in_pull_failed_in_the_row(models, ollama):
    ollama.scripts.append([manifest(), {"error": "pull model manifest: file does not exist"}])
    install_button(models, "small:1b").click()
    error = catalog_row(models, "small:1b").locator("wl-error")
    error.wait_for()
    assert error.get_attribute("data-code") == "pull_failed"
    assert error.locator(".wl-error-message").inner_text() == (
        "Le modèle small:1b n'a pas pu être installé : ce nom n'existe pas dans le registre d'Ollama."
    )
    assert "La liste des modèles est inchangée." in error.locator(".wl-error-action").inner_text()
    assert models.locator(".models-installed tbody tr").count() == 1  # liste inchangée
    assert install_button(models, "small:1b").get_attribute("aria-disabled") == "false"
    wait_notice(models, error.locator(".wl-error-message").inner_text())


def test_ollama_stopping_in_the_middle_ends_in_pull_failed_ollama_down(models, ollama):
    ollama.scripts.append([manifest(), layer("sha256:eeee", 4 * GB, GB), "cut"])
    install_button(models, "mid:7b").click()
    error = catalog_row(models, "mid:7b").locator("wl-error")
    error.wait_for()
    assert "Ollama ne répond plus" in error.locator(".wl-error-message").inner_text()
    assert 'cause : "ollama_down"' in error.locator(".wl-error-technical").text_content()


def test_leaving_the_screen_and_coming_back_resumes_the_progress(models, ollama, models_server):
    resume = threading.Event()
    ollama.scripts.append(
        [
            manifest(),
            layer("sha256:ffff", 4 * GB, GB),
            resume,
            layer("sha256:ffff", 4 * GB, 3 * GB),
            {"status": "success"},
        ]
    )
    install_button(models, "mid:7b").click()
    wait_for(
        models,
        "() => /25/.test(document.querySelector('.models-catalog .wl-progress-text')?.textContent ?? '')",
    )
    models.evaluate("location.hash = '#/'")
    wait_for(models, "() => document.querySelector('[data-screen=\"models\"]').hidden")
    resume.set()
    models.evaluate("location.hash = '#/modeles'")
    wait_notice(models, "Moyen 7B installé.")
    assert catalog_row(models, "mid:7b").count() == 0
    assert ollama.pull_requests == ["mid:7b"]  # une seule demande à Ollama


def test_a_page_reloaded_during_an_install_rejoins_it(models, ollama, models_server):
    resume = threading.Event()
    ollama.scripts.append(
        [manifest(), layer("sha256:aabb", 4 * GB, 2 * GB), resume, {"status": "success"}]
    )
    install_button(models, "mid:7b").click()
    wait_for(
        models,
        "() => /50/.test(document.querySelector('.models-catalog .wl-progress-text')?.textContent ?? '')",
    )
    models.reload()
    wait_ready(models)
    # Le flux système dit qu'un run `pull` est actif : l'écran le rejoint, tag compris.
    wait_for(
        models,
        "() => /50/.test(document.querySelector('.models-catalog .wl-progress-text')?.textContent ?? '')",
        timeout_s=15,
    )
    resume.set()
    wait_for(models, "() => document.querySelectorAll('.models-installed tbody tr').length === 2")


def test_a_second_install_while_one_runs_joins_it_without_an_error(models_lenient, ollama):
    models = models_lenient
    resume = threading.Event()
    ollama.scripts.append(
        [manifest(), layer("sha256:ccdd", 4 * GB, GB), resume, {"status": "success"}]
    )
    models.evaluate(
        """async () => {
            await fetch('/api/models/pull', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tag: 'mid:7b' }),
            });
            const input = document.getElementById('models-install-name');
            input.value = 'small:1b';
            input.form.requestSubmit();
        }"""
    )
    wait_for(
        models,
        "() => /Téléchargement/.test(document.querySelector('.models-catalog .wl-progress-text')?.textContent ?? '')",
    )
    assert models.locator("wl-error:visible").count() == 0
    assert ollama.pull_requests == ["mid:7b"]
    resume.set()
    wait_for(models, "() => document.querySelectorAll('.models-installed tbody tr').length === 2")


# --- Mise en page, charte, accessibilité ----------------------------------------------------------


def test_usage_and_origin_columns_fold_under_1024_px_and_a_button_shows_them(models):
    toggle = models.locator(".models-toggle")
    assert toggle.inner_text(timeout=2000) == "Afficher les colonnes Usage et Origine"
    assert toggle.is_hidden()  # large : toutes les colonnes sont là
    assert models.locator(".models-installed th.models-secondary").first.is_visible()
    models.set_viewport_size({"width": 900, "height": 800})
    assert toggle.is_visible()
    assert models.locator(".models-installed th.models-secondary").first.is_hidden()
    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "true"
    assert models.locator(".models-installed th.models-secondary").first.is_visible()
    models.get_by_role("button", name="Replier les colonnes Usage et Origine").click()
    assert models.locator(".models-installed th.models-secondary").first.is_hidden()


def test_the_screen_fits_a_phone_width_without_horizontal_scroll_of_the_page(models):
    models.set_viewport_size({"width": 320, "height": 800})
    overflow = models.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_nothing_on_the_lists_the_progress_and_the_error(models, ollama, theme):
    models.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(models, f"listes, thème {theme}")
    resume = threading.Event()
    ollama.scripts.append(
        [manifest(), layer("sha256:9999", 4 * GB, GB), resume, {"status": "success"}]
    )
    install_button(models, "mid:7b").click()
    wait_for(
        models,
        "() => /Téléchargement/.test(document.querySelector('.models-catalog .wl-progress-text')?.textContent ?? '')",
    )
    assert_no_axe_violations(models, f"installation en cours, thème {theme}")
    resume.set()
    wait_notice(models, "Moyen 7B installé.")
    ollama.scripts.append([{"error": "pull model manifest: file does not exist"}])
    install_button(models, "small:1b").click()
    catalog_row(models, "small:1b").locator("wl-error").wait_for()
    assert_no_axe_violations(models, f"échec, thème {theme}")


def test_the_filled_install_button_uses_primary_fill_with_white_text(models):
    style = models.locator(".models-install-named").evaluate(
        "n => { const s = getComputedStyle(n); return [s.backgroundColor, s.color]; }"
    )
    assert style == ["rgb(69, 29, 199)", "rgb(255, 255, 255)"]


def test_no_api_call_leaves_before_the_shell_is_ready(page, models_server, ollama):
    ollama.reset({"here:2b": GB})
    page.add_init_script(
        """(() => {
            const original = window.fetch.bind(window);
            window.__apiCalls = [];
            window.fetch = (input, init) => {
                const url = String(input instanceof Request ? input.url : input);
                if (url.includes('/api/')) window.__apiCalls.push({
                    url, ready: performance.getEntriesByName('shell-ready').length > 0,
                });
                return original(input, init);
            };
        })()"""
    )
    page.goto(f"{models_server.base_url}/#/modeles")
    wait_ready(page)
    wait_for(
        page, "() => window.__apiCalls.some((call) => call.url.includes('/api/models/catalog'))"
    )
    calls = page.evaluate("() => window.__apiCalls")
    assert calls and all(call["ready"] for call in calls), calls
    assert not any("/api/models/pull" in call["url"] for call in calls)  # lire ne télécharge pas


def test_reading_the_screen_never_asks_ollama_to_pull(models, ollama):
    page = models
    page.reload()
    wait_ready(page)
    page.locator("wl-data-table").nth(1).wait_for()
    assert ollama.pull_requests == []
