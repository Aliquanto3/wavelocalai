"""Port `ChatModel`, adaptateur `fake` et service de flux (AD-8, AD-18) : sans Ollama ni réseau."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.inference.streaming import stream_into_run
from wavelocalai.models.fake import FakeChatModel, Sleep, fake_models
from wavelocalai.models.port import (
    ChatMessage,
    ChatModel,
    ChatRequest,
    ChatResult,
    Done,
    LoadState,
    TextDelta,
)
from wavelocalai.runs.hub import RunHub
from wavelocalai.store.db import Store, db_path

from ..conftest import make_settings

REQUEST = ChatRequest([ChatMessage("user", "Bonjour")])


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


async def _collect(model, request=REQUEST):
    return [chunk async for chunk in model.stream(request)]


def _row(store, run_id):
    return store.read("SELECT * FROM runs WHERE id = ?", (run_id,))[0]


def test_the_fake_is_registered_only_when_testing(tmp_path):
    assert fake_models(make_settings(tmp_path)) == {}
    registered = fake_models(make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}))
    assert list(registered) == ["fake:1b"]
    assert isinstance(registered["fake:1b"], ChatModel)  # respecte le port


async def test_the_fake_plays_its_script_then_ends_with_a_single_done():
    model = FakeChatModel([LoadState("loading"), TextDelta("a b"), TextDelta("c", "thought")])
    chunks = await _collect(model)
    assert [type(c) for c in chunks] == [LoadState, TextDelta, TextDelta, Done]
    assert chunks[-1].result.output_tokens == 3 and chunks[-1].result.tps_source == "wallclock"
    explicit = FakeChatModel([TextDelta("x"), Done(ChatResult(output_tokens=9))])
    assert sum(isinstance(c, Done) for c in await _collect(explicit)) == 1
    assert (model.opened, model.closed) == (1, 1) and model.requests == [REQUEST]


async def test_the_fake_closes_its_stream_when_the_consumer_stops_or_fails():
    model = FakeChatModel([TextDelta("a"), ProviderError("ollama_down"), TextDelta("jamais")])
    with pytest.raises(ProviderError):
        await _collect(model)
    assert model.closed == 1
    slow = FakeChatModel([TextDelta("a"), Sleep(10)])
    task = asyncio.create_task(_collect(slow))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert slow.closed == 1  # `finally` de l'adaptateur


async def test_a_run_streams_text_deltas_then_metrics_then_ends_ok(hub, store):
    model = FakeChatModel([LoadState("loading", 0.1), LoadState("loaded", 0.1), TextDelta("Sa"),
                           TextDelta("lut")])  # fmt: skip
    handle = await hub.create_run("chat", models=[model.ref.tag], user_message="Bonjour")
    await stream_into_run(hub, handle.run_id, model, REQUEST)
    events = await hub.events_after(handle.run_id)
    assert [e["type"] for e in events] == [
        "run_started", "model_loading", "model_loaded", "token", "metrics", "run_ended",
    ]  # fmt: skip
    token = events[3]["data"]
    assert token == {"lane": "fake:1b", "text": "Salut", "channel": "answer"}
    metrics = events[4]["data"]
    assert metrics["lane"] == "fake:1b" and metrics["origin"] == "local"
    assert metrics["co2"]["method"] == "unmeasurable" and metrics["co2"]["reason"]
    assert events[-1]["data"] == {"status": "ok", "error": None}
    row = _row(store, handle.run_id)
    assert row["status"] == "ok" and row["output_tokens"] == 2 and row["tps"] == 100.0
    assert model.closed == 1


async def test_a_provider_error_ends_the_run_with_the_error_envelope(hub, store):
    secret = "sk-proj-AbCdEf0123456789XyZ"
    model = FakeChatModel(
        [TextDelta("débu"), ProviderError("ollama_down", f"refusé avec la clé {secret}")]
    )
    handle = await hub.create_run("chat", models=["fake:1b"], user_message="Q")
    await stream_into_run(hub, handle.run_id, model, REQUEST)
    last = (await hub.events_after(handle.run_id))[-1]
    error = last["data"]["error"]
    assert last["data"]["status"] == "error"
    assert list(error) == ["code", "message", "action", "detail"] and error["code"] == "ollama_down"
    assert secret not in str(error) and "***" in error["detail"]["technical"]
    assert _row(store, handle.run_id)["status"] == "error"
    # le texte déjà reçu reste dans la conversation (partiel)
    assert store.read("SELECT content FROM messages WHERE role = 'assistant'")[0][0] == "débu"
    assert model.closed == 1


async def test_an_unexpected_exception_becomes_an_internal_error(hub):
    model = FakeChatModel([RuntimeError("boum")])
    handle = await hub.create_run("chat", models=["fake:1b"])
    await stream_into_run(hub, handle.run_id, model, REQUEST)
    error = (await hub.events_after(handle.run_id))[-1]["data"]["error"]
    assert error["code"] == "internal" and "boum" in error["detail"]["technical"]


async def test_cancelling_the_run_cancels_the_task_and_closes_the_adapter_stream(hub, store):
    model = FakeChatModel([TextDelta("par"), Sleep(30), TextDelta("jamais")])
    handle = await hub.create_run("chat", models=["fake:1b"], user_message="Q")
    task = asyncio.create_task(stream_into_run(hub, handle.run_id, model, REQUEST))
    hub.attach_task(handle.run_id, task)
    await asyncio.sleep(0.1)
    started = asyncio.get_running_loop().time()
    assert await hub.cancel(handle.run_id)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert asyncio.get_running_loop().time() - started < 1.0
    assert model.closed == 1
    last = (await hub.events_after(handle.run_id))[-1]
    assert last["type"] == "run_ended" and last["data"]["status"] == "cancelled"
    assert _row(store, handle.run_id)["status"] == "cancelled"
    assert store.read("SELECT content FROM messages WHERE role = 'assistant'")[0][0] == "par"


async def test_an_error_with_an_undeclared_detail_key_still_ends_the_run(hub):
    # Une `AppError` dont `detail` porte une clé non déclarée ne doit pas laisser le run actif
    # (il garderait sa place de `kind` jusqu'au redémarrage).
    model = FakeChatModel([ProviderError("internal", "boum", cle_inconnue=1)])
    handle = await hub.create_run("chat", models=["fake:1b"])
    await stream_into_run(hub, handle.run_id, model, REQUEST)
    error = (await hub.events_after(handle.run_id))[-1]["data"]["error"]
    assert error["code"] == "internal" and "boum" in error["detail"]["technical"]
    assert hub.active_root("chat") is None
