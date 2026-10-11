"""Maintien en éveil de Windows pendant une campagne (AD-13).

``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)`` à
l'entrée, ``ES_CONTINUOUS`` seul dans le ``finally``. L'état est propre au thread appelant :
le contexte s'ouvre depuis le thread principal. Sans effet hors Windows.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def _is_windows() -> bool:
    return sys.platform == "win32"


def _set_thread_execution_state(flags: int) -> int:
    """Appel Win32 ; rend l'état précédent, 0 en cas d'échec."""
    function = ctypes.windll.kernel32.SetThreadExecutionState  # type: ignore[attr-defined]
    function.argtypes = [ctypes.c_uint32]
    function.restype = ctypes.c_uint32
    return int(function(flags))


@contextmanager
def keep_awake() -> Iterator[None]:
    """Empêche la mise en veille (système et écran) pendant le bloc ``with``."""
    if not _is_windows():
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("keep_awake() doit être appelé depuis le thread principal")
    if _set_thread_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED) == 0:
        logger.warning("SetThreadExecutionState a échoué : la mise en veille reste possible.")
    else:
        logger.info("Mise en veille de Windows bloquée pendant la campagne.")
    try:
        yield
    finally:
        _set_thread_execution_state(ES_CONTINUOUS)
        logger.info("Mise en veille de Windows rendue au système.")
