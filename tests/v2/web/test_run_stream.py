"""Flux SSE d'un run (AD-6) : trame, reprise sans doublon ni trou, `204`, maintien, erreurs.

Le hub est alimenté par les producteurs de `tests/v2/producers.py` ou par la route de test (modèle
`fake`) : aucun adaptateur réel. Le client est un client httpx ASGI, qui lit le flux jusqu'à sa fin.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from wavelocalai.runs.models import LeafResult

from ..producers import LOCAL_CO2, produce_arena, produce_chat
from .conftest import parse_sse

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def _stream(client, run_id, **kwargs):
    response = await client.get(f"/api/runs/{run_id}/events", **kwargs)
    return response, *parse_sse(response.text)


async def _scripted(client, script, **body):
    response = await client.post("/api/test/runs", json={"script": script, **body})
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


async def _ended(client, run_id, timeout=3.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


async def test_frame_is_id_then_data_without_event_field_and_utc_timestamps(served):
    app, client = served
    run_id = await _scripted(client, [{"text": "Sa"}, {"sleep_s": 0.08}, {"text": "lut"}])
    response, frames, _ = await _stream(client, run_id)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert all(f["fields"] == ["data", "id"] for f in frames)  # jamais de champ `event:`
    assert "event:" not in response.text
    envelopes = [f["data"] for f in frames]
    assert [f["id"] for f in frames] == [str(e["seq"]) for e in envelopes]
    assert [e["seq"] for e in envelopes] == list(range(1, len(envelopes) + 1))  # contigu dès 1
    assert envelopes[0]["type"] == "run_started" and envelopes[-1]["type"] == "run_ended"
    assert [e["type"] for e in envelopes].count("run_ended") == 1
    for envelope in envelopes:
        assert set(envelope) == {"seq", "run_id", "type", "ts", "data"}
        assert envelope["run_id"] == run_id and ISO_UTC.match(envelope["ts"])
    tokens = [e["data"] for e in envelopes if e["type"] == "token"]
    assert all(t["lane"] == "fake:1b" and t["channel"] == "answer" for t in tokens)
    assert "".join(t["text"] for t in tokens) == "Salut"
    assert envelopes[-1]["data"] == {"status": "ok", "error": None}


async def test_live_stream_follows_a_running_run_until_run_ended(served):
    app, client = served
    hub = app.state.hub
    handle = await hub.create_run("chat", models=["fake:1b"], user_message="Q")
    reader = asyncio.create_task(_stream(client, handle.run_id))
    await asyncio.sleep(0.05)  # le flux est ouvert sur un run actif
    for text in ("a", "b", "c"):
        hub.publish(handle.run_id, "token", {"lane": "fake:1b", "text": text, "channel": "answer"})
        await asyncio.sleep(0.02)
    assert not reader.done()
    await hub.finish_leaf(handle.run_id, LeafResult(origin="local"), LOCAL_CO2)
    _, frames, _ = await asyncio.wait_for(reader, 2)
    assert [f["data"]["type"] for f in frames] == [
        "run_started", "token", "token", "token", "run_ended",
    ]  # fmt: skip
    assert [f["data"]["seq"] for f in frames] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("how", ["header", "query"])
async def test_resume_on_an_active_run_has_no_gap_and_no_duplicate(served, how):
    app, client = served
    hub = app.state.hub
    handle = await hub.create_run("chat", models=["fake:1b"])
    for index in range(7):  # seq 1 (run_started) à 8
        hub.publish(handle.run_id, "token", {"lane": "m", "text": str(index), "channel": "answer"})
    kwargs = {"headers": {"Last-Event-ID": "7"}} if how == "header" else {"params": {"after": 7}}
    reader = asyncio.create_task(_stream(client, handle.run_id, **kwargs))
    await asyncio.sleep(0.05)
    hub.publish(handle.run_id, "token", {"lane": "m", "text": "tard", "channel": "answer"})
    await hub.finish_leaf(handle.run_id, LeafResult(origin="local"), LOCAL_CO2)
    _, frames, _ = await asyncio.wait_for(reader, 2)
    assert [f["data"]["seq"] for f in frames] == [8, 9, 10]
    assert frames[0]["data"]["data"]["text"] == "6" and frames[-1]["data"]["type"] == "run_ended"


async def test_resume_straddling_a_persisted_batch_matches_memory_and_database(served):
    app, client = served
    hub = app.state.hub
    handle = await hub.create_run("chat", models=["fake:1b"], user_message="Q")
    live = asyncio.create_task(_stream(client, handle.run_id))
    for index in range(5):
        hub.publish(handle.run_id, "token", {"lane": "m", "text": f"a{index}", "channel": "answer"})
    await hub.flush()  # seq 1 à 6 en base
    for index in range(5):
        hub.publish(handle.run_id, "token", {"lane": "m", "text": f"b{index}", "channel": "answer"})
        await asyncio.sleep(0.01)
    # Reprise au milieu du lot persisté, run encore actif : lue en mémoire.
    resumed = asyncio.create_task(_stream(client, handle.run_id, params={"after": 3}))
    await asyncio.sleep(0.05)  # le flux repris est ouvert sur le run actif (mémoire)
    await hub.finish_leaf(handle.run_id, LeafResult(origin="local"), LOCAL_CO2)
    _, from_memory, _ = await asyncio.wait_for(resumed, 2)
    _, everything, _ = await asyncio.wait_for(live, 2)
    seqs = [f["data"]["seq"] for f in everything]
    assert seqs == list(range(1, 13))  # le flux continu n'a ni trou ni doublon
    # Même reprise une fois le run en base : identique à ce que la mémoire a rendu.
    for cursor in (3, 6, 9):  # avant, à la limite et après le lot persisté
        _, from_db, _ = await _stream(client, handle.run_id, params={"after": cursor})
        assert [f["data"] for f in from_db] == [f["data"] for f in everything[cursor:]]
    assert [f["data"]["seq"] for f in from_memory] == list(range(4, 13))


async def test_a_cursor_on_the_last_seq_of_a_finished_run_answers_204(served):
    app, client = served
    handle = await produce_chat(app.state.hub)
    _, frames, _ = await _stream(client, handle.run_id)
    last = frames[-1]["data"]["seq"]
    for kwargs in (
        {"params": {"after": last}},
        {"params": {"after": last + 5}},
        {"headers": {"Last-Event-ID": str(last)}},
    ):
        response = await client.get(f"/api/runs/{handle.run_id}/events", **kwargs)
        assert response.status_code == 204 and response.content == b""
    one_left = await client.get(f"/api/runs/{handle.run_id}/events", params={"after": last - 1})
    assert one_left.status_code == 200 and parse_sse(one_left.text)[0][0]["data"]["type"] == (
        "run_ended"
    )


async def test_query_cursor_wins_over_the_header(served):
    app, client = served
    handle = await produce_chat(app.state.hub)
    response = await client.get(
        f"/api/runs/{handle.run_id}/events",
        params={"after": 1},
        headers={"Last-Event-ID": "999"},
    )
    assert response.status_code == 200 and parse_sse(response.text)[0][0]["data"]["seq"] == 2


async def test_unknown_run_child_run_and_bad_cursor_use_the_error_envelope(served):
    app, client = served
    missing = await client.get("/api/runs/inconnu/events")
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"
    _, leaves = await produce_arena(app.state.hub)
    child = await client.get(f"/api/runs/{leaves[0].run_id}/events")
    assert child.status_code == 404  # le parent publie seul (AD-5)
    for kwargs in ({"headers": {"Last-Event-ID": "abc"}}, {"params": {"after": -1}}):
        bad = await client.get(f"/api/runs/{leaves[0].run_id}/events", **kwargs)
        assert bad.status_code == 422 and bad.json()["code"] == "invalid_request"


async def test_a_keepalive_comment_is_sent_while_the_run_is_quiet(served, monkeypatch):
    app, client = served
    monkeypatch.setattr("fastapi.routing._PING_INTERVAL", 0.05)  # 15 s en production
    run_id = await _scripted(client, [{"text": "a"}, {"sleep_s": 0.4}, {"text": "b"}])
    _, frames, comments = await _stream(client, run_id)
    assert "ping" in comments
    assert frames[-1]["data"]["type"] == "run_ended"
    from fastapi.sse import _PING_INTERVAL

    assert _PING_INTERVAL == 15.0  # le réglage natif de FastAPI


async def test_tokens_are_grouped_by_lane_in_the_stream(served):
    app, client = served
    script = [{"text": f"{i} "} for i in range(20)]  # 20 morceaux d'un coup
    run_id = await _scripted(client, script)
    _, frames, _ = await _stream(client, run_id)
    tokens = [f["data"]["data"]["text"] for f in frames if f["data"]["type"] == "token"]
    assert 1 <= len(tokens) < 20
    assert "".join(tokens) == "".join(f"{i} " for i in range(20))
