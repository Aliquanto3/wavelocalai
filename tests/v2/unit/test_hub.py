"""Hub des runs : seq, lots, transaction finale, conversation, annulation, redémarrage (AD-5, AD-7).

Les producteurs de `tests/v2/producers.py` jouent le rôle d'un service : aucun adaptateur de modèle.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from wavelocalai.errors import AppError
from wavelocalai.runs import repo
from wavelocalai.runs.hub import RunHub, check_params, strip_source_text
from wavelocalai.runs.models import AssistantMessage, Co2, LeafResult
from wavelocalai.store.db import Store, db_path

from ..producers import LOCAL_CO2, produce_arena, produce_chat


@pytest.fixture
async def store(tmp_path: Path):
    opened = Store.open(db_path(tmp_path / "data"))
    yield opened
    opened.close()


@pytest.fixture
async def hub(store: Store):
    started = RunHub(store, batch_interval_s=3600)  # les lots partent à la main (`flush`)
    await started.start()
    yield started
    await started.stop()


def _run(store, run_id):
    return dict(store.read("SELECT * FROM runs WHERE id = ?", (run_id,))[0])


def _events(store, run_id):
    return [tuple(r) for r in store.read(
        "SELECT seq, type, data FROM run_events WHERE run_id = ? ORDER BY seq", (run_id,)
    )]  # fmt: skip


def _messages(store, conversation_id):
    return [dict(r) for r in store.read(
        "SELECT role, content, reasoning, tool_calls, run_id FROM messages"
        " WHERE conversation_id = ? ORDER BY rowid", (conversation_id,)
    )]  # fmt: skip


# --- numérotation et lots ----------------------------------------------------------------------


async def test_hub_alone_numbers_events_contiguously_from_run_started_to_run_ended(hub, store):
    handle = await produce_chat(hub, tokens=["a", "b", "c"])
    events = await hub.events_after(handle.run_id)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "run_started" and events[-1]["type"] == "run_ended"
    assert [e["type"] for e in events].count("run_ended") == 1
    assert events[0]["data"] == {
        "kind": "chat", "models": ["fake:1b"], "params": {"temperature": 0.2, "allow_cloud": False}
    }  # fmt: skip
    assert events[-1]["data"] == {"status": "ok", "error": None}
    assert all(e["run_id"] == handle.run_id and e["ts"].endswith("Z") for e in events)
    # Une fois clos, le rejeu vient de la base et rend les mêmes enveloppes.
    assert await hub.events_after(handle.run_id) == events
    assert [e["seq"] for e in await hub.events_after(handle.run_id, after=3)] == [4, 5, 6]


async def test_services_cannot_publish_reserved_events_or_on_a_child(hub):
    parent, (leaf, _) = await produce_arena(hub)
    for reserved in ("run_started", "run_ended"):
        with pytest.raises(ValueError, match="hub seul"):
            hub.publish(parent.run_id, reserved)
    with pytest.raises(ValueError, match="parent publie"):
        hub.publish(leaf.run_id, "token", {"lane": "a:1b", "text": "x"})
    with pytest.raises(KeyError):
        hub.publish("inconnu", "token")


async def test_events_stay_in_memory_then_are_written_in_batches(store):
    hub = RunHub(store, batch_interval_s=0.05)
    await hub.start()
    try:
        handle = await produce_chat(hub, tokens=["a", "b", "c"], finish=False)
        assert len(_events(store, handle.run_id)) == 1  # tout le reste est encore en mémoire
        for _ in range(100):  # le lot part de lui-même, en moins d'une seconde
            if len(_events(store, handle.run_id)) == 4:
                break
            await asyncio.sleep(0.05)
        assert [e[1] for e in _events(store, handle.run_id)] == [
            "run_started",
            "token",
            "token",
            "token",
        ]
        assert _run(store, handle.run_id)["status"] == "running"
    finally:
        await hub.stop()


async def test_only_unflushed_events_are_written_by_each_batch(hub, store):
    handle = await produce_chat(hub, tokens=["a"], finish=False)
    assert len(_events(store, handle.run_id)) == 1  # run_started est écrit à la création
    hub.publish(handle.run_id, "token", {"lane": "m", "text": "b"})
    await hub.flush()
    await hub.flush()  # rien de neuf : aucun doublon
    assert [e[0] for e in _events(store, handle.run_id)] == [1, 2, 3]


async def test_last_batch_status_and_assistant_message_are_one_transaction(hub, store, monkeypatch):
    handle = await produce_chat(hub, tokens=["a", "b"], finish=False)
    original = repo.insert_message

    def failing(conn, conversation_id, run_id, role, created_at, message):
        if role == "assistant":
            raise RuntimeError("disque plein")
        original(conn, conversation_id, run_id, role, created_at, message)

    monkeypatch.setattr(repo, "insert_message", failing)
    with pytest.raises(RuntimeError, match="disque plein"):
        await hub.finish_leaf(handle.run_id, LeafResult(), LOCAL_CO2)
    # Rien de la clôture n'est resté : ni run_ended, ni statut, ni dernier lot, ni métriques.
    assert [e[1] for e in _events(store, handle.run_id)] == ["run_started"]
    row = _run(store, handle.run_id)
    assert row["status"] == "running" and row["ended_at"] is None and row["co2_method"] is None
    assert [m["role"] for m in _messages(store, handle.conversation_id)] == ["user"]


async def test_late_publish_and_finish_are_dropped_not_raised(hub):
    handle = await produce_chat(hub)
    assert hub.publish(handle.run_id, "token", {"text": "tard"}) is None
    assert await hub.finish_leaf(handle.run_id, LeafResult()) is False
    assert await hub.cancel(handle.run_id) is False


# --- conversation et messages ------------------------------------------------------------------


async def test_run_creates_the_conversation_and_the_user_message(hub, store):
    handle = await produce_chat(hub, "Quelle heure est-il ?", finish=False)
    conversation = store.read("SELECT * FROM conversations")[0]
    assert conversation["id"] == handle.conversation_id and conversation["kind"] == "chat"
    assert _messages(store, handle.conversation_id) == [
        {"role": "user", "content": "Quelle heure est-il ?", "reasoning": None,
         "tool_calls": None, "run_id": handle.run_id}
    ]  # fmt: skip


async def test_assistant_message_is_written_with_the_final_status(hub, store):
    handle = await hub.create_run("chat", models=["m"], user_message="Q")
    hub.publish(
        handle.run_id, "token", {"lane": "m", "text": "ignoré, le service a le dernier mot"}
    )
    message = AssistantMessage("Réponse", "Je réfléchis", [{"name": "calc", "arguments": {"x": 1}}])
    await hub.finish_leaf(handle.run_id, LeafResult(assistant=message), LOCAL_CO2)
    assistant = _messages(store, handle.conversation_id)[1]
    assert assistant["role"] == "assistant" and assistant["content"] == "Réponse"
    assert assistant["reasoning"] == "Je réfléchis"
    assert json.loads(assistant["tool_calls"]) == [{"name": "calc", "arguments": {"x": 1}}]


async def test_assistant_message_defaults_to_the_streamed_text(hub, store):
    handle = await hub.create_run("chat", models=["m"], user_message="Q")
    hub.publish(handle.run_id, "token", {"lane": "m", "text": "pen", "channel": "thought"})
    hub.publish(handle.run_id, "token", {"lane": "m", "text": "Bon", "channel": "answer"})
    hub.publish(handle.run_id, "token", {"lane": "m", "text": "jour", "channel": "answer"})
    await hub.finish_leaf(handle.run_id, LeafResult(), LOCAL_CO2)
    assistant = _messages(store, handle.conversation_id)[1]
    assert (assistant["content"], assistant["reasoning"]) == ("Bonjour", "pen")


async def test_second_run_continues_the_conversation(hub, store):
    first = await produce_chat(hub, "Un")
    second = await produce_chat(hub, "Deux", conversation_id=first.conversation_id)
    assert second.conversation_id == first.conversation_id
    assert store.read("SELECT count(*) FROM conversations")[0][0] == 1
    roles = [(m["role"], m["run_id"]) for m in _messages(store, first.conversation_id)]
    assert roles == [
        ("user", first.run_id), ("assistant", first.run_id),
        ("user", second.run_id), ("assistant", second.run_id),
    ]  # fmt: skip


async def test_conversation_kind_is_fixed_and_must_exist(hub):
    chat = await produce_chat(hub)
    with pytest.raises(AppError) as wrong_kind:
        await hub.create_run("rag", user_message="Q", conversation_id=chat.conversation_id)
    assert wrong_kind.value.code == "invalid_request"
    with pytest.raises(AppError) as absent:
        await hub.create_run("chat", user_message="Q", conversation_id="absente")
    assert absent.value.code == "not_found"
    with pytest.raises(ValueError, match="n'ouvre pas de conversation"):
        await hub.create_run("arena", user_message="Q")


async def test_failed_creation_leaves_nothing_behind(hub, store):
    with pytest.raises(AppError):
        await hub.create_run("chat", user_message="Q", conversation_id="absente")
    assert store.read("SELECT count(*) FROM runs")[0][0] == 0
    assert store.read("SELECT count(*) FROM messages")[0][0] == 0


# --- params sans texte saisi -------------------------------------------------------------------


async def test_run_params_never_hold_typed_text(hub, store):
    question = "Quel est le secret de la tarte aux pommes de ma grand-mère ?"
    handle = await produce_chat(hub, question)
    row = _run(store, handle.run_id)
    assert json.loads(row["params"]) == {"temperature": 0.2, "allow_cloud": False}
    assert question not in row["params"]
    for refused in (
        {"prompt": "x"},
        {"nested": {"Message": "x"}},
        {"note": question},
        {"long": "x" * 300},
        {"list": [{"question": "x"}]},
    ):
        with pytest.raises(ValueError):
            await hub.create_run("chat", params=refused, user_message=question)
    check_params({"temperature": 0.2, "models": ["a:1b"], "strategy": "hyde"})


# --- sources ------------------------------------------------------------------------------------


def test_strip_source_text_handles_objects_and_lists():
    source = {"n": 1, "doc_id": "d", "text": "contenu du document", "rank": 1}
    assert strip_source_text(source) == {"n": 1, "doc_id": "d", "rank": 1}
    assert strip_source_text({"sources": [source]}) == {
        "sources": [{"n": 1, "doc_id": "d", "rank": 1}]
    }
    assert strip_source_text([source]) == [{"n": 1, "doc_id": "d", "rank": 1}]


async def test_sources_are_persisted_without_text_but_live_with_it(hub, store):
    handle = await hub.create_run("rag", models=["m"], user_message="Q")
    hub.publish(handle.run_id, "sources", {"n": 1, "chunk_id": 7, "text": "EXTRAIT SECRET"})
    live = await hub.events_after(handle.run_id)
    assert live[1]["data"]["text"] == "EXTRAIT SECRET"  # en mémoire : complet
    await hub.finish_leaf(handle.run_id, LeafResult(), LOCAL_CO2)
    stored = await hub.events_after(handle.run_id)
    assert stored[1]["data"] == {"n": 1, "chunk_id": 7}
    assert b"EXTRAIT SECRET" not in db_path(store.path.parent).read_bytes()


# --- feuille, métriques et CO2 -----------------------------------------------------------------


async def test_finish_leaf_writes_metrics_and_co2_columns(hub, store):
    handle = await produce_chat(hub)
    row = _run(store, handle.run_id)
    assert row["status"] == "ok" and row["ended_at"].endswith("Z")
    assert (row["input_tokens"], row["output_tokens"], row["tps"]) == (4, 2, 42.0)
    assert (row["tps_source"], row["origin"], row["energy_wh"]) == ("ollama_eval", "local", 0.001)
    assert (row["co2_mg"], row["co2_method"], row["co2_estimated"]) == (1.5, "codecarbon", 0)
    assert (row["co2_allocation"], row["co2_reason"], row["model"]) == ("direct", None, "fake:1b")
    assert row["app_session"] == hub.app_session_id


async def test_unmeasurable_co2_keeps_its_reason_and_range_is_stored(hub, store):
    unknown = Co2(None, "unmeasurable", reason="modèle absent de la table")
    estimate = Co2(2.0, "ecologits", estimated=True, range_mg={"low": 1.0, "high": 3.5})
    a = await hub.create_run("chat", models=["m"])
    b = await hub.create_run("rag", models=["m"])
    await hub.finish_leaf(a.run_id, LeafResult(origin="cloud"), unknown)
    await hub.finish_leaf(b.run_id, LeafResult(origin="cloud"), estimate)
    row_a, row_b = _run(store, a.run_id), _run(store, b.run_id)
    assert (row_a["co2_mg"], row_a["co2_method"], row_a["co2_reason"]) == (
        None, "unmeasurable", "modèle absent de la table",
    )  # fmt: skip
    assert (row_b["co2_range_low_mg"], row_b["co2_range_high_mg"], row_b["co2_estimated"]) == (
        1.0,
        3.5,
        1,
    )


def test_co2_shape_follows_ad10():
    assert LOCAL_CO2.as_dict() == {
        "mg": 1.5, "method": "codecarbon", "estimated": False,
        "range_mg": None, "allocation": "direct", "reason": None,
    }  # fmt: skip
    for bad in (
        {"mg": None, "method": "unmeasurable"},  # reason requis
        {"mg": 1.0, "method": "unmeasurable", "reason": "x"},  # inconnu : pas de valeur
        {"mg": 1.0, "method": "local"},
        {"mg": 1.0, "method": "codecarbon", "allocation": "moitie"},
        {"mg": 1.0, "method": "codecarbon", "range_mg": {"min": 1}},
    ):
        with pytest.raises(ValueError):
            Co2(**bad)


# --- composites et annulation ------------------------------------------------------------------


async def test_cancelling_the_parent_cancels_both_children_and_the_parent(hub, store):
    parent, leaves = await produce_arena(hub)

    async def lane():
        try:
            await asyncio.sleep(60)
        finally:
            stopped.append(True)

    stopped: list[bool] = []
    tasks = [asyncio.create_task(lane()) for _ in leaves]
    for handle, task in zip(leaves, tasks, strict=True):
        hub.attach_task(handle.run_id, task)
    await asyncio.sleep(0)

    assert await hub.cancel(parent.run_id) is True
    await asyncio.gather(*tasks, return_exceptions=True)
    assert stopped == [True, True] and all(t.cancelled() for t in tasks)

    for run_id in (parent.run_id, *(h.run_id for h in leaves)):
        row = _run(store, run_id)
        assert row["status"] == "cancelled" and row["ended_at"] is not None
        assert row["co2_method"] is None and row["tps"] is None and row["energy_wh"] is None
    events = _events(store, parent.run_id)
    assert events[-1][1] == "run_ended" and json.loads(events[-1][2])["status"] == "cancelled"
    assert events[-1][0] == len(events) and hub.active_runs() == []


async def test_metrics_live_on_leaves_only(hub, store):
    parent, (done, running) = await produce_arena(hub)
    await hub.finish_leaf(done.run_id, LeafResult(origin="local", tps=30.0), LOCAL_CO2)
    with pytest.raises(ValueError, match="composite"):
        await hub.finish_leaf(parent.run_id, LeafResult(), LOCAL_CO2)
    with pytest.raises(
        ValueError, match="feuille"
    ):  # on ne termine pas une feuille comme une racine
        await hub.finish_run(running.run_id)
    await hub.cancel(parent.run_id)
    kept, cancelled, root = (_run(store, h.run_id) for h in (done, running, parent))
    assert (kept["status"], kept["tps"], kept["co2_mg"]) == ("ok", 30.0, 1.5)  # déjà terminée
    assert cancelled["status"] == "cancelled" and cancelled["co2_mg"] is None
    assert root["status"] == "cancelled" and root["co2_method"] is None and root["tps"] is None


async def test_a_declared_leaf_closed_without_co2_keeps_an_unmeasurable_co2(hub, store):
    """AD-10 : une feuille annulée (enfant ou racine sans enfant) garde un `co2` avec sa raison ;
    une feuille déjà terminée garde le sien, le parent composite n'en a toujours pas."""
    gone = Co2(mg=None, method="unmeasurable", reason="annulée")
    parent, (done, running) = await produce_arena(hub)
    for handle in (done, running):
        hub.declare_leaf(handle.run_id, gone)
    await hub.finish_leaf(done.run_id, LeafResult(origin="local", tps=30.0), LOCAL_CO2)
    await hub.cancel(parent.run_id)
    kept, cancelled, root = (_run(store, h.run_id) for h in (done, running, parent))
    assert (kept["co2_mg"], kept["co2_method"]) == (1.5, LOCAL_CO2.method)
    assert (cancelled["co2_method"], cancelled["co2_reason"]) == ("unmeasurable", "annulée")
    assert root["co2_method"] is None

    parent, (alone, _) = await produce_arena(hub)
    hub.declare_leaf(alone.run_id, gone)
    await hub.cancel(alone.run_id)  # une feuille annulée seule
    assert _run(store, alone.run_id)["co2_reason"] == "annulée"
    await hub.cancel(parent.run_id)

    chat = await hub.create_run("chat", models=["m"], user_message="Bonjour")
    hub.declare_leaf(chat.run_id, gone)
    await hub.cancel(chat.run_id)  # racine sans enfant : un chat annulé
    row = _run(store, chat.run_id)
    assert (row["status"], row["co2_method"], row["co2_mg"]) == ("cancelled", "unmeasurable", None)


