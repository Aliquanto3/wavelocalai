"""Écran Chat libre et fil de conversation (story 2.2) : règles de structure et textes, sans
navigateur. Les parcours (flux, arrêt, reprise, `run_busy`, axe) vivent dans
`tests/v2/e2e/test_chat.py`."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .static_files import catalog, read_static

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "src" / "wavelocalai" / "web" / "static"
CATALOG = catalog()


def source(name: str) -> str:
    return read_static(name)


NEW_SCRIPTS = [
    "screens/chat.js",
    "components/wl-chat-thread.js",
    "core/markdown.js",
    "core/drafts.js",
    "core/screen-tabs.js",
]


def test_every_thread_and_chat_text_is_used_and_every_used_text_exists():
    thread = source("components/wl-chat-thread.js")
    used = set(re.findall(r"""["']components\.thread\.(\w+)["']""", thread))
    assert used == set(CATALOG["components"]["thread"])
    screen = source("screens/chat.js")
    assert set(re.findall(r"""\bt\(\s*["']chat\.(\w+)["']""", screen)) == set(CATALOG["chat"])
    assert set(
        re.findall(r"""\bt\(\s*["']tabs\.(\w+)["']""", source("core/screen-tabs.js"))
    ) == set(CATALOG["tabs"])


def test_the_model_text_never_reaches_the_dom_as_html():
    # Le texte d'un modèle et celui de la personne passent par des nœuds de texte : aucun des
    # fichiers du chat n'écrit de HTML, ni ne l'évalue.
    forbidden = re.compile(
        r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|createContextualFragment|"
        r"DOMParser|\beval\(|new Function|setAttribute\(\s*[\"']on|srcdoc"
    )
    for name in NEW_SCRIPTS:
        code = "\n".join(
            line for line in source(name).splitlines() if not line.lstrip().startswith("//")
        )
        assert not forbidden.search(code), name


def test_markdown_only_follows_safe_link_schemes():
    text = source("core/markdown.js")
    assert '["http:", "https:", "mailto:"]' in text
    assert 'rel = "noopener noreferrer"' in text


def test_the_thread_is_a_silent_log_with_a_separate_polite_announcement():
    thread = source("components/wl-chat-thread.js")
    assert 'setAttribute("role", "log")' in thread
    assert 'setAttribute("aria-live", "off")' in thread  # rien n'est annoncé pendant le flux
    assert 'setAttribute("aria-live", "polite")' in thread
    assert "RENDER_MS = 150" in thread
    assert "attachShadow" not in thread


def test_the_screen_reads_the_run_stream_once_and_resumes_by_after():
    screen = source("screens/chat.js")
    assert screen.count("connectRun(") == 1 and "EventSource" not in screen
    assert "keepSeq: true" in screen  # masqué : le dernier `seq` reste, la reprise est `?after=`
    assert "allow_cloud: store.get().allowCloud" in screen  # AD-9, sur chaque commande
    assert "temperature" in screen and 'status.setAttribute("driven", "")' in screen
    run_status = source("components/wl-run-status.js")
    assert "feed(envelope)" in run_status and "abandon()" in run_status


def test_the_stop_error_code_is_the_one_of_the_server():
    # AD-5 : la coupure répétée est `generation_interrupted`, jamais `interrupted` (un statut).
    from wavelocalai.errors import ERRORS

    assert "generation_interrupted" in ERRORS and "interrupted" not in ERRORS
    assert "generation_interrupted" not in source("screens/chat.js")  # le front relaie le message


def test_new_front_files_stay_under_the_size_budget():
    for name in [*NEW_SCRIPTS, "chat.css"]:
        assert len(source(name).splitlines()) <= 600, name


def test_chat_css_is_linked_and_a_planned_tab_is_disabled_with_its_reason():
    index = source("index.html")
    assert '<link rel="stylesheet" href="/static/chat.css">' in index
    tabs = source("core/screen-tabs.js")
    assert 'setAttribute("aria-disabled", "true")' in tabs and "aria-describedby" in tabs
    registry = source("core/registry.js")
    assert re.search(r'id: "agents-crew",[^}]*status: "planned"', registry)
