"""Écran Discussion et panneau des sources (stories 4.5 et 4.6) : règles de structure et de textes,
sans navigateur. Les parcours (étapes, sources avant la réponse, passage, « extrait supprimé »,
« Afficher les sources », mise en page, reprise, axe, stratégies, citations) vivent dans
`e2e/test_discussion.py` et `e2e/test_discussion_strategies.py`."""

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


def code(name: str) -> str:
    return "\n".join(
        line for line in source(name).splitlines() if not line.lstrip().startswith("//")
    )


SCREEN_FILES = (
    "screens/documents.js",
    "screens/documents-chat-settings.js",
    "screens/documents-citations.js",
    "screens/documents-notes.js",
    "screens/documents-replay.js",
)
SCREEN = "\n".join(source(name) for name in SCREEN_FILES)
PANEL = source("components/wl-source-panel.js")


def used_keys(text: str, section: str) -> set[str]:
    literal = set(re.findall(rf"""["']{section}\.(\w+)["']""", text))
    plurals = set(re.findall(rf"""\bplural\(\s*["']{section}\.(\w+)["']""", text))
    keys = (literal - plurals) | {f"{base}_{form}" for base in plurals for form in ("one", "other")}
    # Famille choisie par un état : `t(`discussion.strategy_${key}`)`.
    for prefix in re.findall(rf"""t\(`{section}\.(\w+_)\$\{{""", text):
        keys |= {key for key in CATALOG_SECTION[section] if key.startswith(prefix)}
    return keys


CATALOG_SECTION = {
    "discussion": CATALOG["discussion"],
    "components.sources": CATALOG["components"]["sources"],
}


def test_every_discussion_text_is_used_and_exists():
    used = used_keys(SCREEN, "discussion")
    # Les textes du plural des documents d'une autre section sont lus ailleurs (`docs.chunks`).
    assert used == set(CATALOG["discussion"])


def test_every_source_panel_text_is_used_and_exists():
    used = set(re.findall(r"""["']components\.sources\.(\w+)["']""", PANEL))
    assert used == set(CATALOG["components"]["sources"])
    thread_code = source("components/wl-chat-thread.js")
    thread = set(re.findall(r"""["']components\.thread\.(\w+)["']""", thread_code))
    assert thread == set(CATALOG["components"]["thread"])
    assert {"retrieving", "hypothesizing", "verifying"} <= set(CATALOG["components"]["run_status"])


def test_the_screen_reads_the_stream_through_the_single_sse_client_and_resumes_by_after():
    text = code("screens/documents.js")
    assert "EventSource" not in text and "connectStream(" not in text
    assert text.count("connectRun(") == 1  # le run suivi
    assert (
        code("screens/documents-replay.js").count("connectRun(") == 1
    )  # le rejeu d'une réponse finie
    assert "keepSeq: true" in text  # masqué : le dernier `seq` reste, la reprise est `?after=`
    assert "allow_cloud: store.get().allowCloud" in text  # AD-9, sur chaque commande
    assert 'status.setAttribute("driven", "")' in text
    assert 'status.setAttribute("first-stage", "retrieving")' in text
    assert 'setAttribute("purpose", "rag")' in text
    run_status = source("components/wl-run-status.js")
    assert "retrieval_step:" in run_status and "sources:" in run_status
    assert "first-stage" in run_status


def test_the_documents_never_reach_the_dom_as_html():
    forbidden = re.compile(
        r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|createContextualFragment|"
        r"DOMParser|\beval\(|new Function|setAttribute\(\s*[\"']on|srcdoc"
    )
    for name in (*SCREEN_FILES, "components/wl-source-panel.js"):
        assert not forbidden.search(code(name)), name
    assert "attachShadow" not in PANEL


def test_the_passage_is_cut_by_code_points_and_chosen_by_the_server_only():
    text = code("components/wl-source-panel.js")
    assert "Array.from(" in text  # les positions de `passage` sont des points de code Python
    assert "source.passage" in text and "api.chunk(source.chunk_id)" in text
    assert "chunk_not_found" in text  # 404 : « extrait supprimé »
    for forbidden in ("relevance_label =", "raw_score *", "split(/[.!?]"):
        assert forbidden not in text  # le front ne désigne aucun passage, ne calcule aucun libellé


