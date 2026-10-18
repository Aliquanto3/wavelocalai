"""Arrêt réel de `python -m wavelocalai` avec des flux ouverts (AD-23).

uvicorn attend la fin des connexions **avant** l'arrêt du cycle de vie : un flux système ou le flux
d'un run actif, s'ils n'étaient pas fermés d'abord, retiendraient l'arrêt sans fin. Le test lance le
vrai serveur, ouvre les deux flux, envoie l'arrêt (Ctrl+Break sous Windows, SIGINT ailleurs) et
vérifie une sortie rapide, cycle de vie arrêté et run passé à `cancelled`.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time

import pytest

from ..conftest import closed_port

WINDOWS = sys.platform == "win32"


def _launch(port: int, data_dir, ollama_port: int) -> subprocess.Popen:
    env = {
        **os.environ,
        "WAVELOCALAI_OLLAMA_HOST": f"http://127.0.0.1:{ollama_port}",
        "WAVELOCALAI_TESTING": "1",
        "PYTHONUTF8": "1",
    }
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0  # Ctrl+Break visé
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "wavelocalai", "--port", str(port), "--data-dir", str(data_dir)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


def _wait_ready(port: int, proc: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail("le serveur s'est arrêté au démarrage")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    pytest.fail("le serveur n'a pas démarré à temps")


def _open_stream(port: int, path: str) -> socket.socket:
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    sock.sendall(
        f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAccept: text/event-stream\r\n\r\n".encode()
    )
    assert sock.recv(64).startswith(b"HTTP/1.1 200")
    return sock


def test_shutdown_with_open_streams_ends_quickly_and_cancels_active_runs(tmp_path):
    port, data = closed_port(), tmp_path / "data"
    proc = _launch(port, data, closed_port())
    streams: list[socket.socket] = []
    try:
        _wait_ready(port, proc)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"script": [{"text": "a"}, {"sleep_s": 30}]})
        conn.request("POST", "/api/test/runs", body, {"Content-Type": "application/json"})
        run_id = json.loads(conn.getresponse().read())["run_id"]
        conn.close()
        streams.append(_open_stream(port, "/api/system/stream"))
        streams.append(_open_stream(port, f"/api/runs/{run_id}/events"))

        started = time.monotonic()
        proc.send_signal(signal.CTRL_BREAK_EVENT if WINDOWS else signal.SIGINT)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            pytest.fail("l'arrêt reste bloqué par les flux ouverts")
        # Bien sous le filet de `GRACEFUL_SHUTDOWN_S` : les flux ont été fermés, pas coupés.
        assert time.monotonic() - started < 4
    finally:
        for sock in streams:
            sock.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    log = (data / "logs" / "wavelocalai.log").read_text(encoding="utf-8")
    assert "Application shutdown complete" in log
    assert "timeout graceful shutdown exceeded" not in log
    with contextlib.closing(sqlite3.connect(data / "wavelocalai.db")) as db:
        status = db.execute("SELECT status FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert status == ("cancelled",)
