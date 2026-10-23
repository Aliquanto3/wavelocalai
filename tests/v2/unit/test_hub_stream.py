"""Ajouts du hub pour le flux (story 1.4) : groupage des `token`, abonnement, un run actif par genre.

Les producteurs de `tests/v2/producers.py` jouent le rôle d'un service : aucun adaptateur de modèle.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from wavelocalai.errors import ERRORS, AppError, build_envelope
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import STATUSES, LeafResult
from wavelocalai.store.db import Store, db_path

from ..producers import produce_arena, produce_chat


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


async def _types(hub, run_id):
    return [e["type"] for e in await hub.events_after(run_id)]


# --- groupage des token (AD-6) -----------------------------------------------------------------


async def test_tokens_of_a_slice_become_one_event_per_lane_and_keep_their_text(hub):
    handle = await hub.create_run("arena", models=["a:1b", "b:1b"])
    for text_a, text_b in [("Sa", "Un"), ("lu", " de"), ("t", "ux")]:
        hub.publish_token(handle.run_id, "a:1b", text_a)
        hub.publish_token(handle.run_id, "b:1b", text_b)
    assert len(await hub.events_after(handle.run_id)) == 1  # rien n'est parti : tranche ouverte
    await asyncio.sleep(0.12)
    tokens = [e for e in await hub.events_after(handle.run_id) if e["type"] == "token"]
    assert [(e["data"]["lane"], e["data"]["text"]) for e in tokens] == [
        ("a:1b", "Salut"),
        ("b:1b", "Un deux"),
    ]
    assert all(e["data"]["channel"] == "answer" for e in tokens)
    assert [e["seq"] for e in await hub.events_after(handle.run_id)] == [1, 2, 3]  # contigu


async def test_a_steady_flow_is_cut_in_slices_of_about_50_ms(hub):
    handle = await hub.create_run("chat", models=["m"])
    for index in range(30):  # 30 morceaux sur ~0,3 s
        hub.publish_token(handle.run_id, "m", f"{index},")
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.1)
    tokens = [e for e in await hub.events_after(handle.run_id) if e["type"] == "token"]
    assert 3 <= len(tokens) <= 15  # ni un événement par morceau, ni un seul pour tout
    joined = "".join(e["data"]["text"] for e in tokens)
    assert joined == "".join(f"{i}," for i in range(30))  # aucun morceau perdu ni réordonné


async def test_pending_tokens_precede_the_next_event_and_channels_stay_apart(hub):
    handle = await hub.create_run("chat", models=["m"])
    hub.publish_token(handle.run_id, "m", "réfl", "thought")
    hub.publish_token(handle.run_id, "m", "rép", "answer")
    hub.publish(handle.run_id, "lane_status", {"lane": "m", "status": "done"})
    events = await hub.events_after(handle.run_id)
    assert [e["type"] for e in events] == ["run_started", "token", "token", "lane_status"]
    assert [e["data"]["channel"] for e in events[1:3]] == ["thought", "answer"]


async def test_closing_flushes_pending_tokens_into_the_stream_and_the_partial_message(hub, store):
    handle = await hub.create_run("chat", models=["m"], user_message="Q")
    hub.publish_token(handle.run_id, "m", "par")
    hub.publish_token(handle.run_id, "m", "tiel")
    assert await hub.cancel(handle.run_id)
    rows = store.read(
        "SELECT type, data FROM run_events WHERE run_id = ? ORDER BY seq", (handle.run_id,)
    )
    assert [r["type"] for r in rows] == ["run_started", "token", "run_ended"]
    assert json.loads(rows[1]["data"])["text"] == "partiel"
    message = store.read("SELECT content FROM messages WHERE role = 'assistant'")[0]
    assert message["content"] == "partiel"


async def test_a_token_needs_a_lane_and_only_a_root_publishes(hub):
    parent, leaves = await produce_arena(hub)
    with pytest.raises(ValueError, match="lane"):
        hub.publish_token(parent.run_id, "", "x")
    with pytest.raises(ValueError, match="parent"):
        hub.publish_token(leaves[0].run_id, "a:1b", "x")
    with pytest.raises(KeyError):
        hub.publish_token("inconnu", "a:1b", "x")


async def test_a_late_token_after_closing_is_dropped(hub):
    handle = await hub.create_run("chat", models=["m"])
    await hub.cancel(handle.run_id)
    hub.publish_token(handle.run_id, "m", "tard")  # ne lève pas, n'écrit rien


# --- abonnement --------------------------------------------------------------------------------


async def test_watch_fires_on_each_event_then_on_closing_and_is_none_afterwards(hub):
    handle = await hub.create_run("chat", models=["m"])
    first = hub.watch(handle.run_id)
    assert first is not None and not first.is_set()
    hub.publish(handle.run_id, "retry", {"reason": "x"})
    assert first.is_set()
    second = hub.watch(handle.run_id)
    assert second is not first and not second.is_set()
    await hub.finish_leaf(handle.run_id, LeafResult(origin="local"))
    assert second.is_set()
    assert hub.watch(handle.run_id) is None


async def test_a_leaf_has_no_stream_to_watch(hub):
    _, leaves = await produce_arena(hub)
    assert hub.watch(leaves[0].run_id) is None


# --- un run racine actif par genre (AD-14) -----------------------------------------------------


async def test_a_second_root_of_the_same_kind_is_busy_and_names_the_active_run(hub):
    first = await hub.create_run("chat", models=["m"])
    with pytest.raises(AppError) as busy:
        await hub.create_run("chat", models=["m"])
    assert busy.value.code == "run_busy" and busy.value.detail == {"run_id": first.run_id}
    other_kind = await hub.create_run("rag", models=["m"])  # un autre genre passe
    assert other_kind.run_id != first.run_id
    await hub.finish_leaf(first.run_id, LeafResult(origin="local"))
    assert (await hub.create_run("chat", models=["m"])).run_id  # libéré à la fin


async def test_concurrent_creations_leave_exactly_one_winner(hub):
    results = await asyncio.gather(
        *(hub.create_run("chat", models=["m"]) for _ in range(5)), return_exceptions=True
    )
    winners = [r for r in results if not isinstance(r, Exception)]
    losers = [r for r in results if isinstance(r, AppError)]
    assert len(winners) == 1 and len(losers) == 4
    assert {e.detail["run_id"] for e in losers} == {winners[0].run_id}


async def test_children_and_cancelled_runs_do_not_block(hub):
    parent, leaves = await produce_arena(hub)  # deux feuilles `generation` sous une arène
    assert len(leaves) == 2
    with pytest.raises(AppError):
        await hub.create_run("arena", models=["x"])
    await hub.cancel(parent.run_id)
    assert (await hub.create_run("arena", models=["x"])).run_id


async def test_a_failed_creation_releases_the_reservation(hub):
    with pytest.raises(AppError):  # conversation inconnue : l'écriture échoue
        await hub.create_run("chat", models=["m"], user_message="Q", conversation_id="absente")
    assert hub.active_root("chat") is None
    assert (await produce_chat(hub)).run_id


def test_run_busy_envelope_and_no_error_code_reuses_a_status_name():
    envelope = build_envelope("run_busy", run_id="abc")
    assert envelope["code"] == "run_busy" and envelope["detail"]["run_id"] == "abc"
    assert ERRORS["run_busy"].status == 409
    assert not set(ERRORS) & set(STATUSES)  # AD-5 : aucun code ne reprend un nom de statut


async def test_the_answer_text_gathers_the_tokens_of_an_active_conversation_run(hub):
    handle = await hub.create_run("rag", models=["a:1b"], user_message="Question ?")
    assert hub.answer_text(handle.run_id) == ""
    hub.publish_token(handle.run_id, "a:1b", "Le chat ")
    hub.publish_token(handle.run_id, "a:1b", "dort [1].")
    assert hub.answer_text(handle.run_id) == "Le chat dort [1]."  # les jetons en attente comptent
    hub.publish(handle.run_id, "retry", {"lane": "a:1b"})
    assert hub.answer_text(handle.run_id) == ""  # une génération relancée repart de zéro
    await hub.finish_run(handle.run_id, "ok")
    assert hub.answer_text(handle.run_id) is None  # plus actif
    assert hub.answer_text("inconnu") is None
