"""Sonde d'Ollama : délai de 1 s au plus, cache de 5 s, jamais bloquante (AD-15)."""

from __future__ import annotations

import asyncio
import time

import httpx

from wavelocalai.models.ollama_probe import DOWN, OllamaProbe

from ..conftest import closed_port


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _transport(calls: list[str], *, delay: float = 0.0, status: int = 200, body=None):
    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if delay:
            await asyncio.sleep(delay)
        return httpx.Response(status, json={"version": "0.40.6"} if body is None else body)

    return httpx.MockTransport(handler)


async def test_up_reports_version_and_latency():
    calls: list[str] = []
    probe = OllamaProbe("http://127.0.0.1:11434", transport=_transport(calls), wait_s=1.0)
    status = await probe.status()
    assert status.up and status.version == "0.40.6" and status.latency_ms >= 1
    assert calls == ["http://127.0.0.1:11434/api/version"]


async def test_state_stays_cached_five_seconds():
    calls: list[str] = []
    clock = FakeClock()
    probe = OllamaProbe(
        "http://127.0.0.1:11434", transport=_transport(calls), wait_s=1.0, cache_s=5.0, clock=clock
    )
    await probe.status()
    clock.now += 4.9
    await probe.status()
    assert len(calls) == 1
    clock.now += 0.2
    await probe.status()
    assert len(calls) == 2


async def test_hanging_ollama_gives_up_after_the_probe_timeout():
    calls: list[str] = []
    probe = OllamaProbe(
        "http://127.0.0.1:11434",
        transport=_transport(calls, delay=10),
        timeout_s=0.2,
        wait_s=0.05,
    )
    started = time.perf_counter()
    assert await probe.status() == DOWN
    assert time.perf_counter() - started < 0.15  # ne bloque pas sur la sonde
    await asyncio.sleep(0.4)  # la sonde a fini en arrière-plan (délai écoulé)
    assert await probe.status() == DOWN
    assert len(calls) == 1  # l'échec est lui aussi en cache


async def test_slow_but_up_is_seen_by_the_next_call():
    probe = OllamaProbe("http://127.0.0.1:11434", transport=_transport([], delay=0.15), wait_s=0.02)
    assert (await probe.status()).up is False  # pas encore connu : jamais d'attente longue
    await asyncio.sleep(0.3)
    assert (await probe.status()).up is True


async def test_concurrent_calls_share_one_probe():
    calls: list[str] = []
    probe = OllamaProbe(
        "http://127.0.0.1:11434", transport=_transport(calls, delay=0.05), wait_s=1.0
    )
    await asyncio.gather(*(probe.status() for _ in range(5)))
    assert len(calls) == 1


async def test_http_error_or_garbage_means_down():
    assert (
        await OllamaProbe("http://x", transport=_transport([], status=500), wait_s=1.0).status()
        == DOWN
    )
    assert (
        await OllamaProbe(
            "http://x", transport=_transport([], body=["pas", "un objet"]), wait_s=1.0
        ).status()
        == DOWN
    )


async def test_closed_port_answers_down_within_the_read_budget():
    probe = OllamaProbe(f"http://127.0.0.1:{closed_port()}")
    started = time.perf_counter()
    assert await probe.status() == DOWN
    assert time.perf_counter() - started < 0.25


async def test_start_probes_before_the_first_read_so_a_slow_ollama_is_seen_up():
    calls: list[str] = []
    probe = OllamaProbe(
        "http://127.0.0.1:11434", transport=_transport(calls, delay=0.15), wait_s=0.02
    )
    probe.start()  # démarrage du serveur
    await asyncio.sleep(0.3)  # le navigateur s'ouvre
    assert (await probe.status()).up is True
    assert len(calls) == 1


async def test_expired_cache_keeps_the_last_state_while_the_next_probe_runs():
    calls: list[str] = []
    clock = FakeClock()
    probe = OllamaProbe(
        "http://127.0.0.1:11434",
        transport=_transport(calls, delay=0.15),
        wait_s=0.02,
        clock=clock,
    )
    probe.start()
    await asyncio.sleep(0.3)
    clock.now += 10  # cache échu, sonde suivante lente
    assert (await probe.status()).up is True  # état précédent, pas « arrêté »
    assert len(calls) == 2
    await probe.aclose()


async def test_slow_client_construction_does_not_block_the_read(monkeypatch):
    # Le chargement synchrone des certificats (lent sous Windows) ne doit pas retenir `status()`.
    real_client = httpx.AsyncClient

    def slow_client(*args, **kwargs):
        time.sleep(0.4)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", slow_client)
    probe = OllamaProbe(f"http://127.0.0.1:{closed_port()}")
    started = time.perf_counter()
    assert await probe.status() == DOWN
    assert time.perf_counter() - started < 0.25
    await probe.aclose()


# --- « Réessayer » : sonde forcée (C8) -------------------------------------------------------


async def test_recheck_probes_again_without_waiting_for_the_cache():
    calls: list[str] = []
    clock = FakeClock()
    probe = OllamaProbe(
        "http://127.0.0.1:11434", transport=_transport(calls), wait_s=1.0, cache_s=5.0, clock=clock
    )
    await probe.status()
    clock.now += 0.1  # le cache est tout frais : `status()` ne sonderait pas
    await probe.status()
    assert len(calls) == 1
    status = await probe.recheck()
    assert len(calls) == 2 and status.up and probe.settled


async def test_recheck_sees_ollama_started_since_the_last_probe():
    state = {"up": False}

    async def handler(request: httpx.Request) -> httpx.Response:
        if not state["up"]:
            raise httpx.ConnectError("refusé")
        return httpx.Response(200, json={"version": "0.9.9"})

    probe = OllamaProbe(
        "http://127.0.0.1:11434", transport=httpx.MockTransport(handler), wait_s=1.0, cache_s=60.0
    )
    assert (await probe.status()).up is False
    state["up"] = True
    assert (await probe.status()).up is False  # le cache de 60 s masque le démarrage
    assert (await probe.recheck()).up is True


async def test_recheck_answers_within_its_wait_and_settles_later():
    probe = OllamaProbe("http://127.0.0.1:11434", transport=_transport([], delay=0.3))
    started = time.perf_counter()
    status = await probe.recheck(wait_s=0.05)
    assert time.perf_counter() - started < 0.2  # sous le budget de 300 ms, sonde lente ou non
    assert status == DOWN and not probe.settled  # l'état précédent (aucun) est rendu
    assert (await probe.wait_settled()).up is True and probe.settled


async def test_a_probe_started_before_a_recheck_cannot_overwrite_its_result():
    """La sonde lancée avant le clic finit après la forcée : son résultat est plus ancien."""
    answers = iter([(0.3, 500), (0.0, 200)])

    async def handler(request: httpx.Request) -> httpx.Response:
        delay, code = next(answers)
        await asyncio.sleep(delay)
        return httpx.Response(code, json={"version": "0.9.9"})

    probe = OllamaProbe(
        "http://127.0.0.1:11434", transport=httpx.MockTransport(handler), wait_s=0.01
    )
    probe.start()  # lente, et en erreur : « arrêté »
    await asyncio.sleep(0.05)
    assert (await probe.recheck(wait_s=1.0)).up is True
    await asyncio.sleep(0.4)  # la première finit maintenant : elle ne réécrit rien
    assert (await probe.status()).up is True
