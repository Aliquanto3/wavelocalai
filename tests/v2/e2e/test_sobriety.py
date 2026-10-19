"""Écran Sobriété et matériel (story 5.1) dans un vrai navigateur : santé du système en direct,
accélérateur (NVML simulé par `POST /api/test/gpu`), Ollama arrêté ou disponible, empreinte
carbone de la session qui suit `carbon_updated`, pause sur `visibilitychange`, panneaux repliés
(identité, méthode et équivalence en voiture), accessibilité (axe-core, clair et sombre).

Ollama n'est jamais le vrai : le serveur pointe sur un port fermé, ou sur FakeOllama."""

from __future__ import annotations

import re

import pytest

from .test_home import set_tab_hidden, stream_requests
from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready
from .test_topbar import CLOUD_CO2, LOCAL_CO2, NBSP, apply_theme, run_scripted

GPU = {
    "name": "NVIDIA GeForce RTX 3050",
    "memory_used_gb": 2.1,
    "memory_total_gb": 6.0,
    "temperature_c": 62.0,
    "thermal_throttle": False,
}
UNMEASURED = {"mg": None, "method": "unmeasurable", "estimated": False, "reason": "essai"}


def norm(text: str) -> str:
    """Espaces ordinaires et retours à la ligne ramenés à une espace ; l'insécable est gardée."""
    return re.sub(r"[ \t\r\n]+", " ", text).strip()


def card(page, name: str):
    return page.locator(f'[data-screen="sobriety"] [data-card="{name}"]')


def value(page, name: str) -> str:
    return card(page, name).locator(".wl-metric-value").inner_text()


def card_text(page, name: str) -> str:
    return norm(card(page, name).inner_text())


def wait_card(page, name: str, text: str, timeout_s: float = 10.0) -> None:
    wait_for(
        page,
        f'() => document.querySelector(\'[data-screen="sobriety"] [data-card="{name}"]\')'
        f"?.innerText.includes({text!r})",
        timeout_s,
    )


def screen_text(page) -> str:
    return norm(page.locator('[data-screen="sobriety"]').inner_text())


def wait_screen(page, text: str, timeout_s: float = 10.0) -> None:
    wait_for(
        page,
        "() => (document.querySelector('[data-screen=\"sobriety\"]')?.innerText ?? '')"
        f".replace(/[ \\t\\r\\n]+/g, ' ').includes({text!r})",
        timeout_s,
    )


def set_gpu(page, server, gpu) -> None:
    response = page.request.post(f"{server.base_url}/api/test/gpu", data={"gpu": gpu})
    assert response.ok, response.text()


def open_screen(page, server) -> None:
    page.goto(f"{server.base_url}/#/sobriete")
    wait_ready(page)
    wait_for(
        page,
        '() => document.querySelector(\'[data-screen="sobriety"] [data-card="cpu"]\')'
        "?.getAttribute('aria-busy') === 'false'",
    )


@pytest.fixture
def sobriety(backend, page):
    """L'écran sur un serveur neuf (session carbone vide), Ollama arrêté, un GPU simulé."""
    server = backend.start()
    set_gpu(page, server, GPU)
    open_screen(page, server)
    return page, server


@pytest.fixture
def sobriety_with_ollama(backend, fake_ollama, page):
    backend.ollama_port = fake_ollama.port
    fake_ollama.start()
    server = backend.start()
    set_gpu(page, server, None)
    open_screen(page, server)
    return page, server, fake_ollama


# --- Contenu ----------------------------------------------------------------------------------


def test_the_screen_has_one_title_and_the_sections_in_order(sobriety):
    page, _ = sobriety
    assert page.locator("h1:visible").inner_text() == "Sobriété et matériel"
    assert page.title() == "Sobriété et matériel · WaveLocalAI"
    headings = page.locator('[data-screen="sobriety"] h2').all_inner_texts()
    assert headings == ["Santé du système", "Empreinte carbone de cette session"]
    summaries = page.locator('[data-screen="sobriety"] details > summary').all_inner_texts()
    assert summaries == ["Carte d'identité technique", "Comment ces chiffres sont calculés"]
    assert page.locator("a.screen-tab-link").count() == 0  # un seul écran dans le module


