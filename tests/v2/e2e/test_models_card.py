"""Fiche d'un modèle (story 5.6) dans un vrai navigateur, sur le vrai serveur : `#/modeles/<tag>`,
« Pourquoi ce débit ? », « Sur d'autres postes » (résultats `qb.results/1` d'une fixture copiée en
dossier temporaire, aucun fichier de `benchmarks/` du dépôt), et le bouton « Fiche du modèle » à
côté d'un `wl-model-picker`. Ollama est un faux HTTP local (`ThreadedOllama`)."""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

import pytest

from ..conftest import closed_port
from ..pull_fake import GB, ThreadedOllama
from .conftest import Backend
from .test_shell import assert_no_axe_violations, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
FIXTURE = Path(__file__).parent.parent / "fixtures" / "slm-quality-results.sample.json"
AGENT = "agentmodel:7b"  # mêmes poids que le banc : résultats exacts
DOCS = "docmodel:4b"  # autre empreinte que celle du banc : « autre version »
SMALL = "smallmodel:1b"  # résultats `null` côté banc
HF = "hf.co/acme/depot:Q4_K_M"  # un tag avec des `/`
BIG = "bigmodel:70b"  # au catalogue seulement, trop gros pour ce poste
UNPUBLISHED = "unpublished:3b"
INSTALLED = {AGENT: 4 * GB, DOCS: 2 * GB, SMALL: GB, HF: 3 * GB, UNPUBLISHED: GB}
RENAMES = {"mid:7b": AGENT, "other:4b": DOCS, "small:1b": SMALL, "grand:14b": BIG}
CATALOG = {
    "models": {
        "Gros 70B": {
            "ollama_tag": BIG, "size_gb": "900 GB", "params_tot": "70B", "params_act": "70B",
            "capabilities": ["chat", "tools"], "moe": False, "ctx": 131072,
        },
    }
}  # fmt: skip


def _results(path: Path) -> None:
    """La fixture, ses tags remplacés par ceux du faux Ollama (empreintes `d-<tag>`, sauf l'« autre
    version »)."""
    text = FIXTURE.read_text(encoding="utf-8")
    for old, new in RENAMES.items():
        text = text.replace(f'"d-{old}"', f'"d-{new}"').replace(f'"{old}"', f'"{new}"')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(scope="module")
def ollama():
    fake = ThreadedOllama(closed_port())
    fake.start()
    yield fake
    fake.stop()


@pytest.fixture(scope="module")
def card_server(tmp_path_factory, ollama):
    root = tmp_path_factory.mktemp("e2e-card")
    (root / "reglages.toml").write_text("[ollama]\nprobe_cache_s = 0.2\n", encoding="utf-8")
    (root / "config").mkdir()
    (root / "config" / "models_catalog.json").write_text(json.dumps(CATALOG), encoding="utf-8")
    _results(root / "benchmarks" / "slm-quality" / "slm-quality-results.json")
    ollama.reset(INSTALLED)
    ollama.params = {AGENT: "7B", DOCS: "4B", SMALL: "1B", HF: "3B", UNPUBLISHED: "3B"}
    ollama.tools = {AGENT}
    (root / "data").mkdir()
    backend = Backend(root / "data", ollama_port=ollama.port, config=root / "reglages.toml")
    try:
        server = backend.start()
        server.root = root
        yield server
    finally:
        backend.stop()


def results_file(server) -> Path:
    return server.root / "benchmarks" / "slm-quality" / "slm-quality-results.json"


@pytest.fixture
def results_restored(card_server):
    """Le fichier des résultats remis à l'identique après un test qui l'a retiré ou changé."""
    path = results_file(card_server)
    saved = path.read_bytes()
    yield path
    path.write_bytes(saved)


def open_card(page, server, tag: str) -> None:
    page.goto(f"{server.base_url}/#/modeles/{urllib.parse.quote(tag, safe='')}")
    wait_ready(page)
    wait_for(page, "() => !!document.querySelector('.models-fiche h2.models-card-title')")


@pytest.fixture
def models(page, card_server):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{card_server.base_url}/#/modeles")
    wait_ready(page)
    wait_for(
        page,
        f"() => document.querySelectorAll('.models-installed tbody tr').length === {len(INSTALLED)}",
    )
    return page


