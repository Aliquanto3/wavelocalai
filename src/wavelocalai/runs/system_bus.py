"""Port `SystemBus` et flux d'événements système (AD-6, AD-10).

Tout service publie un événement système (ex. `carbon_updated`, après chaque feuille) par le port
`SystemBus` ; il part sur `GET /api/system/stream` dans la même enveloppe que les runs, avec
`run_id: null`, sans `id:` ni rejeu. Le service ne connaît que le port : il ignore qui l'écoute.

`SystemFeed` en est l'implémentation en mémoire. Elle gère aussi la mesure périodique : un
échantillonneur (état d'Ollama, CPU, mémoire, runs actifs) publié toutes les 2 s, mais **seulement
tant qu'un client écoute** (pause à la dernière déconnexion, reprise à la première connexion), et
rien ne reste abonné après une déconnexion : l'abonnement se referme dans le `finally` du flux.
Tout se passe dans la boucle d'événements : `publish` est synchrone et ne touche que la mémoire.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Iterator, Mapping
from typing import Any, Protocol

from wavelocalai.store.db import utc_now_iso

logger = logging.getLogger("wavelocalai.runs")

SAMPLE_INTERVAL_S = 2.0  # AD-6 : l'état du système est publié toutes les 2 s
QUEUE_SIZE = (
    64  # un client lent perd les plus anciens événements, il ne fait pas grossir la mémoire
)
STATE_EVENT = "system_state"  # événement périodique ; les autres viennent des services

Sampler = Callable[[], Awaitable[Mapping[str, Any]]]


class SystemBus(Protocol):
    """Ce que voit un service : publier un événement système, rien d'autre."""

    def publish(self, event_type: str, data: Mapping[str, Any] | None = None) -> None: ...


class SystemFeed:
    """Bus système en mémoire et boucle de mesure à la demande ; une instance par serveur."""

    def __init__(
        self,
        sampler: Sampler | None = None,
        *,
        interval_s: float = SAMPLE_INTERVAL_S,
        queue_size: int = QUEUE_SIZE,
        clock: Callable[[], str] = utc_now_iso,
    ) -> None:
        self._sampler = sampler
        self._interval_s = interval_s
        self._queue_size = queue_size
        self._clock = clock
        self._subscribers: set[asyncio.Queue[dict[str, Any] | None]] = set()
        self._seq = 0
        self._task: asyncio.Task[None] | None = None
        self._last_state: dict[str, Any] | None = None
        self._closed = False

    # --- port SystemBus ------------------------------------------------------------------------

    def publish(self, event_type: str, data: Mapping[str, Any] | None = None) -> None:
        """Diffuse un événement à tous les clients connectés (aucun client : il est perdu, le flux
        n'a pas de rejeu). `seq` croît pour toute la vie du serveur : informatif seulement."""
        self._seq += 1
        envelope = {
            "seq": self._seq,
            "run_id": None,
            "type": event_type,
            "ts": self._clock(),
            "data": dict(data or {}),
        }
        if event_type == STATE_EVENT:
            self._last_state = envelope
        for queue in self._subscribers:
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()  # le plus ancien cède la place
            queue.put_nowait(envelope)

    # --- clients -------------------------------------------------------------------------------

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def sampling(self) -> bool:
        """Vrai tant que la boucle de mesure tourne (au moins un client connecté)."""
        return self._task is not None and not self._task.done()

    @contextlib.contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[dict[str, Any] | None]]:
        """File des enveloppes d'un client. La première connexion démarre la mesure, la dernière
        déconnexion l'arrête. `None` dans la file demande au flux de se terminer (arrêt du
        serveur)."""
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(self._queue_size)
        if self._closed:
            queue.put_nowait(None)
            yield queue
            return
        self._subscribers.add(queue)
        if self.sampling and self._last_state is not None:
            queue.put_nowait(self._last_state)  # un client qui arrive en cours de route
        self._ensure_sampling()
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)
            if not self._subscribers:
                self._stop_sampling()

    # --- mesure périodique ---------------------------------------------------------------------

    def _ensure_sampling(self) -> None:
        if self._sampler is not None and not self.sampling:
            self._task = asyncio.get_running_loop().create_task(
                self._sample_loop(self._sampler), name="wavelocalai-system-sampler"
            )

    def _stop_sampling(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _sample_loop(self, sampler: Sampler) -> None:
        while True:
            try:
                self.publish(STATE_EVENT, await sampler())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Mesure du système en échec, nouvel essai au prochain tick")
            await asyncio.sleep(self._interval_s)

    async def aclose(self) -> None:
        """Arrêt du serveur : mesure arrêtée, les flux ouverts reçoivent leur fin."""
        self._closed = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for queue in list(self._subscribers):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(None)
