"""
Accueil et structure des cinq pages, dans l'app réelle (Ollama démarré).

Constats couverts : D1/U12 (local au démarrage), U11 (Disponible), U13 (aucun delta détourné),
U1/U3/U4 (charte, barre d'outils, couleur de l'action principale), U2/U8/U9/U10 (titres,
noms, lexique, pied de page), U18 (outils de l'agent visibles), F8 (localhost seulement),
F14 (aucun avertissement de dépréciation).
"""

import re
from datetime import date
from pathlib import Path

import pytest
import toml

from src.app.modules import AGENTS, APP_NAME, DOCUMENTS, MODULES
from tests.e2e import helpers as h

pytestmark = pytest.mark.e2e

CLOUD_TOGGLE_LABEL = "Autoriser le cloud"
# (chemin d'URL, h1 et titre d'onglet attendus)
PAGES = [("", APP_NAME)] + [(m.url_path, m.title) for m in MODULES]
PAGE_IDS = ["Accueil"] + [m.url_path for m in MODULES]

# Avertissement de dépréciation émis par Streamlit dans le journal du serveur.
STREAMLIT_DEPRECATION_RE = re.compile(r"streamlit.*deprecat", re.I)
CONFIG_PATH = Path(__file__).resolve().parents[2] / ".streamlit" / "config.toml"

# Couleur primaire claire (DESIGN.md, .streamlit/config.toml) et rouge par défaut de Streamlit.
PRIMARY_LIGHT_RGB = "rgb(69, 29, 199)"
STREAMLIT_RED_RGB = "rgb(255, 75, 75)"

# Libellés remplacés par le lexique (EXPERIENCE.md) : jamais affichés.
LEGACY_TEXTS = [
    re.compile(r"\bchunks?\b", re.I),
    re.compile(r"Solo \(LangGraph\)"),
    re.compile(r"Crew \(Multi-Agent\)"),
    re.compile(r"Labo de tests", re.I),
    re.compile(r"FIGHT"),
    re.compile(r"Opérationnel"),
    re.compile(r"Inference Arena|RAG Knowledge|Agent Lab|Socle Hardware|Cockpit GreenOps"),
    re.compile(r"\d\s?GB\b"),
]


def test_home_is_local_and_available(page, app):
    """Accueil : Système « Disponible » (Ollama répond), Mode « Local », contrôle cloud
    décoché, badge Local, aucun delta, modules sous leur nom unique, pied de page vrai."""
    h.goto(page, app.base_url)
    main = h.main(page)

    assert h.metric_value(main, "Système") == "Disponible"
    assert h.metric_value(main, "Mode") == "Local"
    toggle = h.sidebar(page).get_by_role("switch", name=CLOUD_TOGGLE_LABEL)
    assert toggle.count() == 1, "un seul contrôle « Autoriser le cloud »"
    assert not toggle.is_checked(), "le cloud doit être désactivé au démarrage (D1)"
    assert "Local" in h.flat(main.inner_text())
    assert page.locator('[data-testid="stMetricDelta"]').count() == 0

    # Menu : Accueil puis les modules, dans l'ordre, sous leur nom unique.
    links = h.sidebar(page).locator('[data-testid="stSidebarNav"] a')
    shown = [h.flat(t) for t in links.all_inner_texts()]
    expected = ["Accueil"] + [m.title for m in MODULES]
    assert len(shown) == len(expected)
    for label, title in zip(shown, expected, strict=True):
        assert label.endswith(title), f"menu « {label} » au lieu de « {title} »"
    for module in MODULES:
        assert main.get_by_role("link", name=re.compile(re.escape(module.title))).count() == 1
    assert main.get_by_text("Démo recommandée").count() == 1

    text = h.flat(main.inner_text())
    assert f"© {date.today().year} {APP_NAME} · Wavestone" in text
    assert not re.search(r"v\d+\.\d+\.\d+", text), "aucune version inventée au pied de page"
    assert page.locator('[data-testid="stAppDeployButton"]').count() == 0
    assert h.ui_errors(page) == []


