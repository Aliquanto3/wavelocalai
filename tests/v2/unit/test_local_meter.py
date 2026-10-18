"""Mesure CO2 d'une feuille locale (story 2.3) : CodeCarbon sous le sémaphore, un seul à la fois,
sans réseau, et une panne de mesure n'arrête jamais un run (AD-10, AD-11, AD-14).

Les tests utilisent le double `carbon_stub` ; un seul lance le vrai `OfflineEmissionsTracker`, avec
tout accès au réseau bloqué.
"""

from __future__ import annotations

import asyncio
import math
import socket
from pathlib import Path

import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.greenops.local_meter import Footprint, LocalMeter, combine
from wavelocalai.greenops.local_meter import load_tracker_class as real_loader  # avant le double
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import stream_into_run
from wavelocalai.models.fake import FAKE_REF, FakeChatModel, Sleep
from wavelocalai.models.port import ChatMessage, ChatRequest, ModelRef, TextDelta
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.system_bus import SystemFeed
from wavelocalai.store.db import Store, db_path

from ..carbon_stub import Probe

REQUEST = ChatRequest([ChatMessage("user", "Bonjour")])
CLOUD_REF = ModelRef("openai/gpt-x", "openai", "cloud", "chat")


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


@pytest.fixture
def probe() -> Probe:
    return Probe()


@pytest.fixture
def meter(probe: Probe) -> LocalMeter:
    return LocalMeter("FRA", 1.2, loader=probe.loader())


async def _start(hub: RunHub, kind: str = "chat"):
    return await hub.create_run(kind, models=["fake:1b"], user_message="Bonjour")


def _row(store, run_id):
    return store.read("SELECT * FROM runs WHERE id = ?", (run_id,))[0]


async def _events(hub, run_id):
    return await hub.events_after(run_id)


def _metrics(events):
    return next(e["data"] for e in events if e["type"] == "metrics")


async def _play(hub, handle, script, meter, **kwargs):
    kwargs.setdefault("slot", LocalSlot())
    await stream_into_run(hub, handle.run_id, FakeChatModel(script), REQUEST, meter=meter, **kwargs)


# --- la feuille locale porte son CO2 mesuré -------------------------------------------------------


async def test_a_local_leaf_ends_with_its_measured_co2_and_energy(hub, store, meter):
    handle = await _start(hub)
    await _play(hub, handle, [TextDelta("Bonjour")], meter)
    events = await _events(hub, handle.run_id)
    assert events[-1]["data"]["status"] == "ok"
    assert _metrics(events)["co2"] == {
        "mg": pytest.approx(1.8),
        "method": "codecarbon",
        "estimated": False,
        "range_mg": None,
        "allocation": "direct",
        "reason": None,
    }
    assert _metrics(events)["energy_wh"] == pytest.approx(0.001)
    row = _row(store, handle.run_id)
    assert row["co2_method"] == "codecarbon" and row["co2_mg"] == pytest.approx(1.8)
    assert row["energy_wh"] == pytest.approx(0.001) and row["co2_reason"] is None
    assert row["co2_allocation"] == "direct" and not row["co2_estimated"]


async def test_the_tracker_gets_the_country_and_pue_and_writes_and_sends_nothing(hub, meter, probe):
    await _play(hub, await _start(hub), [TextDelta("a")], meter)
    (kwargs,) = probe.kwargs
    assert kwargs["country_iso_code"] == "FRA" and kwargs["pue"] == 1.2
    assert kwargs["save_to_file"] is False and kwargs["save_to_api"] is False
    assert kwargs["tracking_mode"] == "machine"  # Ollama est un autre processus


async def test_the_tracker_runs_while_the_slot_is_held(hub, meter, probe):
    slot = LocalSlot()
    seen: dict[str, bool] = {}

    class Spy(FakeChatModel):
        def stream(self, request):
            seen["busy"] = slot.busy
            seen["running"] = probe.running == 1
            return super().stream(request)

    handle = await _start(hub)
    await stream_into_run(
        hub, handle.run_id, Spy([TextDelta("a")]), REQUEST, slot=slot, meter=meter
    )
    assert seen == {"busy": True, "running": True}  # mesuré pendant la place prise
    assert probe.started == probe.stopped == 1 and not slot.busy


async def test_a_slow_tracker_start_is_outside_the_lane_delay(hub, meter, probe):
    probe.start_delay_s = 0.3  # bien plus long que le délai de lane
    handle = await _start(hub)
    await _play(hub, handle, [TextDelta("Ok")], meter, timeout_s=0.15)
    assert (await _events(hub, handle.run_id))[-1]["data"]["status"] == "ok"