async def test_parent_finishes_ok_without_metrics_and_children_are_listed(hub, store):
    parent, leaves = await produce_arena(hub)
    for handle in leaves:
        await hub.finish_leaf(handle.run_id, LeafResult(origin="local", tps=10.0), LOCAL_CO2)
    assert await hub.finish_run(parent.run_id) is True
    root = _run(store, parent.run_id)
    assert root["status"] == "ok" and root["tps"] is None and root["co2_method"] is None
    children = store.read(
        "SELECT status, parent_run_id FROM runs WHERE parent_run_id = ?", (parent.run_id,)
    )
    assert [(c["status"], c["parent_run_id"]) for c in children] == [("ok", parent.run_id)] * 2


async def test_children_must_be_leaf_kinds_of_an_active_root(hub):
    parent, (leaf, _) = await produce_arena(hub)
    with pytest.raises(ValueError, match="feuille"):
        await hub.create_run("chat", parent_run_id=parent.run_id)
    with pytest.raises(ValueError, match="racine actif"):
        await hub.create_run("generation", parent_run_id=leaf.run_id)
    with pytest.raises(ValueError, match="racine"):
        await hub.create_run("generation")
    await hub.cancel(parent.run_id)
    with pytest.raises(ValueError, match="racine actif"):
        await hub.create_run("generation", parent_run_id=parent.run_id)