def fiche(page):
    return page.locator(".models-fiche")


def trait(page, term: str) -> str:
    return (
        fiche(page)
        .locator("dt", has_text=re.compile(f"^{term}$"))
        .locator("xpath=following-sibling::dd[1]")
        .inner_text()
    )


# --- Ouverture -----------------------------------------------------------------------------------


def test_clicking_a_model_opens_its_card_without_rebuilding_the_screen(models, card_server):
    models.locator(".models-layout").evaluate("layout => { layout.dataset.kept = 'yes' }")
    models.get_by_role("link", name=f"Fiche du modèle {AGENT}", exact=True).click()
    wait_for(models, "() => !!document.querySelector('.models-fiche h2.models-card-title')")
    assert models.url.endswith(f"#/modeles/{urllib.parse.quote(AGENT, safe='')}")
    assert fiche(models).locator("h2").inner_text() == AGENT
    # Le routeur a suivi l'adresse sans remonter l'écran : la disposition marquée est toujours là.
    assert models.locator(".models-layout[data-kept='yes']").count() == 1
    assert (
        models.get_by_role("link", name=f"Fiche du modèle {AGENT}", exact=True).get_attribute(
            "aria-current"
        )
        == "true"
    )
    # Le focus est sur le titre de la fiche.
    wait_for(models, "() => document.activeElement?.matches('.models-fiche h2')")


def test_the_card_opens_directly_from_the_address_even_with_slashes_in_the_tag(page, card_server):
    open_card(page, card_server, HF)
    assert fiche(page).locator("h2").inner_text() == HF
    assert "%2F" in page.url


def test_closing_the_card_goes_back_to_the_plain_list(models):
    models.get_by_role("link", name=f"Fiche du modèle {AGENT}", exact=True).click()
    wait_for(models, "() => !!document.querySelector('.models-fiche h2.models-card-title')")
    fiche(models).get_by_role("link", name="Fermer la fiche").click()
    wait_for(models, "() => document.querySelector('.models-fiche')?.hidden === true")
    assert models.url.endswith("#/modeles")


def test_an_unknown_tag_says_so_and_offers_the_way_back(
    page_tolerating_failed_requests, card_server
):
    page = page_tolerating_failed_requests  # le `404` de la fiche est attendu
    page.goto(f"{card_server.base_url}/#/modeles/inconnu%3A1b")
    wait_ready(page)
    wait_for(
        page, "() => document.querySelector('.models-fiche')?.textContent.includes('introuvable')"
    )
    assert f"«{NBSP}inconnu:1b{NBSP}» n'est ni installé" in fiche(page).inner_text()
    fiche(page).get_by_role("link", name="Retour à la liste des modèles").click()
    wait_for(page, "() => document.querySelector('.models-fiche')?.hidden === true")


# --- Caractéristiques ----------------------------------------------------------------------------


def test_the_card_shows_its_traits_and_says_unknown_for_a_missing_value(page, card_server):
    open_card(page, card_server, AGENT)
    assert trait(page, "Architecture") == "Dense"
    assert trait(page, "Quantification") == "Q4_K_M"
    assert trait(page, "Outils vérifiés") == "Oui"
    assert trait(page, "Raisonnement vérifié") == "Non"
    # Ni `/api/show` du faux Ollama ni le catalogue ne publient licence ni contexte : « inconnu ».
    assert trait(page, "Licence") == "inconnu"
    assert trait(page, "Contexte") == "inconnu"
    assert "0 tokens" not in fiche(page).inner_text()


def test_a_model_not_installed_that_does_not_fit_offers_to_install_it_anyway(page, card_server):
    open_card(page, card_server, BIG)
    text = fiche(page).inner_text()
    assert (
        "n'est pas installé sur ce poste" in text and "Ne tient pas dans la mémoire libre" in text
    )
    button = fiche(page).get_by_role("button", name="Installer quand même")
    assert button.is_visible() and button.get_attribute("aria-disabled") == "false"
    assert re.fullmatch(r"131.072\stokens", trait(page, "Contexte")), trait(page, "Contexte")
    fiche(page).locator("details[data-part='why'] summary").click()
    assert "Installez ce modèle pour mesurer son débit" in fiche(page).inner_text()


# --- Pourquoi ce débit ? -------------------------------------------------------------------------


