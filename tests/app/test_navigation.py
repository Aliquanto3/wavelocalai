"""
Tests de la navigation et du vocabulaire (story 3) : menu st.navigation, nom unique par module,
contrôle cloud unique, anciens noms absents des textes affichés.

Référence : _bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md.
Usage: python -m pytest tests/app/test_navigation.py -v
"""

import ast
import re
from types import SimpleNamespace

import pytest
import streamlit
from streamlit.testing.v1 import AppTest

from src.app.formatting import NBSP
from tests.app.conftest import APP_DIR, ROOT_DIR
from tests.app.test_pages import RENDER_TIMEOUT_S

# Information Architecture d'EXPERIENCE.md : ordre du menu, noms et icônes.
EXPECTED_MENU = [
    ("Accueil", ":material/home:"),
    ("Arène des modèles", ":material/leaderboard:"),
    ("Assistant documentaire", ":material/description:"),
    ("Agents autonomes", ":material/smart_toy:"),
    ("Sobriété et matériel", ":material/eco:"),
]
# Fichier de page → (nom du module, url_path hérité des anciens fichiers).
MODULE_PAGES = {
    "views/02_Inference_Arena.py": ("Arène des modèles", "Inference_Arena"),
    "views/03_RAG_Knowledge.py": ("Assistant documentaire", "RAG_Knowledge"),
    "views/04_Agent_Lab.py": ("Agents autonomes", "Agent_Lab"),
    "views/01_Socle_Hardware.py": ("Sobriété et matériel", "Socle_Hardware"),
}
HOME_TAB_TITLE = "WaveLocalAI"
CLOUD_TOGGLE = "Autoriser le cloud"
# Badges de DESIGN.md (badge-local, badge-cloud), tels que st.badge les rend.
LOCAL_BADGE = ":green-badge[:material/computer: Local]"
CLOUD_BADGE = ":orange-badge[:material/cloud: Cloud]"

# Anciens noms et jargon interdits dans les textes affichés de src/app.
FORBIDDEN_TEXTS = [
    re.compile(r"Inference Arena", re.I),
    re.compile(r"RAG Knowledge", re.I),
    re.compile(r"Agent Lab", re.I),
    re.compile(r"Socle Hardware", re.I),
    re.compile(r"Cockpit GreenOps", re.I),
    re.compile(r"chunks", re.I),
    re.compile(r"FIGHT", re.I),
    re.compile(r"Activer Cloud", re.I),
    re.compile(r"\bGB\b"),
]


@pytest.fixture
def spies(monkeypatch):
    """Enregistre les pages passées à st.navigation et chaque appel à st.set_page_config."""
    recorded = {"pages": None, "page_configs": []}
    original_navigation = streamlit.navigation
    original_page_config = streamlit.set_page_config

    def navigation(pages, *args, **kwargs):
        recorded["pages"] = list(pages)
        return original_navigation(pages, *args, **kwargs)

    def set_page_config(*args, **kwargs):
        recorded["page_configs"].append(kwargs)
        return original_page_config(*args, **kwargs)

    monkeypatch.setattr(streamlit, "navigation", navigation)
    monkeypatch.setattr(streamlit, "set_page_config", set_page_config)
    return recorded


def _app():
    return AppTest.from_file(str(APP_DIR / "Accueil.py"), default_timeout=RENDER_TIMEOUT_S)


def _stop_tracker(at):
    if "tracker" in at.session_state:
        at.session_state["tracker"].stop()


def _tab_title(recorded):
    """Titre de l'onglet : dernier page_title passé à st.set_page_config pendant l'exécution."""
    titles = [c["page_title"] for c in recorded["page_configs"] if c.get("page_title")]
    return titles[-1] if titles else None


def _cloud_toggles(at):
    return [t for t in at.toggle if "cloud" in t.label.lower()]


# ---------------------------------------------------------------------------
# Routeur (AppTest)
# ---------------------------------------------------------------------------


def test_menu_order_names_and_icons(spies):
    """Menu : Accueil, Arène des modèles, Assistant documentaire, Agents autonomes, Sobriété
    et matériel, dans cet ordre, chacun avec son icône ; l'accueil est la page par défaut."""
    at = _app()
    try:
        at.run()
        assert not at.exception, [e.value for e in at.exception]

        pages = spies["pages"]
        assert [(p.title, p.icon) for p in pages] == EXPECTED_MENU
        # Page par défaut (url_path vide), puis les anciens chemins d'URL, dans l'ordre du menu.
        assert [p.url_path for p in pages] == ["", *(u for _, u in MODULE_PAGES.values())]
    finally:
        _stop_tracker(at)