def test_the_four_health_cards_show_cpu_memory_accelerator_and_ollama(sobriety):
    page, _ = sobriety
    assert re.fullmatch(rf"\d+{NBSP}%", value(page, "cpu")), value(page, "cpu")
    memory = value(page, "memory")
    assert re.fullmatch(rf"\d+(,\d+)? / \d+(,\d+)?{NBSP}Go", memory), memory
    assert re.search(rf"\d+(,\d+)?{NBSP}Go disponibles", card_text(page, "memory"))
    assert value(page, "ollama") == "Ollama ne répond pas"
    assert card(page, "ollama").get_by_role("button", name="Réessayer").is_visible()
    assert "Lancez Ollama" in card_text(page, "ollama")


def test_the_accelerator_shows_the_gpu_memory_temperature_and_follows_the_stream_without_a_click(
    sobriety,
):
    page, server = sobriety
    assert value(page, "accelerator") == f"2,1 / 6{NBSP}Go"
    text = card_text(page, "accelerator")
    assert "NVIDIA GeForce RTX 3050" in text and f"62{NBSP}°C" in text
    assert "Bridage thermique" not in text
    set_gpu(page, server, {**GPU, "memory_used_gb": 3.5, "temperature_c": 88.0})
    wait_card(page, "accelerator", f"3,5 / 6{NBSP}Go")  # le flux, sans clic ni rechargement
    assert f"88{NBSP}°C" in card_text(page, "accelerator")


def test_a_thermal_throttle_is_said_in_words_with_an_icon(sobriety):
    page, server = sobriety
    set_gpu(page, server, {**GPU, "thermal_throttle": True})
    wait_card(page, "accelerator", "Bridage thermique en cours")
    line = card(page, "accelerator").locator(".sob-warn")
    assert line.inner_text() == "Bridage thermique en cours"
    assert line.locator("svg.icon").count() == 1  # jamais la couleur seule


def test_without_a_gpu_the_accelerator_says_none_and_never_active(sobriety_with_ollama):
    page, _, _ = sobriety_with_ollama
    assert value(page, "accelerator") == "Aucun"
    assert "Aucune carte graphique détectée" in card_text(page, "accelerator")
    assert "Actif" not in screen_text(page) and "actif" not in screen_text(page)
    assert card(page, "accelerator").locator(".sob-warn").is_hidden()


def test_ollama_loaded_models_and_its_version_in_the_section_legend(sobriety_with_ollama):
    page, _, fake = sobriety_with_ollama
    wait_card(page, "ollama", "1 modèle chargé")
    legend = page.locator('[data-legend="ollama-version"]')
    assert legend.inner_text() == f"Ollama {fake.VERSION}"
    # Les noms sont dans l'aide de la métrique, pas dans la valeur.
    card(page, "ollama").get_by_role("button", name=re.compile("Aide")).click()
    assert "qwen2.5:1.5b (2" in card(page, "ollama").locator(".wl-metric-help").inner_text()
    fake.models = []
    wait_card(page, "ollama", "Aucun modèle chargé")


def test_the_retry_button_asks_the_stream_to_check_again(sobriety):
    page, _ = sobriety
    retry = card(page, "ollama").get_by_role("button", name="Réessayer")
    retry.click()  # la demande de la barre haute : le prochain état du flux dit la même chose
    wait_for(
        page,
        "() => document.querySelector('[data-card=\"ollama\"] button.btn')"
        "?.getAttribute('aria-disabled') === 'false'",
    )
    assert value(page, "ollama") == "Ollama ne répond pas"  # toujours arrêté
    assert retry.is_visible()


# --- Empreinte carbone ------------------------------------------------------------------------


def carbon_text(page) -> str:
    return norm(page.locator('[data-screen="sobriety"] .sob-carbon').inner_text())


