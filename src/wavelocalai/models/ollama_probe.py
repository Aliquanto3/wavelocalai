"""Sonde de santé d'Ollama : délai de 1 s au plus, état en cache 5 s (AD-15).

Les routes de lecture ne bloquent jamais sur Ollama : `status()` rend l'état en cache, ou lance
une sonde unique (en tâche de fond) et n'en attend le résultat que `wait_s`. Ollama arrêté, la
connexion refusée peut durer ~2 s sous Windows : on rend alors `up=False` sans attendre, et la
sonde finit son travail pour l'appel suivant.

`start()`, appelé au démarrage du serveur, lance la première sonde avant toute requête : un Ollama
vivant mais lent à répondre (démarrage à froid) n'est donc pas annoncé arrêté à la première
lecture. Une fois l'état connu, un cache échu rend l'état précédent pendant que la sonde suivante
tourne : seul un échec de sonde fait passer à `up=False`.

`recheck()` (« Réessayer » du panneau Ollama, C8) force une sonde neuve sans attendre l'échéance du
cache et n'en attend le résultat que `wait_s` (le budget de 300 ms tient) ; `settled` dit si elle a
fini, `wait_settled()` l'attend pour publier l'état dès qu'il est connu.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class OllamaStatus:
    up: bool
    version: str | None
    latency_ms: int | None


DOWN = OllamaStatus(up=False, version=None, latency_ms=None)


class OllamaProbe:
    def __init__(
        self,
        host: str,
        *,
        timeout_s: float = 1.0,
        cache_s: float = 5.0,
        wait_s: float = 0.1,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._host = host.rstrip("/")
        self._timeout_s = timeout_s
        self._cache_s = cache_s
        self._wait_s = wait_s
        self._transport = transport
        self._clock = clock
        self._state: OllamaStatus | None = None
        self._checked_at = 0.0
        self._task: asyncio.Task[None] | None = None
        self._generation = 0  # une sonde forcée rend caduque celle qui tournait (état plus ancien)
        self._forced: asyncio.Task[None] | None = None  # dernière sonde forcée (coalescence)

    async def status(self) -> OllamaStatus:
        """État d'Ollama, rendu en `wait_s` au plus."""
        if self._state is not None and self._clock() - self._checked_at < self._cache_s:
            return self._state
        task = self._ensure_task()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), self._wait_s)
        return self._state or DOWN

    async def recheck(self, wait_s: float = 0.25) -> OllamaStatus:
        """Sonde neuve, lancée tout de suite quel que soit l'âge du cache ; rend l'état connu après
        `wait_s` au plus (le nouvel état s'il est arrivé, sinon le précédent : voir `settled`). Une
        sonde déjà en cours est laissée finir sans écrire : son résultat date d'avant le clic. Une
        sonde forcée encore en cours sert aux clics suivants (aucune sonde de plus vers Ollama)."""
        loop = asyncio.get_running_loop()
        task = self._forced
        if task is None or task.done() or task.get_loop() is not loop or task is not self._task:
            self._generation += 1
            task = self._task = self._forced = loop.create_task(self._refresh(self._generation))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), wait_s)
        return self._state or DOWN

    @property
    def settled(self) -> bool:
        """Vrai quand aucune sonde n'est en cours (le dernier état est à jour)."""
        return self._task is None or self._task.done()

    async def wait_settled(self) -> OllamaStatus:
        """Attend la sonde en cours (aucune : rend l'état tout de suite)."""
        task = self._task
        if task is not None and not task.done():
            await asyncio.shield(task)
        return self._state or DOWN

    @property
    def cached(self) -> OllamaStatus | None:
        """Dernier état connu, sans sonde ni attente (`None` avant la première sonde terminée) :
        la fiche machine y lit la version d'Ollama."""
        return self._state

    def start(self) -> None:
        """Lance la première sonde sans l'attendre (à appeler dans la boucle du serveur)."""
        self._ensure_task()

    async def aclose(self) -> None:
        """Annule la sonde en cours (arrêt du serveur)."""
        task = self._task
        if task is not None and not task.done() and task.get_loop() is asyncio.get_running_loop():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _ensure_task(self) -> asyncio.Task[None]:
        loop = asyncio.get_running_loop()
        task = self._task
        if task is None or task.done() or task.get_loop() is not loop:
            task = self._task = loop.create_task(self._refresh(self._generation))
        return task

    async def _refresh(self, generation: int) -> None:
        state = await self._probe()
        if generation != self._generation:
            return  # une sonde forcée est partie depuis : ce résultat est plus ancien
        self._state = state
        self._checked_at = self._clock()

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._host,
            timeout=self._timeout_s,
            transport=self._transport,
            trust_env=False,  # pas de proxy système pour une adresse locale
        )

    async def _probe(self) -> OllamaStatus:
        started = time.perf_counter()
        try:
            # Construit hors de la boucle : le chargement des certificats est synchrone et
            # bloquerait `status()` au-delà de `wait_s` (lent sous Windows).
            client = await asyncio.to_thread(self._make_client)
            async with client:
                response = await asyncio.wait_for(client.get("/api/version"), self._timeout_s)
            response.raise_for_status()
            version = response.json().get("version")
        except Exception:  # noqa: BLE001 - toute panne de la sonde = Ollama indisponible
            return DOWN
        latency_ms = max(1, round((time.perf_counter() - started) * 1000))
        return OllamaStatus(
            up=True, version=str(version) if version else None, latency_ms=latency_ms
        )