def test_the_panel_is_always_open_from_1024px_without_a_fold_button():
    assert '"(min-width: 1024px)"' in PANEL
    assert "event.preventDefault()" in PANEL and "tabIndex = wide ? -1 : 0" in PANEL
    css = source("components.css")
    assert re.search(r"\.wl-sources\.is-wide > \.wl-sources-summary \{[^}]*list-style: none", css)
    docs = source("documents.css")
    assert re.search(r"@media \(min-width: 1024px\) \{\s*\.docs-chat-layout \{", docs)


def test_the_passage_highlight_is_a_violet_fill_under_white_text_without_hard_coded_color():
    css = source("components.css")
    block = re.search(r"\.wl-source-mark \{(.*?)\}", css, re.DOTALL)
    assert block
    assert "var(--color-primary-fill)" in block.group(1)
    assert "var(--color-on-primary)" in block.group(1)


def test_the_screen_is_registered_as_available_and_the_panel_is_a_shared_component():
    registry = source("core/registry.js")
    assert re.search(
        r'id: "documents-chat",\s*path: "/documents",\s*status: "available",\s*'
        r'load: \(\) => import\("\.\./\.\./screens/documents\.js"\)',
        registry,
    )
    assert "wl-source-panel.js" in source("components/index.js")


def test_no_download_and_no_citation_marker_is_invented():
    text = code("screens/documents.js")
    assert "conversationExportUrl" not in text and "exportMenu" not in text
    # Seuls les marqueurs que `citations` confirme deviennent des boutons : sans `citations`, rien.
    citations = code("screens/documents-citations.js")
    assert "if (!confirmed.size) return;" in citations
    assert "record.citations" in citations and "citations: (data)" in text
    assert "hooks.enter" in citations and "wl-source-link" in text
    run_status = code("components/wl-run-status.js")
    assert "hypothesizing" in run_status and "verifying" in run_status


def test_the_technical_names_of_the_strategies_only_appear_in_help_texts():
    discussion = CATALOG["discussion"]
    labels = [v for k, v in discussion.items() if k.startswith("strategy_") and "_help" not in k]
    labels += [discussion["strategy"], discussion["top_k"], discussion["advanced"]]
    assert len(labels) >= 6
    for label in labels:
        assert not re.search(r"hyde|self-rag|top-k|naive|\brag\b", label, re.IGNORECASE), label
    helps = " ".join(v for k, v in discussion.items() if "_help" in k)
    assert "HyDE" in helps and "Self-RAG" in helps and "Top-K" in helps
    settings = code("screens/documents-chat-settings.js")
    assert 'export const STRATEGIES = ["naive", "hyde", "self_rag"];' in settings
    # le défaut et le plafond viennent des réglages de la base (4.3), plus du palliatif de la liste
    assert "api.ragSettings()" in code("screens/documents.js")
    assert "base.search" not in code("screens/documents.js")


def test_plural_texts_come_in_pairs():
    for section in (CATALOG["discussion"], CATALOG["components"]["sources"]):
        for key in section:
            if key.endswith("_one"):
                assert f"{key.removesuffix('_one')}_other" in section, key


def test_new_front_files_stay_under_the_size_budget():
    for name in (*SCREEN_FILES, "components/wl-source-panel.js", "documents.css"):
        assert len(source(name).splitlines()) <= 600, name


def test_the_reranking_stage_and_its_state_come_from_the_server_and_never_download():
    """Story 4.7 : « Reclassement… » est annoncé par `search` (`reranking`), l'état et la raison par
    `settings.reranker` ; l'écran ne devine rien et n'appelle aucune route de téléchargement."""
    run_status = code("components/wl-run-status.js")
    assert "reranking" in run_status and "step.reranking" in run_status
    assert CATALOG["components"]["run_status"]["reranking"] == "Reclassement…"
    settings = code("screens/documents-chat-settings.js")
    assert "reranker.available" in settings and "reranker.reason" in settings
    assert "reranker: settings.reranker" in code("screens/documents.js")
    assert "pull" not in settings.lower() and "fetch(" not in settings
    off = CATALOG["discussion"]["rerank_off"]
    assert off == "Reclassement indisponible\u00a0: {reason}."
    assert "{model}" in CATALOG["discussion"]["rerank_on"]
