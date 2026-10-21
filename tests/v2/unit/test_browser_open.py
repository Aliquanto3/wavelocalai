"""Ouverture du navigateur au démarrage (story 9.1) : `webbrowser.open` toujours simulé, jamais de
vrai navigateur. `_open_browser_when_ready` sonde le port (pas un délai fixe) ; `main` ne lance ce
guetteur que si `--no-browser` est absent et `[server] open_browser` vaut `true`."""

from __future__ import annotations

import logging
import socket
import threading
import time

import pytest

import wavelocalai.__main__ as launcher
from wavelocalai.__main__ import _open_browser_when_ready, main
from wavelocalai.store.logs import close_logging

from ..conftest import closed_port


@pytest.fixture(autouse=True)
def _logs_closed():
    yield
    close_logging()


def _listen(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", port))
    sock.listen()
    return sock


def test_opens_once_after_the_port_is_ready_never_before(monkeypatch):
    port = closed_port()
    url = f"http://127.0.0.1:{port}/"
    calls: list[str] = []
    monkeypatch.setattr(launcher.webbrowser, "open", lambda u: (calls.append(u), True)[1])

    stop = threading.Event()
    thread = threading.Thread(target=_open_browser_when_ready, args=(url, port, stop))
    thread.start()
    try:
        time.sleep(0.3)
        assert calls == []  # le port ne répond pas encore : pas d'ouverture
        server = _listen(port)
        try:
            thread.join(timeout=5)
            assert not thread.is_alive()
            assert calls == [url]  # ouvert une seule fois, une fois le port prêt
        finally:
            server.close()
    finally:
        stop.set()
        thread.join(timeout=5)


def test_failed_open_writes_the_url_to_console_and_log(monkeypatch, capsys, caplog):
    port = closed_port()
    url = f"http://127.0.0.1:{port}/"
    server = _listen(port)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda u: False)
    caplog.set_level(logging.WARNING)
    try:
        _open_browser_when_ready(url, port, threading.Event())
    finally:
        server.close()
    assert url in capsys.readouterr().err
    assert any(url in record.message for record in caplog.records)


def test_open_exception_is_caught_and_logged_without_crashing(monkeypatch, caplog):
    port = closed_port()
    url = f"http://127.0.0.1:{port}/"
    server = _listen(port)

    def _boom(_url):
        raise RuntimeError("pas d'affichage")

    monkeypatch.setattr(launcher.webbrowser, "open", _boom)
    caplog.set_level(logging.ERROR)
    try:
        _open_browser_when_ready(url, port, threading.Event())  # ne lève pas
    finally:
        server.close()
    assert any("navigateur" in record.message.lower() for record in caplog.records)


class _ThreadSpy:
    """Remplace `threading.Thread` dans `__main__` : capture l'appel au lieu de lancer un fil."""

    created: list[tuple[object, tuple]] = []

    def __init__(self, target=None, args=(), daemon=None):
        _ThreadSpy.created.append((target, args))

    def start(self) -> None:
        pass


def _fake_serve(settings, sock, store=None) -> None:
    sock.close()


class _FakeThreadingModule:
    """Remplace le nom `threading` vu par `__main__` seulement : `store/db.py` garde le vrai
    module, ses propres fils (écriture SQLite) ne sont donc pas affectés."""

    Thread = _ThreadSpy
    Event = threading.Event


@pytest.fixture
def no_real_server(monkeypatch):
    monkeypatch.setattr(launcher, "threading", _FakeThreadingModule)
    monkeypatch.setattr("wavelocalai.web.server.serve", _fake_serve)
    _ThreadSpy.created = []
    yield _ThreadSpy
    _ThreadSpy.created = []


def test_default_launch_schedules_the_browser_guard(no_real_server, tmp_path):
    port = closed_port()
    assert main(["--port", str(port), "--data-dir", str(tmp_path / "data")]) == 0
    assert len(no_real_server.created) == 1
    target, args = no_real_server.created[0]
    assert target is _open_browser_when_ready
    url, probed_port, _stop = args
    assert url == f"http://127.0.0.1:{port}/"
    assert probed_port == port


def test_no_browser_flag_skips_the_guard(no_real_server, tmp_path):
    code = main(
        ["--port", str(closed_port()), "--data-dir", str(tmp_path / "data"), "--no-browser"]
    )
    assert code == 0
    assert no_real_server.created == []


def test_open_browser_false_setting_skips_the_guard(no_real_server, tmp_path):
    toml = tmp_path / "wavelocalai.toml"
    toml.write_text("[server]\nopen_browser = false\n", encoding="utf-8")
    code = main(
        [
            "--port",
            str(closed_port()),
            "--data-dir",
            str(tmp_path / "data"),
            "--config",
            str(toml),
        ]
    )
    assert code == 0
    assert no_real_server.created == []
