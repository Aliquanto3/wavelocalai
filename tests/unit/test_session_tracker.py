"""
Tracker CodeCarbon unique par processus et mesure par session (différence de compteurs).

Usage: python -m pytest tests/unit/test_session_tracker.py -v
"""

import threading
import time

import pandas as pd
import pytest

from src.core import green_monitor
from src.core.green_monitor import (
    SESSION_PROJECT,
    TRACKER_FAILED_TEXT,
    GreenTracker,
    SessionTracker,
    ensure_shared_tracker,
    shared_emissions_kg,
    shared_tracker_failure,
    stop_shared_tracker,
)


class FakeProcessTracker:
    """Tracker du processus simulé : compteur cumulé en kg réglé par le test."""

    created: list["FakeProcessTracker"] = []

    def __init__(self):
        self._is_running = False
        self.total_kg = 0.0
        self.stopped = False
        FakeProcessTracker.created.append(self)

    def start(self):
        self._is_running = True

    def stop(self):
        self._is_running = False
        self.stopped = True
        return self.total_kg

    def snapshot_kg(self):
        # `total_kg` à None : lecture en échec (flush de CodeCarbon qui renvoie None).
        return self.total_kg if self._is_running else None


@pytest.fixture(autouse=True)
def fake_process(tmp_path, monkeypatch):
    """Tracker du processus simulé, état du module remis à zéro avant et après chaque test."""
    monkeypatch.setattr(green_monitor, "LOGS_DIR", tmp_path)
    FakeProcessTracker.created = []
    monkeypatch.setattr(green_monitor, "_new_shared_tracker", FakeProcessTracker)
    stop_shared_tracker()
    yield
    stop_shared_tracker()


def _ready_tracker() -> FakeProcessTracker:
    """Lance le tracker du processus et attend son démarrage de fond."""
    ensure_shared_tracker()
    deadline = time.monotonic() + 10
    while shared_emissions_kg() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    return FakeProcessTracker.created[-1]


def test_one_tracker_per_process():
    """Dix sessions, un seul tracker CodeCarbon."""
    sessions = [SessionTracker() for _ in range(10)]
    for session in sessions:
        session.start()
    _ready_tracker()

    assert len(FakeProcessTracker.created) == 1


def test_start_does_not_wait_for_tracker(monkeypatch):
    """L'initialisation de CodeCarbon (jusqu'à 9 s) ne bloque pas le premier rendu."""
    release = threading.Event()
    entered = threading.Event()

    class SlowTracker(FakeProcessTracker):
        def __init__(self):
            entered.set()
            release.wait(10)
            super().__init__()

    monkeypatch.setattr(green_monitor, "_new_shared_tracker", SlowTracker)
    session = SessionTracker()

    started = time.perf_counter()
    session.start()
    elapsed = time.perf_counter() - started

    assert session._is_running
    assert elapsed < 1.0
    assert entered.wait(5)
    assert shared_emissions_kg() is None  # pas encore prêt
    release.set()
    _ready_tracker()
    assert shared_emissions_kg() == 0.0


def test_sessions_measure_by_counter_difference():
    """Deux sessions décalées sur le même compteur : chacune ne compte que ses émissions."""
    first = SessionTracker()
    first.start()
    process = _ready_tracker()

    process.total_kg = 0.001  # 1 g avant l'arrivée de la seconde session
    second = SessionTracker()
    second.start()
    process.total_kg = 0.0015

    assert first.stop() == pytest.approx(1.5)
    assert second.stop() == pytest.approx(0.5)


def test_resume_accumulates_and_skips_pause():
    session = SessionTracker()
    session.start()
    process = _ready_tracker()

    process.total_kg = 0.0002
    assert session.stop() == pytest.approx(0.2)
    process.total_kg = 0.0010  # pause : 0,8 g non comptés
    session.start()
    process.total_kg = 0.0013

    assert session.stop() == pytest.approx(0.5)


def test_stop_and_double_calls_are_safe():
    session = SessionTracker()
    assert session.stop() == 0.0  # jamais démarré
    session.start()
    session.start()  # sans effet
    _ready_tracker()

    assert session.stop() == pytest.approx(0.0)
    assert session.stop() == 0.0
    assert not session._is_running


