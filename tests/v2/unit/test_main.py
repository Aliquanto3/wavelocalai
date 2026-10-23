"""Lanceur : port occupé, verrou du dossier de données, réglages invalides (sans serveur)."""

from __future__ import annotations

import socket

import pytest

from wavelocalai.__main__ import main
from wavelocalai.store.datadir import DataDirLock
from wavelocalai.store.logs import close_logging
from wavelocalai.web.server import PortBusyError, bind_socket

from ..conftest import closed_port


@pytest.fixture(autouse=True)
def _logs_closed():
    yield
    close_logging()


@pytest.fixture
def busy_port():
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen()
    yield holder.getsockname()[1]
    holder.close()


def test_bind_listens_on_loopback_only():
    port = closed_port()
    sock = bind_socket(port)
    try:
        assert sock.getsockname() == ("127.0.0.1", port)
    finally:
        sock.close()


def test_busy_port_is_refused_with_a_clear_message(busy_port):
    with pytest.raises(PortBusyError, match=f"port {busy_port} est occupé"):
        bind_socket(busy_port)


def test_second_launch_refuses_when_port_is_busy(tmp_path, busy_port, capsys):
    code = main(["--port", str(busy_port), "--data-dir", str(tmp_path / "data")])
    assert code == 1
    assert f"port {busy_port} est occupé" in capsys.readouterr().err
    with DataDirLock(tmp_path / "data"):  # le verrou a bien été relâché
        pass


def test_second_launch_refuses_when_data_dir_is_locked(tmp_path, capsys):
    data = tmp_path / "data"
    with DataDirLock(data):
        code = main(["--port", str(closed_port()), "--data-dir", str(data)])
    assert code == 1
    err = capsys.readouterr().err
    assert "autre wavelocalai-v2" in err and str(data) in err


def test_second_launch_writes_nothing_in_the_live_servers_log(tmp_path, capsys):
    """C5 : `setup_logging` vient après le verrou ; un lancement refusé laisse le journal du
    serveur vivant intact (il n'ouvre même pas le fichier)."""
    data = tmp_path / "data"
    log = data / "logs" / "wavelocalai.log"
    with DataDirLock(data):
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("ligne du serveur vivant", encoding="utf-8")
        before = log.stat()
        code = main(["--port", str(closed_port()), "--data-dir", str(data)])
        assert code == 1
        assert log.read_text(encoding="utf-8") == "ligne du serveur vivant"
        assert log.stat().st_mtime_ns == before.st_mtime_ns
    assert "autre wavelocalai-v2" in capsys.readouterr().err


def test_lock_failure_for_another_reason_is_not_reported_as_a_live_server(tmp_path, capsys):
    """C5 : un verrou impossible à créer (droits, disque) dit sa vraie cause."""
    from wavelocalai.store.datadir import LOCK_NAME

    data = tmp_path / "data"
    data.mkdir()
    (data / LOCK_NAME).mkdir()
    assert main(["--port", str(closed_port()), "--data-dir", str(data)]) == 1
    err = capsys.readouterr().err
    assert "Impossible de créer le verrou" in err and "autre wavelocalai-v2" not in err
    assert not (data / "logs" / "wavelocalai.log").exists()


def test_onedrive_data_dir_is_logged_as_a_warning(tmp_path, busy_port):
    data = tmp_path / "OneDrive - Test" / "data"
    main(["--port", str(busy_port), "--data-dir", str(data)])
    log = (data / "logs" / "wavelocalai.log").read_text(encoding="utf-8")
    assert "OneDrive" in log and "WARNING" in log


def test_invalid_settings_stop_the_launch(tmp_path, capsys):
    bad = tmp_path / "wavelocalai.toml"
    bad.write_text("[server\n", encoding="utf-8")
    assert main(["--config", str(bad), "--data-dir", str(tmp_path / "data")]) == 2
    assert "illisible" in capsys.readouterr().err
