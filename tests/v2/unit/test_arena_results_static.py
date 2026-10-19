"""Classement, matrice et tableau de l'Arène (story 3.4) : règles de structure et textes, sans
navigateur. Les parcours et les calculs d'échelle (exécutés dans la page) vivent dans
`tests/v2/e2e/test_arena_results.py`."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "src" / "wavelocalai" / "web" / "static"
CATALOG = json.loads((STATIC / "i18n/fr.json").read_text(encoding="utf-8"))
SCRIPTS = [
    "screens/arena-results.js",
    "screens/arena-results-data.js",
    "screens/arena-tabs.js",
    "screens/arena-verdict.js",
    "components/wl-chart-svg.js",
    "components/segments.js",
    "core/chart-scale.js",
]
NBSP = "\N{NO-BREAK SPACE}"


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def lookup(key: str):
    value = CATALOG
    for part in key.split("."):
        value = value[part]
    return value


def code_of(name: str) -> str:
    return "\n".join(
        line for line in source(name).splitlines() if not line.lstrip().startswith("//")
    )


def test_every_text_the_results_scripts_name_exists_in_the_catalog():
    used: set[str] = set()
    for name in SCRIPTS:
        used |= set(
            re.findall(
                r"""\bt\(\s*["']((?:arena\.(?:results|chart)|components\.\w+)\.[\w.]+)["']""",
                source(name),
            )
        )
    assert {"arena.results.title", "arena.chart.see_table", "arena.chart.same_unit"} <= used
    assert lookup("arena.results.help_live") and lookup("arena.results.help_frozen")
    for key in used:
        assert isinstance(lookup(key), str), key


def test_the_dynamic_text_families_match_the_catalog():
    results = source("screens/arena-results.js")
    partial = re.search(r"const PARTIAL = new Set\(\[(.*?)\]\);", results)
    assert partial
    states = re.findall(r'"(\w+)"', partial.group(1))
    assert set(states) == {"cancelled", "interrupted", "error"}
    for state in states:
        assert lookup(f"arena.results.partial_{state}")
    for key in (
        "col_model",
        "col_origin",
        "col_score",
        "col_rate",
        "col_co2",
        "col_load",
        "col_total",
    ):
        assert CATALOG["arena"]["chart"][key]
    for key in ("score", "rate", "load", "co2"):
        assert CATALOG["arena"]["chart"][f"def_{key}"]
    assert CATALOG["arena"]["chart"]["matrix"] == "Matrice"
    assert CATALOG["arena"]["chart"]["table"] == "Tableau"
    assert CATALOG["arena"]["chart"]["see_table"] == "Voir le tableau"


def test_the_results_texts_follow_the_french_typography():
    texts = list(CATALOG["arena"]["results"].values()) + list(CATALOG["arena"]["chart"].values())
    for text in texts:
        assert not re.search(r" [:;!?»]|« ", text), text  # espace insécable, jamais l'ordinaire
    assert CATALOG["arena"]["results"]["not_evaluated_line"] == f"Non évalué{NBSP}: {{reason}}"
    assert CATALOG["arena"]["results"]["tie"] == "ex æquo"


def test_the_not_evaluated_and_unmeasurable_states_are_texts_never_a_zero_or_a_dash():
    results = CATALOG["arena"]["results"]
    assert results["not_measured"] == "non mesuré" and results["in_progress"] == "en cours"
    assert CATALOG["components"]["thread"]["co2_unmeasurable"] == "non mesurable"
    data = code_of("screens/arena-results-data.js")
    assert '"—"' not in data and '"-"' not in data and "|| 0" not in data
    assert "components.lane.not_evaluated_status." in data  # les motifs de statut de lane (3.3)


def test_the_new_front_files_build_the_dom_without_html_strings_and_stay_small():
    forbidden = re.compile(
        r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|createContextualFragment|"
        r"DOMParser|\beval\(|new Function|setAttribute\(\s*[\"']on|srcdoc"
    )
    for name in SCRIPTS:
        assert not forbidden.search(code_of(name)), name
        assert len(source(name).splitlines()) <= 600, name
    assert len(source("arena-results.css").splitlines()) <= 600


def test_the_pure_modules_never_touch_the_page():
    for name in ("core/chart-scale.js", "screens/arena-results-data.js"):
        code = code_of(name)
        assert not re.search(r"\b(document|window|localStorage|fetch)\b", code), name


def test_the_chart_is_styled_from_tokens_only_and_the_css_is_linked():
    css = source("arena-results.css")
    components = source("components.css")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
    chart = components[components.index("/* Groupe de segments (components/segments.js)") :]
    assert not re.search(
        r"#[0-9a-fA-F]{3,8}\b", chart
    )  # segments et graphique : aucune couleur en dur
    assert "var(--color-chart-" in source("components/wl-chart-svg.js")
    assert "var(--color-primary-fill)" in chart and "var(--color-on-primary)" in chart  # A19
    assert '<link rel="stylesheet" href="/static/arena-results.css">' in source("index.html")
    assert "WlChartSvg" in source("components/index.js")


def test_the_chart_is_a_titled_described_image_whose_text_follows_the_projection_mode():
    chart = source("components/wl-chart-svg.js")
    assert 'role: "img"' in chart and '"aria-labelledby"' in chart
    assert 'add("title"' in chart and 'add("desc"' in chart
    assert "data-projection" in chart  # le tracé suit la police de la page
    components = source("components.css")
    assert "font-size: 0.75rem" in components  # le texte du SVG est en rem


def test_the_segments_are_a_radiogroup_with_arrow_keys_and_a_check_icon():
    segments = source("components/segments.js")
    assert 'setAttribute("role", "radiogroup")' in segments and '"radio"' in segments
    assert "ArrowRight" in segments and "ArrowLeft" in segments
    assert 'icon("check")' in segments  # le choix porte l'icône, jamais la seule couleur


def test_the_screen_hands_the_lanes_to_the_results_and_freezes_them_at_the_end():
    screen = source("screens/arena.js")
    assert "resultsView(uid, lanesEl)" in screen and "results.el" in screen
    assert "results.end(state, runId)" in screen and "results.reset()" in screen
    lane = source("components/wl-arena-lane.js")
    assert "wl-lane-change" in lane and lane.count("this.#changed()") >= 3
    assert "wl-lane-change" in source("screens/arena-results.js")
    # Jamais à chaque token : `token()` ne signale rien lui-même.
    token = re.search(r"  token\(text, channel\) \{(.*?)\n  \}", lane, re.DOTALL)
    assert token and "#changed" not in token.group(1)
