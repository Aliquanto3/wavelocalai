"""Arrêt propre : SIGINT et fichier STOP lèvent un drapeau lu entre deux unités (AD-13)."""

import logging
import signal

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common import stop as stop_module
from scripts.quality_bench.common.stop import StopFlag


def test_stop_file_present_at_launch_removed_and_logged(caplog):
    stop_path = paths.generation_stop_path("c1")
    stop_path.parent.mkdir(parents=True)
    stop_path.write_text("", encoding="utf-8")
    with caplog.at_level(logging.WARNING), StopFlag(stop_path) as stop:
        assert not stop_path.exists()
        assert not stop.should_stop()
    assert "STOP présent au lancement" in caplog.text


def test_stop_file_during_run_raises_flag_and_is_removed_at_exit():
    stop_path = paths.generation_stop_path("c1")
    stop_path.parent.mkdir(parents=True)
    with StopFlag(stop_path) as stop:
        assert not stop.should_stop()
        stop_path.write_text("", encoding="utf-8")  # l'opérateur crée STOP
        assert stop.should_stop()
        assert stop.should_stop()  # le drapeau reste levé
        assert "STOP" in stop.reason
    assert not stop_path.exists()


def test_sigint_only_raises_flag_and_handler_restored():
    previous = signal.getsignal(signal.SIGINT)
    stop_path = paths.generation_stop_path("c1")
    units_done = 0
    with StopFlag(stop_path) as stop:
        for _ in range(5):
            if stop.should_stop():
                break
            signal.raise_signal(signal.SIGINT)  # Ctrl+C pendant l'unité : pas d'exception
            units_done += 1  # l'unité en cours se termine
        assert stop.reason == "SIGINT"
    assert units_done == 1
    assert signal.getsignal(signal.SIGINT) is previous


def test_sigint_logged_at_next_check_not_in_handler(caplog):
    with caplog.at_level(logging.WARNING), StopFlag(paths.generation_stop_path("c1")) as stop:
        signal.raise_signal(signal.SIGINT)
        assert "Arrêt demandé" not in caplog.text  # le gestionnaire ne journalise rien
        assert stop.should_stop()
        assert caplog.text.count("Arrêt demandé") == 1
        assert stop.should_stop()
        assert caplog.text.count("Arrêt demandé") == 1


def test_second_sigint_raises_keyboard_interrupt():
    with StopFlag(paths.generation_stop_path("c1")) as stop:
        signal.raise_signal(signal.SIGINT)
        assert stop.should_stop()
        with pytest.raises(KeyboardInterrupt):
            signal.raise_signal(signal.SIGINT)


def test_previous_handler_none_restored_as_default(monkeypatch):
    calls = []

    def fake_signal(signum, handler):
        calls.append(handler)
        return None  # gestionnaire installé hors de Python

    monkeypatch.setattr(stop_module.signal, "signal", fake_signal)
    with StopFlag(paths.generation_stop_path("c1")):
        pass
    assert calls[-1] is signal.SIG_DFL


def test_absent_stop_file_at_launch_not_logged(caplog):
    with caplog.at_level(logging.WARNING), StopFlag(paths.generation_stop_path("c1")):
        pass
    assert "STOP présent" not in caplog.text
