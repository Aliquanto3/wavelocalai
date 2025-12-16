import atexit
import contextlib
import logging
import os
import platform
from dataclasses import dataclass
from typing import Any

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


# ==========================================
# 1. CONSTANTES & CALIBRATION (SCIENTIFIQUE)
# ==========================================

# --- CONFIGURATION MISTRAL / ECOLOGITS ---
# Source : GenAI Impact / EcoLogits (https://ecologits.ai)
# Formule : E = N_tokens * (alpha * P_actifs + beta)
ALPHA = 8.91e-5  # Pente (Wh par milliard de paramètres)
BETA = 1.43e-3  # Ordonnée à l'origine (Overhead fixe)

# Données de Référence (ACV Mistral Juillet 2025)
REF_MODEL_PARAMS_B = 123.0  # Mistral Large 2
REF_OUTPUT_TOKENS = 400.0  # Scénario de référence
REF_CARBON_G = 1.14  # gCO2e (Scope 3 complet : Fabrication + Usage)

# --- CONFIGURATION LOCALE (Fallback) ---
# Moyenne observée sur laptop pro (M2/Intel i7) pour SLM 7B
# 0.19 mg/token = 0.00019 g/token
LOCAL_THEORETICAL_G_PER_TOKEN = 0.00019


# ==========================================
# 2. MOTEUR DE CALCUL (STATIQUE)
# ==========================================


class CarbonCalculator:
    """
    Service utilitaire pur pour les calculs d'empreinte.
    Toutes les sorties sont en GRAMMES (gCO2e).
    """

    @staticmethod
    def _calculate_mistral_energy_wh(active_params_billions: float, output_tokens: int) -> float:
        """Calcule l'énergie (Wh) selon la formule de régression EcoLogits."""
        # Protection contre les mauvaises entrées
        if active_params_billions <= 0:
            return 0.0

        energy_per_token_wh = (ALPHA * active_params_billions) + BETA
        total_energy_wh = output_tokens * energy_per_token_wh
        return total_energy_wh

    @staticmethod
    def _get_mistral_implicit_mix() -> float:
        """
        Dérive le 'Mix Énergétique Implicite' (gCO2e/Wh) basé sur l'ACV Mistral.
        Cache le résultat en variable de classe si besoin (ici calculé à la volée car très léger).
        """
        ref_energy_wh = CarbonCalculator._calculate_mistral_energy_wh(
            REF_MODEL_PARAMS_B, int(REF_OUTPUT_TOKENS)
        )
        if ref_energy_wh == 0:
            return 0.0
        return REF_CARBON_G / ref_energy_wh

    @classmethod
    def compute_mistral_impact_g(cls, active_params_billions: float, output_tokens: int) -> float:
        """
        Estime l'impact carbone (Scope 3) pour un modèle Cloud type Mistral.

        Args:
            active_params_billions (float): Paramètres actifs (ex: 7.0, 12.0, 3.5).
            output_tokens (int): Nombre de tokens générés.

        Returns:
            float: Impact en grammes de CO2e.
        """
        if output_tokens <= 0:
            return 0.0

        target_energy_wh = cls._calculate_mistral_energy_wh(active_params_billions, output_tokens)
        implicit_mix = cls._get_mistral_implicit_mix()

        return target_energy_wh * implicit_mix

    @staticmethod
    def compute_local_theoretical_g(tokens_count: int) -> float:
        """
        Estimation théorique rapide pour le local (si CodeCarbon indisponible).
        Basé sur une moyenne statistique (Scope 2 Usage uniquement).
        """
        return tokens_count * LOCAL_THEORETICAL_G_PER_TOKEN


# ==========================================
# 3. MONITORING MATÉRIEL (TEMPS RÉEL)
# ==========================================


