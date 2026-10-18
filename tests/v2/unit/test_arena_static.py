"""Écran Arène et colonne `wl-arena-lane` (story 3.2) : règles de structure et textes, sans
navigateur. Les parcours (flux, délais, reprise, onglets, axe) vivent dans
`tests/v2/e2e/test_arena.py`."""

from __future__ import annotations

import json
import re
from pathlib import Path

from wavelocalai.inference.arena import LANE_STATUSES

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "src" / "wavelocalai" / "web" / "static"
CATALOG = json.loads((STATIC / "i18n/fr.json").read_text(encoding="utf-8"))
NEW_SCRIPTS = ["screens/arena.js", "components/wl-arena-lane.js"]


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_every_arena_text_the_scripts_name_exists_in_the_catalog():
    used: set[str] = set()
    for name in NEW_SCRIPTS:
        used |= set(re.findall(r"""\bt\(\s*["'](arena\.[\w.]+)["']""", source(name)))
        used |= set(re.findall(r"""\bt\(\s*["'](components\.lane\.[\w.]+)["']""", source(name)))
    assert {"arena.launch", "arena.need_models", "arena.execution"} <= used
    for key in used:
        value = CATALOG
        for part in key.split("."):
            value = value[part]
        assert isinstance(value, str), key


def test_the_dynamic_text_families_match_the_catalog():
    screen = source("screens/arena.js")
    scenarios = re.search(r"const SCENARIOS = \[(.*?)\];", screen, re.DOTALL)
    assert scenarios
    assert re.findall(r'"(\w+)"', scenarios.group(1)) == list(CATALOG["arena"]["scenario"])
    for scenario in CATALOG["arena"]["scenario"].values():
        assert scenario["label"] and scenario["prompt"]
    assert {"running", "ok", "cancelled", "error", "interrupted", "stopping"} == set(
        CATALOG["arena"]["banner"]
    )
    assert {"started", "ok", "cancelled", "error", "interrupted"} == set(
        CATALOG["arena"]["announce"]
    )


def test_every_lane_status_of_the_server_has_a_text_and_an_icon():
    statuses = set(CATALOG["components"]["lane"]["status"])
    assert set(LANE_STATUSES) | {"judging", "interrupted"} == statuses
    lane = source("components/wl-arena-lane.js")
    icons = set(re.findall(r'i-([\w-]+)"', (STATIC / "icons.svg").read_text(encoding="utf-8")))
    block = re.search(r"const STATUS_ICON = \{(.*?)\};", lane, re.DOTALL)
    assert block
    named = dict(re.findall(r'(\w+): "([\w-]+)"', block.group(1)))
    assert set(named) == statuses
    assert set(named.values()) <= icons
    assert {"open-in-full"} <= icons


def test_the_scenarios_fill_the_question_with_the_four_scenarios_of_the_spec():
    labels = [s["label"] for s in CATALOG["arena"]["scenario"].values()]
    assert labels == ["Vulgarisation", "Extraction JSON", "Résumé", "Traduction"]
    assert CATALOG["arena"]["execution"].replace(" ", " ") == (
        "Les modèles locaux passent l'un après l'autre (mémoire) ; les modèles cloud en parallèle."
    )
    assert CATALOG["arena"]["need_models"] == "Choisissez au moins 2 modèles"
    assert CATALOG["components"]["lane"]["timeout_note"] == (
        "Délai dépassé pour ce modèle. Les autres continuent."
    )


def test_the_model_text_never_reaches_the_dom_as_html():
    forbidden = re.compile(
        r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|createContextualFragment|"
        r"DOMParser|\beval\(|new Function|setAttribute\(\s*[\"']on|srcdoc"
    )
    for name in NEW_SCRIPTS:
        code = "\n".join(
            line for line in source(name).splitlines() if not line.lstrip().startswith("//")
        )
        assert not forbidden.search(code), name


def test_the_screen_reads_the_run_stream_once_and_resumes_by_after():
    screen = source("screens/arena.js")
    assert screen.count("connectRun(") == 1 and "EventSource" not in screen
    assert "keepSeq: true" in screen  # masqué : le dernier `seq` reste, la reprise est `?after=`
    assert "allow_cloud: store.get().allowCloud" in screen  # AD-9, sur chaque commande
    assert "run_busy" in screen and "params.run_id" in screen
    assert screen.count("api.startArena(") == 1 and "api.cancelRun(" in screen
    assert "grid-auto-columns" in source("arena.css")  # deux colonnes visibles, défilement


def test_the_launch_button_is_a_primary_fill_surface_with_a_visible_reason():
    css = source("arena.css")
    block = re.search(r"\.arena-launch \{(.*?)\}", css, re.DOTALL)
    assert block and "var(--color-primary-fill)" in block.group(1)
    assert "var(--color-primary)" not in block.group(1)  # A19 : jamais le violet de texte
    assert "aria-describedby" in source("screens/arena.js")


def test_the_arena_css_is_linked_and_the_front_files_stay_under_the_size_budget():
    assert '<link rel="stylesheet" href="/static/arena.css">' in source("index.html")
    for name in [*NEW_SCRIPTS, "arena.css"]:
        assert len(source(name).splitlines()) <= 600, name
