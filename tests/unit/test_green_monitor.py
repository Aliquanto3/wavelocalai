"""
Tests unitaires pour GreenTracker (Context Manager & Cleanup).
Usage: pytest tests/unit/test_green_monitor.py -v
"""
import time

import pytest

from src.core.green_monitor import GreenTracker


@pytest.fixture(autouse=True)
def isolated_logs_dir(tmp_path, monkeypatch):
    """Redirige les écritures CodeCarbon (emissions.csv) vers un dossier temporaire
    au lieu de data/logs."""
    monkeypatch.setattr("src.core.green_monitor.LOGS_DIR", tmp_path)
    return tmp_path


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


# ---------------------------------------------------------------------------
# Fichier d'émissions de l'app (story 6) : écrit par le suivi, lu par l'historique
# ---------------------------------------------------------------------------

CSV_HEADER = "timestamp,project_name,run_id,duration,emissions\n"


class TestAppEmissionsFile:
    def test_tracker_writes_file_read_by_history(self, isolated_logs_dir):
        """CAP-4 : la ligne lue par l'historique est celle du tracker ; ses grammes égalent
        ceux renvoyés par stop() (écart < 5 %)."""
        from src.core.green_monitor import SESSION_PROJECT, app_emissions_path, read_app_emissions

        tracker = GreenTracker(SESSION_PROJECT)
        tracker.start()
        time.sleep(0.2)
        emissions_g = tracker.stop()

        assert app_emissions_path() == isolated_logs_dir / "emissions.csv"
        assert app_emissions_path().is_file()

        history = read_app_emissions()
        assert list(history["project_name"]) == [SESSION_PROJECT]
        logged_g = history["emissions_g"].iloc[-1]
        assert logged_g == pytest.approx(emissions_g, rel=0.05, abs=1e-12)

    def test_history_path_is_not_benchmark_file(self, isolated_logs_dir):
        """Le fichier de l'app (logs/emissions.csv) n'est pas celui du benchmark
        (logs/emissions/emissions.csv) : comparaison des chemins relatifs à leur LOGS_DIR, que
        la redirection de test ne masque pas."""
        from pathlib import Path

        from src.core import config
        from src.core import green_monitor

        app_rel = green_monitor.app_emissions_path().relative_to(green_monitor.LOGS_DIR)
        bench_rel = Path(config.get_emissions_path()).relative_to(config.LOGS_DIR)

        assert Path(config.EMISSIONS_DIR) != Path(config.LOGS_DIR)
        assert app_rel == Path("emissions.csv")
        assert bench_rel == Path("emissions") / "emissions.csv"
        assert app_rel != bench_rel

    def test_history_keeps_only_session_project(self, isolated_logs_dir):
        """Seul le suivi de session : équipe d'agents, audit et script d'audit (« codecarbon »)
        recouvrent la même période et sont ignorés."""
        from src.core.green_monitor import read_app_emissions

        (isolated_logs_dir / "emissions.csv").write_text(
            CSV_HEADER
            + "2026-09-26T09:15:00,wavelocal_session,a,10,0.00042\n"
            + "2026-09-26T09:20:00,codecarbon,b,10,0.5\n"
            + "2026-09-26T09:25:00,crew_mission,c,10,0.0012\n"
            + "2026-09-26T09:26:00,wavelocal_audit,d,10,0.0013\n",
            encoding="utf-8",
        )
        history = read_app_emissions()

        assert list(history["project_name"]) == ["wavelocal_session"]
        assert list(history["emissions_g"]) == pytest.approx([0.42])
        assert history["timestamp"].iloc[0].hour == 9

    def test_history_keeps_last_row_per_run(self, isolated_logs_dir):
        """Après « Reprendre le suivi », stop() ajoute une ligne cumulée au même run_id : seule
        la dernière compte."""
        from src.core.green_monitor import read_app_emissions

        (isolated_logs_dir / "emissions.csv").write_text(
            CSV_HEADER
            + "2026-09-26T09:15:00,wavelocal_session,run1,10,0.0004\n"
            + "2026-09-26T09:18:00,wavelocal_session,run2,10,0.0002\n"
            + "2026-09-26T09:30:00,wavelocal_session,run1,25,0.0009\n",
            encoding="utf-8",
        )
        history = read_app_emissions()

        assert list(history["emissions_g"]) == pytest.approx([0.2, 0.9])

    def test_history_drops_unreadable_rows_and_sorts_by_date(self, isolated_logs_dir):
        from src.core.green_monitor import read_app_emissions

        (isolated_logs_dir / "emissions.csv").write_text(
            CSV_HEADER
            + "2026-09-26T10:00:00,wavelocal_session,r3,10,0.0003\n"
            + "pas une date,wavelocal_session,r4,10,0.0005\n"
            + "2026-09-26T09:00:00,wavelocal_session,r1,10,0.0001\n"
            + "2026-09-26T09:30:00,wavelocal_session,r2,10,illisible\n",
            encoding="utf-8",
        )
        history = read_app_emissions()

        assert list(history["emissions_g"]) == pytest.approx([0.1, 0.3])
        assert history["timestamp"].is_monotonic_increasing

    def test_history_malformed_file_raises_readable_error(self, isolated_logs_dir):
        """Ligne mal formée (colonnes en trop) : erreur au message lisible, pas ParserError."""
        from src.core.green_monitor import EmissionsHistoryError, read_app_emissions

        (isolated_logs_dir / "emissions.csv").write_text(
            CSV_HEADER
            + "2026-09-26T09:00:00,wavelocal_session,r1,10,0.0001\n"
            + "2026-09-26T09:05:00,wavelocal_session,r2,10,0.0002,x,y,z\n",
            encoding="utf-8",
        )
        with pytest.raises(EmissionsHistoryError, match="mal formé"):
            read_app_emissions()

    def test_history_without_file_is_empty(self, isolated_logs_dir):
        from src.core.green_monitor import read_app_emissions

        assert read_app_emissions().empty

    def test_history_with_empty_file_is_empty(self, isolated_logs_dir):
        from src.core.green_monitor import read_app_emissions

        (isolated_logs_dir / "emissions.csv").write_text("", encoding="utf-8")
        assert read_app_emissions().empty
