"""Sémaphore « Ollama local » à 1 (AD-14), pris par appel de modèle et non par run.

Une génération, un lot d'embedding : chaque appel local prend la place le temps du flux, ce qui
laisse s'intercaler un chat et une ingestion. Un appel cloud n'y passe pas. La mesure CO2 d'une
feuille locale (story 2.3) s'ouvre et se ferme à l'intérieur de cette place.
"""

from __future__ import annotations

import asyncio
from types import TracebackType


class LocalSlot:
    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(1)
        self.acquired = 0  # nombre de prises depuis le démarrage (diagnostic et tests)
        self.waiting = 0  # appels en attente de la place

    @property
    def busy(self) -> bool:
        return self._semaphore.locked()

    async def __aenter__(self) -> None:
        self.waiting += 1
        try:
            await self._semaphore.acquire()
        finally:
            self.waiting -= 1
        self.acquired += 1

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._semaphore.release()
