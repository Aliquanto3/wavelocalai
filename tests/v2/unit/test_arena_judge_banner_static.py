"""Revue de la story 9.3 : bandeau du juge (constante partagée avec le serveur, horloge hors de la
région live, minuteur arrêté) et phases du juge (`_PhasedModel`, ordre réel, annulation)."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from wavelocalai.evaluation.judge import _PhasedModel
from wavelocalai.inference.judge_port import NOT_EVALUATED_UNAVAILABLE
from wavelocalai.models.fake import FakeChatModel, Sleep
from wavelocalai.models.port import ChatMessage, ChatRequest, LoadState, ModelRef, TextDelta

STATIC = Path(__file__).parents[3] / "src" / "wavelocalai" / "web" / "static"
BANNER = (STATIC / "screens" / "arena-judge-banner.js").read_text(encoding="utf-8")
ARENA = (STATIC / "screens" / "arena.js").read_text(encoding="utf-8")
REQUEST = ChatRequest([ChatMessage("user", "Note.")])


def test_the_unavailable_reason_is_the_server_constant_not_a_substring():
    match = re.search(r'export const JUDGE_UNAVAILABLE = "([^"]+)";', BANNER)
    assert match and match.group(1) == NOT_EVALUATED_UNAVAILABLE
    assert "includes(" not in BANNER and 'juge indisponible")' not in ARENA


def test_the_clock_is_outside_the_live_region_and_the_timer_is_stopped_on_every_exit():
    assert 'clockEl.setAttribute("aria-hidden", "true")' in BANNER
    assert 'textEl.setAttribute("aria-live", "polite")' in BANNER
    assert 'el.setAttribute("aria-live"' not in BANNER  # la région n'englobe pas l'horloge
    assert "progress.end()" in ARENA  # fin du run, flux perdu compris (`finish`)
    assert ARENA.count("progress.reset()") == 2  # nouvelle comparaison et démontage


def model(script, origin="local") -> FakeChatModel:
    return FakeChatModel(script, ModelRef("fake:j", "fake", origin, "chat"))


async def phases_of(script, origin="local") -> list[str]:
    said: list[str] = []
    async for _ in _PhasedModel(model(script, origin), said.append).stream(REQUEST):
        pass
    return said


@pytest.mark.parametrize(
    ("script", "origin", "expected"),
    [
        (
            [LoadState("loading"), LoadState("loaded", 0.1), TextDelta("{}")],
            "local",
            ["loading", "scoring"],
        ),
        ([TextDelta("{}")], "local", ["scoring"]),
        ([Sleep(0.5), TextDelta("{}")], "local", ["scoring"]),
        ([TextDelta("{}")], "cloud", ["scoring"]),
        ([], "local", ["scoring"]),
    ],
)
async def test_phases_follow_the_real_order_and_never_repeat(script, origin, expected):
    assert await phases_of(script, origin) == expected


async def test_a_judge_that_fails_before_answering_says_no_phase():
    from wavelocalai.errors import ProviderError

    with pytest.raises(ProviderError):
        await phases_of([ProviderError("ollama_down", "éteint")])


async def test_cancelling_during_the_grace_wait_closes_the_upstream_cleanly():
    said: list[str] = []
    stream = _PhasedModel(model([Sleep(30), TextDelta("{}")]), said.append).stream(REQUEST)

    async def consume():
        async for _ in stream:
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.4)  # délai de grâce passé : `scoring` dit, premier fragment attendu
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert said == ["scoring"]
    assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
