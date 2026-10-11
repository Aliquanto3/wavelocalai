"""Maintien en éveil : SetThreadExecutionState à l'entrée et dans le finally (AD-13)."""

import threading

import pytest

from scripts.quality_bench.common import keepawake


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    def fake(flags):
        recorded.append(flags)
        return keepawake.ES_CONTINUOUS

    monkeypatch.setattr(keepawake, "_set_thread_execution_state", fake)
    return recorded


def test_flags_on_enter_and_reset_on_exit(monkeypatch, calls):
    monkeypatch.setattr(keepawake, "_is_windows", lambda: True)
    with keepawake.keep_awake():
        assert calls == [0x80000000 | 0x1 | 0x2]
    assert calls == [0x80000003, 0x80000000]


def test_reset_even_on_exception(monkeypatch, calls):
    monkeypatch.setattr(keepawake, "_is_windows", lambda: True)
    with pytest.raises(RuntimeError, match="boom"), keepawake.keep_awake():
        raise RuntimeError("boom")
    assert calls[-1] == keepawake.ES_CONTINUOUS


def test_no_effect_outside_windows(monkeypatch, calls):
    monkeypatch.setattr(keepawake, "_is_windows", lambda: False)
    with keepawake.keep_awake():
        pass
    assert calls == []


def test_refused_outside_main_thread(monkeypatch, calls):
    monkeypatch.setattr(keepawake, "_is_windows", lambda: True)
    errors = []

    def worker():
        try:
            with keepawake.keep_awake():
                pass
        except RuntimeError as exc:
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert errors and calls == []


@pytest.mark.skipif(not keepawake._is_windows(), reason="appel Win32 réel")
def test_real_call_on_windows():
    with keepawake.keep_awake():
        pass
