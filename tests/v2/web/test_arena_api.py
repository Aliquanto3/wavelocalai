"""`POST /api/arena/runs` : une même question sur 2 à 4 modèles, de bout en bout (story 3.1).

L'app est la vraie (hub, registre, service de l'Arène, sémaphore, flux SSE) ; les modèles sont des
`FakeChatModel` scriptés, locaux ou cloud. Aucun Ollama, aucun réseau.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import httpx
import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.inference.arena import LANE_STATUSES
from wavelocalai.models.fake import FakeChatModel, Sleep
from wavelocalai.models.port import LoadState, ModelRef, TextDelta
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.store.db import Store, db_path
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from .conftest import parse_sse

BASE = f"http://127.0.0.1:{TEST_PORT}"
PROMPT = "Explique la photosynthèse à un enfant de dix ans, en trois phrases simples."


def local(tag: str, script=()) -> FakeChatModel:
    return FakeChatModel(script, ModelRef(tag, "fake", "local", "chat"))


def cloud(tag: str, script=()) -> FakeChatModel:
    return FakeChatModel(script, ModelRef(tag, "fake", "cloud", "chat"))


def say(*words: str) -> list[TextDelta]:
    return [TextDelta(word) for word in words]


@contextlib.asynccontextmanager
async def arena_app(tmp_path, *fakes: FakeChatModel, **settings):
    config = make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}, **settings)
    registry = ModelRegistry(config, extra_refs={m.ref.tag: m.ref for m in fakes})
    app = create_app(config, registry=registry)
    app.state.models.update({m.ref.tag: m for m in fakes})  # la fabrique les prend au démarrage
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


async def _post(client, *models: str, **body):
    payload = {"models": list(models), "prompt": PROMPT, "allow_cloud": True, **body}
    return await client.post("/api/arena/runs", json=payload)


async def _ended(client, run_id, timeout=5.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


async def _events(client, run_id):
    response = await client.get(f"/api/runs/{run_id}/events")
    return [f["data"] for f in parse_sse(response.text)[0]]


async def _until(app, run_id, predicate, timeout=3.0):
    async with asyncio.timeout(timeout):
        while True:
            events = await app.state.hub.events_after(run_id)
            if predicate(events):
                return events
            await asyncio.sleep(0.01)


def statuses(events, lane):
    return [
        e["data"]["status"]
        for e in events
        if e["type"] == "lane_status" and e["data"]["lane"] == lane
    ]


def index(events, type_, lane=None, status=None):
    for i, e in enumerate(events):
        data = e["data"]
        same_lane = lane is None or data.get("lane") == lane
        if e["type"] == type_ and same_lane and (status is None or data.get("status") == status):
            return i
    raise AssertionError(f"{type_} {lane} {status} absent")


def children(snapshot):
    return {c["model"]: c for c in snapshot["children"]}


async def test_two_local_lanes_and_a_cloud_lane_compose_one_run(tmp_path, _stub_codecarbon):
    a, b = local("fake:a", say("Les ", "plantes")), local("fake:b", say("Elles ", "mangent"))
    c = cloud("fake/c", say("La ", "lumière"))
    probe = _stub_codecarbon
    async with arena_app(tmp_path, a, b, c) as (app, client):
        async with asyncio.timeout(5):
            while probe.stopped < 1:  # préchauffage de CodeCarbon au démarrage
                await asyncio.sleep(0.01)
        response = await _post(client, "fake:a", "fake:b", "fake/c")
        assert response.status_code == 200, response.text
        assert set(response.json()) == {"run_id"}  # pas de conversation
        run_id = response.json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)

        assert snapshot["kind"] == "arena" and snapshot["status"] == "ok"
        assert snapshot["conversation_id"] is None and snapshot["metrics"] is None
        assert snapshot["error"] is None
        kids = children(snapshot)
        assert set(kids) == {"fake:a", "fake:b", "fake/c"}
        for tag, child in kids.items():
            assert child["kind"] == "generation" and child["parent_run_id"] == run_id
            assert child["status"] == "ok"
            assert child["metrics"]["origin"] == ("cloud" if tag == "fake/c" else "local")
            co2 = child["metrics"]["co2"]
            if tag == "fake/c":  # cloud : ecologits pas encore branché
                assert co2["method"] == "unmeasurable" and co2["mg"] is None and co2["reason"]
            else:  # chaque lane locale a son propre tracker (AD-10, AD-11)
                assert co2["method"] == "codecarbon" and co2["allocation"] == "direct"
                assert co2["mg"] == pytest.approx(1.8)
        # Un tracker par lane locale, jamais deux à la fois ; aucun pour la lane cloud.
        assert probe.started == probe.stopped == 3 and probe.peak == 1  # préchauffage compris
        # Seul le parent publie : les feuilles n'ont pas de flux.
        for child in snapshot["children"]:
            assert (await client.get(f"/api/runs/{child['run_id']}/events")).status_code == 404
        # Aucune conversation ni message.
        assert app.state.store.read("SELECT count(*) AS n FROM conversations")[0]["n"] == 0
        assert app.state.store.read("SELECT count(*) AS n FROM messages")[0]["n"] == 0

    types = [e["type"] for e in events]
    assert types[:2] == ["run_started", "question"] and types[-1] == "run_ended"
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["data"]["kind"] == "arena"
    assert events[0]["data"]["models"] == ["fake:a", "fake:b", "fake/c"]
    assert events[1]["data"] == {"text": PROMPT, "criteria": []}
    assert events[-1]["data"] == {"status": "ok", "error": None}
    for lane, words in (
        ("fake:a", "Les plantes"),
        ("fake:b", "Elles mangent"),
        ("fake/c", "La lumière"),
    ):
        assert statuses(events, lane)[0] == "waiting" and statuses(events, lane)[-1] == "done"
        assert set(statuses(events, lane)) <= set(LANE_STATUSES)
        text = "".join(
            e["data"]["text"] for e in events if e["type"] == "token" and e["data"]["lane"] == lane
        )
        assert text == words
        metrics = [e for e in events if e["type"] == "metrics" and e["data"]["lane"] == lane]
        assert len(metrics) == 1
        # Le flux porte le `co2` mesuré de la lane, celui de sa feuille en base.
        assert metrics[0]["data"]["co2"] == kids[lane]["metrics"]["co2"]
        assert index(events, "metrics", lane) < index(events, "lane_status", lane, "done")
    # `lane` est présent sur tout ce qui porte une lane.
    for e in events:
        if e["type"] in ("token", "metrics", "lane_status"):
            assert e["data"]["lane"]


async def test_locals_run_in_sequence_under_the_slot_and_the_cloud_runs_at_once(tmp_path):
    a = local("fake:a", [Sleep(0.15), *say("A")])
    b = local("fake:b", [Sleep(0.05), *say("B")])
    c = cloud("fake/c", say("C"))
    async with arena_app(tmp_path, a, b, c) as (app, client):
        run_id = (await _post(client, "fake:a", "fake/c", "fake:b")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
        assert app.state.local_slot.acquired == 2 and not app.state.local_slot.busy

    # Le second local attend la fin du premier ; le cloud part sans attendre la place.
    assert statuses(events, "fake:b") == ["waiting", "generating", "done"]
    # B (0,05 s) ne rattrape pas A (0,15 s) : sa place ne vient qu'après la dernière sortie de A.
    assert index(events, "token", "fake:a") < index(events, "token", "fake:b")
    assert index(events, "token", "fake:a") < index(events, "lane_status", "fake:b", "generating")
    assert index(events, "lane_status", "fake:a", "generating") < index(
        events, "lane_status", "fake:b", "generating"
    )
    # Le cloud ne passe pas par la place : il part et finit pendant que A dort.
    assert index(events, "lane_status", "fake/c", "done") < index(events, "token", "fake:a")


async def test_lane_timeout_counts_from_the_slot_not_from_the_wait(tmp_path):
    # 0,25 s chacune pour un délai de 0,4 s : la seconde attend 0,25 s mais ne dépasse pas.
    a = local("fake:a", [Sleep(0.25), *say("A")])
    b = local("fake:b", [Sleep(0.25), *say("B")])
    async with arena_app(tmp_path, a, b, delays={"lane_timeout_s": 0.4}) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b")).json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)
    assert statuses(events, "fake:a")[-1] == statuses(events, "fake:b")[-1] == "done"
    assert snapshot["status"] == "ok"


async def test_a_slow_lane_times_out_and_a_failing_lane_fails_while_the_others_finish(tmp_path):
    slow = local("fake:slow", [*say("début"), Sleep(30)])
    broken = local("fake:broken", [*say("x"), ProviderError("ollama_error", "boum")])
    fine = local("fake:fine", say("ok"))
    online = cloud("fake/online", say("cloud"))
    async with arena_app(tmp_path, slow, broken, fine, online, delays={"lane_timeout_s": 0.2}) as (
        app,
        client,
    ):
        run_id = (
            await _post(client, "fake:slow", "fake:broken", "fake:fine", "fake/online")
        ).json()["run_id"]
        snapshot = await _ended(client, run_id, timeout=6)
        events = await _events(client, run_id)
        assert slow.closed == slow.opened == 1  # flux fermé malgré le délai

    assert snapshot["status"] == "ok" and snapshot["error"] is None  # l'orchestration a abouti
    assert events[-1]["data"] == {"status": "ok", "error": None}
    kids = children(snapshot)
    assert (
        kids["fake:slow"]["status"] == "error" and kids["fake:slow"]["error"]["code"] == "timeout"
    )
    assert kids["fake:broken"]["status"] == "error"
    assert kids["fake:broken"]["error"]["code"] == "ollama_error"
    assert kids["fake:fine"]["status"] == kids["fake/online"]["status"] == "ok"

    timeout = next(
        e for e in events if e["type"] == "lane_status" and e["data"]["status"] == "timeout"
    )
    assert timeout["data"]["lane"] == "fake:slow" and timeout["data"]["error"]["code"] == "timeout"
    failed = next(
        e for e in events if e["type"] == "lane_status" and e["data"]["status"] == "failed"
    )
    assert (
        failed["data"]["lane"] == "fake:broken"
        and failed["data"]["error"]["code"] == "ollama_error"
    )
    assert statuses(events, "fake:fine")[-1] == statuses(events, "fake/online")[-1] == "done"
    # Le texte reçu avant l'échec reste dans le flux de sa lane.
    assert "début" in "".join(
        e["data"]["text"]
        for e in events
        if e["type"] == "token" and e["data"]["lane"] == "fake:slow"
    )


async def test_the_loading_phase_is_published_for_a_local_lane(tmp_path):
    a = local("fake:a", [LoadState("loading"), Sleep(0.02), LoadState("loaded", 0.02), *say("A")])
    b = local("fake:b", say("B"))
    async with arena_app(tmp_path, a, b) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    assert statuses(events, "fake:a") == ["waiting", "generating", "loading", "generating", "done"]


async def test_cancelling_the_parent_cancels_every_lane_and_keeps_the_partials(
    tmp_path, _stub_codecarbon
):
    a = local("fake:a", [*say("partiel A"), Sleep(30)])
    b = local("fake:b", [*say("jamais")])  # attend la place de A
    c = cloud("fake/c", [*say("partiel C"), Sleep(30)])
    async with arena_app(tmp_path, a, b, c) as (app, client):
        run_id = (await _post(client, "fake:a", "fake:b", "fake/c")).json()["run_id"]
        await _until(
            app,
            run_id,
            lambda ev: {e["data"].get("lane") for e in ev if e["type"] == "token"}
            >= {"fake:a", "fake/c"},
        )
        result = await client.post(f"/api/runs/{run_id}/cancel")
        assert result.json() == {"run_id": run_id, "cancelled": True, "status": "cancelled"}
        snapshot = (await client.get(f"/api/runs/{run_id}")).json()
        events = await _events(client, run_id)  # relu depuis la base
        assert not app.state.local_slot.busy
        async with asyncio.timeout(2):
            while a.closed < 1 or c.closed < 1:  # flux des adaptateurs fermés
                await asyncio.sleep(0.01)
        # La lane locale annulée garde l'énergie mesurée jusqu'à l'arrêt (AD-10), écrite après
        # la clôture ; la lane en attente et la lane cloud restent non mesurables, avec raison.
        async with asyncio.timeout(2):
            while True:
                co2 = {
                    r["model"]: r
                    for r in app.state.store.read(
                        "SELECT model, co2_mg, co2_method, co2_reason FROM runs"
                        " WHERE parent_run_id = ?",
                        (run_id,),
                    )
                }
                if co2["fake:a"]["co2_method"] == "codecarbon":
                    break
                await asyncio.sleep(0.01)
        root_co2 = app.state.store.read(
            "SELECT co2_mg, co2_method, energy_wh FROM runs WHERE id = ?", (run_id,)
        )[0]

    assert co2["fake:a"]["co2_mg"] == pytest.approx(1.8)
    for lane in ("fake:b", "fake/c"):
        assert co2[lane]["co2_method"] == "unmeasurable" and co2[lane]["co2_mg"] is None
        assert co2[lane]["co2_reason"]
    # Le parent ne porte ni métriques ni CO2 (AD-5).
    assert dict(root_co2) == {"co2_mg": None, "co2_method": None, "energy_wh": None}

    assert snapshot["status"] == "cancelled"
    assert [c_["status"] for c_ in snapshot["children"]] == ["cancelled"] * 3
    assert events[-1]["type"] == "run_ended" and events[-1]["data"]["status"] == "cancelled"
    for lane in ("fake:a", "fake:b", "fake/c"):
        assert statuses(events, lane)[-1] == "cancelled"
        assert index(events, "lane_status", lane, "cancelled") < len(events) - 1
    text = {
        lane: "".join(
            e["data"]["text"] for e in events if e["type"] == "token" and e["data"]["lane"] == lane
        )
        for lane in ("fake:a", "fake:b", "fake/c")
    }
    assert text == {"fake:a": "partiel A", "fake:b": "", "fake/c": "partiel C"}
    assert b.opened == 0  # la lane en attente n'a jamais appelé le modèle


async def test_an_orchestration_failure_ends_every_lane_and_the_root_in_error(tmp_path):
    a = local("fake:a", [*say("partiel A"), Sleep(30)])
    b = local("fake:b", say("B"))
    async with arena_app(tmp_path, a, b) as (app, client):
        hub = app.state.hub
        attach = hub.attach_task
        leaves: list[str] = []

        def failing_attach(run_id, task):
            if hub._runs[run_id].parent_id is not None:
                leaves.append(run_id)
                if len(leaves) == 2:
                    task.cancel()
                    raise RuntimeError("panne simulée")
            attach(run_id, task)

        hub.attach_task = failing_attach
        run_id = (await _post(client, "fake:a", "fake:b")).json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)
    assert snapshot["status"] == "error" and snapshot["error"]["code"] == "internal"
    for lane in ("fake:a", "fake:b"):
        assert statuses(events, lane)[-1] == "cancelled"
    assert events[-1]["type"] == "run_ended"


async def test_a_second_arena_gets_409_run_busy_with_the_active_run_id(tmp_path):
    a = local("fake:a", [Sleep(0.3), *say("A")])
    b = local("fake:b", say("B"))
    async with arena_app(tmp_path, a, b) as (_, client):
        first = (await _post(client, "fake:a", "fake:b")).json()["run_id"]
        second = await _post(client, "fake:a", "fake:b")
        assert second.status_code == 409
        assert second.json()["code"] == "run_busy"
        assert second.json()["detail"]["run_id"] == first
        await _ended(client, first)
        assert (await _post(client, "fake:a", "fake:b")).status_code == 200  # la place est libre


async def test_a_cloud_model_without_allow_cloud_is_refused_before_any_call_or_write(tmp_path):
    a, b, c = local("fake:a", say("A")), local("fake:b", say("B")), cloud("fake/c", say("C"))
    async with arena_app(tmp_path, a, b, c) as (app, client):
        response = await _post(client, "fake:a", "fake/c", allow_cloud=False)
        assert response.status_code == 403 and response.json()["code"] == "cloud_not_allowed"
        assert response.json()["detail"]["tag"] == "fake/c"
        absent = await client.post(
            "/api/arena/runs", json={"models": ["fake:a", "fake/c"], "prompt": PROMPT}
        )
        assert absent.json()["code"] == "cloud_not_allowed"  # absent vaut faux
        judge = await _post(client, "fake:a", "fake:b", judge="fake/c", allow_cloud=False)
        assert judge.json()["code"] == "cloud_not_allowed"  # le juge aussi, avant tout run
        await asyncio.sleep(0.05)
        assert a.opened == b.opened == c.opened == 0
        assert app.state.store.read("SELECT count(*) AS n FROM runs")[0]["n"] == 0


@pytest.mark.parametrize(
    ("models", "extra", "code"),
    [
        (["fake:a"], {}, "invalid_request"),
        (["fake:a", "fake:b", "fake:c", "fake:d", "fake/e"], {}, "invalid_request"),
        (["fake:a", "fake:a"], {}, "invalid_request"),
        (["fake:a", "fake:b"], {"prompt": "   "}, "invalid_request"),
        (["fake:a", "fake:b"], {"criteria": ["x" * 65]}, "invalid_request"),
        (["fake:a", "fake:inconnu"], {}, "model_not_found"),
    ],
)
async def test_invalid_requests_are_refused_without_creating_a_run(tmp_path, models, extra, code):
    fakes = [local(f"fake:{n}", say(n)) for n in "abcd"] + [cloud("fake/e", say("e"))]
    async with arena_app(tmp_path, *fakes) as (app, client):
        response = await _post(client, *models, **extra)
        assert response.status_code in (404, 422), response.text
        assert response.json()["code"] == code
        assert app.state.store.read("SELECT count(*) AS n FROM runs")[0]["n"] == 0


async def test_the_prompt_lives_in_run_events_never_in_run_params(tmp_path):
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    async with arena_app(tmp_path, a, b) as (app, client):
        run_id = (
            await _post(
                client, "fake:a", "fake:b", judge="fake:a", criteria=["clarté", "exactitude"]
            )
        ).json()["run_id"]
        await _ended(client, run_id)
        rows = app.state.store.read("SELECT kind, params FROM runs")
        events = app.state.store.read(
            "SELECT type, data FROM run_events WHERE run_id = ? ORDER BY seq", (run_id,)
        )
    assert len(rows) == 3
    assert all(PROMPT not in row["params"] for row in rows)
    root = next(json.loads(r["params"]) for r in rows if r["kind"] == "arena")
    assert root == {
        "temperature": 0.2,
        "allow_cloud": True,
        "judge": "fake:a",
    }
    # Les critères sont du texte saisi : dans l'événement `question`, comme la question (AD-7).
    assert all("clarté" not in row["params"] for row in rows)
    assert PROMPT not in events[0]["data"] and "clarté" not in events[0]["data"]  # run_started
    assert json.loads(events[1]["data"]) == {
        "text": PROMPT,
        "criteria": ["clarté", "exactitude"],
    }  # question


async def test_the_arena_is_cancelled_with_the_server(tmp_path):
    a = local("fake:a", [*say("en cours"), Sleep(30)])
    b = local("fake:b", say("B"))
    async with arena_app(tmp_path, a, b) as (app, client):
        run_id = (await _post(client, "fake:a", "fake:b")).json()["run_id"]
        await _until(app, run_id, lambda ev: any(e["type"] == "token" for e in ev))
    # Le cycle de vie est fermé : `hub.stop()` a clos le run en `cancelled`, lanes comprises.
    store = Store.open(db_path(tmp_path / "data"))
    try:
        rows = store.read("SELECT kind, status FROM runs ORDER BY rowid")
        last = store.read(
            "SELECT type, data FROM run_events WHERE run_id = ? ORDER BY seq DESC LIMIT 3",
            (run_id,),
        )
    finally:
        store.close()
    assert [r["status"] for r in rows] == ["cancelled"] * 3
    assert last[0]["type"] == "run_ended"
    assert {json.loads(r["data"]).get("status") for r in last[1:]} == {"cancelled"}
