"""
Tests unitaires pour HardwareMonitor.
Usage: pytest tests/unit/test_hardware_monitor.py -v
"""
import pytest

from src.core.green_monitor import HardwareMonitor, SystemMetrics


class TestHardwareMonitorSystemInfo:
    """Tests de get_system_info."""

    def test_get_system_info_structure(self):
        """Test que get_system_info retourne la structure attendue."""
        info = HardwareMonitor.get_system_info()

        # Vérifier les clés obligatoires
        required_keys = [
            "os",
            "os_release",
            "processor",
            "cpu_cores_physical",
            "cpu_cores_logical",
            "cpu_brand",
        ]
        for key in required_keys:
            assert key in info, f"La clé '{key}' devrait être présente"

    def test_get_system_info_types(self):
        """Test que les types de données sont corrects."""
        info = HardwareMonitor.get_system_info()

        assert isinstance(info["os"], str)
        assert isinstance(info["os_release"], str)
        assert isinstance(info["cpu_cores_physical"], (int, type(None)))
        assert isinstance(info["cpu_cores_logical"], int)
        assert isinstance(info["cpu_brand"], str)

    def test_cpu_cores_logical_positive(self):
        """Test que le nombre de cores logiques est positif."""
        info = HardwareMonitor.get_system_info()

        assert info["cpu_cores_logical"] > 0, "Devrait avoir au moins 1 core logique"

    def test_cpu_brand_not_empty(self):
        """Test que la marque CPU n'est pas vide."""
        info = HardwareMonitor.get_system_info()

        assert len(info["cpu_brand"]) > 0, "La marque CPU ne devrait pas être vide"


class TestHardwareMonitorRealtimeMetrics:
    """Tests de get_realtime_metrics."""

    def test_realtime_metrics_structure(self):
        """Test que get_realtime_metrics retourne un SystemMetrics."""
        metrics = HardwareMonitor.get_realtime_metrics()

        assert isinstance(metrics, SystemMetrics)

    def test_cpu_usage_valid_range(self):
        """Test que l'usage CPU est dans [0, 100]."""
        metrics = HardwareMonitor.get_realtime_metrics()

        assert 0 <= metrics.cpu_usage_percent <= 100, "L'usage CPU devrait être entre 0 et 100%"

    def test_ram_usage_valid_range(self):
        """Test que l'usage RAM est dans [0, 100]."""
        metrics = HardwareMonitor.get_realtime_metrics()

        assert 0 <= metrics.ram_usage_percent <= 100, "L'usage RAM devrait être entre 0 et 100%"

    def test_ram_total_positive(self):
        """Test que la RAM totale est positive."""
        metrics = HardwareMonitor.get_realtime_metrics()

        assert metrics.ram_total_gb > 0, "La RAM totale devrait être > 0"

    def test_ram_used_consistent(self):
        """Test que RAM utilisée <= RAM totale."""
        metrics = HardwareMonitor.get_realtime_metrics()

        assert (
            metrics.ram_used_gb <= metrics.ram_total_gb
        ), "La RAM utilisée ne peut pas dépasser la RAM totale"

    def test_gpu_name_not_none(self):
        """Test que gpu_name a toujours une valeur."""
        metrics = HardwareMonitor.get_realtime_metrics()

        # Devrait être soit un nom de GPU, soit "N/A (CPU Only)"
        assert metrics.gpu_name is not None
        assert isinstance(metrics.gpu_name, str)
        assert len(metrics.gpu_name) > 0

    def test_gpu_memory_consistency(self):
        """Test que les métriques GPU sont cohérentes."""
        metrics = HardwareMonitor.get_realtime_metrics()

        # Si gpu_name est "N/A", les métriques GPU devraient être None
        if "N/A" in metrics.gpu_name or "CPU Only" in metrics.gpu_name:
            # Tolérance : certains champs peuvent être à 0 ou None
            pass
        else:
            # Si GPU détecté, les métriques devraient être présentes
            if metrics.gpu_memory_total_gb is not None:
                assert metrics.gpu_memory_total_gb > 0
                if metrics.gpu_memory_used_gb is not None:
                    assert metrics.gpu_memory_used_gb <= metrics.gpu_memory_total_gb

    def test_multiple_calls_consistency(self):
        """Test que plusieurs appels consécutifs donnent des résultats cohérents."""
        metrics1 = HardwareMonitor.get_realtime_metrics()
        metrics2 = HardwareMonitor.get_realtime_metrics()

        # La RAM totale ne devrait pas changer
        assert metrics1.ram_total_gb == metrics2.ram_total_gb

        # Le nom GPU ne devrait pas changer
        assert metrics1.gpu_name == metrics2.gpu_name

        # L'usage CPU/RAM peut varier, mais devrait rester dans les limites
        assert 0 <= metrics2.cpu_usage_percent <= 100
        assert 0 <= metrics2.ram_usage_percent <= 100


class TestSystemMetricsDataclass:
    """Tests de la dataclass SystemMetrics."""

    def test_creation_minimal(self):
        """Test création avec paramètres minimaux."""
        metrics = SystemMetrics(
            cpu_usage_percent=50.0, ram_usage_percent=60.0, ram_total_gb=16.0, ram_used_gb=9.6
        )

        assert metrics.cpu_usage_percent == 50.0
        assert metrics.ram_usage_percent == 60.0
        assert metrics.gpu_name is None
        assert metrics.co2_emissions_kg == 0.0

    def test_creation_complete(self):
        """Test création avec tous les paramètres."""
        metrics = SystemMetrics(
            cpu_usage_percent=30.0,
            ram_usage_percent=40.0,
            ram_total_gb=32.0,
            ram_used_gb=12.8,
            gpu_name="NVIDIA RTX 4090",
            gpu_memory_total_gb=24.0,
            gpu_memory_used_gb=8.5,
            co2_emissions_kg=0.05,
        )

        assert metrics.gpu_name == "NVIDIA RTX 4090"
        assert metrics.gpu_memory_total_gb == 24.0
        assert metrics.gpu_memory_used_gb == 8.5
        assert metrics.co2_emissions_kg == 0.05
