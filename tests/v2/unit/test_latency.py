"""Règle de mesure de latence (story 8.5) : un appel lent isolé ne fait pas échouer le budget, une
route lente à chaque appel le fait toujours. Mesures simulées, aucune horloge réelle."""

from __future__ import annotations

import asyncio

import pytest

from ..latency import assert_under_budget, assert_under_budget_async, second_best_of_five_many


def scripted(durations):
    it = iter(durations)
    return lambda: next(it)


def test_an_isolated_slow_call_stays_under_the_budget():
    # échauffement lent, puis un seul appel à 400 ms parmi cinq
    assert_under_budget(scripted([0.9, 0.05, 0.4, 0.05, 0.05, 0.05]), 0.3)


def test_a_route_slow_at_every_call_fails_with_every_measurement():
    with pytest.raises(AssertionError, match=r"400, 400, 400, 400, 400 ms \(budget 300 ms\)"):
        assert_under_budget(scripted([0.4] * 6), 0.3, "route")


def test_four_slow_calls_out_of_five_fail():
    with pytest.raises(AssertionError):
        assert_under_budget(scripted([0.05, 0.4, 0.4, 0.05, 0.4, 0.4]), 0.3)


def test_the_async_helper_follows_the_same_rule():
    durations = iter([0.9, 0.05, 0.4, 0.05, 0.05, 0.05])

    async def measure():
        return next(durations)

    asyncio.run(assert_under_budget_async(measure, 0.3))


def test_named_timings_take_the_second_best_of_each_name():
    runs = iter(
        [{"fcp": 9, "ready": 9}]
        + [{"fcp": f, "ready": r} for f, r in [(5, 1), (1, 5), (2, 2), (3, 3), (4, 4)]]
    )
    best, _ = second_best_of_five_many(lambda: next(runs))
    assert best == {"fcp": 2, "ready": 2}
