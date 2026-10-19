"""Lancement réel de `python -m wavelocalai` en sous-processus (données en dossier temporaire,
Ollama pointé sur un port fermé : aucun vrai réseau hors de la boucle locale)."""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import time

import pytest

from ..conftest import closed_port


def _get(port: int, path: str, host: str | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    conn.putrequest("GET", path, skip_host=host is not None)
    if host is not None:
        conn.putheader("Host", host)
    conn.endheaders()
    response = conn.getresponse()
    return response.status, json.loads(response.read() or b"{}"), dict(response.getheaders())


def _launch(port: int, data_dir, ollama_port: int) -> subprocess.Popen:
    env = {
        **os.environ,
        "WAVELOCALAI_OLLAMA_HOST": f"http://127.0.0.1:{ollama_port}",
        # Sortie tubée sous Windows : sinon encodée en cp1252, illisible en UTF-8.
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "wavelocalai", "--port", str(port), "--data-dir", str(data_dir)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def _wait_ready(port: int, proc: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"le serveur s'est arrêté : {proc.stderr.read()}")
        try:
            _get(port, "/api/health", host=f"127.0.0.1:{port}")
            return
        except OSError:
            time.sleep(0.2)
    pytest.fail("le serveur n'a pas démarré à temps")


def test_real_server_answers_health_refuses_foreign_host_and_a_second_launch(tmp_path):
    port, data = closed_port(), tmp_path / "data"
    proc = _launch(port, data, closed_port())
    try:
        _wait_ready(port, proc)

        # Budget AD-15 (300 ms) : meilleur de 3 lectures, un pic de charge du runner en gonfle une.
        timings = []
        for _ in range(3):
            started = time.perf_counter()
            status, body, headers = _get(port, "/api/health", host=f"localhost:{port}")
            timings.append(time.perf_counter() - started)
        assert min(timings) < 0.3, [f"{t * 1000:.0f} ms" for t in timings]
        assert status == 200 and body["ollama"]["up"] is False
        assert not [h for h in headers if h.lower().startswith("access-control-")]

        status, body, _ = _get(port, "/api/health", host="evil.example")
        assert status == 403 and body["code"] == "forbidden_host"

        # Un second serveur sur le même dossier de données refuse de démarrer.
        second = _launch(closed_port(), data, closed_port())
        _, err = second.communicate(timeout=30)
        assert second.returncode == 1 and "autre wavelocalai-v2" in err

        # Un second serveur sur le même port (autre dossier) aussi.
        third = _launch(port, tmp_path / "autre", closed_port())
        _, err = third.communicate(timeout=30)
        assert third.returncode == 1 and f"port {port} est occupé" in err
    finally:
        proc.terminate()
        proc.communicate(timeout=30)
    assert (data / "logs" / "wavelocalai.log").is_file()
