"""L'Arène arrête une lane qui tourne en boucle, qui atteint `arena.max_tokens`, ou à la demande
(story 9.2) : `stopped_reason` dans `lane_status`, réponse partielle gardée et notée, `POST
/api/runs/{lane_run_id}/stop` distinct de l'annulation du run entier."""

from __future__ import annotations

import asyncio

import pytest

from wavelocalai.models.fake import Sleep
from wavelocalai.models.port import ChatResult, Done, TextDelta

from .test_arena_api import _ended, _events, _until, arena_app, children, local, say, statuses


def _lane_run_id(events, lane: str) -> str:
    for e in events:
        if e["type"] == "lane_status" and e["data"]["lane"] == lane:
            return e["data"]["run_id"]
    raise AssertionError(f"lane_status {lane} absent")


async def test_a_lane_that_hits_max_tokens_finishes_done_with_a_stopped_reason_and_is_scored(
    tmp_path,
):
    a = local(
        "fake:a",
        [*say("Un ", "mot "), Done(ChatResult(finish_reason="length", output_tokens=2, tps=10.0))],
    )
    b = local("fake:b", say("B"))
    async with arena_app(tmp_path, a, b, arena={"max_tokens": 32}) as (app, client):
        response = await client.post(
            "/api/arena/runs",
            json={
                "models": ["fake:a", "fake:b"],
                "prompt": "Explique.",
                "allow_cloud": True,
                "judge": "fake:b",
            },
        )
        run_id = response.json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)
    # La requête de chaque lane porte le plafond réglé (`[arena] max_tokens`).
    assert a.requests[0].max_tokens == 32 and b.requests[0].max_tokens == 32
    assert statuses(events, "fake:a")[-1] == "done"
    done = next(
        e
        for e in events
        if e["type"] == "lane_status"
        and e["data"]["lane"] == "fake:a"
        and e["data"]["status"] == "done"
    )
    assert done["data"]["stopped_reason"] == "max_tokens"
    # La réponse partielle est gardée, et notée comme une lane finie normalement (jamais sautée).
    text = "".join(
        e["data"]["text"] for e in events if e["type"] == "token" and e["data"]["lane"] == "fake:a"
    )
    assert text == "Un mot "
    assert any(e["type"] == "judge_score" and e["data"]["lane"] == "fake:a" for e in events)
    assert children(snapshot)["fake:b"]["status"] == "ok"  # l'autre lane continue normalement
    b_done = next(
        e
        for e in events
        if e["type"] == "lane_status"
        and e["data"]["lane"] == "fake:b"
        and e["data"]["status"] == "done"
    )
    assert "stopped_reason" not in b_done["data"]  # fin naturelle : pas de raison d'arrêt


async def test_a_repeating_lane_is_stopped_with_loop_and_scored_while_the_other_lane_continues(
    tmp_path, _stub_codecarbon
):
    fragment = "Je boucle encore un peu. "  # 26 caractères
    script = [TextDelta(fragment) for _ in range(10)]  # jamais tous livrés si la boucle est vue
    a = local("fake:a", script)
    b = local("fake:b", say("B"))
    async with arena_app(
        tmp_path, a, b, arena={"loop_min_repeats": 4, "loop_window_chars": 80}
    ) as (app, client):
        response = await client.post(
            "/api/arena/runs",
            json={
                "models": ["fake:a", "fake:b"],
                "prompt": "Explique.",
                "allow_cloud": True,
                "judge": "fake:b",
            },
        )
        run_id = response.json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)
        assert a.closed == a.opened == 1  # flux fermé avant la fin du script

    done = next(
        e
        for e in events
        if e["type"] == "lane_status"
        and e["data"]["lane"] == "fake:a"
        and e["data"]["status"] == "done"
    )
    assert done["data"]["stopped_reason"] == "loop"
    text = "".join(
        e["data"]["text"] for e in events if e["type"] == "token" and e["data"]["lane"] == "fake:a"
    )
    assert len(text) < len(fragment) * len(script)  # arrêtée avant d'avoir tout dit
    assert statuses(events, "fake:a")[-1] == "done"
    assert children(snapshot)["fake:b"]["status"] == "ok"
    assert any(
        e["type"] == "judge_score" and e["data"]["lane"] == "fake:a" for e in events
    )  # notée