def test_an_empty_session_says_so_and_never_shows_zero(sobriety):
    page, _ = sobriety
    wait_screen(page, "Aucune réponse mesurée dans cette session")
    assert f"0{NBSP}mg" not in screen_text(page)
    assert page.locator('[data-screen="sobriety"] .sob-carbon wl-metric').is_hidden()


def test_the_session_follows_carbon_updated_by_module_and_origin_without_a_click(sobriety):
    page, server = sobriety
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    wait_screen(page, f"1,8{NBSP}mg")
    text = carbon_text(page)
    assert f"Par module{NBSP}: Chat libre 1,8{NBSP}mg" in text
    assert f"Local 1,8{NBSP}mg" in text and f"Cloud{NBSP}: aucun appel" in text
    assert "Aucune réponse non mesurable" in text

    run_scripted(page, server, kind="rag", origin="cloud", co2=CLOUD_CO2)
    wait_screen(page, f"Cloud 0,9{NBSP}mg (estimé)")
    text = carbon_text(page)
    assert f"Par module{NBSP}: Chat libre 1,8{NBSP}mg · Discussion 0,9{NBSP}mg" in text
    assert f"2,7{NBSP}mg" in text  # le total, dans une seule unité pour toute la section

    run_scripted(page, server, kind="agent", origin="local", co2=UNMEASURED)
    wait_screen(page, "1 réponse non mesurable")
    assert "Agents" not in carbon_text(page)  # un module à 0 mg est omis


def test_one_unit_for_the_whole_section_and_no_colour_by_threshold(sobriety):
    page, server = sobriety
    run_scripted(page, server, kind="chat", origin="local", co2={**LOCAL_CO2, "mg": 2500.0})
    run_scripted(page, server, kind="rag", origin="cloud", co2=CLOUD_CO2)
    wait_screen(page, f"Cloud 0,0009{NBSP}g (estimé)")
    text = carbon_text(page)
    assert f"2,5{NBSP}g" in text and f"Local 2,5{NBSP}g" in text
    assert "mg" not in text  # grammes pour tout le bloc, jamais deux unités mélangées
    # Aucun jugement : pas de mot d'appréciation, pas de classe de seuil.
    assert not re.search(r"\b(bon|élevé|faible|excessif)\b", text, re.IGNORECASE)
    assert (
        page.locator('[data-screen="sobriety"] [class*="level"], [class*="threshold"]').count() == 0
    )


def test_only_unmeasurable_responses_are_counted_apart(sobriety):
    page, server = sobriety
    run_scripted(page, server, kind="chat", origin="local", co2=UNMEASURED)
    wait_screen(
        page, f"Aucune réponse mesurée{NBSP}: celles de cette session ne sont pas mesurables"
    )
    assert f"0{NBSP}mg" not in screen_text(page)
    assert page.get_by_role("button", name="1 réponse non mesurable").is_visible()


def test_the_unmeasurable_link_opens_the_method_panel(sobriety):
    page, server = sobriety
    run_scripted(page, server, kind="chat", origin="local", co2=UNMEASURED)
    link = page.get_by_role("button", name="1 réponse non mesurable")
    method = page.locator("#sob-method")
    assert method.get_attribute("open") is None
    link.click()
    assert method.get_attribute("open") is not None
    assert page.evaluate("document.activeElement.tagName") == "SUMMARY"
    text = method.inner_text()
    assert "CodeCarbon" in text and "ecologits" in text and "Débit" in text  # la règle D3 du débit
    assert "jamais comme 0" in text


# --- Onglet masqué ----------------------------------------------------------------------------


