"""API de l'historique carbone et de la remise à zéro (story 5.2) : `GET /api/carbon/history`,
`POST /api/carbon/session/reset`, budget de lecture sur 1 000 runs, garde d'origine."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, closed_port, make_settings
from ..producers import produce_chat
from .conftest import BASE
from .test_system import Stream

BUDGET_S = 0.3


async def seed(client, *sessions) -> None:
    response = await client.post("/api/test/carbon-sessions", json={"sessions": list(sessions)})
    assert response.status_code == 200, response.text


def leaves(count: int, mg: float | None = 2.0, origin: str = "local") -> list[dict]:
    return [{"kind": "chat", "origin": origin, "mg": mg} for _ in range(count)]


# --- Historique ---------------------------------------------------------------------------------


async def test_history_gives_one_row_per_closed_session_of_the_window(served):
    app, client = served
    await seed(
        client,
        {"days_ago": 1, "leaves": leaves(2) + leaves(1, 4.0, "cloud")},
        {"days_ago": 10, "leaves": leaves(1, 3.0)},
        {"days_ago": 40, "leaves": leaves(1, 5.0)},
    )
    week = (await client.get("/api/carbon/history?window=7d")).json()
    assert week["window"] == "7d" and len(week["sessions"]) == 1
    row = week["sessions"][0]
    assert row["total_mg"] == pytest.approx(8.0)
    assert row["local_mg"] == pytest.approx(4.0) and row["cloud_mg"] == pytest.approx(4.0)
    assert row["measured_runs"] == 3 and row["unmeasurable_runs"] == 0
    assert row["started_at"] < row["ended_at"]
    assert set(row) == {
        "id", "started_at", "ended_at", "total_mg", "local_mg", "cloud_mg",
        "measured_runs", "unmeasurable_runs",
    }  # fmt: skip

    month = (await client.get("/api/carbon/history?window=30d")).json()["sessions"]
    assert [round(r["total_mg"]) for r in month] == [3, 8]  # du plus ancien au plus récent
    every = (await client.get("/api/carbon/history?window=all")).json()["sessions"]
    assert [round(r["total_mg"]) for r in every] == [5, 3, 8]


async def test_history_defaults_to_seven_days_and_refuses_an_unknown_window(served):
    _, client = served
    await seed(client, {"days_ago": 20, "leaves": leaves(1)})
    assert (await client.get("/api/carbon/history")).json() == {"window": "7d", "sessions": []}
    refused = await client.get("/api/carbon/history?window=1y")
    assert refused.status_code == 422 and refused.json()["code"] == "invalid_request"


async def test_history_without_any_session_is_an_empty_list(served):
    _, client = served
    assert (await client.get("/api/carbon/history?window=all")).json() == {
        "window": "all",
        "sessions": [],
    }


async def test_the_session_in_progress_is_not_listed(served):
    app, client = served
    await produce_chat(app.state.hub)
    assert (await client.get("/api/carbon/history?window=all")).json()["sessions"] == []


# --- Remise à zéro ------------------------------------------------------------------------------


async def test_reset_opens_a_new_session_and_the_closed_one_enters_the_history(served):
    app, client = served
    await produce_chat(app.state.hub)
    first = (await client.get("/api/carbon/session")).json()
    assert first["total_mg"] == pytest.approx(1.5)

    response = await client.post("/api/carbon/session/reset")
    assert response.status_code == 200
    fresh = response.json()
    assert fresh["total_mg"] == 0.0 and fresh["measured_runs"] == 0
    assert fresh["app_session"]["reason"] == "reset"
    assert fresh["app_session"]["id"] != first["app_session"]["id"]
    assert (await client.get("/api/carbon/session")).json()["total_mg"] == 0.0

    rows = (await client.get("/api/carbon/history?window=all")).json()["sessions"]
    assert [r["id"] for r in rows] == [first["app_session"]["id"]]
    assert rows[0]["total_mg"] == pytest.approx(1.5)


async def test_reset_publishes_a_null_carbon_updated_on_the_system_stream(served):
    app, client = served
    await produce_chat(app.state.hub)
    stream = Stream(app, "/api/system/stream")
    await stream.frame()  # le premier échantillon
    await client.post("/api/carbon/session/reset")
    for _ in range(10):
        frame = (await stream.frame())["data"]
        if frame["type"] == "carbon_updated":
            break
    assert frame["type"] == "carbon_updated" and frame["data"]["total_mg"] == 0.0
    await stream.disconnect()


async def test_reset_does_not_erase_anything_and_the_history_total_never_drops(served):
    app, client = served
    hub = app.state.hub
    handle = await produce_chat(hub)
    await client.post("/api/carbon/session/reset")
    before = (await client.get("/api/carbon/history?window=all")).json()["sessions"][0]
    assert (await client.delete(f"/api/conversations/{handle.conversation_id}")).status_code == 204
    after = (await client.get("/api/carbon/history?window=all")).json()["sessions"][0]
    assert after["total_mg"] == pytest.approx(before["total_mg"])  # AD-13


async def test_an_active_run_stays_counted_in_the_session_where_it_started(served):
    """Un run scripté lent : la remise à zéro tombe pendant qu'il tourne ; sa réponse finit dans la
    session close, la nouvelle session reste à zéro."""
    app, client = served
    await produce_chat(app.state.hub)  # le compteur n'est pas vide : la remise à zéro a un sens
    started = await client.post(
        "/api/test/runs",
        json={
            "script": [{"text": "a"}, {"sleep_s": 0.4}, {"text": "b"}],
            "co2": {"mg": 7.0, "method": "codecarbon", "estimated": False},
        },
    )
    assert started.status_code == 200
    reset = (await client.post("/api/carbon/session/reset")).json()
    assert reset["total_mg"] == 0.0
    deadline = time.monotonic() + 10
    while app.state.hub.active_runs():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.1)
    assert (await client.get("/api/carbon/session")).json()["total_mg"] == 0.0
    (row,) = (await client.get("/api/carbon/history?window=all")).json()["sessions"]
    assert row["total_mg"] == pytest.approx(8.5)  # 1,5 mg du premier chat et 7 mg du run actif
    assert row["measured_runs"] == 2


# --- Garde d'origine et budget ------------------------------------------------------------------


async def test_reset_refuses_a_foreign_origin_and_leaves_the_session_alone(served):
    app, client = served
    await produce_chat(app.state.hub)
    refused = await client.post(
        "/api/carbon/session/reset", headers={"Origin": "http://evil.example"}
    )
    assert refused.status_code == 403 and refused.json()["code"] == "forbidden_origin"
    assert (await client.get("/api/carbon/session")).json()["total_mg"] == pytest.approx(1.5)
    allowed = await client.post(
        "/api/carbon/session/reset", headers={"Origin": f"http://127.0.0.1:{TEST_PORT}"}
    )
    assert allowed.status_code == 200


async def test_history_answers_under_300_ms_with_1000_runs_and_ollama_down(tmp_path):
    settings = make_settings(
        tmp_path,
        environ={"WAVELOCALAI_TESTING": "1"},
        ollama={"host": f"http://127.0.0.1:{closed_port()}"},
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client,
    ):
        await seed(client, *({"days_ago": index / 10, "leaves": leaves(20)} for index in range(50)))
        total = await app.state.store.aread("SELECT COUNT(*) AS n FROM runs")
        assert total[0]["n"] == 1000
        timings = []
        for window in ("7d", "30d", "all", "all"):
            started = time.perf_counter()
            response = await client.get(f"/api/carbon/history?window={window}")
            timings.append(time.perf_counter() - started)
            assert response.status_code == 200
        assert len(response.json()["sessions"]) == 50
    assert min(timings) < BUDGET_S and max(timings) < BUDGET_S, timings


def test_the_history_route_enters_the_read_budget_and_reset_is_a_write(tmp_path):
    from .test_read_budget import discover_read_routes

    app = create_app(make_settings(tmp_path))
    assert "/api/carbon/history" in discover_read_routes(app)
    operations = app.openapi()["paths"]["/api/carbon/session/reset"]
    assert set(operations) == {"post"}