def test_why_this_throughput_explains_the_speed_without_any_calculation_on_screen(
    page, card_server
):
    open_card(page, card_server, AGENT)
    why = fiche(page).locator("details[data-part='why']")
    why.locator("summary").click()
    text = why.inner_text()
    assert "Pourquoi ce débit" in text
    assert "milliards de paramètres à chaque token" in text
    assert "Quantification" in text and "bande passante mémoire" in text
    assert "Débit non mesuré sur ce poste" in text  # aucun run sur ce poste de test
    # Les phrases viennent du serveur : espace insécable avant « : », jamais d'espace simple.
    assert re.search(r" [:;!?]", text) is None


# --- Sur d'autres postes -------------------------------------------------------------------------


def others(page):
    box = fiche(page).locator("details[data-part='others']")
    if box.get_attribute("open") is None:
        box.locator("summary").click()
    return box


def test_other_posts_list_the_published_speed_memory_and_energy(page, card_server):
    open_card(page, card_server, AGENT)
    box = others(page)
    rows = box.locator("tbody tr")
    wait_for(page, "() => document.querySelectorAll('.models-fiche tbody tr').length === 3")
    assert "PC pro, 16 Go, sans GPU" in rows.nth(0).inner_text()  # le PC pro d'abord
    pc, portable, station = (rows.nth(i).inner_text() for i in range(3))
    assert f"5,2{NBSP}tokens/s" in pc and "non mesurée" in pc and "Sans carte graphique" in pc
    assert f"40{NBSP}%" in pc  # 6 Go sur 15 Go de mémoire vive : pourcentage, jamais une fraction
    assert f"18,4{NBSP}tokens/s" in portable and "0,42" in portable and f"100{NBSP}%" in portable
    assert "0,31" in station
    assert re.search(r"Source\s: slm-quality-bench, version 1\.4\.0", box.inner_text())
    assert "autre version" not in box.inner_text().lower()


def test_a_null_is_unknown_never_zero_and_unmeasured_energy_is_not_a_number(page, card_server):
    open_card(page, card_server, SMALL)
    rows = others(page).locator("tbody tr")
    wait_for(page, "() => document.querySelectorAll('.models-fiche tbody tr').length === 3")
    pc = rows.nth(0).inner_text()
    assert pc.count("inconnu") >= 2 and "0 tokens/s" not in pc
    assert "non validée" in pc  # énergie `unvalidated` : pas de valeur


def test_another_digest_says_the_published_figures_are_for_another_version(page, card_server):
    open_card(page, card_server, DOCS)
    box = others(page)
    wait_for(page, "() => document.querySelectorAll('.models-fiche tbody tr').length === 3")
    assert "Autre version" in box.inner_text() and "indicatives" in box.inner_text()
    assert f"25{NBSP}tokens/s" in box.inner_text()


def test_a_model_the_bench_does_not_measure_says_so(page, card_server):
    open_card(page, card_server, UNPUBLISHED)
    assert "n'est pas dans les résultats publiés" in others(page).inner_text()


def test_without_the_results_file_the_card_says_what_is_missing(
    page, card_server, results_restored
):
    results_restored.unlink()
    open_card(page, card_server, AGENT)
    text = others(page).inner_text()
    assert "Références indisponibles" in text and "pas synchronisé" in text
    assert "Les caractéristiques ci-dessus restent valables" in text
    assert fiche(page).locator("h2").inner_text() == AGENT  # le reste de la fiche s'affiche
    assert trait(page, "Architecture") == "Dense"


# --- Disposition ---------------------------------------------------------------------------------


def test_the_panel_is_on_the_right_from_1120_px_and_above_the_list_below(models):
    models.get_by_role("link", name=f"Fiche du modèle {AGENT}", exact=True).click()
    wait_for(models, "() => !!document.querySelector('.models-fiche h2.models-card-title')")
    boxes = models.evaluate(
        """() => {
          const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
          const f = rect('.models-fiche'), m = rect('.models-main');
          return { fx: f.left, fy: f.top, fb: f.bottom, mx: m.left, my: m.top };
        }"""
    )
    assert boxes["fx"] > boxes["mx"], boxes  # à droite
    models.set_viewport_size({"width": 1000, "height": 900})
    boxes = models.evaluate(
        """() => {
          const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
          const f = rect('.models-fiche'), m = rect('.models-main');
          return { fb: f.bottom, my: m.top };
        }"""
    )
    assert boxes["fb"] <= boxes["my"] + 1, boxes  # au-dessus de la liste
    models.set_viewport_size({"width": 320, "height": 800})
    overflow = models.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, f"défilement horizontal de {overflow} px"


