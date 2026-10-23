import atexit
import contextlib
import logging
import os
import platform
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cpuinfo
import pandas as pd
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

# Fichier d'émissions de l'app, dans LOGS_DIR (data/logs/emissions.csv) : écrit par
# GreenTracker, lu par l'historique de « Sobriété et matériel ». Distinct du fichier du
# benchmark (EMISSIONS_DIR, data/logs/emissions/emissions.csv), jamais lu ici.
APP_EMISSIONS_FILE = "emissions.csv"

# Projets CodeCarbon de l'app, tous écrits dans ce fichier. L'historique (une barre par
# lancement de l'application) ne garde que SESSION_PROJECT : les autres recouvrent la même
# période, et le fichier peut aussi recevoir d'autres lignes (scripts/audit_and_update.py,
# projet « codecarbon » par défaut).
SESSION_PROJECT = "wavelocal_session"  # Suivi unique du processus (routeur, Accueil.py)
AUDIT_PROJECT = "wavelocal_audit"  # Défaut de GreenTracker
CREW_PROJECT = "crew_mission"  # Équipe d'agents (ancien tracker par mission, plus créé)


def app_emissions_path() -> Path:
    """Chemin du fichier d'émissions écrit par GreenTracker (lu à l'appel : LOGS_DIR peut
    être redirigé, en test notamment)."""
    return Path(LOGS_DIR) / APP_EMISSIONS_FILE


class EmissionsHistoryError(Exception):
    """Fichier d'émissions de l'app illisible (ligne tronquée, format inattendu)."""


def read_app_emissions(path: Path | str | None = None) -> pd.DataFrame:
    """
    Sessions mesurées par l'app, depuis le fichier écrit par GreenTracker.

    Colonnes : `timestamp` (datetime), `project_name`, `emissions` (kg, unité de CodeCarbon)
    et `emissions_g` (grammes, unité de GreenTracker.stop()).

    - Seul le suivi de l'application (`SESSION_PROJECT`) est gardé : les missions d'équipe
      et l'audit recouvrent la même période et compteraient deux fois les mêmes émissions.
    - Une ligne par `run_id`, la dernière : le suivi est unique par processus (`SessionTracker`
      le partage entre les sessions du navigateur) et chaque enregistrement ajoute une
      ligne cumulée au même run. Une barre de l'historique est donc un lancement de
      l'application, toutes sessions du navigateur comprises.
    - Lignes à horodatage ou émissions illisibles écartées ; tri par date.

    DataFrame vide si le fichier est absent, vide ou sans session de l'app.

    Raises:
        EmissionsHistoryError: fichier illisible (dernière ligne tronquée, par exemple).
    """
    columns = ["timestamp", "project_name", "emissions", "emissions_g"]
    csv_path = Path(path) if path is not None else app_emissions_path()
    if not csv_path.is_file():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)
    except pd.errors.ParserError as e:
        raise EmissionsHistoryError(
            f"le fichier {csv_path.name} est mal formé (ligne tronquée ou colonnes en trop)."
        ) from e
    if not {"timestamp", "project_name", "emissions"} <= set(df.columns):
        return pd.DataFrame(columns=columns)

    df = df[df["project_name"] == SESSION_PROJECT].copy()
    if "run_id" in df.columns:
        # Dernière ligne (cumulée) de chaque run ; les lignes sans run_id restent.
        has_run = df["run_id"].notna()
        df = pd.concat([df[has_run].drop_duplicates("run_id", keep="last"), df[~has_run]])
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", format="mixed")
    df["emissions"] = pd.to_numeric(df["emissions"], errors="coerce")
    df = df.dropna(subset=["timestamp", "emissions"]).sort_values("timestamp")
    df["emissions_g"] = df["emissions"] * 1000.0
    return df[columns].reset_index(drop=True)


