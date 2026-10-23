"""Routes des runs : annulation (parent puis enfants), instantané, `409 run_busy`, run en erreur,
commande de test réservée à `WAVELOCALAI_TESTING` (AD-5, AD-14, AD-18)."""

from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient

from wavelocalai.runs.models import STATUSES
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..producers import LOCAL_CO2, produce_arena, produce_chat
from .conftest import parse_sse

SLOW = [{"text": "par"}, {"sleep_s": 30}, {"text": "jamais"}]


async def _post(client, script, **body):
    return await client.post("/api/test/runs", json={"script": script, **body})


async def _wait_status(client, run_id, wanted, timeout=3.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] in wanted:
                return snapshot
            await asyncio.sleep(0.02)


async def test_cancel_ends_the_run_within_a_second_and_keeps_the_partial(served):
    app, client = served
    started = await _post(client, SLOW, message="Q")
    body = started.json()
    run_id = body["run_id"]
    assert body["conversation_id"]
    await asyncio.sleep(0.15)  # « par » est reçu, le modèle attend

    t0 = time.perf_counter()
    response = await client.post(f"/api/runs/{run_id}/cancel")
    stream = await client.get(f"/api/runs/{run_id}/events")
    assert time.perf_counter() - t0 < 1.0
    assert response.status_code == 200
    assert response.json() == {"run_id": run_id, "cancelled": True, "status": "cancelled"}

    envelopes = [f["data"] for f in parse_sse(stream.text)[0]]
    assert envelopes[-1]["type"] == "run_ended" and envelopes[-1]["data"]["status"] == "cancelled"
    assert "".join(e["data"]["text"] for e in envelopes if e["type"] == "token") == "par"
    row = app.state.store.read("SELECT content FROM messages WHERE role = 'assistant'")
    assert row[0]["content"] == "par"  # le partiel est conservé
    again = await client.post(f"/api/runs/{run_id}/cancel")  # idempotent
    assert again.json() == {"run_id": run_id, "cancelled": False, "status": "cancelled"}


async def test_cancelling_a_parent_cancels_its_children(served):
    app, client = served
    parent, leaves = await produce_arena(app.state.hub)
    response = await client.post(f"/api/runs/{parent.run_id}/cancel")
    assert response.json()["status"] == "cancelled"
    snapshot = (await client.get(f"/api/runs/{parent.run_id}")).json()
    assert snapshot["status"] == "cancelled" and snapshot["kind"] == "arena"
    assert [c["status"] for c in snapshot["children"]] == ["cancelled", "cancelled"]
    assert {c["run_id"] for c in snapshot["children"]} == {h.run_id for h in leaves}
    assert all(c["kind"] == "generation" and c["parent_run_id"] == parent.run_id
               for c in snapshot["children"])  # fmt: skip
    stream = await client.get(f"/api/runs/{parent.run_id}/events")
    last = parse_sse(stream.text)[0][-1]["data"]
    assert last["type"] == "run_ended" and last["data"]["status"] == "cancelled"


async def test_cancelling_an_unknown_run_is_404(served):
    _, client = served
    response = await client.post("/api/runs/inconnu/cancel")
    assert response.status_code == 404 and response.json()["code"] == "run_not_found"


async def test_snapshot_of_a_finished_run_gives_status_metrics_and_no_error(served):
    app, client = served
    handle = await produce_chat(app.state.hub)
    snapshot = (await client.get(f"/api/runs/{handle.run_id}")).json()
    assert snapshot["status"] == "ok" and snapshot["error"] is None
    assert snapshot["kind"] == "chat" and snapshot["conversation_id"] == handle.conversation_id
    assert snapshot["metrics"]["tps"] == 42.0 and snapshot["metrics"]["tps_source"] == "ollama_eval"
    assert snapshot["metrics"]["co2"] == LOCAL_CO2.as_dict()
    assert snapshot["children"] == [] and snapshot["ended_at"]
    missing = await client.get("/api/runs/inconnu")
    assert missing.status_code == 404 and missing.json()["code"] == "run_not_found"


async def test_snapshot_of_a_composite_carries_metrics_on_leaves_only(served):
    app, client = served
    parent, _ = await produce_arena(app.state.hub)
    snapshot = (await client.get(f"/api/runs/{parent.run_id}")).json()
    assert snapshot["status"] == "running" and snapshot["metrics"] is None
    assert len(snapshot["children"]) == 2


async def test_a_provider_error_ends_the_run_with_the_ad18_envelope(served):
    app, client = served
    started = await _post(client, [{"text": "début"}, {"fail": "ollama_down", "technical": "x"}])
    run_id = started.json()["run_id"]
    snapshot = await _wait_status(client, run_id, {"error"})
    assert snapshot["status"] == "error" and snapshot["status"] in STATUSES
    error = snapshot["error"]
    assert list(error) == ["code", "message", "action", "detail"]
    assert error["code"] == "ollama_down" and error["code"] not in STATUSES
    stream = await client.get(f"/api/runs/{run_id}/events")
    ended = parse_sse(stream.text)[0][-1]["data"]
    assert ended["type"] == "run_ended" and ended["data"] == {"status": "error", "error": error}


async def test_a_second_run_of_the_same_kind_is_409_with_the_active_run_id(served):
    app, client = served
    first = (await _post(client, SLOW)).json()["run_id"]
    second = await _post(client, SLOW)
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "run_busy" and body["detail"]["run_id"] == first
    assert list(body) == ["code", "message", "action", "detail"]
    other_kind = await _post(client, SLOW, kind="rag")
    assert other_kind.status_code == 200  # un autre genre n'est pas bloqué
    await client.post(f"/api/runs/{first}/cancel")
    await client.post(f"/api/runs/{other_kind.json()['run_id']}/cancel")
    assert (await _post(client, [{"text": "ok"}])).status_code == 200  # libéré par l'annulation


async def test_two_simultaneous_requests_give_one_run_and_one_409(served):
    _, client = served
    responses = await asyncio.gather(_post(client, SLOW), _post(client, SLOW))
    assert sorted(r.status_code for r in responses) == [200, 409]


async def test_the_test_command_validates_its_input(served):
    _, client = served
    for script in ([{"inconnu": 1}], [{"fail": "code_inexistant"}], [{"sleep_s": "x"}]):
        response = await _post(client, script)
        assert response.status_code == 422 and response.json()["code"] == "invalid_request"
    assert (await _post(client, [], kind="pull", message="Q")).status_code == 422
    assert (await _post(client, [], model="autre:1b")).status_code == 404


def test_without_testing_the_command_and_the_fake_do_not_exist(tmp_path):
    app = create_app(make_settings(tmp_path))
    assert app.state.models == {}
    with TestClient(app, base_url=f"http://127.0.0.1:{TEST_PORT}") as client:
        response = client.post("/api/test/runs", json={"script": []})
        assert response.status_code == 404 and response.json()["code"] == "not_found"
        assert (
            client.get("/api/runs/inconnu").status_code == 404
        )  # les routes de runs, elles, existent