# --- Bouton « Fiche du modèle » à côté du sélecteur ----------------------------------------------


def test_the_picker_has_a_card_button_that_opens_the_same_card_without_changing_the_address(
    page, card_server
):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{card_server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.loaded === true")
    wait_for(page, "() => !!document.querySelector('.models-card-open')")
    before = page.url
    button = page.locator(".models-card-open").first
    button.click()
    drawer = page.locator(".models-card-drawer")
    wait_for(page, "() => !!document.querySelector('.models-card-drawer h2.models-card-title')")
    assert page.url == before  # aucune navigation
    assert drawer.get_by_role("link", name="Ouvrir dans l'écran Modèles").is_visible()
    assert "Caractéristiques" in drawer.inner_text()
    wait_for(page, "() => document.activeElement?.matches('.models-card-drawer h2')")
    page.keyboard.press("Escape")
    wait_for(page, "() => !document.querySelector('.models-card-drawer')")
    assert page.evaluate("() => document.activeElement?.classList.contains('models-card-open')")


def test_the_card_button_is_outside_the_option_list(page, card_server):
    page.goto(f"{card_server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => !!document.querySelector('.models-card-open')")
    assert page.locator("wl-model-picker .models-card-open").count() == 0
    assert page.locator("[role='listbox'] .models-card-open").count() == 0


def test_the_card_button_follows_a_choice_made_by_code_and_a_moved_picker(page, card_server):
    """Revue : `picker.value = …` (garde-fou mémoire, reprise d'une configuration) ne lève aucun
    événement ; le bouton suit quand même le choix, et suit le sélecteur déplacé."""
    page.goto(f"{card_server.base_url}/#/arene/chat")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.loaded === true")
    wait_for(page, "() => !!document.querySelector('.models-card-open')")
    page.evaluate(f"() => {{ document.querySelector('wl-model-picker').value = '{SMALL}'; }}")
    wait_for(page, f"() => document.querySelector('.models-card-open')?.dataset.tag === '{SMALL}'")
    page.evaluate(
        """() => {
          const picker = document.querySelector('wl-model-picker');
          const place = document.createElement('div');
          place.id = 'moved-here';
          picker.closest('main, body').append(place);
          place.append(picker);
        }"""
    )
    wait_for(
        page,
        "() => document.querySelector('#moved-here wl-model-picker')"
        "?.nextElementSibling?.classList.contains('models-card-open-box')",
    )
    assert page.locator(".models-card-open-box").count() == page.locator("wl-model-picker").count()


# --- Accessibilité -------------------------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_nothing_on_the_open_card_and_the_picker_panel(page, card_server, theme):
    open_card(page, card_server, AGENT)
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    fiche(page).locator("details[data-part='why'] summary").click()
    others(page)
    wait_for(page, "() => document.querySelectorAll('.models-fiche tbody tr').length === 3")
    assert_no_axe_violations(page, f"fiche du modèle, thème {theme}")
    page.goto(f"{card_server.base_url}/#/modeles/{urllib.parse.quote(DOCS, safe='')}")
    others(page)
    wait_for(
        page, "() => document.querySelector('.models-fiche')?.textContent.includes('Autre version')"
    )
    assert_no_axe_violations(page, f"fiche, autre version, thème {theme}")
    page.goto(f"{card_server.base_url}/#/arene/chat")
    wait_for(page, "() => !!document.querySelector('.models-card-open')")
    page.locator(".models-card-open").first.click()
    wait_for(page, "() => !!document.querySelector('.models-card-drawer h2.models-card-title')")
    assert_no_axe_violations(page, f"panneau d'un sélecteur, thème {theme}")


def test_axe_finds_nothing_when_the_references_are_unavailable(page, card_server, results_restored):
    results_restored.unlink()
    open_card(page, card_server, AGENT)
    others(page)
    assert_no_axe_violations(page, "fiche sans références")