async def test_cancel_keeps_the_partial_assistant_message(hub, store):
    handle = await produce_chat(hub, tokens=["Début", " de réponse"], finish=False)
    assert await hub.cancel(handle.run_id) is True
    assert _run(store, handle.run_id)["status"] == "cancelled"
    assistant = _messages(store, handle.conversation_id)[1]
    assert (assistant["role"], assistant["content"]) == ("assistant", "Début de réponse")
    assert [e[1] for e in _events(store, handle.run_id)][-1] == "run_ended"


async def test_cancelling_a_single_leaf_leaves_the_parent_running(hub, store):
    parent, (first, second) = await produce_arena(hub)
    assert await hub.cancel(first.run_id) is True
    assert _run(store, first.run_id)["status"] == "cancelled"
    assert _run(store, second.run_id)["status"] == "running"
    assert hub.active_runs() == [{"run_id": parent.run_id, "kind": "arena", "status": "running"}]


async def test_error_status_carries_the_error_envelope(hub, store):
    handle = await hub.create_run("chat", models=["m"], user_message="Q")
    error = {"code": "ollama_down", "message": "m", "action": "a", "detail": {"technical": None}}
    await hub.finish_leaf(handle.run_id, LeafResult(status="error", error=error))
    row = _run(store, handle.run_id)
    assert row["status"] == "error" and json.loads(row["error"]) == error
    last = (await hub.events_after(handle.run_id))[-1]
    assert last["data"] == {"status": "error", "error": error}
    with pytest.raises(ValueError):  # `interrupted` est réservé au démarrage du serveur
        LeafResult(status="interrupted")


