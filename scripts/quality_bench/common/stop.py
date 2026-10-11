"""Arrêt propre (AD-13) : SIGINT et fichier ``STOP`` ne font que lever un drapeau.

Un second SIGINT n'attend plus : il lève ``KeyboardInterrupt`` (``signal.default_int_handler``).

Le drapeau est lu **entre deux unités** (questions ou lots) par ``should_stop()`` : l'unité en
cours se termine et s'écrit. Un ``STOP`` présent au lancement est supprimé et journalisé ; il
est aussi supprimé à la sortie.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from pathlib import Path
from types import FrameType, TracebackType
from typing import Any

logger = logging.getLogger(__name__)


class StopFlag:
    """Drapeau d'arrêt, en contexte : ``with StopFlag(paths.generation_stop_path(c)) as stop``."""

    def __init__(self, stop_path: str | os.PathLike[str]) -> None:
        self.stop_path = Path(stop_path)
        self._requested = False
        self._reason: str | None = None
        self._logged = False
        self._sigints = 0
        self._previous_handler: Any = None
        self._installed = False

    @property
    def reason(self) -> str | None:
        return self._reason

    def request_stop(self, reason: str) -> None:
        """Lève le drapeau, sans rien interrompre ni journaliser (``should_stop`` s'en charge)."""
        if not self._requested:
            self._reason = reason
            self._requested = True

    def should_stop(self) -> bool:
        """À appeler entre deux unités : vrai si SIGINT a été reçu ou si ``STOP`` existe."""
        if not self._requested and self.stop_path.exists():
            self.request_stop(f"fichier {self.stop_path}")
        if self._requested and not self._logged:
            self._logged = True
            logger.warning(
                "Arrêt demandé (%s) : l'unité en cours est terminée, le processus sort.",
                self._reason,
            )
        return self._requested

    def _on_sigint(self, signum: int, frame: FrameType | None) -> None:
        # Gestionnaire de signal : aucun journal ici (réentrance des flux), seulement le drapeau.
        self._sigints += 1
        if self._sigints > 1:
            signal.default_int_handler(signum, frame)  # second Ctrl+C : KeyboardInterrupt
        self.request_stop("SIGINT")

    def __enter__(self) -> StopFlag:
        try:
            self.stop_path.unlink()
        except FileNotFoundError:
            pass
        else:
            logger.warning("Fichier STOP présent au lancement, supprimé : %s", self.stop_path)
        if threading.current_thread() is threading.main_thread():
            self._previous_handler = signal.signal(signal.SIGINT, self._on_sigint)
            self._installed = True
        else:
            logger.warning("StopFlag hors du thread principal : SIGINT non intercepté.")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._installed:
            # None : gestionnaire installé hors de Python ; on rend le comportement par défaut.
            previous = self._previous_handler
            signal.signal(signal.SIGINT, signal.SIG_DFL if previous is None else previous)
            self._installed = False
        self.stop_path.unlink(missing_ok=True)
