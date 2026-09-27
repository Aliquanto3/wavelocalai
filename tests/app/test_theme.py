"""
Tests du thème Wavestone, des icônes et de l'accessibilité du code source (story 2).

Référence : _bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md.
Usage: python -m pytest tests/app/test_theme.py -v
"""

import re

import pytest
import toml
from streamlit import config as st_config
from streamlit.testing.v1 import AppTest

from tests.app.conftest import APP_DIR, ROOT_DIR
from tests.app.test_pages import PAGES, RENDER_TIMEOUT_S

CONFIG_PATH = ROOT_DIR / ".streamlit" / "config.toml"

# Tableau Colors de DESIGN.md, clé config.toml -> valeur, par thème.
EXPECTED_THEME = {
    "light": {
        "primaryColor": "#451DC7",
        "backgroundColor": "#FFFFFF",
        "secondaryBackgroundColor": "#F6F5FA",
        "textColor": "#0A0A14",
        "borderColor": "#E6E6EC",
        "linkColor": "#451DC7",
        "chartCategoricalColors": ["#6A4DE6", "#0E9F5E", "#2F7FD8", "#C98A00"],
    },
    "dark": {
        "primaryColor": "#6A4DE6",
        "backgroundColor": "#0A0A14",
        "secondaryBackgroundColor": "#16162A",
        "textColor": "#F6F5FA",
        "borderColor": "#2E2E44",
        "linkColor": "#9B85F0",
        "chartCategoricalColors": ["#7A5FEA", "#12A564", "#3B86DB", "#B07800"],
    },
}
# Clés natives ajoutées hors tableau, pour un contraste AA sur les couleurs sémantiques.
EXTRA_THEME_KEYS = {"light": {"greenTextColor"}, "dark": set()}
FONT_STACK = "Aptos, Inter, sans-serif"

# Une icône Material par page, jamais partagée (EXPERIENCE.md, Information Architecture),
# déclarée une seule fois dans src/app/modules.py (menu et liens de l'accueil). Le favicon est
# un fichier local commun (FAVICON_PATH).
MODULE_ICONS = {
    "home.py": "home",
    "views/01_Socle_Hardware.py": "eco",
    "views/02_Inference_Arena.py": "leaderboard",
    "views/03_RAG_Knowledge.py": "description",
    "views/04_Agent_Lab.py": "smart_toy",
}

# Pictogrammes emoji : « ‼ », « ⁉ », « ℹ », flèches (sauf « → »), symboles techniques, formes
# géométriques, symboles divers, dingbats, flèches et formes emoji, sélecteur de variante
# emoji (U+FE0F) et plans pictographiques. Ni « → », ni « · », ni « © », ni « ▌ ».
EMOJI_RE = re.compile(
    "[\u203c\u2049\u2139\u2190\u2191\u2193-\u21ff\u2300-\u23ff\u25a0-\u25ff"
    "\u2600-\u27bf\u2b00-\u2bff\ufe0f\U0001f000-\U0001faff]"
)
# Seule exception autorisée par DESIGN.md : l'accueil de l'agent.
ALLOWED_EMOJI_LINE = "👋 Bonjour !"

HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
# Cherché sur le fichier entier : attrape aussi st.markdown(\n    "### …").
MARKDOWN_HEADING_RE = re.compile(r"""markdown\(\s*f?["']#""")

# Fichiers de src/core dont les textes renvoyés atteignent l'interface (journal d'outils,
# bulles de chat).
CORE_DISPLAYED_SOURCES = [
    ROOT_DIR / "src" / "core" / "agent_tools.py",
    ROOT_DIR / "src" / "core" / "llm_provider.py",
    *sorted((ROOT_DIR / "src" / "core" / "providers").glob("*.py")),
]


def _app_sources():
    """Fichiers Python de l'app rendus par les pages (src/app/components n'est pas importé)."""
    files = sorted(APP_DIR.rglob("*.py"))
    return [f for f in files if "components" not in f.relative_to(APP_DIR).parts]


def _config():
    return toml.load(CONFIG_PATH)


# ---------------------------------------------------------------------------
# Configuration du thème
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_theme_colors_match_design(mode):
    """[theme.light] et [theme.dark] reprennent le tableau Colors de DESIGN.md."""
    section = _config()["theme"][mode]

    assert {k: section.get(k) for k in EXPECTED_THEME[mode]} == EXPECTED_THEME[mode]
    assert set(section) - set(EXPECTED_THEME[mode]) == EXTRA_THEME_KEYS[mode]