# --- cycle de vie du serveur -------------------------------------------------------------------


async def test_start_interrupts_running_runs_and_opens_a_new_session(store):
    before = RunHub(store, batch_interval_s=3600)
    await before.start()
    done = await produce_chat(before, "Autre")  # terminé d'abord : un seul chat actif à la fois
    chat = await produce_chat(before, "Q", tokens=["par", "tiel"], finish=False)
    await before.flush()  # les deux jetons sont en base ; le serveur « s'arrête » là
    parent, leaves = await produce_arena(before)
    before_session = before.app_session_id

    after = RunHub(store, batch_interval_s=3600)
    interrupted = await after.start()
    try:
        assert set(interrupted) == {chat.run_id, parent.run_id, *(h.run_id for h in leaves)}
        for run_id in interrupted:
            assert _run(store, run_id)["status"] == "interrupted"
        assert _run(store, done.run_id)["status"] == "ok"  # un run terminé ne bouge pas

        events = _events(store, chat.run_id)
        assert [e[0] for e in events] == [1, 2, 3, 4]  # contigu
        assert events[-1][1] == "run_ended"
        assert json.loads(events[-1][2]) == {"status": "interrupted", "error": None}
        assert [e[1] for e in events].count("run_ended") == 1
        assert _events(store, leaves[0].run_id) == []  # les feuilles ne portent pas de flux
        partial = _messages(store, chat.conversation_id)[1]
        assert (partial["role"], partial["content"]) == ("assistant", "partiel")

        sessions = store.read("SELECT id, reason FROM app_sessions ORDER BY rowid")
        assert [s["reason"] for s in sessions] == ["startup", "startup"]
        assert after.app_session_id == sessions[1]["id"] != before_session
        assert after.active_runs() == []
    finally:
        await after.stop()


