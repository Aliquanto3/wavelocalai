"""Le hub et la validation d'une action sensible : demande, réponse, expiration, annulation (6.3, AD-9).

Aucun service : un test joue le rôle de la boucle d'un agent. Aucun email, aucun réseau.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

import pytest

from wavelocalai.runs.hub import RunHub
from wavelocalai.store.db import Store, db_path

DETAILS = {"destinataire": "a@example.org", "objet": "Bonjour", "corps": "Corps"}


@pytest.fixture
async def store(tmp_path: Path):
    opened = Store.open(db_path(tmp_path / "data"))
    yield opened
    opened.close()


@pytest.fixture
async def hub(store: Store):
    started = RunHub(store, batch_interval_s=3600)
    await started.start()
    yield started
    await started.stop()


def _status(store, run_id):
    return store.read("SELECT status FROM runs WHERE id = ?", (run_id,))[0][0]


async def _types(hub, run_id):
    return [e["type"] for e in await hub.events_after(run_id)]


async def _required(hub, run_id) -> list[dict]:
    return [e["data"] for e in await hub.events_after(run_id) if e["type"] == "approval_required"]


async def _pending(hub, run_id, count=1) -> list[dict]:
    """Données des `approval_required` publiés (attend qu'il y en ait `count`)."""
    async with asyncio.timeout(2):
        while len(found := await _required(hub, run_id)) < count:
            await asyncio.sleep(0.01)
    return found


def _ask(hub, run_id, expiry_s=5.0):
    return asyncio.create_task(
        hub.request_approval(run_id, "email", DETAILS, expiry_s=expiry_s, call_id="c1")
    )


async def test_a_request_publishes_the_details_and_moves_the_run_to_awaiting_and_back(hub, store):
    run = await hub.create_run("agent", models=["m"])
    task = _ask(hub, run.run_id)
    (data,) = await _pending(hub, run.run_id)
    assert data == {
        "approval_id": data["approval_id"],
        "kind": "email",
        **DETAILS,
        "call_id": "c1",
        "expiry_s": 5.0,
    }
    # Le run garde son genre ; son statut, en mémoire et en base, est `awaiting_approval`.
    assert hub.active_runs() == [
        {"run_id": run.run_id, "kind": "agent", "status": "awaiting_approval"}
    ]
    assert _status(store, run.run_id) == "awaiting_approval"
    assert not task.done()  # rien ne continue sans réponse

    assert await hub.resolve_approval(run.run_id, data["approval_id"], "approved") is True
    assert await task == "approved"
    assert _status(store, run.run_id) == "running"
    assert hub.active_runs()[0]["status"] == "running"
    events = await hub.events_after(run.run_id)
    assert [e["type"] for e in events] == ["run_started", "approval_required", "approval_resolved"]
    assert events[-1]["data"] == {"approval_id": data["approval_id"], "decision": "approved"}


async def test_a_request_is_answered_once_and_only_by_approved_or_rejected(hub):
    run = await hub.create_run("agent")
    task = _ask(hub, run.run_id)
    approval_id = (await _pending(hub, run.run_id))[0]["approval_id"]
    with pytest.raises(ValueError):  # `expired` n'est jamais dit par un client
        await hub.resolve_approval(run.run_id, approval_id, "expired")
    assert await hub.resolve_approval(run.run_id, "inconnu", "approved") is False
    assert await hub.resolve_approval(run.run_id, approval_id, "rejected") is True
    assert await hub.resolve_approval(run.run_id, approval_id, "approved") is False  # déjà traitée
    assert await task == "rejected"
    assert (await _types(hub, run.run_id)).count("approval_resolved") == 1


async def test_no_answer_in_time_is_expired_and_the_run_goes_on(hub, store):
    run = await hub.create_run("agent")
    decision = await hub.request_approval(run.run_id, "email", DETAILS, expiry_s=0.05)
    assert decision == "expired"
    last = (await hub.events_after(run.run_id))[-1]
    assert last["type"] == "approval_resolved" and last["data"]["decision"] == "expired"
    assert _status(store, run.run_id) == "running"
    # Une réponse tardive n'est plus acceptée.
    assert await hub.resolve_approval(run.run_id, last["data"]["approval_id"], "approved") is False


async def test_cancelling_the_run_rejects_the_pending_request_before_run_ended(hub, store):
    run = await hub.create_run("agent")
    task = _ask(hub, run.run_id, expiry_s=30)
    hub.attach_task(run.run_id, task)
    approval_id = (await _pending(hub, run.run_id))[0]["approval_id"]
    assert await hub.cancel(run.run_id) is True
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert task.cancelled()  # la tâche est coupée : l'action ne s'exécute jamais
    events = await hub.events_after(run.run_id)
    kinds = [e["type"] for e in events]
    assert kinds[-3:] == ["approval_required", "approval_resolved", "run_ended"]
    assert events[-2]["data"] == {"approval_id": approval_id, "decision": "rejected"}
    assert events[-1]["data"]["status"] == "cancelled"
    assert _status(store, run.run_id) == "cancelled"
    assert await hub.resolve_approval(run.run_id, approval_id, "approved") is False


async def test_a_closed_run_asks_for_nothing_and_a_leaf_cannot_ask(hub):
    run = await hub.create_run("agent")
    leaf = await hub.create_run("generation", models=["m"], parent_run_id=run.run_id)
    with pytest.raises(ValueError):
        await hub.request_approval(leaf.run_id, "email", DETAILS, expiry_s=1)
    await hub.finish_run(run.run_id, "ok")
    assert await hub.request_approval(run.run_id, "email", DETAILS, expiry_s=1) == "rejected"
    with pytest.raises(KeyError):
        await hub.request_approval("inconnu", "email", DETAILS, expiry_s=1)


async def test_the_run_stays_awaiting_until_every_pending_request_is_answered(hub, store):
    run = await hub.create_run("agent")
    first, second = _ask(hub, run.run_id), _ask(hub, run.run_id)
    ids = [d["approval_id"] for d in await _pending(hub, run.run_id, count=2)]
    await hub.resolve_approval(run.run_id, ids[0], "approved")
    assert _status(store, run.run_id) == "awaiting_approval"
    await hub.resolve_approval(run.run_id, ids[1], "rejected")
    assert _status(store, run.run_id) == "running"
    assert sorted([await first, await second]) == ["approved", "rejected"]


async def test_a_restart_during_the_wait_interrupts_the_run_and_nothing_is_approved(store):
    before = RunHub(store, batch_interval_s=3600)
    await before.start()
    run = await before.create_run("agent")
    task = _ask(before, run.run_id)
    await _pending(before, run.run_id)
    await before.flush()  # le serveur « s'arrête » ici, pendant l'attente
    assert _status(store, run.run_id) == "awaiting_approval"

    after = RunHub(store, batch_interval_s=3600)
    interrupted = await after.start()
    try:
        assert interrupted == [run.run_id]
        assert _status(store, run.run_id) == "interrupted"
        rows = store.read(
            "SELECT type, data FROM run_events WHERE run_id = ? ORDER BY seq", (run.run_id,)
        )
        assert [r[0] for r in rows] == ["run_started", "approval_required", "run_ended"]
        assert json.loads(rows[-1][1]) == {"status": "interrupted", "error": None}
        assert not any(r[0] == "approval_resolved" for r in rows)  # aucune décision n'a existé
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await after.stop()


async def test_an_answer_after_the_wait_was_interrupted_is_refused(hub, store):
    # Revue : le délai (ou une annulation) interrompt l'attente ; une réponse arrivée avant que la
    # tâche reprenne ne doit pas publier `approved`, puisque rien ne sera exécuté.
    run = await hub.create_run("agent", models=["m"])
    task = _ask(hub, run.run_id)
    (data,) = await _pending(hub, run.run_id)
    async with asyncio.timeout(2):  # la tâche attend la réponse (transition écrite)
        while _status(store, run.run_id) != "awaiting_approval":
            await asyncio.sleep(0.01)
    await asyncio.sleep(0.01)
    task.cancel()  # ce que fait le rappel d'`asyncio.timeout` à l'échéance
    assert await hub.resolve_approval(run.run_id, data["approval_id"], "approved") is False
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert "approval_resolved" not in await _types(hub, run.run_id)