@pytest.mark.parametrize(("path", "title"), PAGES, ids=PAGE_IDS)
def test_page_structure(page, app, path, title):
    """Un seul h1 (le nom du module), le même dans l'onglet ; aucun emoji dans les titres
    (sauf l'accueil de l'agent), aucun libellé d'avant le lexique, aucune trace Python."""
    h.goto(page, app.base_url, path)

    assert h.headings(page, "h1") == [title]
    assert title in page.title()
    for heading in h.headings(page, "h1, h2, h3, h4"):
        if heading not in h.ALLOWED_EMOJI_HEADINGS:
            assert not h.EMOJI_RE.search(heading), f"emoji dans le titre « {heading} »"
    text = h.flat(h.main(page).inner_text()) + " " + h.flat(h.sidebar(page).inner_text())
    for pattern in LEGACY_TEXTS:
        assert not pattern.search(text), f"texte proscrit ({pattern.pattern}) sur « {title} »"
    assert h.exceptions(page) == []
    # Aucun module n'affiche « Ollama ne répond pas » quand Ollama répond.
    assert h.main(page).get_by_text("Ollama ne répond pas").count() == 0


def test_primary_action_uses_brand_color(page, app):
    """L'action principale est violette (#451DC7), jamais le rouge par défaut de Streamlit
    (U4) ; police Inter chargée localement, fond blanc en thème clair (U1)."""
    # Base documentaire vide (app neuve) : « Importer des documents » est l'action principale.
    h.goto(page, app.base_url, DOCUMENTS.url_path)
    button = h.main(page).get_by_role("button", name="Importer des documents")
    assert button.evaluate("e => getComputedStyle(e).backgroundColor") == PRIMARY_LIGHT_RGB
    colors = page.locator("button").evaluate_all(
        "els => els.map(e => getComputedStyle(e).backgroundColor)"
    )
    assert STREAMLIT_RED_RGB not in colors
    # Inter déclarée par @font-face et servie localement (Aptos, si elle est installée, passe
    # devant : on vérifie la déclaration et le fichier, pas la police employée).
    families = page.evaluate("[...document.fonts].map(f => f.family.replace(/[\"']/g, ''))")
    assert "Inter" in families, families
    for face in toml.load(CONFIG_PATH)["theme"]["fontFaces"]:
        if face["family"] == "Inter":
            response = page.request.get(f"{app.base_url}/{face['url']}")
            assert response.status == 200, f"{face['url']} : HTTP {response.status}"
    background = page.locator('[data-testid="stApp"]').evaluate(
        "e => getComputedStyle(e).backgroundColor"
    )
    assert background == "rgb(255, 255, 255)"


def test_agent_tools_all_visible_email_unconfigured(page, app):
    """Neuf outils visibles à 1440 px (U18) ; sans SMTP, « Envoi d'email » reste visible,
    décoché et non sélectionnable, sous « Outil non configuré » (D2)."""
    h.goto(page, app.base_url, AGENTS.url_path)
    main = h.main(page)
    pills = main.locator('[data-testid="stButtonGroup"] button[data-variant="pills"]')
    names = [h.flat(t) for t in pills.all_inner_texts()]
    assert len(names) == 9, names
    viewport_width = page.viewport_size["width"]
    for i in range(pills.count()):
        box = pills.nth(i).bounding_box()
        assert pills.nth(i).is_visible() and box and box["x"] + box["width"] <= viewport_width
    email = pills.filter(has_text="Envoi d'email")
    assert email.count() == 1
    assert email.get_attribute("aria-pressed") != "true"
    assert email.is_disabled()
    assert main.get_by_text("Outil non configuré").count() == 1
    others = pills.filter(has_not_text="Envoi d'email")
    assert all(others.nth(i).get_attribute("aria-pressed") == "true" for i in range(8))


def test_server_listens_on_localhost_only(page, app):
    """Le démarrage n'annonce que localhost, jamais d'URL réseau (F8, D5)."""
    h.goto(page, app.base_url)
    log = app.server_log()
    assert re.search(r"URL: http://localhost:\d+", log), log[-2000:]
    assert not re.search(r"(Network|External) URL", log), log[-2000:]


def test_no_deprecation_warning_on_any_page(page, app):
    """Toutes les pages, puis le journal du serveur : aucun avertissement de dépréciation de
    Streamlit (F14, CAP-6), aucune trace à l'écran."""
    for path, _ in PAGES:
        h.goto(page, app.base_url, path)
        assert h.exceptions(page) == []
    log = app.server_log()
    assert "use_container_width" not in log
    deprecations = [line for line in log.splitlines() if STREAMLIT_DEPRECATION_RE.search(line)]
    assert not deprecations, deprecations