class GreenTracker:
    """
    Wrapper CodeCarbon pour mesurer l'impact réel (Scope 2).
    Retourne les valeurs en GRAMMES.
    """

    _active_trackers: list["GreenTracker"] = []
    _atexit_registered = False

    def __init__(self, project_name=AUDIT_PROJECT):
        emissions_path = app_emissions_path()
        emissions_path.parent.mkdir(parents=True, exist_ok=True)
        self.project_name = project_name
        self.tracker = OfflineEmissionsTracker(
            project_name=project_name,
            output_dir=str(emissions_path.parent),
            output_file=emissions_path.name,
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

    def snapshot_kg(self) -> float | None:
        """
        Émissions cumulées (kg) depuis le démarrage, sonde toujours active ; None si elle est
        arrêtée ou si la lecture échoue (exception, ou `flush()` qui renvoie None). CodeCarbon ajoute alors une ligne cumulée au fichier
        d'émissions (même `run_id` : la dernière fait foi).
        """
        if not self._is_running:
            return None
        try:
            emissions_kg = self.tracker.flush()
        except Exception as e:
            logger.error(f"Erreur lecture tracker '{self.project_name}': {e}")
            return None
        # `flush()` est décoré `@suppress(Exception)` et renvoie None s'il échoue ou si
        # CodeCarbon a trouvé son verrou au démarrage : valeur inconnue, jamais 0.
        return None if emissions_kg is None else float(emissions_kg)

    @classmethod
    def _cleanup_all_trackers(cls):
        """Sécurité : Arrêt forcé des trackers zombies."""
        for tracker in list(cls._active_trackers):
            with contextlib.suppress(Exception):
                if tracker._is_running:
                    tracker.stop()


# ==========================================
# 5. SUIVI UNIQUE PAR PROCESSUS, MESURE PAR SESSION
# ==========================================
# Un `OfflineEmissionsTracker` par session du navigateur coûtait 6 à 11 s au premier accès
# (dont environ 9 s de `py-cpuinfo`) et 1,3 s par session suivante, avec deux fils jamais
# arrêtés avant la fin du processus. Un seul tracker (`SESSION_PROJECT`) mesure maintenant la
# machine pendant toute la vie du processus, démarré dans un fil de fond pour ne pas bloquer
# le premier rendu. Chaque session (ou mission d'équipe) lit ses émissions par différence de
# compteurs (`SessionTracker`) : la mesure par session reste exacte, sans second tracker.

_shared_lock = threading.Lock()  # état du démarrage
# Lectures du compteur : CodeCarbon n'est pas sûr entre fils (mesure puis écriture du
# fichier) ; un `flush` dure quelques millisecondes, la sérialisation reste invisible.
_read_lock = threading.Lock()
_shared_tracker: GreenTracker | None = None
_shared_thread: threading.Thread | None = None
_shared_failure: str | None = None

TRACKER_LOCKED_TEXT = (
    "Mesure carbone indisponible : une autre instance de CodeCarbon tourne déjà sur cette "
    "machine (un second lancement de l'application, par exemple), ou son fichier de verrou "
    "{lock} est resté après un arrêt brutal. Fermer l'autre instance ou supprimer ce fichier, "
    "puis relancer l'application."
)
TRACKER_FAILED_TEXT = (
    "Mesure carbone indisponible : CodeCarbon n'a pas pu démarrer (détail dans le journal). "
    "Relancer l'application pour réessayer."
)
SESSION_UNKNOWN_TEXT = (
    "Mesure carbone inconnue pour cette session : le compteur de CodeCarbon n'était pas "
    "lisible au début ou à la fin de la mesure."
)


def _new_shared_tracker() -> GreenTracker:
    """Tracker du processus (remplacé dans les tests)."""
    return GreenTracker(project_name=SESSION_PROJECT)


def _codecarbon_lock_path() -> str:
    """Chemin du verrou de CodeCarbon (dossier temporaire du système), pour le message."""
    try:
        from codecarbon.lock import LOCKFILE

        return str(LOCKFILE)
    except Exception:
        return ".codecarbon.lock"


def _start_shared_tracker() -> None:
    """Corps du fil de démarrage : crée et lance le tracker du processus. Un échec (exception,
    ou CodeCarbon qui refuse de démarrer parce qu'il trouve son verrou) est journalisé et
    noté dans `shared_tracker_failure()` : les sessions comptent alors « inconnu », jamais 0."""
    global _shared_tracker, _shared_failure
    try:
        tracker = _new_shared_tracker()
        tracker.start()
    except Exception:
        logger.exception("Tracker CodeCarbon du processus non démarré")
        _shared_failure = TRACKER_FAILED_TEXT
        return
    # CodeCarbon ne lève rien quand il trouve son verrou : il ne mesure pas, et `flush()`
    # renvoie None à chaque lecture.
    if getattr(getattr(tracker, "tracker", None), "_another_instance_already_running", False):
        logger.error("Tracker CodeCarbon du processus non démarré : verrou déjà pris")
        _shared_failure = TRACKER_LOCKED_TEXT.format(lock=_codecarbon_lock_path())
        return
    _shared_tracker = tracker


def ensure_shared_tracker() -> None:
    """Lance, sans attendre, le tracker unique du processus (une seule fois)."""
    global _shared_thread
    with _shared_lock:
        if _shared_thread is not None:
            return
        _shared_thread = threading.Thread(
            target=_start_shared_tracker, name="codecarbon-start", daemon=True
        )
        _shared_thread.start()


def shared_tracker_failure() -> str | None:
    """Message (français) si le tracker du processus n'a pas pu démarrer ; None sinon (prêt,
    en cours de démarrage ou pas encore lancé)."""
    return _shared_failure


def shared_tracker_ready() -> bool:
    """True quand le tracker du processus mesure."""
    return _shared_tracker is not None


def shared_emissions_kg() -> float | None:
    """Émissions cumulées (kg) du processus ; None tant que le tracker démarre, s'il n'a pas
    démarré ou si la lecture échoue. Lecture sérialisée : plusieurs sessions peuvent la
    demander en même temps."""
    tracker = _shared_tracker
    if tracker is None:
        return None
    with _read_lock:
        return tracker.snapshot_kg()


def stop_shared_tracker(timeout: float = 30.0) -> None:
    """Arrête le tracker du processus (écrit la ligne finale) et réarme le démarrage. En fin
    de processus, `GreenTracker._cleanup_all_trackers` l'arrête déjà ; sert surtout aux tests."""
    global _shared_tracker, _shared_thread, _shared_failure
    thread = _shared_thread
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout)
    with _shared_lock:
        tracker, _shared_tracker, _shared_thread = _shared_tracker, None, None
        _shared_failure = None
    if tracker is not None:
        tracker.stop()