def test_a_hidden_tab_closes_the_stream_and_the_return_reads_the_session_again(
    backend, page, traffic
):
    server = backend.start()
    set_gpu(page, server, GPU)
    open_screen(page, server)
    host = page.locator('[data-screen="sobriety"]')
    wait_for(page, "() => performance.getEntriesByName('shell-ready').length > 0")
    opened = stream_requests(traffic)
    assert opened >= 1 and host.get_attribute("data-live") == "true"
    assert "Mise à jour toutes les 2 secondes" in page.locator('[data-legend="live"]').inner_text()

    set_tab_hidden(page, True)
    assert host.get_attribute("data-live") == "false"
    assert "Mises à jour en pause" in page.locator('[data-legend="live"]').inner_text()
    page.wait_for_timeout(500)
    reads_hidden = sum(1 for url in traffic.urls if url.endswith("/api/carbon/session"))
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    page.wait_for_timeout(2500)  # plus d'un échantillon du flux : rien ne change onglet masqué
    assert f"1,8{NBSP}mg" not in carbon_text(page)  # les dernières valeurs restent affichées
    assert value(page, "cpu").endswith("%")
    assert stream_requests(traffic) == opened  # aucun flux rouvert pendant la pause

    set_tab_hidden(page, False)
    assert host.get_attribute("data-live") == "true"
    wait_screen(page, f"1,8{NBSP}mg")  # la somme relue : la réponse jouée pendant la pause
    assert stream_requests(traffic) == opened + 1  # le flux est rouvert au retour
    reads_after = sum(1 for url in traffic.urls if url.endswith("/api/carbon/session"))
    assert reads_after > reads_hidden  # `GET /api/carbon/session` relu à la reconnexion
    assert "Mise à jour toutes les 2 secondes" in page.locator('[data-legend="live"]').inner_text()


# --- Panneaux repliés -------------------------------------------------------------------------


def test_the_identity_card_is_folded_and_reads_the_machine_when_opened(
    sobriety_with_ollama, traffic
):
    page, server, fake = sobriety_with_ollama
    identity = page.locator('[data-panel="identity"]')
    assert identity.get_attribute("open") is None
    assert not any(url.endswith("/api/system/identity") for url in traffic.urls)  # rien avant
    identity.locator("summary").click()
    wait_for(
        page,
        "() => document.querySelectorAll('[data-panel=\"identity\"] dd').length === 6",
    )
    text = norm(identity.inner_text())
    for label in ("Processeur", "Mémoire", "Accélérateur", "Système", "Version d'Ollama"):
        assert label in text
    assert f"Version d'Ollama {fake.VERSION}" in text  # lue dans l'état en cache de la sonde
    assert "Version de WaveLocalAI" in text
    assert re.search(rf"\d+(,\d+)?{NBSP}Go de mémoire vive", text)


def test_the_method_panel_gives_the_car_equivalence_computed_by_the_server(backend, page, tmp_path):
    config = tmp_path / "equivalence.toml"
    config.write_text(
        '[carbon.car_equivalence]\ng_per_km = 111\nsource = "Source de test (ADEME)"\n'
        "retrieved_at = 2026-10-19\n",
        encoding="utf-8",
    )
    backend.config = config
    server = backend.start()
    open_screen(page, server)
    run_scripted(page, server, kind="chat", origin="local", co2={**LOCAL_CO2, "mg": 412.0})
    wait_screen(page, f"412{NBSP}mg")
    page.locator("#sob-method summary").click()
    equivalence = page.locator("#sob-method .sob-equivalence")
    equivalence.wait_for(state="visible")
    sentence = norm(equivalence.inner_text())
    assert sentence == (
        f"Pour se représenter l'ordre de grandeur{NBSP}: 412{NBSP}mg correspondent à environ "
        f"3,71{NBSP}m parcourus en voiture (facteur{NBSP}: 111{NBSP}g de CO₂ par km{NBSP}; "
        f"source{NBSP}: Source de test (ADEME), relevé le 19 oct. 2026)."
    )
    # Panneau ouvert : une nouvelle réponse met l'équivalence à jour, sans clic.
    run_scripted(page, server, kind="rag", origin="local", co2={**LOCAL_CO2, "mg": 111.0})
    wait_for(
        page,
        f"() => document.querySelector('#sob-method .sob-equivalence').innerText.includes('523{NBSP}mg')",
    )
    assert f"4,71{NBSP}m" in equivalence.inner_text()


