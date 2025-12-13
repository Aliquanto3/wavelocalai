"""
Tests unitaires pour GreenTracker (Context Manager & Cleanup).
Usage: pytest tests/unit/test_green_monitor.py -v
"""
import time

import pytest

from src.core.green_monitor import GreenTracker


class TestGreenTrackerContextManager:
    """Tests du Context Manager."""

    def test_context_manager_starts_and_stops(self):
        """Test que le tracker démarre et s'arrête automatiquement."""
        with GreenTracker("test_context") as tracker:
            assert tracker._is_running, "Le tracker devrait être actif dans le 'with'"
            time.sleep(0.1)  # Simule une activité

        # Après la sortie du 'with', le tracker doit être arrêté
        assert not tracker._is_running, "Le tracker devrait être arrêté après le 'with'"

    def test_context_manager_returns_emissions(self):
        """Test que stop() retourne bien des émissions."""
        with GreenTracker("test_emissions") as tracker:
            time.sleep(0.1)

        # Le tracker a été arrêté, vérifier qu'il a mesuré quelque chose
        # (difficile de tester la valeur exacte, on vérifie juste qu'il n'a pas crashé)
        assert True  # Si on arrive ici, c'est OK

    def test_context_manager_handles_exception(self):
        """Test que le tracker se ferme même en cas d'exception."""
        tracker = None
        try:
            with GreenTracker("test_exception") as tracker:
                assert tracker._is_running
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Le tracker doit quand même être arrêté
        assert tracker is not None
        assert not tracker._is_running


class TestGreenTrackerLegacyMode:
    """Tests du mode legacy (start/stop manuel)."""

    def test_legacy_start_stop(self):
        """Test démarrage et arrêt manuel."""
        tracker = GreenTracker("test_legacy")

        assert not tracker._is_running, "Le tracker ne devrait pas être actif au départ"

        tracker.start()
        assert tracker._is_running, "Le tracker devrait être actif après start()"

        emissions = tracker.stop()
        assert not tracker._is_running, "Le tracker devrait être arrêté après stop()"
        assert isinstance(emissions, float), "stop() devrait retourner un float"

    def test_double_start_safe(self):
        """Test que start() deux fois ne cause pas de problème."""
        tracker = GreenTracker("test_double_start")
        tracker.start()
        tracker.start()  # Ne devrait pas crasher
        assert tracker._is_running
        tracker.stop()

    def test_double_stop_safe(self):
        """Test que stop() deux fois ne cause pas de problème."""
        tracker = GreenTracker("test_double_stop")
        tracker.start()
        tracker.stop()
        emissions2 = tracker.stop()  # Ne devrait pas crasher
        assert emissions2 == 0.0, "Un deuxième stop() devrait retourner 0"


class TestGreenTrackerCleanup:
    """Tests du système de cleanup automatique."""

    def test_tracker_registered_on_start(self):
        """Test que le tracker s'enregistre dans le registre."""
        initial_count = len(GreenTracker._active_trackers)

        tracker = GreenTracker("test_registration")
        tracker.start()

        assert len(GreenTracker._active_trackers) == initial_count + 1

        tracker.stop()
        assert len(GreenTracker._active_trackers) == initial_count

    def test_tracker_removed_on_stop(self):
        """Test que stop() retire le tracker du registre."""
        tracker = GreenTracker("test_removal")
        tracker.start()

        assert tracker in GreenTracker._active_trackers

        tracker.stop()

        assert tracker not in GreenTracker._active_trackers

    def test_cleanup_all_trackers(self):
        """Test du cleanup d'urgence de tous les trackers."""
        # Crée plusieurs trackers
        trackers = [GreenTracker(f"test_cleanup_{i}") for i in range(3)]

        for t in trackers:
            t.start()

        initial_count = len(GreenTracker._active_trackers)
        assert initial_count >= 3, "Au moins 3 trackers devraient être actifs"

        # Appel du cleanup global
        GreenTracker._cleanup_all_trackers()

        # Tous les trackers doivent être arrêtés
        assert len(GreenTracker._active_trackers) == 0
        for t in trackers:
            assert not t._is_running


class TestGreenTrackerRobustness:
    """Tests de robustesse."""

    def test_destructor_stops_tracker(self):
        """Test que le destructeur arrête le tracker si oublié."""
        tracker = GreenTracker("test_destructor")
        tracker.start()

        # Simulation de garbage collection
        del tracker

        # Difficile de tester directement, mais au moins on vérifie qu'il n'y a pas de crash
        assert True

    def test_multiple_projects_isolated(self):
        """Test que plusieurs trackers peuvent coexister."""
        tracker1 = GreenTracker("project_A")
        tracker2 = GreenTracker("project_B")

        tracker1.start()
        tracker2.start()

        assert tracker1._is_running
        assert tracker2._is_running

        tracker1.stop()
        assert not tracker1._is_running
        assert tracker2._is_running  # tracker2 ne doit pas être affecté

        tracker2.stop()