def test_failed_process_tracker_gives_unknown(monkeypatch):
    """CodeCarbon qui échoue au démarrage : la session reste utilisable, sa mesure est
    inconnue (None, jamais 0 g) et la cause est exposée à l'interface."""

    def _boom():
        raise RuntimeError("cpuinfo")

    monkeypatch.setattr(green_monitor, "_new_shared_tracker", _boom)
    session = SessionTracker()
    session.start()
    green_monitor._shared_thread.join(5)

    assert session._is_running
    assert shared_emissions_kg() is None
    assert session.stop() is None
    assert shared_tracker_failure() == TRACKER_FAILED_TEXT


def test_unreadable_base_gives_unknown_not_overcount():
    """Compteur du processus déjà à 500 g, illisible au démarrage de la session : la base
    n'est jamais posée à 0 (sinon stop() rendrait 500,4 g au lieu de 0,4 g)."""
    process = _ready_tracker()
    process.total_kg = None  # flush() de CodeCarbon en échec
    session = SessionTracker()
    session.start()
    process.total_kg = 0.5004

    assert session.stop() is None
    # « Reprendre » ne rend pas la session de nouveau mesurable : un segment manque.
    session.start()
    process.total_kg = 0.5010
    assert session.stop() is None


def test_unreadable_end_gives_unknown():
    process = _ready_tracker()
    process.total_kg = 0.5
    session = SessionTracker()
    session.start()
    process.total_kg = None

    assert session.stop() is None


def test_codecarbon_lock_taken_gives_unknown(monkeypatch):
    """CodeCarbon trouve son verrou (second lancement, verrou resté) : il ne lève rien et ne
    mesure pas. Le tracker du processus est tenu pour en échec, avec un message clair."""

    class LockedTracker(FakeProcessTracker):
        def start(self):
            super().start()
            self.tracker = type("Cc", (), {"_another_instance_already_running": True})()

    monkeypatch.setattr(green_monitor, "_new_shared_tracker", LockedTracker)
    session = SessionTracker()
    session.start()
    green_monitor._shared_thread.join(5)

    assert shared_emissions_kg() is None
    assert "verrou" in shared_tracker_failure()
    assert session.stop() is None


@pytest.mark.parametrize(("flushed", "expected"), [(None, None), (0.0, 0.0), (0.002, 0.002)])
def test_green_tracker_snapshot_keeps_unknown(flushed, expected):
    """`flush()` de CodeCarbon renvoie None en échec (décoré `@suppress(Exception)`) :
    `snapshot_kg` le garde inconnu ; un vrai 0 reste 0."""
    tracker = GreenTracker.__new__(GreenTracker)
    tracker.project_name = SESSION_PROJECT
    tracker._is_running = True
    tracker.tracker = type("Cc", (), {"flush": lambda self: flushed})()

    assert tracker.snapshot_kg() == expected


def test_stop_shared_tracker_stops_and_rearms():
    session = SessionTracker()
    session.start()
    process = _ready_tracker()

    stop_shared_tracker()

    assert process.stopped
    session.start()  # réarmé : nouveau tracker
    new_process = _ready_tracker()
    assert new_process is not process
    assert len(FakeProcessTracker.created) == 2


def test_real_codecarbon_session_is_written_to_history(tmp_path, monkeypatch):
    """Avec le vrai CodeCarbon : une session mesure un total fini, et l'arrêt du tracker du
    processus écrit une ligne `SESSION_PROJECT` que l'historique relit."""
    monkeypatch.setattr(
        green_monitor, "_new_shared_tracker", lambda: green_monitor.GreenTracker(SESSION_PROJECT)
    )
    session = SessionTracker()
    session.start()
    # Attente bornée du démarrage (py-cpuinfo : jusqu'à une dizaine de secondes).
    green_monitor._shared_thread.join(60)
    failure = shared_tracker_failure()
    if failure and "verrou" in failure:
        # Un autre CodeCarbon tourne sur la machine (l'application lancée à côté) : la
        # mesure réelle n'est pas possible ici, ce n'est pas un défaut du code.
        pytest.skip("verrou CodeCarbon déjà pris par une autre instance")
    assert shared_emissions_kg() is not None, failure or "CodeCarbon n'a pas démarré"
    time.sleep(1.5)

    emissions_g = session.stop()
    stop_shared_tracker()

    assert isinstance(emissions_g, float)
    assert emissions_g >= 0.0
    history = green_monitor.read_app_emissions()
    assert isinstance(history, pd.DataFrame)
    assert len(history) == 1  # une ligne par run, la dernière
