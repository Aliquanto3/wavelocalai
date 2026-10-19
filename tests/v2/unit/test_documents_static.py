"""Écran Base documentaire (story 4.2) : règles de structure du front, sans navigateur. Les
parcours (dépôt, progression, échec, tableau, reprise, axe) vivent dans `e2e/test_documents.py`."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "src" / "wavelocalai" / "web" / "static"
CATALOG = json.loads((STATIC / "i18n/fr.json").read_text(encoding="utf-8"))


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


SCREEN = source("screens/documents-base.js") + source("screens/documents-import-row.js")
TABLE = source("components/wl-data-table.js")


def plural_bases(keys: set[str]) -> set[str]:
    return {key.rsplit("_", 1)[0] for key in keys if key.endswith(("_one", "_other"))}


def test_every_screen_text_exists_and_every_catalog_text_is_used():
    literal = set(re.findall(r"""\bt\(\s*["']docs\.(\w+)["']""", SCREEN))
    plurals = set(re.findall(r"""\bplural\(\s*["']docs\.(\w+)["']""", SCREEN))
    used = literal | {f"{base}_{form}" for base in plurals for form in ("one", "other")}
    # Famille de textes choisie par un état : `t(`docs.status_${doc.status}`)`.
    for prefix in re.findall(r"""t\(`docs\.(\w+_)\$\{""", SCREEN):
        used |= {key for key in CATALOG["docs"] if key.startswith(prefix)}
    assert used == set(CATALOG["docs"])


def test_plural_texts_come_in_pairs():
    docs = set(CATALOG["docs"])
    for base in plural_bases(docs):
        assert {f"{base}_one", f"{base}_other"} <= docs, base


def test_the_table_texts_are_used_by_the_component():
    used = set(re.findall(r"""["']components\.table\.(\w+)["']""", TABLE))
    assert used == set(CATALOG["components"]["table"])


def test_the_table_is_a_shared_component_without_shadow_dom():
    index = source("components/index.js")
    assert "wl-data-table.js" in index
    assert "attachShadow" not in TABLE and "innerHTML" not in TABLE
    # Sémantique : légende, en-têtes de colonne et de ligne, tri annoncé par `aria-sort`.
    for marker in ('"caption"', 'th.scope = "col"', 'cell.scope = "row"', "aria-sort"):
        assert marker in TABLE, marker


def test_the_screen_never_writes_html_and_reads_the_stream_through_the_single_sse_client():
    code = "\n".join(line for line in SCREEN.splitlines() if not line.lstrip().startswith("//"))
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(", code)
    assert "connectRun" in code and "EventSource" not in code
    assert "?after=" not in code  # la reprise est celle du client SSE (`keepSeq`)
    assert "keepSeq: true" in code


def test_the_drop_zone_is_built_before_any_server_call():
    # La structure est montée de façon synchrone ; le premier appel (`refresh`) vient après.
    assert SCREEN.index("drop.append(") < SCREEN.index("refresh().then(")
    assert SCREEN.index("host.replaceChildren(") < SCREEN.index("refresh().then(")


def test_the_screen_is_registered_as_available_and_its_stylesheet_is_linked():
    registry = source("core/registry.js")
    assert re.search(
        r'id: "documents-base",\s*path: "/documents/base",\s*status: "available",\s*'
        r'load: \(\) => import\("\.\./screens/documents-base\.js"\)',
        registry,
    )
    assert '<link rel="stylesheet" href="/static/documents.css">' in source("index.html")


def test_the_filled_button_is_on_primary_fill_and_the_css_has_no_color_of_its_own():
    css = source("documents.css")
    block = re.search(r"\.docs-primary \{(.*?)\}", css, re.DOTALL)
    assert block and "var(--color-primary-fill)" in block.group(1)
    assert "var(--color-on-primary)" in block.group(1)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\b(rgb|hsl)a?\(", css)


def test_new_front_files_stay_under_the_size_budget():
    for name in (
        "screens/documents-base.js",
        "screens/documents-import-row.js",
        "components/wl-data-table.js",
        "documents.css",
    ):
        assert len(source(name).splitlines()) <= 600, name


def test_the_upload_uses_xhr_for_its_progress_and_aborts_on_signal():
    api = source("core/api.js")
    assert "xhr.upload.onprogress" in api and "AbortError" in api