def test_home_titles(spies):
    """Accueil : h1 et onglet du navigateur « WaveLocalAI » ; une carte par module, dont le
    lien porte le nom exact du module ; « Arène des modèles » en tête, « Démo recommandée »."""
    at = _app()
    try:
        at.run()
        assert not at.exception, [e.value for e in at.exception]

        assert [t.value for t in at.title] == [HOME_TAB_TITLE]
        assert _tab_title(spies) == HOME_TAB_TITLE
        assert "Démo recommandée" in [c.value for c in at.caption]

        # AppTest n'a pas d'accesseur dédié aux liens de page : lecture du proto.
        links = [(e.proto.label, e.proto.icon) for e in at.get("page_link")]
        assert links == EXPECTED_MENU[1:]
    finally:
        _stop_tracker(at)


@pytest.mark.parametrize("page", list(MODULE_PAGES))
def test_module_title_matches_menu(spies, page):
    """Chaque module : même nom dans le menu, en st.title et dans l'onglet du navigateur."""
    name, _ = MODULE_PAGES[page]
    at = _app()
    try:
        at.run()
        spies["page_configs"].clear()
        at.switch_page(page).run()
        assert not at.exception, [e.value for e in at.exception]

        menu = {p.title for p in spies["pages"]}
        assert name in menu
        assert [t.value for t in at.title] == [name]
        assert _tab_title(spies) == name
    finally:
        _stop_tracker(at)


@pytest.mark.parametrize("page", ["home.py", *MODULE_PAGES])
def test_single_cloud_toggle_per_page(page):
    """Un seul contrôle cloud par page, « Autoriser le cloud », dans la barre latérale."""
    at = _app()
    try:
        at.run()
        if page != "home.py":
            at.switch_page(page).run()
        assert not at.exception, [e.value for e in at.exception]

        toggles = _cloud_toggles(at)
        assert [t.label for t in toggles] == [CLOUD_TOGGLE]
        assert [t.label for t in at.sidebar.toggle] == [CLOUD_TOGGLE]
        assert toggles[0].help and "quittent la machine" in toggles[0].help
    finally:
        _stop_tracker(at)


def test_cloud_state_survives_page_switch(monkeypatch):
    """Local au démarrage (D1, story 8) : les pages ne demandent que les modèles locaux.
    Activé sur l'accueil, le cloud reste activé sur les autres pages ; désactivé de nouveau,
    il le reste aussi."""
    from src.core.llm_provider import LLMProvider
    from tests.app.conftest import FAKE_LOCAL_MODELS

    calls = []

    def list_models(cloud_enabled=True):
        calls.append(cloud_enabled)
        return [dict(m) for m in FAKE_LOCAL_MODELS]

    monkeypatch.setattr(LLMProvider, "list_models", staticmethod(list_models))

    at = _app()
    try:
        at.run()
        # Local à chaque démarrage, même avec une clé d'API (D1).
        assert at.toggle(key="cloud_enabled").value is False

        for enabled in (False, True, False):
            at.switch_page("home.py").run()
            at.toggle(key="cloud_enabled").set_value(enabled).run()
            assert at.session_state["cloud_enabled"] is enabled

            for page in ["views/02_Inference_Arena.py", "views/04_Agent_Lab.py"]:
                calls.clear()
                at.switch_page(page).run()
                assert not at.exception, [e.value for e in at.exception]

                assert at.toggle(key="cloud_enabled").value is enabled
                assert at.session_state["cloud_enabled"] is enabled
                assert calls and all(c is enabled for c in calls), (page, enabled, calls)
    finally:
        _stop_tracker(at)


def _metric(at, label):
    (value,) = [m.value for m in at.metric if m.label == label]
    return value


@pytest.mark.parametrize("page", ["home.py", "views/01_Socle_Hardware.py"])
def test_mode_metric_follows_cloud_toggle(page):
    """Métrique « Mode » : « Local » et badge Local vert au démarrage (D1, story 8), « Cloud »
    et badge Cloud orange après bascule du contrôle global."""
    at = _app()
    try:
        at.run()
        if page != "home.py":
            at.switch_page(page).run()
        assert not at.exception, [e.value for e in at.exception]
        assert _metric(at, "Mode") == "Local"
        badges = [m.value for m in at.markdown]
        assert LOCAL_BADGE in badges and CLOUD_BADGE not in badges

        at.toggle(key="cloud_enabled").set_value(True).run()
        assert not at.exception, [e.value for e in at.exception]
        assert _metric(at, "Mode") == "Cloud"
        badges = [m.value for m in at.markdown]
        assert CLOUD_BADGE in badges and LOCAL_BADGE not in badges
    finally:
        _stop_tracker(at)