async def test_start_is_idempotent_on_a_clean_database(store):
    first = RunHub(store, batch_interval_s=3600)
    assert await first.start() == []
    await first.stop()
    second = RunHub(store, batch_interval_s=3600)
    assert await second.start() == []
    await second.stop()


async def test_clean_stop_cancels_active_runs(store):
    hub = RunHub(store, batch_interval_s=3600)
    await hub.start()
    chat = await produce_chat(hub, tokens=["abc"], finish=False)
    parent, leaves = await produce_arena(hub)
    await hub.stop()
    for handle in (chat, parent, *leaves):
        assert _run(store, handle.run_id)["status"] == "cancelled"
    last = _events(store, chat.run_id)[-1]
    assert last[1] == "run_ended" and json.loads(last[2])["status"] == "cancelled"
    assert _messages(store, chat.conversation_id)[1]["content"] == "abc"


async def test_new_app_session_groups_later_runs(hub, store):
    first = await produce_chat(hub)
    opened = hub.app_session_id
    reset = await hub.new_app_session()
    second = await produce_chat(hub)
    assert reset == hub.app_session_id != opened
    assert _run(store, first.run_id)["app_session"] == opened
    assert _run(store, second.run_id)["app_session"] == reset
    assert [s["reason"] for s in store.read("SELECT reason FROM app_sessions ORDER BY rowid")] == [
        "startup", "reset",
    ]  # fmt: skip


