"""Garde-fou mémoire côté front (story 4.8) : structure et textes, sans navigateur. Les parcours
(deux actions, question gardée, axe-core) vivent dans `tests/v2/e2e/test_memory_guard.py`."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "src" / "wavelocalai" / "web" / "static"
CATALOG = json.loads((STATIC / "i18n/fr.json").read_text(encoding="utf-8"))
NBSP = "\N{NO-BREAK SPACE}"


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_every_error_text_is_used_by_the_error_component_and_exists():
    used = set(
        re.findall(r"""["']components\.error\.(\w+)["']""", source("components/wl-error.js"))
    )
    assert used == set(CATALOG["components"]["error"])


def test_the_two_actions_carry_the_exact_labels_of_the_story():
    texts = CATALOG["components"]["error"]
    assert texts["ram_guard_smaller"] == "Prendre un modèle plus petit"
    assert texts["ram_guard_unload"] == "Décharger les modèles inactifs"


def test_the_component_computes_nothing_it_only_reads_the_envelope():
    code = "\n".join(
        line
        for line in source("components/wl-error.js").splitlines()
        if not line.lstrip().startswith("//")
    )
    assert "detail?.suggested_model" in code  # le bouton vient du serveur
    assert "needed_gb" not in code  # le besoin chiffré s'affiche dans `message`, tel quel
    assert not re.search(r"Math\.|\* *1\.1|navigator\.deviceMemory|performance\.memory", code)


def test_the_screens_that_show_the_error_choose_the_smaller_model_without_relaunching():
    for name, picked in (("screens/chat.js", "picker.value"), ("screens/arena.js", "swapModel(")):
        code = source(name)
        handler = re.search(
            r"onSmallerModel\(host, \(tag(?:, source)?\) => \{(.*?)\n  \}\);", code, re.S
        )
        assert handler, name
        assert picked in handler.group(1), name
        for launch in ("submit()", "startChat", "startArena"):
            assert launch not in handler.group(1), name


def test_the_chat_gives_the_question_back_to_the_field_on_ram_guard_only():
    code = source("screens/chat.js")
    keep = re.search(r"function keepQuestion\(data\) \{(.*?)\n  \}", code, re.S)
    assert keep
    assert "isRamGuard(data.error)" in keep.group(1)
    assert "input.value = lastMessage" in keep.group(1)
    assert 'code === "ram_guard"' in source("core/ram-guard.js")


def test_the_unload_call_is_a_post_to_the_server_route():
    assert 'request("/api/models/unload", { method: "POST"' in source("core/api.js")


def test_the_top_bar_shows_the_free_memory_the_stream_publishes():
    assert 'id="ollama-memory-free"' in source("index.html")
    assert "available_gb" in source("core/topbar.js")


def test_the_new_texts_keep_a_no_break_space_before_a_colon():
    for key in ("ram_guard_suggested", "unloaded", "unload_none", "unload_kept", "unload_failed"):
        text = CATALOG["components"]["error"][key]
        assert f"{NBSP}:" in text and " :" not in text.replace(f"{NBSP}:", ""), key
    assert f"{NBSP}:" in CATALOG["chat"]["model_changed"]
    assert f"{NBSP}:" in CATALOG["arena"]["model_changed"]


def test_the_new_styles_use_design_tokens_only():
    css = source("components.css")
    block = css[css.index("/* Garde-fou mémoire") : css.index(".wl-error-details summary")]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", block)