def test_documents_assistant_with_indexed_base(monkeypatch):
    """Assistant documentaire, base non vide : légende accordée (sources vides ignorées) ;
    modèles demandés sans le cloud au démarrage, avec le cloud après bascule."""
    from src.core.llm_provider import LLMProvider
    from src.core.rag_engine import RAGEngine
    from tests.app.conftest import FAKE_LOCAL_MODELS

    calls = []

    def list_models(cloud_enabled=True):
        calls.append(cloud_enabled)
        return [dict(m) for m in FAKE_LOCAL_MODELS]

    monkeypatch.setattr(LLMProvider, "list_models", staticmethod(list_models))
    monkeypatch.setattr(
        RAGEngine,
        "get_stats",
        lambda self: {
            "count": 14,
            "sources": ["note.docx", "cadrage.pdf", None],
            "collection": "t",
        },
    )

    at = _app()
    try:
        at.run()
        at.switch_page("views/03_RAG_Knowledge.py").run()
        assert not at.exception, [e.value for e in at.exception]
        assert f"2{NBSP}documents indexés · 14{NBSP}extraits" in [c.value for c in at.caption]
        assert calls and not any(calls)

        calls.clear()
        at.toggle(key="cloud_enabled").set_value(True).run()
        assert not at.exception, [e.value for e in at.exception]
        assert calls and all(calls)
    finally:
        _stop_tracker(at)


def test_agents_crew_mode_renders():
    """Agents autonomes, mode « Équipe d'agents » choisi dans la barre latérale : rendu sans
    exception."""
    at = _app()
    try:
        at.run()
        at.switch_page("views/04_Agent_Lab.py").run()
        (mode,) = [r for r in at.sidebar.radio if r.label == "Mode"]
        assert mode.options == ["Agent seul", "Équipe d'agents"]

        mode.set_value("Équipe d'agents").run()
        assert not at.exception, [e.value for e in at.exception]
        assert [t.value for t in at.title] == ["Agents autonomes"]
        assert "Enchaînement des agents" in [h.value for h in at.header]
    finally:
        _stop_tracker(at)


def test_home_metrics_use_french_formats(monkeypatch):
    """Accueil, psutil simulé : « 8,1 % » et mémoire en Go avec virgule décimale."""
    import psutil

    gib = 1024**3
    memory = SimpleNamespace(
        total=32 * gib, available=18.2 * gib, percent=43.1, used=13.8 * gib, free=18.2 * gib
    )
    monkeypatch.setattr(psutil, "cpu_percent", lambda *args, **kwargs: 8.1)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: memory)

    at = _app()
    try:
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert _metric(at, "Processeur") == f"8,1{NBSP}%"
        assert _metric(at, "Mémoire") == f"13,8 / 32,0{NBSP}Go"
    finally:
        _stop_tracker(at)


# ---------------------------------------------------------------------------
# Textes affichés (source)
# ---------------------------------------------------------------------------


def _displayed_strings(path):
    """Littéraux de chaîne d'un fichier (f-strings comprises), hors docstrings.

    Les commentaires ne sont pas des littéraux ; les docstrings (instruction réduite à une
    chaîne) ne sont jamais affichées.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            yield node.lineno, node.value


def test_no_legacy_names_in_displayed_texts():
    """Aucun ancien nom de module ni jargon (« chunks », « FIGHT », « Activer Cloud », « GB »)
    dans les textes de src/app."""
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for lineno, text in _displayed_strings(path):
            for pattern in FORBIDDEN_TEXTS:
                if pattern.search(text):
                    offenders.append(f"{path.relative_to(ROOT_DIR)}:{lineno}: {text!r}")

    assert not offenders, "\n".join(offenders)


def test_forbidden_texts_check_detects_offenders(tmp_path):
    """Le contrôle de source voit les f-strings et ignore les docstrings."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        '"""Docstring : Agent Lab."""\n'
        "import streamlit as st\n"
        'st.caption(f"{n} chunks indexés")\n'
        'st.metric("RAM", f"{x} GB")\n',
        encoding="utf-8",
    )

    found = [
        text
        for _, text in _displayed_strings(sample)
        if any(p.search(text) for p in FORBIDDEN_TEXTS)
    ]
    assert found == [" chunks indexés", " GB"]


def test_tool_names_follow_lexicon():
    """Pastilles de l'agent : noms français du lexique, identifiants internes inchangés."""
    from src.core.agent_tools import AVAILABLE_TOOLS, TOOLS_METADATA

    assert {tool_id: meta["name"] for tool_id, meta in TOOLS_METADATA.items()} == {
        "get_current_time": "Heure",
        "calculator": "Calculatrice",
        "search_wavestone_internal": "Recherche interne Wavestone",
        "send_email": "Envoi d'email",
        "analyze_csv": "Analyse de données",
        "generate_document": "Génération de document",
        "generate_chart": "Génération de graphique",
        "generate_markdown_report": "Rapport Markdown",
        "system_monitor": "Moniteur système",
    }
    assert {t.name for t in AVAILABLE_TOOLS} == set(TOOLS_METADATA)