def test_the_equivalence_appears_nowhere_but_in_the_method_panel(backend, page):
    server = backend.start()
    open_screen(page, server)
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    wait_screen(page, f"1,8{NBSP}mg")
    page.locator("#sob-method summary").click()
    page.locator("#sob-method .sob-equivalence").wait_for(state="visible")
    api = page.request.get(f"{server.base_url}/api/carbon/method").json()["equivalence"]
    assert api["source"] in page.locator("#sob-method").inner_text()  # la source du serveur
    others = page.locator(
        '[data-screen="sobriety"] > :not(#sob-method), .topbar, .footer'
    ).all_inner_texts()
    assert not any("voiture" in text for text in others)
    page.locator("#co2-button").click()
    assert "voiture" not in page.locator("#co2-panel").inner_text()


def test_no_equivalence_sentence_without_a_server_setting(backend, page, tmp_path):
    config = tmp_path / "vide.toml"
    config.write_text('[carbon]\ncountry_iso = "FRA"\n', encoding="utf-8")
    backend.config = config
    server = backend.start()
    open_screen(page, server)
    page.locator("#sob-method summary").click()
    page.wait_for_timeout(500)
    assert page.locator("#sob-method .sob-equivalence").is_hidden()


# --- Accessibilité et mise en page ------------------------------------------------------------


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_in_every_state(sobriety, theme):
    page, server = sobriety
    apply_theme(page, theme)
    assert_no_axe_violations(page, f"Sobriété, session vide, thème {theme}")
    set_gpu(page, server, {**GPU, "thermal_throttle": True})
    wait_card(page, "accelerator", "Bridage thermique en cours")
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    run_scripted(page, server, kind="rag", origin="cloud", co2=CLOUD_CO2)
    run_scripted(page, server, kind="agent", origin="local", co2=UNMEASURED)
    wait_screen(page, "1 réponse non mesurable")
    assert_no_axe_violations(page, f"Sobriété, session mesurée, thème {theme}")
    page.locator('[data-panel="identity"] summary').click()
    page.locator("#sob-method summary").click()
    page.locator("#sob-method .sob-equivalence").wait_for(state="visible")
    wait_for(page, "() => document.querySelectorAll('[data-panel=\"identity\"] dd').length === 6")
    assert_no_axe_violations(page, f"Sobriété, panneaux ouverts, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_without_a_gpu_and_with_ollama_up(sobriety_with_ollama, theme):
    page, _, _ = sobriety_with_ollama
    apply_theme(page, theme)
    wait_card(page, "ollama", "1 modèle chargé")
    assert_no_axe_violations(page, f"Sobriété, sans GPU, Ollama disponible, thème {theme}")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_while_loading_and_when_the_connection_is_lost(
    backend, page_tolerating_failed_requests, theme
):
    page = page_tolerating_failed_requests
    server = backend.start()
    page.route("**/api/system/stream", lambda route: route.abort())
    page.goto(f"{server.base_url}/#/sobriete")
    wait_ready(page)
    apply_theme(page, theme)
    assert card(page, "cpu").get_attribute("aria-busy") == "true"
    assert_no_axe_violations(page, f"Sobriété, squelettes, thème {theme}")
    wait_card(page, "cpu", "inconnu", timeout_s=30)
    assert value(page, "accelerator") == "inconnu"
    assert_no_axe_violations(page, f"Sobriété, connexion perdue, thème {theme}")


@pytest.mark.parametrize("width", [320, 768, 1440])
def test_the_screen_has_no_horizontal_scroll(sobriety, width):
    page, _ = sobriety
    page.set_viewport_size({"width": width, "height": 900})
    page.locator("#sob-method summary").click()
    assert_no_horizontal_scroll(page)
    box = card(page, "accelerator").bounding_box()
    assert box is not None and box["x"] >= 0 and box["x"] + box["width"] <= width


def test_the_screen_never_leaves_127_0_0_1(sobriety, traffic):
    page, server = sobriety
    run_scripted(page, server, kind="chat", origin="local", co2=LOCAL_CO2)
    page.locator("#sob-method summary").click()
    page.locator('[data-panel="identity"] summary').click()
    page.wait_for_timeout(500)
    assert traffic.urls and all(url.startswith(server.base_url) for url in traffic.urls)