@dataclass
class SystemMetrics:
    """Snapshot de l'état du système."""

    cpu_usage_percent: float
    ram_usage_percent: float
    ram_total_gb: float
    ram_used_gb: float
    gpu_name: str | None = None
    gpu_memory_total_gb: float | None = None
    gpu_memory_used_gb: float | None = None
    co2_emissions_kg: float = 0.0  # ✅ AJOUTÉ : Attribut pour les émissions CO2 en kg


class HardwareMonitor:
    """Service d'audit matériel."""

    @staticmethod
    def get_system_info() -> dict[str, Any]:
        """
        Récupère les informations système statiques.

        Returns:
            dict: Informations système (OS, processeur, cœurs, etc.)
        """
        cpu_info = cpuinfo.get_cpu_info()

        return {
            "os": platform.system(),
            "os_release": platform.release(),
            "processor": platform.processor(),
            "cpu_cores_physical": psutil.cpu_count(logical=False),
            "cpu_cores_logical": psutil.cpu_count(logical=True),
            "cpu_brand": cpu_info.get("brand_raw", "Unknown CPU"),
        }

    @staticmethod
    def get_realtime_metrics() -> SystemMetrics:
        """Récupère les métriques instantanées."""

        # CPU & RAM
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        sys_mem = psutil.virtual_memory()

        metrics = SystemMetrics(
            cpu_usage_percent=psutil.cpu_percent(interval=None),
            ram_usage_percent=round(process.memory_percent(), 2),
            ram_total_gb=round(sys_mem.total / (1024**3), 2),
            ram_used_gb=round(mem_info.rss / (1024**3), 2),  # RSS = Resident Set Size (App only)
        )

        # GPU (Safe)
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
                pass  # Fail silently on GPU errors

        return metrics


# ==========================================
# 4. TRACKER CODECARBON (WRAPPER)
# ==========================================


class GreenTracker:
    """
    Wrapper CodeCarbon pour mesurer l'impact réel (Scope 2).
    Retourne les valeurs en GRAMMES.
    """

    _active_trackers: list["GreenTracker"] = []
    _atexit_registered = False

    def __init__(self, project_name="wavelocal_audit"):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.project_name = project_name
        self.tracker = OfflineEmissionsTracker(
            project_name=project_name,
            output_dir=str(LOGS_DIR),
            country_iso_code=DEFAULT_COUNTRY_ISO_CODE,
            log_level="error",
            measure_power_secs=1,  # Mesure fine pour inférence courte
        )
        self._is_running = False

        if not GreenTracker._atexit_registered:
            atexit.register(GreenTracker._cleanup_all_trackers)
            GreenTracker._atexit_registered = True

    def start(self):
        """Démarre la sonde."""
        if not self._is_running:
            self.tracker.start()
            self._is_running = True
            if self not in GreenTracker._active_trackers:
                GreenTracker._active_trackers.append(self)

    def stop(self) -> float:
        """
        Arrête la sonde et retourne les émissions en GRAMMES (g).
        """
        emissions_g = 0.0
        if self._is_running:
            try:
                # CodeCarbon retourne des kg
                emissions_kg = self.tracker.stop()
                emissions_g = emissions_kg * 1000.0 if emissions_kg else 0.0

                self._is_running = False
                if self in GreenTracker._active_trackers:
                    GreenTracker._active_trackers.remove(self)

            except Exception as e:
                logger.error(f"Erreur arrêt tracker '{self.project_name}': {e}")
                return 0.0
        return emissions_g

    # Context Manager Support
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # On ne peut pas retourner la valeur via __exit__,
        # l'utilisateur doit appeler stop() manuellement s'il veut la valeur
        # dans le bloc, ou on stocke le résultat si besoin.
        if self._is_running:
            self.stop()
        return False

    @classmethod
    def _cleanup_all_trackers(cls):
        """Sécurité : Arrêt forcé des trackers zombies."""
        for tracker in list(cls._active_trackers):
            with contextlib.suppress(Exception):
                if tracker._is_running:
                    tracker.stop()
