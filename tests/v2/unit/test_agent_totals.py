"""Totaux d'une tâche d'agent (story 6.4) : le serveur additionne, l'écran met en forme (AD-20)."""

from __future__ import annotations

import pytest

from wavelocalai.runs.agent_totals import PARTIAL_REASON, agent_totals, duration_s, total_co2


def leaf(mg, *, estimated=False, low=None, high=None):
    co2 = (
        None
        if mg is False
        else {
            "mg": mg,
            "method": "ecologits" if estimated else "codecarbon",
            "estimated": estimated,
            "range_mg": None if low is None else {"low": low, "high": high},
            "allocation": "direct",
            "reason": None if mg is not None else "pas de compteur",
        }
    )
    return {"kind": "generation", "metrics": {"co2": co2}}


def test_measured_calls_are_added_up():
    total = total_co2([leaf(1.5), leaf(2.0), leaf(0.5)])
    assert total["mg"] == pytest.approx(4.0)
    assert (total["method"], total["estimated"], total["reason"]) == ("codecarbon", False, None)
    assert total["range_mg"] is None


def test_estimated_calls_stay_estimated_and_their_ranges_are_added():
    total = total_co2(
        [leaf(1.0, estimated=True, low=0.5, high=2.0), leaf(2.0, estimated=True, low=1.0, high=3.0)]
    )
    assert total["mg"] == pytest.approx(3.0)
    assert total["method"] == "ecologits" and total["estimated"] is True
    assert total["range_mg"] == {"low": 1.5, "high": 5.0}


@pytest.mark.parametrize("missing", [None, False])
def test_one_unmeasurable_call_makes_the_total_unmeasurable_never_a_partial_sum(missing):
    total = total_co2([leaf(1.5), leaf(missing)])
    assert total["mg"] is None and total["method"] == "unmeasurable"
    assert total["reason"] == PARTIAL_REASON


def test_no_call_has_no_total():
    assert total_co2([]) is None


def test_the_duration_is_the_span_of_the_run_and_unknown_while_it_runs():
    assert duration_s("2026-10-19T10:00:00Z", "2026-10-19T10:00:12.500Z") == pytest.approx(12.5)
    assert duration_s("2026-10-19T10:00:00Z", None) is None
    assert duration_s("n'importe quoi", "2026-10-19T10:00:00Z") is None


def test_the_totals_count_model_calls_and_the_given_steps():
    snapshot = {
        "children": [leaf(1.0), leaf(2.0)],
        "started_at": "2026-10-19T10:00:00Z",
        "ended_at": "2026-10-19T10:00:03Z",
    }
    totals = agent_totals(snapshot, 5)
    assert (totals["turns"], totals["steps"], totals["duration_s"]) == (2, 5, 3.0)
    assert totals["co2"]["mg"] == pytest.approx(3.0)
