import psutil
import platform
import cpuinfo
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from codecarbon import OfflineEmissionsTracker
from src.core.config import LOGS_DIR, DEFAULT_COUNTRY_ISO_CODE

# --- Patch Lead Tech : Import Sécurisé de GPUtil ---
# GPUtil dépend de distutils (supprimé en Python 3.12). 
# On capture l'erreur pour éviter le crash de l'app si la lib est incompatible.
try:
    import GPUtil
    GPU_LIB_AVAILABLE = True
except ImportError:
    GPU_LIB_AVAILABLE = False
# ---------------------------------------------------

@dataclass
class SystemMetrics:
    """Structure de données standardisée pour l'état du système"""
    cpu_usage_percent: float
    ram_usage_percent: float
    ram_total_gb: float
    ram_used_gb: float
    gpu_name: Optional[str] = None
    gpu_memory_total_gb: Optional[float] = None
    gpu_memory_used_gb: Optional[float] = None
    co2_emissions_kg: float = 0.0

class HardwareMonitor:
    """
    Service responsable de l'audit matériel et de l'estimation carbone.
    """

    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """Récupère les métadonnées statiques du matériel"""
        info = {
            "os": platform.system(),
            "os_release": platform.release(),
            "processor": platform.processor(),
            "cpu_cores_physical": psutil.cpu_count(logical=False),
            "cpu_cores_logical": psutil.cpu_count(logical=True),
        }
        
        try:
            cpu_details = cpuinfo.get_cpu_info()
            info["cpu_brand"] = cpu_details.get("brand_raw", "Unknown CPU")
        except Exception:
            info["cpu_brand"] = platform.processor()

        return info

    @staticmethod
    def get_realtime_metrics() -> SystemMetrics:
        """Récupère les métriques en temps réel"""
        
        # 1. CPU & RAM
        cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        
        metrics = SystemMetrics(
            cpu_usage_percent=cpu_percent,
            ram_usage_percent=mem.percent,
            ram_total_gb=round(mem.total / (1024**3), 2),
            ram_used_gb=round(mem.used / (1024**3), 2)
        )

        # 2. GPU (Sécurisé)
        metrics.gpu_name = "N/A (CPU Only)" # Valeur par défaut
        
        if GPU_LIB_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    metrics.gpu_name = gpu.name
                    metrics.gpu_memory_total_gb = round(gpu.memoryTotal / 1024, 2)
                    metrics.gpu_memory_used_gb = round(gpu.memoryUsed / 1024, 2)
            except Exception:
                # Erreur silencieuse si GPUtil échoue à l'exécution (ex: pas de driver)
                pass
            
        return metrics

class GreenTracker:
    """Wrapper autour de CodeCarbon"""
    
    def __init__(self, project_name="wavelocal_audit"):
        # On s'assure que le dossier logs existe
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        self.tracker = OfflineEmissionsTracker(
            project_name=project_name,
            output_dir=str(LOGS_DIR),
            country_iso_code=DEFAULT_COUNTRY_ISO_CODE,
            log_level="error"
        )
        self._is_running = False

    def start(self):
        if not self._is_running:
            self.tracker.start()
            self._is_running = True

    def stop(self) -> float:
        if self._is_running:
            emissions = self.tracker.stop()
            self._is_running = False
            return emissions
        return 0.0