# --- une panne de mesure n'arrête jamais un run ---------------------------------------------------


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        (lambda p: setattr(p, "start_error", RuntimeError("pas de capteur")), "n'a pas démarré"),
        (lambda p: setattr(p, "stop_error", RuntimeError("boum")), "n'a rien mesuré"),
        (lambda p: setattr(p, "no_data", True), "n'a rien mesuré"),
        (lambda p: setattr(p, "energy_kwh", math.nan), "nulle ou illisible"),
        (lambda p: setattr(p, "energy_kwh", 0.0), "nulle ou illisible"),
        (lambda p: setattr(p, "emissions_kg", -1.0), "nulle ou illisible"),
    ],
    ids=["start", "stop", "no_data", "nan", "zero", "negative"],
)
async def test_a_codecarbon_failure_leaves_the_run_ok_with_an_unmeasurable_co2(
    hub, store, meter, probe, setup, reason
):
    setup(probe)
    handle = await _start(hub)
    await _play(hub, handle, [TextDelta("Bonjour")], meter)
    events = await _events(hub, handle.run_id)
    assert events[-1]["data"]["status"] == "ok"  # le run se termine normalement
    co2 = _metrics(events)["co2"]
    assert co2["mg"] is None and co2["method"] == "unmeasurable" and reason in co2["reason"]
    row = _row(store, handle.run_id)
    assert row["status"] == "ok" and row["co2_mg"] is None and row["energy_wh"] is None


async def test_codecarbon_missing_is_an_unmeasurable_co2_not_a_failed_run(hub, store):
    def absent():
        raise ModuleNotFoundError("codecarbon")

    handle = await _start(hub)
    await _play(hub, handle, [TextDelta("a")], LocalMeter("FRA", 1.1, loader=absent))
    row = _row(store, handle.run_id)
    assert row["status"] == "ok" and row["co2_method"] == "unmeasurable"
    assert "indisponible" in row["co2_reason"]


# --- erreur, annulation, relance, cloud -------------------------------------------------------------


async def test_an_errored_leaf_stops_its_tracker_and_keeps_an_unmeasurable_co2(
    hub, store, meter, probe
):
    handle = await _start(hub)
    await _play(hub, handle, [ProviderError("ollama_down", "arrêté")], meter)
    row = _row(store, handle.run_id)
    assert row["status"] == "error" and row["co2_method"] == "unmeasurable" and row["co2_reason"]
    assert probe.started == probe.stopped == 1 and probe.running == 0


async def test_a_cancelled_leaf_stops_its_tracker_and_keeps_what_was_measured(
    hub, store, meter, probe
):
    slot = LocalSlot()
    handle = await _start(hub)
    task = asyncio.create_task(_play(hub, handle, [TextDelta("a"), Sleep(5)], meter, slot=slot))
    hub.attach_task(handle.run_id, task)
    await asyncio.sleep(0.1)
    assert probe.running == 1 and slot.busy
    await hub.cancel(handle.run_id)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert probe.started == probe.stopped == 1 and probe.running == 0 and not slot.busy
    row = _row(store, handle.run_id)
    # Le hub a clos l'annulation avant la reprise de la tâche : la mesure faite jusqu'à l'arrêt
    # remplace le `co2` de remplacement (`amend_cancelled_leaf`), l'énergie dépensée compte.
    assert row["status"] == "cancelled" and row["co2_method"] == "codecarbon"
    assert row["co2_mg"] == pytest.approx(1.8) and row["energy_wh"] == pytest.approx(0.001)


async def test_a_cancelled_leaf_whose_tracker_failed_keeps_the_unmeasurable_placeholder(
    hub, store, meter, probe
):
    probe.stop_error = RuntimeError("boum")
    handle = await _start(hub)
    task = asyncio.create_task(_play(hub, handle, [TextDelta("a"), Sleep(5)], meter))
    hub.attach_task(handle.run_id, task)
    await asyncio.sleep(0.1)
    await hub.cancel(handle.run_id)
    with pytest.raises(asyncio.CancelledError):
        await task
    row = _row(store, handle.run_id)
    assert row["status"] == "cancelled" and row["co2_method"] == "unmeasurable"
    assert row["co2_mg"] is None and row["co2_reason"]


async def test_a_retried_generation_adds_up_both_measures(hub, store, meter, probe):
    class PerCall:
        ref = FAKE_REF

        def __init__(self) -> None:
            self.calls = 0

        def stream(self, request):
            self.calls += 1
            script = (
                [TextDelta("Par"), ProviderError("generation_interrupted", "coupé")]
                if self.calls == 1
                else [TextDelta("Bonjour")]
            )
            return FakeChatModel(script).stream(request)

    handle = await _start(hub)
    await stream_into_run(
        hub, handle.run_id, PerCall(), REQUEST, slot=LocalSlot(), meter=meter,
        retry_interrupted=True,
    )  # fmt: skip
    row = _row(store, handle.run_id)
    assert probe.started == probe.stopped == 2  # un tracker par appel
    assert row["co2_mg"] == pytest.approx(3.6) and row["energy_wh"] == pytest.approx(0.002)


