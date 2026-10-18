"""Cycle de vie du serveur : base migrée au démarrage, runs orphelins, arrêt propre (AD-23)."""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from wavelocalai.__main__ import main
from wavelocalai.store.db import db_path
from wavelocalai.store.logs import close_logging
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, closed_port, make_settings

BASE = f"http://127.0.0.1:{TEST_PORT}"


def _rows(path, sql):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_startup_migrates_the_database_and_opens_an_app_session(tmp_path):
    settings = make_settings(tmp_path)
    path = db_path(settings.data_dir)
    assert not path.exists()
    with TestClient(create_app(settings), base_url=BASE) as client:
        assert client.get("/api/health").status_code == 200
        assert path.is_file()
        assert _rows(path, "PRAGMA user_version") == [(1,)]
        assert _rows(path, "SELECT reason FROM app_sessions") == [("startup",)]


def test_restart_interrupts_orphans_and_clean_stop_cancels_active_runs(tmp_path):
    settings = make_settings(tmp_path)
    path = db_path(settings.data_dir)

    app = create_app(settings)
    with TestClient(app, base_url=BASE) as client:

        async def start_run():
            return await app.state.hub.create_run("chat", models=["m"])

        run = client.portal.call(start_run)
    # Arrêt propre du serveur : le run actif est annulé.
    assert _rows(path, f"SELECT status FROM runs WHERE id = '{run.run_id}'") == [("cancelled",)]

    # Un arrêt brutal laisse un run `running` : le redémarrage l'interrompt.
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO runs (id, kind, app_session, status, started_at) SELECT 'orphelin', 'chat',"
        " id, 'running', '2026-10-18T10:00:00.000Z' FROM app_sessions LIMIT 1"
    )
    conn.execute(
        "INSERT INTO run_events VALUES ('orphelin', 1, 'run_started', '2026-10-18T10:00:00.000Z', '{}')"
    )
    conn.commit()
    conn.close()
    with TestClient(create_app(settings), base_url=BASE):
        assert _rows(path, "SELECT status FROM runs WHERE id = 'orphelin'") == [("interrupted",)]
        last = _rows(
            path, "SELECT seq, type FROM run_events WHERE run_id = 'orphelin' ORDER BY seq"
        )
        assert last == [(1, "run_started"), (2, "run_ended")]
        assert _rows(path, "SELECT count(*) FROM app_sessions") == [(2,)]


def test_launcher_refuses_a_database_newer_than_the_code(tmp_path, capsys):
    data = tmp_path / "data"
    data.mkdir()
    conn = sqlite3.connect(db_path(data))
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    try:
        code = main(["--port", str(closed_port()), "--data-dir", str(data)])
    finally:
        close_logging()
    assert code == 1
    err = capsys.readouterr().err
    assert "version 99" in err and "plus récente" in err