async def test_hub_must_be_started_before_creating_a_run(store):
    with pytest.raises(RuntimeError, match="pas démarré"):
        await RunHub(store).create_run("chat")


# --- courses entre écrivain et annulation (revue de la story 1.3) ------------------------------


def _gate(monkeypatch, name, when=lambda *a, **k: True):
    """Bloque la première écriture `repo.<name>` qui vérifie `when`, dans le fil de l'écrivain,
    jusqu'à `release.set()`."""
    real = getattr(repo, name)
    entered, release = threading.Event(), threading.Event()

    def gated(*args, **kwargs):
        if not entered.is_set() and when(*args, **kwargs):
            entered.set()
            release.wait(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(repo, name, gated)
    return entered, release


async def test_stop_during_a_batch_still_closes_the_run_once(store, monkeypatch):
    hub = RunHub(store, batch_interval_s=0.01)
    await hub.start()
    handle = await produce_chat(hub, tokens=["a", "b"], finish=False)
    entered, release = _gate(monkeypatch, "insert_events")
    assert await asyncio.to_thread(entered.wait, 5)  # le flusher écrit son lot
    stopping = asyncio.create_task(hub.stop())  # annule le flusher pendant l'écriture
    await asyncio.sleep(0.05)
    release.set()
    await stopping
    row = _run(store, handle.run_id)
    assert row["status"] == "cancelled"
    seqs = [seq for seq, _, _ in _events(store, handle.run_id)]
    assert seqs == list(range(1, len(seqs) + 1))
    assert _events(store, handle.run_id)[-1][1] == "run_ended"
    assert _messages(store, handle.conversation_id)[-1]["content"] == "ab"


async def test_parent_cancelled_while_a_leaf_is_being_created_cancels_the_leaf(
    hub, store, monkeypatch
):
    parent = await hub.create_run("arena", models=["a:1b"], params={})
    entered, release = _gate(
        monkeypatch, "insert_run", when=lambda *a, **k: k.get("kind") == "generation"
    )
    creating = asyncio.create_task(
        hub.create_run("generation", models=["a:1b"], parent_run_id=parent.run_id)
    )
    assert await asyncio.to_thread(entered.wait, 5)
    cancelling = asyncio.create_task(hub.cancel(parent.run_id))
    await asyncio.sleep(0.05)
    release.set()
    leaf = await creating
    assert await cancelling is True
    assert _run(store, leaf.run_id)["status"] == "cancelled"
    assert _run(store, parent.run_id)["status"] == "cancelled"
    # Le service attache sa tâche après coup : elle est annulée, sans KeyError.
    task = asyncio.create_task(asyncio.sleep(10))
    hub.attach_task(leaf.run_id, task)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await hub.finish_leaf(leaf.run_id, LeafResult(status="ok")) is False