async def test_the_false_positive_prose_does_not_stop_the_lane(tmp_path):
    prose = say(
        "La photosynthèse ",
        "transforme la lumière ",
        "du soleil en énergie chimique ",
        "grâce à la chlorophylle des feuilles.",
    )
    a = local("fake:a", prose)
    b = local("fake:b", say("B"))
    async with arena_app(
        tmp_path, a, b, arena={"loop_min_repeats": 4, "loop_window_chars": 80}
    ) as (app, client):
        response = await client.post(
            "/api/arena/runs",
            json={
                "models": ["fake:a", "fake:b"],
                "prompt": "Explique.",
                "allow_cloud": True,
                "judge": "fake:b",
            },
        )
        run_id = response.json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    done = next(
        e
        for e in events
        if e["type"] == "lane_status"
        and e["data"]["lane"] == "fake:a"
        and e["data"]["status"] == "done"
    )
    assert "stopped_reason" not in done["data"]


async def test_stopping_a_lane_keeps_the_other_running_and_notes_the_partial(
    tmp_path, _stub_codecarbon
):
    a = local("fake:a", [TextDelta("partiel "), Sleep(1.0), TextDelta("jamais")])
    b = local("fake:b", [Sleep(0.05), *say("B")])  # attend la place de A : vérifie la lane seule
    async with arena_app(tmp_path, a, b) as (app, client):
        run_id = (
            await client.post(
                "/api/arena/runs",
                json={
                    "models": ["fake:a", "fake:b"],
                    "prompt": "Explique.",
                    "allow_cloud": True,
                    "judge": "fake:b",
                },
            )
        ).json()["run_id"]
        events = await _until(
            app,
            run_id,
            lambda ev: any(e["type"] == "token" and e["data"]["lane"] == "fake:a" for e in ev),
        )
        lane_run_id = _lane_run_id(events, "fake:a")
        result = await client.post(f"/api/runs/{lane_run_id}/stop")
        body = result.json()
        # `status` : « running » d'ordinaire, ou déjà « ok » si la lane a fini pendant la requête.
        assert body["run_id"] == lane_run_id and body["stopped"] is True
        assert body["status"] in ("running", "ok")
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)
        async with asyncio.timeout(2):
            while a.closed < 1:
                await asyncio.sleep(0.01)

    assert snapshot["status"] == "ok"  # l'orchestration aboutit : l'arrêt n'est pas une erreur
    kids = children(snapshot)
    assert kids["fake:a"]["status"] == "ok" and kids["fake:b"]["status"] == "ok"
    done_a = next(
        e
        for e in events
        if e["type"] == "lane_status"
        and e["data"]["lane"] == "fake:a"
        and e["data"]["status"] == "done"
    )
    assert done_a["data"]["stopped_reason"] == "user"
    text_a = "".join(
        e["data"]["text"] for e in events if e["type"] == "token" and e["data"]["lane"] == "fake:a"
    )
    assert text_a == "partiel "  # la réponse partielle est gardée
    assert "jamais" not in text_a
    # L'autre lane continue et finit normalement, sans raison d'arrêt.
    done_b = next(
        e
        for e in events
        if e["type"] == "lane_status"
        and e["data"]["lane"] == "fake:b"
        and e["data"]["status"] == "done"
    )
    assert "stopped_reason" not in done_b["data"]
    # La note et le CO2 restent mesurés pour la lane arrêtée (AD-10) : pas d'erreur, pas de 0 muet.
    assert any(e["type"] == "judge_score" and e["data"]["lane"] == "fake:a" for e in events)
    co2_a = kids["fake:a"]["metrics"]["co2"]
    assert co2_a["method"] == "codecarbon" and co2_a["mg"] == pytest.approx(1.8)


async def test_stopping_an_already_finished_lane_rejects_cleanly(tmp_path):
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    async with arena_app(tmp_path, a, b) as (app, client):
        run_id = (
            await client.post(
                "/api/arena/runs",
                json={
                    "models": ["fake:a", "fake:b"],
                    "prompt": "Explique.",
                    "allow_cloud": True,
                    "judge": "fake:b",
                },
            )
        ).json()["run_id"]
        events = await _events(client, run_id)
        await _ended(client, run_id)
        events = await _events(client, run_id)
        lane_run_id = _lane_run_id(events, "fake:a")
        result = await client.post(f"/api/runs/{lane_run_id}/stop")
        assert result.json()["stopped"] is False


async def test_stopping_an_unknown_run_id_is_run_not_found(tmp_path):
    async with arena_app(tmp_path) as (app, client):
        result = await client.post("/api/runs/does-not-exist/stop")
        assert result.status_code == 404 and result.json()["code"] == "run_not_found"
