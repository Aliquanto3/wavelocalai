"""Arène : chronomètre, « un seul juge » et adresse du run (story 8.1, lot b ; écarts nos 4, 5 et 7
de `decisions-2026-10-19.md`), dans un vrai navigateur, sur le vrai serveur et des lanes `fake`.
"""

from __future__ import annotations

import re

from .test_arena import (  # noqa: F401  (`cancel_leftover_runs` est une fixture automatique)
    DONE,
    STARTED,
    arena,
    banner,
    cancel_leftover_runs,
    lane,
    launch,
    scripted,
    wait_banner,
)
from .test_arena_reopen import JUDGE, post_run, reopen
from .test_arena_results import ok_lane
from .test_shell import wait_for

CLOCK = re.compile(r"· \d+:\d\d$")  # « 0:42 », jamais « 42 s » ni « 0,7 s »


def test_the_address_becomes_the_run_id_at_the_end_without_a_new_history_entry(arena, server):
    scripted(arena, server, {}, judge=JUDGE)
    assert arena.evaluate("location.hash") == "#/arene/comparer"
    before = arena.evaluate("history.length")
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    run_id = STARTED[-1][1]
    wait_for(arena, f"() => location.hash === '#/arene/comparer/{run_id}'")
    assert arena.evaluate("history.length") == before  # `replaceState` : pas d'entrée de plus
    assert lane(arena, "fake:a").locator(".wl-md").inner_text().strip() == "ok"  # écran intact


def test_the_address_is_not_rewritten_while_the_run_goes_on(arena, server):
    scripted(arena, server, {"fake:a": [{"text": "Début"}, {"sleep_s": 30}]}, judge=JUDGE)
    launch(arena)
    wait_banner(arena, "Comparaison en cours")
    assert arena.evaluate("location.hash") == "#/arene/comparer"
    arena.get_by_role("button", name="Arrêter").click()
    wait_banner(arena, "Comparaison arrêtée")
    wait_for(arena, f"() => location.hash === '#/arene/comparer/{STARTED[-1][1]}'")


def test_the_clock_reads_minutes_and_seconds_while_running_and_at_the_end(arena, server):
    scripted(arena, server, {"fake:a": [{"text": "Début"}, {"sleep_s": 2}, {"done": DONE}]})
    launch(arena)
    wait_banner(arena, "Comparaison en cours")
    assert CLOCK.search(banner(arena).inner_text()), banner(arena).inner_text()
    wait_banner(arena, "Comparaison terminée")
    assert CLOCK.search(banner(arena).inner_text()), banner(arena).inner_text()


def test_one_judge_is_said_with_every_score_live_and_when_reopened(arena, server):
    scripted(arena, server, {}, judge=JUDGE)
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    for tag in ("fake:a", "fake:b"):
        badge = lane(arena, tag).locator(".wl-lane-score wl-badge[kind=single-judge]")
        assert badge.inner_text().strip() == "un seul juge"
    run_id = post_run(arena, server, [ok_lane("fake:a", "Alpha"), ok_lane("fake:b", "Bravo")])
    reopen(arena, server, run_id)
    for tag in ("fake:a", "fake:b"):
        score = lane(arena, tag).locator(".wl-lane-score")
        assert score.locator(".wl-score-line").inner_text() == "70/100"
        assert score.locator("wl-badge[kind=single-judge]").inner_text().strip() == "un seul juge"