async def test_a_cloud_leaf_is_not_measured_by_codecarbon(hub, meter, probe):
    handle = await _start(hub)
    await stream_into_run(
        hub, handle.run_id, FakeChatModel([TextDelta("a")], ref=CLOUD_REF), REQUEST,
        slot=LocalSlot(), meter=meter,
    )  # fmt: skip
    assert probe.started == 0 and probe.kwargs == []
    assert _metrics(await _events(hub, handle.run_id))["co2"]["method"] == "unmeasurable"


# --- un seul tracker à la fois ----------------------------------------------------------------------


async def test_several_local_leaves_never_run_two_trackers_at_once(hub, meter, probe):
    slot = LocalSlot()
    handles = [await _start(hub, kind) for kind in ("chat", "rag", "agent")]
    await asyncio.gather(
        *(
            _play(hub, h, [TextDelta("a"), Sleep(0.05), TextDelta("b")], meter, slot=slot)
            for h in handles
        )
    )
    assert probe.started == probe.stopped == 3
    assert probe.peak == 1  # jamais deux trackers simultanés
    assert slot.acquired == 3


async def test_the_meter_alone_serializes_trackers_even_without_the_slot(meter, probe):
    async def one():
        async with meter.track() as tracking:
            await asyncio.sleep(0.03)
        return tracking.footprint

    footprints = await asyncio.gather(one(), one(), one())
    assert probe.peak == 1 and all(f.measured for f in footprints)


# --- carbon_updated après chaque feuille -------------------------------------------------------------


async def test_carbon_updated_is_published_after_each_leaf_including_a_cancelled_one(
    hub, store, meter
):
    feed = SystemFeed()

    async def announce():
        await announce_carbon_updated(feed, store, hub.app_session_id)

    with feed.subscribe() as queue:
        ok = await _start(hub, "chat")
        await _play(hub, ok, [TextDelta("a")], meter, on_leaf_closed=announce)
        first = queue.get_nowait()
        assert first["type"] == "carbon_updated" and first["run_id"] is None
        assert first["data"]["total_mg"] == pytest.approx(1.8)
        assert first["data"]["measured_runs"] == 1

        cancelled = await _start(hub, "rag")
        task = asyncio.create_task(
            _play(hub, cancelled, [TextDelta("a"), Sleep(5)], meter, on_leaf_closed=announce)
        )
        hub.attach_task(cancelled.run_id, task)
        await asyncio.sleep(0.1)
        await hub.cancel(cancelled.run_id)
        with pytest.raises(asyncio.CancelledError):
            await task
        second = queue.get_nowait()
        assert second["type"] == "carbon_updated"
        assert second["data"]["measured_runs"] == 2  # la feuille annulée garde sa mesure
        assert second["data"]["total_mg"] == pytest.approx(3.6)


async def test_a_failing_announcement_does_not_break_the_run(hub, store, meter):
    async def boom():
        raise RuntimeError("bus cassé")

    handle = await _start(hub)
    await _play(hub, handle, [TextDelta("a")], meter, on_leaf_closed=boom)
    assert _row(store, handle.run_id)["status"] == "ok"


# --- combine ---------------------------------------------------------------------------------------


def test_combine_sums_measures_and_one_unknown_makes_the_sum_unknown():
    assert combine([]) is None
    total = combine([Footprint(1.0, 0.1), Footprint(2.0, 0.2)])
    assert total is not None and total.mg == 3.0 and total.energy_wh == pytest.approx(0.3)
    unknown = combine([Footprint(1.0, 0.1), Footprint(reason="x")])
    assert unknown is not None and not unknown.measured and unknown.co2().reason == "x"


# --- le vrai CodeCarbon : aucun réseau, aucun fichier ------------------------------------------------


