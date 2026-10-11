"""Verrous de fichier non bloquants (AD-12)."""

import os

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.locks import FileLock, LockBusyError
from tests.quality_bench.processes import kill_hard, start_append_loop


def test_lock_writes_holder_info_and_releases():
    lock_path = paths.machine_lock_path()
    with FileLock(lock_path) as lock:
        assert lock.held
        assert f"pid={os.getpid()}" in lock_path.read_text(encoding="utf-8")
    assert not lock.held
    with FileLock(lock_path):  # libéré : reprenable
        pass


def test_second_holder_in_same_process_refused():
    lock_path = paths.machine_lock_path()
    with FileLock(lock_path), pytest.raises(LockBusyError) as excinfo:
        FileLock(lock_path).acquire()
    assert f"pid={os.getpid()}" in str(excinfo.value)
    assert excinfo.value.path == lock_path


def test_double_acquire_on_same_object_refused():
    lock = FileLock(paths.machine_lock_path())
    with lock, pytest.raises(RuntimeError):
        lock.acquire()


def test_lock_held_by_other_process_refused_then_freed_by_its_death(tmp_path):
    """Second processus sur le même verrou : refus immédiat, PID du détenteur affiché ; le
    système libère le verrou à la mort du détenteur (pas de verrou orphelin)."""
    lock_path = paths.generation_lock_path("c1")
    holder, holder_pid = start_append_loop(paths.generation_path("c1"), lock_path, 1000, 1)
    try:
        with pytest.raises(LockBusyError) as excinfo:
            FileLock(lock_path).acquire()
        assert f"pid={holder_pid} " in str(excinfo.value)
    finally:
        kill_hard(holder, holder_pid, lock_path)
    with FileLock(lock_path) as lock:
        assert lock.held