def test_theme_keys_exist_in_installed_streamlit():
    """Chaque clé de thème et d'option utilisée existe dans la version figée de Streamlit."""
    known = st_config._config_options_template
    config = _config()

    used = [f"client.{k}" for k in config["client"]] + [f"server.{k}" for k in config["server"]]
    for key, value in config["theme"].items():
        if isinstance(value, dict):
            used += [f"theme.{key}.{sub}" for sub in value]
        else:
            used.append(f"theme.{key}")

    unknown = [k for k in used if k not in known]
    assert not unknown, f"Options inconnues de Streamlit : {unknown}"


def test_theme_shape_and_fonts():
    """Rayon, pile de polices et Inter servie localement (aucun CDN)."""
    theme = _config()["theme"]

    assert theme["baseRadius"] == "12px"
    assert theme["font"] == FONT_STACK
    assert theme["headingFont"] == FONT_STACK

    faces = theme["fontFaces"]
    assert {f["family"] for f in faces} == {"Inter"}
    assert {f["style"] for f in faces} == {"normal", "italic"}
    for face in faces:
        url = face["url"]
        assert url.startswith("app/static/"), f"Police hors service statique : {url}"
        assert (APP_DIR / "static" / url.removeprefix("app/static/")).is_file(), url

    assert (APP_DIR / "static" / "fonts" / "LICENSE.txt").is_file()
    assert not list((APP_DIR / "static").rglob("*ptos*")), "Aucun fichier Aptos versionné"


def test_toolbar_and_static_serving():
    """Barre d'outils en mode lecteur (pas de « Deploy »), fichiers statiques servis."""
    config = _config()

    assert config["client"]["toolbarMode"] == "viewer"
    assert config["server"]["enableStaticServing"] is True
    assert (APP_DIR / "static" / "wordmark.svg").is_file()


# ---------------------------------------------------------------------------
# Code source de l'app
# ---------------------------------------------------------------------------


def test_app_sources_have_no_deprecated_width_nor_injected_html():
    """Ni use_container_width, ni hex, ni <style>, ni unsafe_allow_html, ni titre markdown."""
    offenders = []
    for path in _app_sources():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if (
                "use_container_width" in line
                or "unsafe_allow_html" in line
                or "<style" in line
                or HEX_RE.search(line)
                or re.search(r"<h[1-6]", line)
            ):
                offenders.append(f"{path.relative_to(ROOT_DIR)}:{lineno}: {line.strip()}")
        if MARKDOWN_HEADING_RE.search(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(ROOT_DIR)}: titre markdown (st.markdown('#…'))")

    assert not offenders, "\n".join(offenders)


def test_app_sources_have_no_emoji():
    """Aucun emoji dans src/app ni dans les textes renvoyés par les outils et providers,
    sauf l'accueil « 👋 Bonjour ! » de l'agent."""
    offenders = []
    for path in _app_sources() + CORE_DISPLAYED_SOURCES:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if EMOJI_RE.search(line.replace(ALLOWED_EMOJI_LINE, "")):
                offenders.append(f"{path.relative_to(ROOT_DIR)}:{lineno}: {line.strip()}")

    assert not offenders, "\n".join(offenders)


def test_tool_display_names_have_no_emoji():
    """Les noms affichés en pastilles (TOOLS_METADATA) sont du texte seul."""
    from src.core.agent_tools import TOOLS_METADATA

    assert len(TOOLS_METADATA) == 9
    for tool_id, meta in TOOLS_METADATA.items():
        assert not EMOJI_RE.search(meta["name"]), f"{tool_id} : {meta['name']}"


def test_page_icons_are_local_files():
    """Aucun page_icon Material : le navigateur le téléchargerait depuis fonts.gstatic.com."""
    pages = [APP_DIR / "Accueil.py", APP_DIR / "home.py", *sorted((APP_DIR / "views").glob("*.py"))]
    assert len(pages) == 6
    for path in pages:
        source = path.read_text(encoding="utf-8")
        assert "page_icon=FAVICON_PATH" in source, path.name
        assert not re.search(r"page_icon\s*=\s*[\"']:material/", source), path.name

    from src.app.ui import FAVICON_PATH

    assert FAVICON_PATH.is_file()
    assert FAVICON_PATH.parent == APP_DIR / "static"