def _block_network(monkeypatch) -> list[str]:
    """Tout accès au réseau par `socket` refusé et consigné ; rend la liste des tentatives."""
    attempts: list[str] = []

    class Blocked(socket.socket):
        def __init__(self, *args, **kwargs):
            attempts.append("socket")
            raise OSError("réseau coupé")

    def blocked(name):
        def refuse(*args, **kwargs):
            attempts.append(name)
            raise OSError("réseau coupé")

        return refuse

    monkeypatch.setattr(socket, "socket", Blocked)
    monkeypatch.setattr(socket, "create_connection", blocked("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", blocked("getaddrinfo"))
    monkeypatch.setattr(socket, "gethostbyname", blocked("gethostbyname"))
    return attempts


def test_the_real_offline_tracker_measures_without_any_network_or_file(tmp_path, monkeypatch):
    """`OfflineEmissionsTracker` pour de bon (quelques secondes), tout accès au réseau bloqué et
    consigné : aucune tentative, aucune écriture (CSV) dans le dossier courant."""
    attempts = _block_network(monkeypatch)
    monkeypatch.chdir(tmp_path)

    meter = LocalMeter("FRA", 1.1, loader=real_loader)
    started = meter._start_sync()  # les corps exécutés dans le pool de threads, sans boucle
    assert started.tracker is not None, started.reason
    sum(i * i for i in range(2_000_000))  # un peu de charge pendant la mesure
    footprint = meter._stop_sync(started)

    assert attempts == []  # aucun appel réseau
    assert footprint.measured and footprint.mg > 0 and footprint.energy_wh > 0
    assert list(tmp_path.iterdir()) == []  # aucun CSV


async def test_the_real_tracker_measures_a_local_leaf_through_track(tmp_path, monkeypatch):
    """Le vrai CodeCarbon par le chemin du service : `warm_up` (détection du matériel), puis
    `stream_into_run` → `meter.track()` dans la place, sans réseau ni fichier. Après le
    préchauffage, démarrage et arrêt ne pèsent plus sur la place Ollama."""
    data = tmp_path / "data"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    opened = Store.open(db_path(data))
    hub = RunHub(opened, batch_interval_s=3600)
    await hub.start()
    attempts = _block_network(monkeypatch)
    monkeypatch.chdir(cwd)
    try:
        meter = LocalMeter("FRA", 1.1, loader=real_loader)
        await meter.warm_up()
        handle = await _start(hub)
        burn = Sleep(0.5)  # le tracker mesure pendant la génération
        loop = asyncio.get_running_loop()
        began = loop.time()
        await _play(hub, handle, [burn, TextDelta("Bonjour")], meter)
        elapsed = loop.time() - began
        row = _row(opened, handle.run_id)
    finally:
        await hub.stop()
        opened.close()

    assert attempts == []
    assert list(cwd.iterdir()) == []  # aucun CSV
    assert row["status"] == "ok"
    assert row["co2_method"] == "codecarbon", row["co2_reason"]
    assert row["co2_mg"] > 0 and row["energy_wh"] > 0
    assert elapsed < 0.5 + 3.0  # préchauffé : plus de détection du matériel dans la place


async def test_a_second_cancellation_during_stop_keeps_the_lock_until_the_tracker_stops(probe):
    """Annulé deux fois pendant l'arrêt du tracker, `track` ne libère le verrou (et ne laisse
    démarrer un autre tracker) qu'une fois le `stop` fini."""
    gate = asyncio.Event()
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    meter = LocalMeter("FRA", 1.2, loader=probe.loader())
    original = meter._stop_sync

    def slow_stop(started):
        loop.call_soon_threadsafe(stopping.set)
        asyncio.run_coroutine_threadsafe(gate.wait(), loop).result()
        return original(started)

    meter._stop_sync = slow_stop

    async def leaf():
        async with meter.track():
            await asyncio.sleep(3600)

    task = asyncio.create_task(leaf())
    await asyncio.sleep(0.05)
    task.cancel()
    await stopping.wait()
    task.cancel()  # seconde annulation pendant le `stop`
    await asyncio.sleep(0.05)
    assert not task.done() and meter._lock.locked() and probe.running == 1
    gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert probe.running == 0 and probe.peak == 1 and not meter._lock.locked()


def test_a_tracker_whose_start_fails_midway_is_stopped():
    """`start` qui lève après avoir lancé son fil de mesure : le tracker est arrêté."""
    stopped: list[bool] = []

    class HalfStarted:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("mesure initiale en échec")

        def stop(self):
            stopped.append(True)

    started = LocalMeter("FRA", 1.2, loader=lambda: HalfStarted)._start_sync()
    assert started.tracker is None and "RuntimeError" in (started.reason or "")
    assert stopped == [True]


async def test_warm_up_runs_one_throwaway_tracker_under_the_lock(probe):
    meter = LocalMeter("FRA", 1.2, loader=probe.loader())
    await meter.warm_up()
    assert probe.started == probe.stopped == 1 and probe.running == 0
    probe.start_error = RuntimeError("panne")
    await meter.warm_up()  # ne lève pas
    assert not meter._lock.locked()
