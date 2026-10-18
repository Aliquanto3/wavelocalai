"""Composants partagés (story 1.9) sur la page d'essai `fixtures/components.html` : badges, métriques
et affichage d'erreur, accessibilité (axe-core, clair et sombre, sans exclusion)."""

from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe

BADGES = [
    ("local", "Local", "i-computer"),
    ("cloud", "Cloud", "i-cloud"),
    ("unknown", "Origine inconnue", "i-help"),
    (None, "Origine inconnue", "i-help"),  # sans origine : jamais un Local par défaut
    ("indicative", "indicatif", None),
    ("single-judge", "un seul juge", None),
    ("estimated", "estimé", None),
    ("unmeasurable", "non mesurable", None),
]


@pytest.fixture
def components(page, fixtures_url):
    page.goto(f"{fixtures_url}/components.html")
    page.locator("body[data-ready='true']").wait_for(state="attached")
    return page


def test_every_badge_carries_a_text_and_the_icon_of_its_origin(components):
    badges = components.locator("#badges wl-badge")
    assert badges.count() == len(BADGES)
    for index, (kind, text, sprite) in enumerate(BADGES):
        badge = badges.nth(index)
        assert badge.inner_text().strip() == text, kind
        assert badge.get_attribute("kind") == kind
        icons = badge.locator("use")
        if sprite is None:
            assert icons.count() == 0
        else:
            assert icons.get_attribute("href") == f"/static/icons.svg#{sprite}"


def test_badge_tones_follow_the_origin(components):
    tones = components.evaluate(
        """() => [...document.querySelectorAll('#badges wl-badge')].map(
            (badge) => getComputedStyle(badge).getPropertyValue('--badge-tone').trim())"""
    )
    # Local = chart-2 (vert), Cloud = chart-4 (orange), inconnu et étiquettes = gris.
    assert tones[0] == "#0E9F5E" and tones[1] == "#C98A00"
    assert tones[2] == tones[3] == tones[4] == tones[7] == "#8A8A9E"


def test_badge_follows_its_attribute(components):
    components.evaluate("document.querySelector('#badges wl-badge').setAttribute('kind', 'cloud')")
    assert components.locator("#badges wl-badge").first.inner_text().strip() == "Cloud"


def test_metric_shows_label_value_and_unit(components):
    metric = components.locator("#metric-plain")
    assert metric.locator(".wl-metric-label").inner_text() == "Chargement"
    assert metric.locator(".wl-metric-value").inner_text() == "3,2 s"
    assert metric.locator("button").count() == 0  # pas d'aide : pas de bouton
    size = metric.locator(".wl-metric-number").evaluate("el => getComputedStyle(el).fontSize")
    assert size == "40px"  # metric-value, 2.5rem


def test_metric_help_is_a_button_described_by_its_text(components):
    metric = components.locator("#metric-help")
    button = metric.get_by_role("button", name="Aide sur Débit")
    help_id = button.get_attribute("aria-describedby")
    help_text = components.locator(f"#{help_id}")
    assert help_text.is_hidden() and button.get_attribute("aria-expanded") == "false"
    # Même fermée, l'aide est la description accessible du bouton.
    assert (
        components.evaluate("(id) => document.getElementById(id).textContent", help_id)
        == "Tokens générés par seconde, mesurés par Ollama."
    )

    button.click()
    assert help_text.is_visible() and button.get_attribute("aria-expanded") == "true"
    components.keyboard.press("Escape")
    assert help_text.is_hidden() and button.get_attribute("aria-expanded") == "false"


def test_provisional_metric_is_italic_and_says_so(components):
    metric = components.locator("#metric-provisional")
    assert metric.locator(".wl-metric-value").inner_text() == "41 tokens/s (provisoire)"
    style = metric.locator(".wl-metric-value").evaluate("el => getComputedStyle(el).fontStyle")
    assert style == "italic"
    plain = components.locator("#metric-plain .wl-metric-value")
    assert plain.evaluate("el => getComputedStyle(el).fontStyle") == "normal"


def test_error_shows_message_then_action_with_technical_details_folded(components):
    error = components.locator("#error")
    paragraphs = error.locator("p").all_inner_texts()
    assert paragraphs == [
        "Le fournisseur Anthropic ne répond pas.",
        "Vérifiez la connexion, la clé et le quota, ou repassez en Local.",
    ]
    details = error.locator("details")
    assert details.locator("summary").inner_text() == "Détails techniques"
    assert details.evaluate("el => el.open") is False
    assert error.locator("pre").is_hidden()

    details.locator("summary").click()
    assert error.locator("pre").inner_text() == (
        'ConnectTimeout après 30 s\nprovider : "anthropic"'
    )


def test_error_without_content_is_hidden_and_a_new_error_replaces_it(components):
    error = components.locator("#error")
    components.evaluate("document.getElementById('error').error = null")
    assert error.is_hidden()
    components.evaluate(
        """document.getElementById('error').error = {
            code: 'ollama_down', message: 'Ollama ne répond pas sur ce poste.',
            action: 'Lancez Ollama, puis réessayez.', detail: null }"""
    )
    assert error.locator("p").all_inner_texts() == [
        "Ollama ne répond pas sur ce poste.",
        "Lancez Ollama, puis réessayez.",
    ]
    assert error.locator("details").count() == 0  # aucun détail : rien à replier


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_components(page, fixtures_url, theme):
    page.goto(f"{fixtures_url}/components.html?theme={theme}")
    page.locator("body[data-ready='true']").wait_for(state="attached")
    assert page.get_attribute("html", "data-theme") == theme
    page.locator("#metric-help button").click()  # l'aide ouverte est dans la page vérifiée
    page.locator("#error summary").click()
    results = Axe().run(page)
    assert (
        results.violations_count == 0
    ), f"composants, thème {theme} :\n{results.generate_report()}"
