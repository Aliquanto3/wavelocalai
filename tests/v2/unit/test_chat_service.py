"""Service de génération : sémaphore « Ollama local » par appel, relance unique, délai (AD-8, AD-14).

Sans réseau : le `fake` scriptable et un faux Ollama sous un vrai client. Le hub est le vrai.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import stream_into_run
from wavelocalai.models.fake import FAKE_REF, FakeChatModel, Sleep
from wavelocalai.models.ollama import OllamaChatModel
from wavelocalai.models.port import ChatMessage, ChatRequest, ModelRef, TextDelta
from wavelocalai.runs.hub import RunHub
from wavelocalai.store.db import Store, db_path

from ..fake_ollama import FakeOllama, Plan, final, part

REQUEST = ChatRequest([ChatMessage("user", "Bonjour")])
CLOUD_REF = ModelRef("openai/gpt-x", "openai", "cloud", "chat")
CUT = ProviderError("generation_interrupted", "flux coupé")


class PerCallModel:
    """Un script par appel : le premier appel est coupé, le second réussit, etc."""

    def __init__(self, scripts, ref: ModelRef = FAKE_REF) -> None:
        self.ref = ref
        self._scripts = list(scripts)
        self.models: list[FakeChatModel] = []

    def stream(self, request):
        model = FakeChatModel(self._scripts[len(self.models)], self.ref)
        self.models.append(model)
        return model.stream(request)


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


async def _start(hub: RunHub, kind: str = "chat", message: str | None = "Bonjour"):
    return await hub.create_run(kind, models=["fake:1b"], user_message=message)


def _row(store, run_id):
    return store.read("SELECT * FROM runs WHERE id = ?", (run_id,))[0]


async def _events(hub, run_id):
    return await hub.events_after(run_id)


def _types(events):
    return [e["type"] for e in events]


def _assistant(store, run_id):
    rows = store.read(
        "SELECT content FROM messages WHERE run_id = ? AND role='assistant'", (run_id,)
    )
    return rows[0]["content"] if rows else None


# --- relance unique d'une génération coupée ------------------------------------------------------


async def test_an_interrupted_generation_is_retried_once_and_the_partial_text_is_dropped(
    hub, store
):
    handle = await _start(hub)
    model = PerCallModel([[TextDelta("Par"), CUT], [TextDelta("Bonjour")]])
    slot = LocalSlot()
    await stream_into_run(
        hub, handle.run_id, model, REQUEST, slot=slot, timeout_s=5, retry_interrupted=True
    )
    events = await _events(hub, handle.run_id)
    assert _types(events) == ["run_started", "token", "retry", "token", "metrics", "run_ended"]
    retry = events[2]["data"]
    assert retry["lane"] == "fake:1b" and retry["attempt"] == 2
    assert retry["code"] == "generation_interrupted" and retry["reason"].endswith(".")
    assert events[-1]["data"]["status"] == "ok"
    assert _row(store, handle.run_id)["status"] == "ok"
    assert _assistant(store, handle.run_id) == "Bonjour"  # pas « ParBonjour »
    assert slot.acquired == 2 and not slot.busy  # une prise par appel, rendue à chaque fois
    assert [m.closed for m in model.models] == [1, 1]  # les deux flux fermés


async def test_a_second_interruption_ends_in_error_with_generation_interrupted(hub, store):
    handle = await _start(hub)
    model = PerCallModel([[TextDelta("Par"), CUT], [TextDelta("Enco"), CUT]])
    await stream_into_run(hub, handle.run_id, model, REQUEST, retry_interrupted=True)
    events = await _events(hub, handle.run_id)
    assert _types(events).count("retry") == 1  # une seule relance
    ended = events[-1]["data"]
    assert ended["status"] == "error" and ended["error"]["code"] == "generation_interrupted"
    row = _row(store, handle.run_id)
    assert row["status"] == "error" and row["co2_method"] == "unmeasurable"
    assert row["co2_reason"]  # le co2 est toujours présent, avec sa raison


async def test_other_errors_are_not_retried(hub):
    handle = await _start(hub)
    model = PerCallModel([[ProviderError("ollama_down", "arrêté")], [TextDelta("jamais")]])
    await stream_into_run(hub, handle.run_id, model, REQUEST, retry_interrupted=True)
    events = await _events(hub, handle.run_id)
    assert "retry" not in _types(events) and len(model.models) == 1
    assert events[-1]["data"]["error"]["code"] == "ollama_down"


# --- délai de lane -------------------------------------------------------------------------------


async def test_a_lane_past_its_delay_ends_in_timeout_with_the_settings_delay(hub, store):
    handle = await _start(hub)
    model = FakeChatModel([TextDelta("Lent"), Sleep(5)])
    await stream_into_run(hub, handle.run_id, model, REQUEST, timeout_s=0.1, retry_interrupted=True)
    events = await _events(hub, handle.run_id)
    error = events[-1]["data"]["error"]
    assert error["code"] == "timeout" and error["detail"]["timeout_s"] == 0.1
    assert "retry" not in _types(events)  # un délai n'est pas relancé
    assert model.closed == 1  # le flux est fermé
    assert _assistant(store, handle.run_id) == "Lent"  # le partiel est gardé


async def test_the_local_delay_starts_at_slot_acquisition_not_at_the_call(hub):
    slot = LocalSlot()
    handle = await _start(hub)
    model = FakeChatModel([Sleep(0.05), TextDelta("Ok")])

    async def hold():
        async with slot:
            await asyncio.sleep(0.3)  # bien plus long que le délai de lane

    holder = asyncio.create_task(hold())
    await asyncio.sleep(0.01)
    await stream_into_run(hub, handle.run_id, model, REQUEST, slot=slot, timeout_s=0.15)
    await holder
    assert (await _events(hub, handle.run_id))[-1]["data"]["status"] == "ok"


# --- sémaphore « Ollama local » à 1, pris par appel -----------------------------------------------


async def test_two_local_calls_run_one_after_the_other_the_fake_then_a_fake_ollama(hub):
    slot = LocalSlot()
    first = await _start(hub, "chat")
    second = await _start(hub, "rag", "Question ?")
    fake = FakeChatModel([TextDelta("a"), Sleep(0.2), TextDelta("b")])
    server = FakeOllama(loaded=["qwen2.5:1.5b"], plans=[Plan([part("c"), final()])])
    ollama = OllamaChatModel(ModelRef("qwen2.5:1.5b", "ollama", "local", "chat"), server.client())

    t1 = asyncio.create_task(stream_into_run(hub, first.run_id, fake, REQUEST, slot=slot))
    await asyncio.sleep(0.05)
    t2 = asyncio.create_task(stream_into_run(hub, second.run_id, ollama, REQUEST, slot=slot))
    await asyncio.sleep(0.05)
    assert slot.busy and slot.waiting == 1  # le second attend l'acquisition
    assert server.opened == 0 and server.chat_requests == []  # rien n'est parti vers Ollama
    await asyncio.gather(t1, t2)
    assert server.opened == 1 and server.closed == 1
    assert slot.acquired == 2 and not slot.busy
    for run in (first, second):
        assert (await _events(hub, run.run_id))[-1]["data"]["status"] == "ok"


async def test_a_cloud_call_does_not_take_the_local_slot(hub):
    slot = LocalSlot()
    handle = await _start(hub)
    cloud = FakeChatModel([TextDelta("nuage")], CLOUD_REF)

    async def hold():
        async with slot:
            await asyncio.sleep(0.3)

    holder = asyncio.create_task(hold())
    await asyncio.sleep(0.01)
    await asyncio.wait_for(stream_into_run(hub, handle.run_id, cloud, REQUEST, slot=slot), 0.2)
    assert slot.acquired == 1  # seulement celle du détenteur
    holder.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder


async def test_cancelling_a_run_closes_the_stream_and_frees_the_slot(hub, store):
    slot = LocalSlot()
    handle = await _start(hub)
    server = FakeOllama(loaded=["qwen2.5:1.5b"], plans=[Plan([part("Déb")], end="hang")])
    ollama = OllamaChatModel(ModelRef("qwen2.5:1.5b", "ollama", "local", "chat"), server.client())
    task = asyncio.create_task(stream_into_run(hub, handle.run_id, ollama, REQUEST, slot=slot))
    hub.attach_task(handle.run_id, task)
    for _ in range(100):
        if server.opened:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.1)  # le premier fragment est arrivé
    assert await hub.cancel(handle.run_id)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert server.closed == 1 and not slot.busy  # flux HTTP fermé, place rendue
    assert _row(store, handle.run_id)["status"] == "cancelled"
    assert _assistant(store, handle.run_id) == "Déb"  # le partiel est gardé
