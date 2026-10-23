"""Écran Banc d'essai (story 7.4) : règles de structure, de textes et de style, sans navigateur.

Les parcours (formulaire, flux, verdict, réouverture, liste, délai, axe) vivent dans
`e2e/test_bench.py`.
"""

from __future__ import annotations

import re

from .static_files import STATIC, catalog, read_static

CATALOG = catalog()
SCREEN_FILES = (
    "screens/bench.js",
    "screens/bench-form.js",
    "screens/bench-result.js",
    "screens/bench-history.js",
)
NBSP = "\N{NO-BREAK SPACE}"


def source(name: str) -> str:
    return read_static(name)


def lookup(key: str):
    value = CATALOG
    for part in key.split("."):
        value = value[part]
    return value


def leaves(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, f"{path}.{key}" if path else key)
    else:
        yield path, value


def test_the_screen_is_registered_as_available_with_its_path_parameter():
    registry = source("core/routes/arena.js")
    assert re.search(
        r'id: "arena-bench",\s*path: "/arene/banc",\s*param: "run_id",\s*status: "available",\s*'
        r'load: \(\) => import\("\.\./\.\./screens/bench\.js"\)',
        registry,
    )


def test_the_texts_have_their_own_file_declared_once_with_one_top_level_key():
    assert source("core/i18n.js").count('"bench",') == 1
    assert list(CATALOG["bench"]) and (STATIC / "i18n/fr/bench.json").exists()


def test_every_text_key_the_screen_names_exists():
    used: set[str] = set()
    for name in SCREEN_FILES:
        text = source(name)
        used |= set(re.findall(r"""\bt\(\s*["'](bench\.[\w.]+)["']""", text))
        used |= set(re.findall(r"""\bt\(\s*["'](screens\.[\w-]+)["']""", text))
    assert {"bench.launch", "bench.actions.rerun", "bench.actions.edit"} <= used
    for key in used:
        assert isinstance(lookup(key), str), key


def test_the_dynamic_text_families_match_the_catalog():
    form = source("screens/bench-form.js")
    # Les types du schéma : un texte français par type de schéma JSON que le serveur emploie.
    assert set(CATALOG["bench"]["types"]) >= {"string", "number", "integer", "object", "array"}
    assert "bench.types.${name}" in form
    result = source("screens/bench.js")
    for state in ("ok", "ko", "done", "cancelled", "failed"):
        assert isinstance(CATALOG["bench"]["announce"][state], str)
    assert "bench.announce.${key}" in result
    assert set(CATALOG["bench"]["history"]["status"]) == {
        "ok",
        "cancelled",
        "error",
        "interrupted",
        "running",
    }
    assert "bench.history.status.${state}" in source("screens/bench-history.js")


def test_french_texts_put_a_no_break_space_before_double_punctuation_and_use_no_emoji():
    for key, text in leaves(CATALOG["bench"], "bench"):
        assert isinstance(text, str), key
        assert not re.search(r"[A-Za-zÀ-ÿ0-9)»] [:;!?»]", text), key
        assert not re.search(r"« | »", text), key
        assert not re.search("[\U0001f300-\U0001faff☀-➿]", text), key
    assert CATALOG["bench"]["timeout"] == f"Délai dépassé ({{seconds}}{NBSP}s)"


def test_the_stylesheet_is_linked_after_the_components_and_has_no_hard_coded_color():
    html = source("index.html")
    assert html.count('href="/static/bench.css"') == 1
    assert html.index("/static/evaluation.css") < html.index("/static/bench.css")
    css = source("bench.css")
    assert "@import" not in css
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", css)
    # Le verdict est dit en mots et en icône, la couleur n'est qu'un renfort.
    assert "data-ok" in css and "icon" in css


def test_the_screen_validates_and_measures_nothing_itself_and_never_writes_html():
    for name in SCREEN_FILES:
        text = "\n".join(
            line for line in source(name).splitlines() if not line.lstrip().startswith("//")
        )
        assert "innerHTML" not in text and "insertAdjacentHTML" not in text, name
        assert "JSON.parse" not in text and "JSON.stringify" not in text, name
        assert "localStorage" not in text, name
    assert "format_verdict" in source("screens/bench.js")


def test_the_api_exposes_the_bench_calls_under_their_own_domain_file():
    api = source("core/api/bench.js")
    assert 'request("/api/scenarios")' in api
    assert 'request("/api/bench/runs", { method: "POST", body })' in api
    assert "/api/bench/runs?limit=" in api
    assert 'from "./api/bench.js"' in source("core/api.js")
    assert "...benchApi(request)," in source("core/api.js")


def test_a_timeout_names_the_real_delay_the_server_applied():
    screen = source("screens/bench.js")
    assert "detail?.timeout_s" in screen and 'error?.code !== "timeout"' in screen
