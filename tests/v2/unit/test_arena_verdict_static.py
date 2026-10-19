"""Verdict local/cloud de l'Arène (story 3.5) : règles de structure et textes, sans navigateur.
Les parcours (instantané lu à `run_ended` et à la réouverture, axe-core) vivent dans
`tests/v2/e2e/test_arena_verdict.py`."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .static_files import catalog, read_static

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "src" / "wavelocalai" / "web" / "static"
CATALOG = catalog()
NBSP = "\N{NO-BREAK SPACE}"


def source(name: str) -> str:
    return read_static(name)


def code_of(name: str) -> str:
    return "\n".join(
        line for line in source(name).splitlines() if not line.lstrip().startswith("//")
    )


def lookup(key: str):
    value = CATALOG
    for part in key.split("."):
        value = value[part]
    return value


def test_every_verdict_text_the_script_names_exists_in_the_catalog():
    used = set(re.findall(r"""\bt\(\s*["']([\w.]+)["']""", source("screens/arena-verdict.js")))
    assert {"arena.verdict.title", "arena.verdict.cost", "arena.verdict.data_judge_cloud"} <= used
    for key in used:
        assert isinstance(lookup(key), str), key
    # Les familles dynamiques : une phrase par meneur, un pluriel pour les points et les données.
    for leader in ("local", "cloud", "tie"):
        assert lookup(f"arena.verdict.score_{leader}")
    for key in ("points", "data"):
        assert lookup(f"arena.verdict.{key}_one") and lookup(f"arena.verdict.{key}_many")


def test_the_verdict_texts_follow_the_french_typography():
    for text in CATALOG["arena"]["verdict"].values():
        assert not re.search(r" [:;!?»]|« ", text), text  # espace insécable, jamais l'ordinaire
    assert CATALOG["arena"]["verdict"]["cost_unknown"] == "inconnu"
    assert CATALOG["format"]["money_below"] == "moins de {value}"


def test_the_screen_reads_the_snapshot_and_computes_nothing():
    code = code_of("screens/arena-verdict.js")
    assert (
        "snapshot?.verdict" in code and "api." not in code
    )  # elle affiche, la lecture est ailleurs
    assert "api.run(runId)" in code_of("screens/arena-snapshot.js")
    # Aucun calcul de mesure dans le navigateur (AD-20) : pas d'opération sur les montants, les
    # notes ou les prix ; seuls la mise en forme et le choix de la phrase par `leader`.
    assert not re.search(r"\b(price|per_mtok|input_tokens|output_tokens)\b", code)
    assert not re.search(r"(amount|score|mg)\s*[-*/+]\s*\w", code)
    assert '"—"' not in code and '"-"' not in code and "|| 0" not in code
    assert "run: (runId)" in source("core/api.js")


def test_the_results_read_the_verdict_only_after_a_comparison_that_ended_normally():
    results = source("screens/arena-results.js")
    assert 'if (state === "ok")' in results and "verdict.show(snapshot)" in results
    assert "readSettled(runId" in results and "verdict.reset()" in results
    assert "results.end(state, runId)" in source("screens/arena.js")


def test_no_new_event_type_for_the_verdict():
    for name in ("screens/arena.js", "screens/arena-verdict.js", "core/sse.js"):
        assert "verdict:" not in code_of(name).replace("snapshot?.verdict", ""), name


def test_the_verdict_is_styled_from_tokens_only():
    css = source("arena-results.css")
    block = css[css.index("/* Verdict local/cloud") :]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", block)
    assert "var(--color-surface-alt)" in block and "var(--color-line)" in block


def test_a_money_amount_is_formatted_in_the_price_table_currency_never_as_a_bare_zero():
    fmt = source("core/format.js")
    assert "export function formatMoney(amount, currency)" in fmt
    assert 'style: "currency"' in fmt and "money_below" in fmt
