import atexit
import logging
import platform
from dataclasses import dataclass
from typing import Any, Optional

import cpuinfo
import psutil
from codecarbon import OfflineEmissionsTracker

from src.core.config import DEFAULT_COUNTRY_ISO_CODE, LOGS_DIR

# Logging
logger = logging.getLogger(__name__)

# --- Patch Lead Tech : Import Sécurisé de GPUtil ---
try:
    import GPUtil

    GPU_LIB_AVAILABLE = True
except ImportError:
    GPU_LIB_AVAILABLE = False


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
    def get_system_info() -> dict[str, Any]:
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
            ram_used_gb=round(mem.used / (1024**3), 2),
        )

        # 2. GPU (Sécurisé)
        metrics.gpu_name = "N/A (CPU Only)"

        if GPU_LIB_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    metrics.gpu_name = gpu.name
                    metrics.gpu_memory_total_gb = round(gpu.memoryTotal / 1024, 2)
                    metrics.gpu_memory_used_gb = round(gpu.memoryUsed / 1024, 2)
            except Exception:
                pass

        return metrics


class GreenTracker:
    """
    Wrapper autour de CodeCarbon avec gestion automatique du cycle de vie.

    Usage recommandé (Context Manager) :
        with GreenTracker("my_project") as tracker:
            # Votre code ici
            pass
        # Le tracker est automatiquement arrêté

    Usage legacy (compatible avec le code existant) :
        tracker = GreenTracker("my_project")
        tracker.start()
        # ... code ...
        tracker.stop()  # ⚠️ Ne pas oublier !
    """

    # Registre global des trackers actifs pour cleanup
    _active_trackers: list["GreenTracker"] = []
    _atexit_registered = False

    def __init__(self, project_name="wavelocal_audit"):
        # Création du dossier logs
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        self.project_name = project_name
        self.tracker = OfflineEmissionsTracker(
            project_name=project_name,
            output_dir=str(LOGS_DIR),
            country_iso_code=DEFAULT_COUNTRY_ISO_CODE,
            log_level="error",
        )
        self._is_running = False

        # Enregistrement du hook atexit (une seule fois pour la classe)
        if not GreenTracker._atexit_registered:
            atexit.register(GreenTracker._cleanup_all_trackers)
            GreenTracker._atexit_registered = True
            logger.info("✅ Hook atexit enregistré pour GreenTracker")

    def start(self):
        """Démarre le tracking et s'enregistre dans le registre global."""
        if not self._is_running:
            self.tracker.start()
            self._is_running = True
            # Ajout au registre des trackers actifs
            if self not in GreenTracker._active_trackers:
                GreenTracker._active_trackers.append(self)
                logger.info(f"✅ Tracker '{self.project_name}' démarré et enregistré")

    def stop(self) -> float:
        """Arrête le tracking et se retire du registre."""
        if self._is_running:
            try:
                emissions = self.tracker.stop()
                self._is_running = False
                # Retrait du registre
                if self in GreenTracker._active_trackers:
                    GreenTracker._active_trackers.remove(self)
                    logger.info(f"✅ Tracker '{self.project_name}' arrêté proprement")
                return emissions
            except Exception as e:
                logger.error(f"Erreur lors de l'arrêt du tracker : {e}")
                return 0.0
        return 0.0

    # ========================================
    # CONTEXT MANAGER (Recommandé)
    # ========================================

    def __enter__(self):
        """Support du 'with' statement."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cleanup automatique à la sortie du 'with'."""
        if self._is_running:
            emissions = self.stop()
            logger.info(f"📊 Tracker '{self.project_name}' : {emissions:.6f} kg CO2eq")
        return False  # Ne supprime pas les exceptions

    # ========================================
    # CLEANUP GLOBAL (Sécurité)
    # ========================================

    @classmethod
    def _cleanup_all_trackers(cls):
        """
        Arrête tous les trackers actifs (appelé par atexit).
        Protection contre les fermetures brutales de l'application.
        """
        if cls._active_trackers:
            logger.warning(
                f"⚠️ Cleanup d'urgence : {len(cls._active_trackers)} tracker(s) encore actif(s)"
            )
            for tracker in list(
                cls._active_trackers
            ):  # Copie pour éviter modification pendant itération
                try:
                    if tracker._is_running:
                        tracker.stop()
                        logger.info(f"🧹 Tracker '{tracker.project_name}' nettoyé")
                except Exception as e:
                    logger.error(f"Erreur cleanup tracker '{tracker.project_name}' : {e}")
            cls._active_trackers.clear()

    def __del__(self):
        """Destructeur : cleanup de sécurité si l'objet est garbage collecté."""
        if self._is_running:
            logger.warning(f"⚠️ Tracker '{self.project_name}' détruit sans avoir été arrêté")
            try:
                self.stop()
            except Exception:
                pass
