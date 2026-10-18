"""Port `SystemBus` et flux système en mémoire (AD-6) : enveloppe, abonnements, pause et reprise."""

from __future__ import annotations

import asyncio
import re

from wavelocalai.runs.system_bus import STATE_EVENT, SystemBus, SystemFeed

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


class Counter:
    """Échantillonneur de test : compte ses appels."""

    def __init__(self, fail_first: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first

    async def __call__(self) -> dict:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("mesure en panne")
        return {"n": self.calls}


async def _next(queue, timeout: float = 1.0):
    return await asyncio.wait_for(queue.get(), timeout)


async def test_publish_builds_an_ad6_envelope_without_run_id_and_reaches_every_client():
    feed = SystemFeed()
    with feed.subscribe() as one, feed.subscribe() as two:
        feed.publish("carbon_updated", {"total_mg": 1.5})
        feed.publish("carbon_updated", {"total_mg": 3.0})
        first, second = await _next(one), await _next(one)
        assert await _next(two) == first
    assert set(first) == {"seq", "run_id", "type", "ts", "data"}
    assert first["run_id"] is None and first["type"] == "carbon_updated"
    assert ISO_UTC.match(first["ts"]) and first["data"] == {"total_mg": 1.5}
    assert second["seq"] == first["seq"] + 1


async def test_a_service_only_needs_the_port():
    def service(bus: SystemBus) -> None:
        bus.publish("carbon_updated", {"total_mg": 2.0})

    feed = SystemFeed()
    with feed.subscribe() as queue:
        service(feed)
        assert (await _next(queue))["data"] == {"total_mg": 2.0}


async def test_publish_without_client_is_lost_without_error():
    feed = SystemFeed()
    feed.publish("carbon_updated", {})  # pas de rejeu : personne n'écoute
    with feed.subscribe() as queue:
        assert queue.empty()


async def test_sampling_follows_the_clients_pause_then_resume_without_leak():
    sampler = Counter()
    feed = SystemFeed(sampler, interval_s=0.01)
    assert not feed.sampling and feed.subscriber_count == 0
    with feed.subscribe() as queue:
        assert feed.sampling
        first = await _next(queue)
        assert first["type"] == STATE_EVENT and first["data"] == {"n": 1}
        await _next(queue)
    assert feed.subscriber_count == 0 and not feed.sampling  # dernier client parti : pause
    await asyncio.sleep(0.01)  # laisse la tâche annulée se terminer
    calls = sampler.calls
    await asyncio.sleep(0.05)
    assert sampler.calls == calls  # plus aucune mesure sans client
    with feed.subscribe() as queue:  # reprise à la reconnexion
        assert feed.sampling
        resumed = await _next(queue)
        assert resumed["type"] == STATE_EVENT and resumed["data"]["n"] > calls
    assert feed.subscriber_count == 0 and not feed.sampling


async def test_sampling_survives_until_the_last_of_several_clients_leaves():
    sampler = Counter()
    feed = SystemFeed(sampler, interval_s=0.01)
    with feed.subscribe() as one:
        await _next(one)
        with feed.subscribe() as two:
            replay = await _next(two)  # le nouveau venu reçoit tout de suite le dernier état
            assert replay["type"] == STATE_EVENT
        assert feed.sampling and feed.subscriber_count == 1
        await _next(one)  # la mesure continue pour le client restant
    assert not feed.sampling


async def test_subscription_is_released_when_the_client_task_is_cancelled():
    feed = SystemFeed(Counter(), interval_s=0.01)

    async def client() -> None:
        with feed.subscribe() as queue:
            while True:
                await queue.get()

    task = asyncio.create_task(client())
    await asyncio.sleep(0.03)
    assert feed.subscriber_count == 1
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert feed.subscriber_count == 0 and not feed.sampling


async def test_a_failing_measure_does_not_stop_the_loop():
    sampler = Counter(fail_first=True)
    feed = SystemFeed(sampler, interval_s=0.01)
    with feed.subscribe() as queue:
        envelope = await _next(queue)
    assert envelope["data"] == {"n": 2} and sampler.calls >= 2


async def test_a_slow_client_loses_the_oldest_events_not_the_memory():
    feed = SystemFeed(queue_size=3)
    with feed.subscribe() as queue:
        for n in range(10):
            feed.publish("carbon_updated", {"n": n})
        assert queue.qsize() == 3
        assert [(await _next(queue))["data"]["n"] for _ in range(3)] == [7, 8, 9]


async def test_aclose_ends_open_streams_and_refuses_new_measures():
    sampler = Counter()
    feed = SystemFeed(sampler, interval_s=0.01)
    with feed.subscribe() as queue:
        await _next(queue)
        await feed.aclose()
        while (await _next(queue)) is not None:  # vide les états déjà en file
            pass
        assert not feed.sampling
    with feed.subscribe() as late:  # serveur arrêté : le flux se termine aussitôt
        assert await _next(late) is None
    assert feed.subscriber_count == 0
