"""Lancement et arrêt brutal de l'écrivain de test ``samples/append_loop.py``."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from scripts.quality_bench.common.locks import FileLock, LockBusyError

APPEND_LOOP = Path(__file__).parent / "samples" / "append_loop.py"


def start_append_loop(
    jsonl: Path, lock: Path, last: int, pause: float
) -> tuple[subprocess.Popen[str], int]:
    """Lance l'écrivain et attend qu'il tienne le verrou ; rend le processus et le PID de
    l'interpréteur réel (sous Windows, ``python.exe`` d'un venv est un lanceur qui crée un
    processus enfant)."""
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, str(APPEND_LOOP), str(jsonl), str(lock), str(last), str(pause)],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    status, pid = process.stdout.readline().split()
    assert status == "ready"
    return process, int(pid)


def kill_hard(process: subprocess.Popen[str], pid: int, lock: Path, timeout: float = 30) -> None:
    """Tue l'interpréteur sans lui laisser finir quoi que ce soit (``TerminateProcess`` sous
    Windows, ``SIGKILL`` ailleurs), puis attend que le système libère son verrou."""
    with contextlib.suppress(OSError):  # déjà mort
        os.kill(pid, signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM)
    process.kill()
    process.wait(timeout=timeout)
    process.stdout.close()
    deadline = time.monotonic() + timeout
    while True:
        try:
            with FileLock(lock):
                return
        except LockBusyError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)