def test_module_icons_are_material_and_not_shared():
    """Chaque page a sa propre icône Material, déclarée une fois dans modules.py avec le fichier
    de la page, portée par le menu et le lien de l'accueil, et utilisée nulle part ailleurs."""
    from src.app.modules import HOME_ICON, MODULES

    declared = {"home.py": HOME_ICON} | {m.path: m.icon for m in MODULES}
    assert declared == {page: f":material/{icon}:" for page, icon in MODULE_ICONS.items()}

    modules_src = (APP_DIR / "modules.py").read_text(encoding="utf-8")
    for page, icon in MODULE_ICONS.items():
        assert modules_src.count(f":material/{icon}:") == 1, page

    # Le routeur et l'accueil lisent l'icône dans modules.py, jamais en dur.
    accueil = (APP_DIR / "Accueil.py").read_text(encoding="utf-8")
    home = (APP_DIR / "home.py").read_text(encoding="utf-8")
    assert "icon=module.icon" in accueil and "icon=HOME_ICON" in accueil
    assert "icon=module.icon" in home

    for path in _app_sources():
        if path.name == "modules.py":
            continue
        source = path.read_text(encoding="utf-8")
        for page, icon in MODULE_ICONS.items():
            assert f":material/{icon}:" not in source, f"{path.name} réutilise l'icône de {page}"


def test_no_legacy_pages_directory():
    """Aucun dossier pages/ à côté du point d'entrée : Streamlit exécuterait alors la première
    requête sans le routeur st.navigation (anciens noms, pas de contrôle cloud)."""
    assert not (APP_DIR / "pages").exists()


# ---------------------------------------------------------------------------
# Rendu (AppTest)
# ---------------------------------------------------------------------------


def _run(page):
    at = AppTest.from_file(str(APP_DIR / page), default_timeout=RENDER_TIMEOUT_S)
    at.run()
    return at


def _stop_tracker(at):
    if "tracker" in at.session_state:
        at.session_state["tracker"].stop()


@pytest.mark.parametrize("page", PAGES)
def test_page_has_single_title_without_emoji(page):
    """Un seul st.title par page, sans emoji."""
    at = _run(page)
    try:
        assert not at.exception, [e.value for e in at.exception]
        titles = [t.value for t in at.title]
        assert len(titles) == 1, titles
        assert not EMOJI_RE.search(titles[0]), titles[0]
    finally:
        _stop_tracker(at)


def test_agent_solo_shows_all_nine_tools():
    """Agent seul : les 9 outils sont proposés en pastilles, repliables sur plusieurs lignes."""
    at = _run("views/04_Agent_Lab.py")
    try:
        assert not at.exception, [e.value for e in at.exception]
        pills = [p for p in at.button_group if p.label == "Outils"]
        assert len(pills) == 1
        assert len(pills[0].options) == 9
    finally:
        _stop_tracker(at)


def test_agent_lab_model_order_and_tool_log_states(monkeypatch):
    """Agents autonomes : modèles aux outils vérifiés d'abord (cloud avant local), puis les autres ;
    l'état d'un journal d'outil vient du champ « done », pas du texte."""
    from src.core.llm_provider import LLMProvider
    from tests.app.conftest import FAKE_LOCAL_MODELS

    cloud = {"model": "mistral-large-2512", "size": 0, "type": "cloud", "provider": "mistral"}
    models = [dict(m) for m in FAKE_LOCAL_MODELS] + [cloud]
    monkeypatch.setattr(
        LLMProvider,
        "list_models",
        staticmethod(lambda cloud_enabled=True: [dict(m) for m in models]),
    )

    at = AppTest.from_file(str(APP_DIR / "views/04_Agent_Lab.py"), default_timeout=RENDER_TIMEOUT_S)
    at.session_state["agent_messages"] = [
        {"role": "user", "content": "Demande"},
        {
            "role": "assistant",
            "type": "tool_log",
            "tool": "calculator",
            "args": {},
            "content": "Résultat de l'outil:\n4",
            "done": True,
        },
        {
            "role": "assistant",
            "type": "tool_log",
            "tool": "system_monitor",
            "args": {},
            "content": "En attente du résultat...",
        },
    ]
    try:
        at.run()
        assert not at.exception, [e.value for e in at.exception]

        (select,) = [s for s in at.selectbox if s.label == "Modèle"]
        assert select.options == [
            "Mistral Large · Cloud · outils vérifiés",
            "Qwen 2.5 1.5B · Local · outils vérifiés",
            "Gemma 3 1B · Local",
        ]

        # Libellé = nom affiché de l'outil (lexique), pas son identifiant interne.
        states = {s.label: s.state for s in at.status}
        assert states == {"Calculatrice": "complete", "Moniteur système": "running"}
    finally:
        _stop_tracker(at)
