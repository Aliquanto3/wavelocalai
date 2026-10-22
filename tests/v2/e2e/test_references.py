"""Références, « Quel modèle pour quel usage » (story 5.8) dans un vrai navigateur, sur le vrai serveur.

Les résultats `qb.results/1` viennent de la fixture `tests/v2/fixtures/` réécrite en dossier temporaire
(aucun fichier de `benchmarks/` du dépôt) ; Ollama est un faux HTTP local (`ThreadedOllama`). Chaque
test passe par le garde-fou de `conftest.py` : aucune requête ne sort de 127.0.0.1.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..conftest import closed_port
from ..pull_fake import GB, ThreadedOllama, layer, manifest
from ..web.test_references_api import bench_data
from .conftest import Backend
from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready

NBSP = "\N{NO-BREAK SPACE}"
MID, OTHER, SMALL = "mid:7b", "other:4b", "small:1b"  # grand:14b n'est pas installé
INSTALLED = {MID: 4 * GB, OTHER: 2 * GB, SMALL: GB}


def write_results(root: Path, data: dict) -> Path:
    path = root / "benchmarks" / "slm-quality" / "slm-quality-results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def ollama():
    fake = ThreadedOllama(closed_port())
    fake.start()
    yield fake
    fake.stop()


def _start(tmp_path_factory, name: str, ollama_port: int | None):
    root = tmp_path_factory.mktemp(name)
    (root / "reglages.toml").write_text("[ollama]\nprobe_cache_s = 0.2\n", encoding="utf-8")
    write_results(root, bench_data())
    (root / "data").mkdir()
    backend = Backend(root / "data", ollama_port=ollama_port, config=root / "reglages.toml")
    server = backend.start()
    server.root = root
    return backend, server


@pytest.fixture(scope="module")
def refs_server(tmp_path_factory, ollama):
    ollama.reset(INSTALLED)
    ollama.params = {MID: "7B", OTHER: "4B", SMALL: "1B"}
    backend, server = _start(tmp_path_factory, "e2e-refs", ollama.port)
    try:
        yield server
    finally:
        backend.stop()


@pytest.fixture(scope="module")
def down_server(tmp_path_factory):
    """Ollama ne répond pas : un port fermé."""
    backend, server = _start(tmp_path_factory, "e2e-refs-down", None)
    try:
        yield server
    finally:
        backend.stop()


@pytest.fixture
def results_restored(refs_server):
    """Le fichier des résultats remis à l'identique après un test qui l'a retiré ou changé."""
    path = refs_server.root / "benchmarks" / "slm-quality" / "slm-quality-results.json"
    saved = path.read_bytes()
    yield path
    path.write_bytes(saved)


def open_references(page, server, *, cards: int | None = 2):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server.base_url}/#/arene/references")
    wait_ready(page)
    if cards is not None:
        wait_for(page, f"() => document.querySelectorAll('.ref-card').length === {cards}")
    return page


def card(page, usage: str):
    return page.locator(f'.ref-card[data-usage="{usage}"]')


def names(page, usage: str) -> list[str]:
    return card(page, usage).locator(".ref-model-name").all_inner_texts()


def leave_and_return(page, server) -> None:
    """Quitte l'écran pour l'Accueil puis y revient (le routeur le garde monté et le masque)."""
    page.goto(f"{server.base_url}/#/")
    wait_for(page, "() => document.title === 'Accueil · WaveLocalAI'")
    page.goto(f"{server.base_url}/#/arene/references")
    wait_for(page, "() => document.title === 'Références · WaveLocalAI'")


def arena_values(page) -> str:
    return page.evaluate(
        """() => document.querySelector(
            'section[data-screen="arena-compare"] wl-model-picker[purpose="arena"]'
        )?.values.join(',') ?? ''"""
    )


# --- Cartes --------------------------------------------------------------------------------------


def test_one_card_per_usage_with_the_best_group_by_name_and_no_rank(page, refs_server):
    open_references(page, refs_server)
    assert page.get_by_role("heading", level=1).inner_text() == "Références"
    assert page.title() == "Références · WaveLocalAI"
    assert page.locator(".screen-tabs [aria-current='page']").inner_text() == "Références"
    assert [h.inner_text() for h in page.locator(".ref-card h3").all()] == [
        "Raisonnement",
        "Appel d'outils",
    ]
    assert names(page, "tools") == ["Grand 14B", "Moyen 7B"]  # à égalité statistique : par nom
    assert names(page, "reasoning") == ["Moyen 7B"]
    text = card(page, "tools").text_content()  # intertitre en majuscules par CSS (story 9.7)
    assert "Groupe des meilleurs" in text and "aucun rang" in text
    assert "Meilleur modèle" in card(page, "reasoning").text_content()
    assert f"Part de réussite 78{NBSP}%" in text and f"Part de réussite 72{NBSP}%" in text
    assert f"entre 73{NBSP}% et 83{NBSP}%" in text
    assert f"5,2{NBSP}tokens/s sur le poste de référence" in text
    assert "Part d'appels d'outils corrects" in text


def test_the_source_line_names_the_bench_the_date_and_the_reference_machine(page, refs_server):
    open_references(page, refs_server)
    source = page.locator(".ref-source").inner_text()
    assert f"Source{NBSP}: slm-quality-bench 1.4.0" in source
    assert "PC pro, 16 Go, sans GPU" in source and f"15{NBSP}Go de mémoire" in source
    assert "1 oct. 2026" in source


def test_marks_say_installed_or_nothing_without_legend_or_other_models_block(page, refs_server):
    open_references(page, refs_server)
    moyen = card(page, "tools").locator(".ref-model", has_text="Moyen 7B")
    grand = card(page, "tools").locator(".ref-model", has_text="Grand 14B")
    assert moyen.locator(".ref-mark").inner_text() == "installé"
    assert grand.locator(".ref-mark").count() == 0  # au catalogue seulement
    body = page.locator('[data-screen="arena-references"]').inner_text()
    # Décision du 2026-10-19 : ni « Autres modèles mesurés », ni lien vers le banc, ni légende.
    assert "Autres modèles" not in body and "Voir le tableau" not in body
    assert (
        "Ce poste a ce modèle" not in body
        and page.locator(".ref-legend, dl.rf-legend").count() == 0
    )
    assert page.locator('[data-screen="arena-references"] a[href^="http"]').count() == 0


def test_energy_is_shown_only_when_measured(page, refs_server, results_restored):
    data = bench_data()
    for result in data["results"]:
        if (
            result["model"] == MID
            and result["machine"] == "pc-pro"
            and result["track"] == "think_off"
        ):
            result["energy"] = {
                "status": "measured",
                "gpu_power_avg_w": 30,
                "gpu_wh_per_1k_tokens": 0.4,
            }
        if result["model"] == "grand:14b" and result["machine"] == "pc-pro":
            result["energy"] = {
                "status": "unvalidated",
                "gpu_power_avg_w": 30,
                "gpu_wh_per_1k_tokens": 0.9,
            }
    results_restored.write_text(json.dumps(data), encoding="utf-8")
    open_references(page, refs_server)
    moyen = card(page, "tools").locator(".ref-model", has_text="Moyen 7B").inner_text()
    grand = card(page, "tools").locator(".ref-model", has_text="Grand 14B").inner_text()
    assert f"0,4{NBSP}Wh pour 1{NBSP}000 tokens, mesurés" in moyen.replace(" ", NBSP)
    assert "Wh" not in grand


# --- « Comparer ces modèles » -----------------------------------------------------------------------


def test_compare_opens_the_arena_preselected_on_the_installed_models_of_the_group(
    page, refs_server
):
    open_references(page, refs_server)
    button = card(page, "tools").get_by_role("button", name="Comparer ces modèles")
    assert button.is_enabled() and button.get_attribute("aria-disabled") is None
    button.click()
    wait_for(page, "() => location.hash === '#/arene/comparer'")
    wait_for(
        page,
        '() => document.querySelector(\'section[data-screen="arena-compare"] '
        "wl-model-picker[purpose=\"arena\"]')?.values.join(',') === 'mid:7b'",
    )
    assert arena_values(page) == MID  # Grand 14B, du groupe, n'est pas installé : il reste dehors
    assert page.get_by_role("heading", level=1).inner_text() == "Arène"


def test_compare_is_disabled_with_its_reason_when_no_group_model_is_installed(
    page, refs_server, results_restored
):
    data = bench_data()
    data["results"] = [r for r in data["results"] if r["model"] == "grand:14b"]
    results_restored.write_text(json.dumps(data), encoding="utf-8")
    open_references(page, refs_server, cards=1)
    button = card(page, "tools").get_by_role("button", name="Comparer ces modèles")
    assert button.get_attribute("aria-disabled") == "true"
    reason = card(page, "tools").locator(".ref-compare-reason")
    assert reason.inner_text() == "Aucun modèle de ce groupe n'est installé sur ce poste."
    assert button.get_attribute("aria-describedby") == reason.get_attribute("id")
    button.focus()
    assert button.evaluate("el => el === document.activeElement")
    button.dispatch_event("click")
    assert page.evaluate("location.hash") == "#/arene/references"


# --- Tableau -------------------------------------------------------------------------------------


def test_the_table_is_the_same_content_with_unranked_models_and_a_sortable_score(page, refs_server):
    open_references(page, refs_server)
    page.get_by_role("radio", name="Tableau").click()
    wait_for(page, "() => document.querySelectorAll('.ref-body wl-data-table tbody tr').length > 0")
    assert page.locator(".ref-card").count() == 0
    headers = page.locator(".ref-body thead th").all_inner_texts()
    assert [h.strip() for h in headers][:4] == ["Modèle", "Usage", "Groupe", "Part de réussite"]
    rows = page.locator(".ref-body tbody tr")
    assert rows.count() == 8  # quatre modèles mesurés pour chacun des deux usages
    petit = rows.filter(has_text="Petit 1B").filter(has_text="Appel d'outils")
    assert "non classé" in petit.inner_text() and "installé" in petit.inner_text()
    grand = rows.filter(has_text="Grand 14B").filter(has_text="Appel d'outils")
    assert "Meilleurs, à égalité" in grand.inner_text()
    page.get_by_role("button", name="Part de réussite").click()
    sorted_header = page.locator(
        '.ref-body th[aria-sort="ascending"], .ref-body th[aria-sort="descending"]'
    )
    assert sorted_header.count() == 1 and "Part de réussite" in sorted_header.inner_text()
    page.get_by_role("radio", name="Cartes").click()
    wait_for(page, "() => document.querySelectorAll('.ref-card').length === 2")


# --- Indisponible, Ollama arrêté -----------------------------------------------------------------


def test_without_the_results_file_the_reason_is_shown_and_no_empty_card(
    page, refs_server, results_restored
):
    results_restored.unlink()
    open_references(page, refs_server, cards=None)
    wait_for(page, "() => !!document.querySelector('.ref-unavailable')")
    unavailable = page.locator(".ref-unavailable")
    assert unavailable.locator("h2").inner_text() == "Références indisponibles"
    assert "pas synchronisé" in unavailable.inner_text()
    assert page.locator(".ref-card").count() == 0 and page.locator(".ref-grid").count() == 0
    page.goto(f"{refs_server.base_url}/#/")
    wait_ready(page)
    page.wait_for_timeout(800)  # la lecture de la carte de l'Accueil est faite
    assert page.locator(".home-references").is_hidden()


def test_a_file_with_no_ranked_model_says_so(page, refs_server, results_restored):
    data = bench_data({})
    results_restored.write_text(json.dumps(data), encoding="utf-8")
    open_references(page, refs_server, cards=None)
    wait_for(page, "() => !!document.querySelector('.ref-unavailable')")
    assert "aucun modèle" in page.locator(".ref-unavailable").inner_text()


def test_with_ollama_down_the_references_stay_readable_without_marks(page, down_server):
    open_references(page, down_server)
    assert names(page, "tools") == ["Grand 14B", "Moyen 7B"]
    assert page.locator(".ref-mark").count() == 0
    notice = page.locator(".ref-notices .wl-notice").inner_text()
    assert f"Ollama ne répond pas{NBSP}:" in notice and f"«{NBSP}installé{NBSP}»" in notice
    button = card(page, "tools").get_by_role("button", name="Comparer ces modèles")
    assert button.get_attribute("aria-disabled") == "true"
    assert (
        card(page, "tools").locator(".ref-compare-reason").inner_text()
        == f"Modèles installés non vérifiés{NBSP}: Ollama ne répond pas."
    )
    page.get_by_role("radio", name="Tableau").click()
    wait_for(page, "() => document.querySelectorAll('.ref-body tbody tr').length > 0")
    assert "non vérifié" in page.locator(".ref-body tbody").first.inner_text()


# --- Accueil -------------------------------------------------------------------------------------


def test_the_home_card_says_the_best_score_and_opens_the_references(page, refs_server, traffic):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{refs_server.base_url}/#/")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('.home-references')?.hidden === false")
    link = page.locator(".home-references a")
    assert link.get_attribute("href") == "#/arene/references"
    text = link.inner_text()
    assert "Références" in text and "Quel modèle pour quel usage" in text
    assert (
        f"Part de réussite 78{NBSP}%" in text and "Grand 14B" in text and "Appel d'outils" in text
    )
    icons = link.locator("use").evaluate("el => el.getAttribute('href')")
    assert icons.endswith("#i-help")
    arena_icon = page.locator('.home-module-link[href="#/arene/chat"] use').evaluate(
        "el => el.getAttribute('href')"
    )
    assert arena_icon != icons
    assert sum(url.endswith("/api/references") for url in traffic.urls) == 1  # un seul appel
    link.click()
    wait_for(page, "() => location.hash === '#/arene/references'")
    wait_for(page, "() => document.querySelectorAll('.ref-card').length === 2")


def test_the_references_are_read_again_when_the_screen_is_shown_again(page, refs_server, ollama):
    open_references(page, refs_server)
    moyen = card(page, "tools").locator(".ref-model", has_text="Moyen 7B")
    assert moyen.locator(".ref-mark").inner_text() == "installé"
    ollama.reset({OTHER: 2 * GB, SMALL: GB})  # Moyen 7B est supprimé du poste
    try:
        # Le registre rafraîchit en tâche de fond (AD-15) : la lecture qui suit le départ d'un modèle peut
        # encore le voir ; un retour sur l'écran relit, et la marque finit par disparaître.
        for _ in range(8):
            leave_and_return(page, refs_server)
            if card(page, "tools").locator(".ref-mark", has_text="installé").count() == 0:
                break
            page.wait_for_timeout(300)
        assert card(page, "tools").locator(".ref-mark", has_text="installé").count() == 0
        assert card(page, "tools").locator(".ref-model", has_text="Moyen 7B").count() == 1
    finally:
        ollama.reset(INSTALLED)
        ollama.params = {MID: "7B", OTHER: "4B", SMALL: "1B"}


# --- Accessibilité et mise en page -----------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_nothing_on_cards_table_and_unavailable_state(
    page, refs_server, results_restored, theme
):
    open_references(page, refs_server)
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(page, f"références, cartes, thème {theme}")
    page.get_by_role("radio", name="Tableau").click()
    wait_for(page, "() => document.querySelectorAll('.ref-body tbody tr').length > 0")
    assert_no_axe_violations(page, f"références, tableau, thème {theme}")
    results_restored.unlink()
    leave_and_return(page, refs_server)
    wait_for(page, "() => !!document.querySelector('.ref-unavailable')")
    assert_no_axe_violations(page, f"références indisponibles, thème {theme}")


def test_axe_finds_nothing_with_ollama_down_and_a_disabled_compare(page, down_server):
    open_references(page, down_server)
    assert_no_axe_violations(page, "références, Ollama arrêté")


@pytest.mark.parametrize("width", [320, 768, 1440])
def test_the_screen_never_scrolls_horizontally(page, refs_server, width):
    open_references(page, refs_server)
    page.set_viewport_size({"width": width, "height": 800})
    assert_no_horizontal_scroll(page)
    page.get_by_role("radio", name="Tableau").click()
    wait_for(page, "() => document.querySelectorAll('.ref-body tbody tr').length > 0")
    wrap = page.locator(".ref-body wl-data-table")
    assert wrap.evaluate(
        "el => el.scrollWidth <= el.clientWidth || getComputedStyle(el).overflowX !== 'visible'"
    )
    assert_no_horizontal_scroll(page)


# --- Parcours : Sobriété, Modèles, fiche, Références ---------------------------------------------------


def test_journey_sobriety_then_models_install_then_card_then_references(page, refs_server, ollama):
    import threading

    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{refs_server.base_url}/#/sobriete")
    wait_ready(page)
    # Les métriques vivent sans clic : le flux système les remplit.
    wait_for(
        page,
        '() => !!document.querySelector(\'[data-screen="sobriety"] [data-card="cpu"] .wl-metric-value\')'
        "?.textContent.trim()",
    )
    resume = threading.Event()
    ollama.scripts.append(
        [manifest(), layer("sha256:cccc", GB, GB // 2), resume, {"status": "success"}]
    )
    try:
        page.goto(f"{refs_server.base_url}/#/modeles")
        wait_for(page, "() => document.querySelectorAll('.models-installed tbody tr').length === 3")
        page.get_by_label("Installer un modèle par son nom").fill("perso:3b")
        page.get_by_role("button", name="Installer le modèle saisi").click()
        wait_for(
            page,
            "() => /Téléchargement/.test(document.querySelector('.models-pull-panel .wl-progress-text')"
            "?.textContent ?? '')",
        )
        resume.set()
        wait_for(
            page,
            "() => document.querySelector('.models-notice')?.textContent === 'perso:3b installé.'",
        )
        assert page.locator(".models-pull-panel").inner_text().strip() == "Installé"
        wait_for(page, "() => document.querySelectorAll('.models-installed tbody tr').length === 4")
        page.get_by_role("link", name="Fiche du modèle perso:3b", exact=True).click()
        wait_for(page, "() => !!document.querySelector('.models-fiche h2.models-card-title')")
        assert page.locator(".models-fiche h2").inner_text() == "perso:3b"
        page.goto(f"{refs_server.base_url}/#/arene/references")
        wait_for(page, "() => document.querySelectorAll('.ref-card').length === 2")
        assert_no_axe_violations(page, "parcours, références")
    finally:
        resume.set()
        ollama.reset(INSTALLED)
        ollama.params = {MID: "7B", OTHER: "4B", SMALL: "1B"}