class SessionTracker:
    """
    Émissions d'une session du navigateur (ou d'une mission), en GRAMMES, par différence de
    compteurs du tracker unique du processus. Même interface que `GreenTracker` côté pages :
    `start()`, `stop()` (grammes, ou None si inconnues), `_is_running`.

    `stop()` ajoute aussi au fichier d'émissions la ligne cumulée du processus. « Reprendre »
    (`start()` après `stop()`) cumule : les émissions de la pause ne sont pas comptées.

    Valeur inconnue (None), jamais 0 : tracker en échec (`shared_tracker_failure()`), compteur
    illisible au début ou à la fin d'un segment, ou tracker pas encore prêt à l'arrêt. Une
    session démarrée pendant le démarrage du tracker part de 0, comme son compteur.
    """

    def __init__(self):
        self._is_running = False
        self._accumulated_kg = 0.0
        self._segment_start_kg: float | None = 0.0
        self.unknown = False  # au moins un segment non mesuré : total inconnu

    def start(self) -> None:
        """Démarre (ou reprend) la mesure ; lance le tracker du processus s'il ne l'est pas."""
        if self._is_running:
            return
        ensure_shared_tracker()
        if shared_tracker_ready():
            # Lecture en échec : base inconnue (None), jamais 0 sur un compteur déjà avancé.
            self._segment_start_kg = shared_emissions_kg()
        elif shared_tracker_failure() is None:
            # Tracker en cours de démarrage : son compteur partira de zéro, la base aussi.
            self._segment_start_kg = 0.0
        else:
            self._segment_start_kg = None
        self._is_running = True

    def _total_g(self) -> float | None:
        return None if self.unknown else self._accumulated_kg * 1000.0

    def stop(self) -> float | None:
        """Arrête la mesure et renvoie les émissions cumulées de la session, en grammes ;
        None si une mesure a manqué (voir la classe)."""
        if not self._is_running:
            return self._total_g()
        now_kg = shared_emissions_kg()
        if now_kg is None or self._segment_start_kg is None:
            self.unknown = True
        else:
            self._accumulated_kg += max(0.0, now_kg - self._segment_start_kg)
        self._is_running = False
        return self._total_g()
