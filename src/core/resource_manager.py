import logging

import psutil

from src.core.models_db import MODELS_DB, get_friendly_name_from_tag

# Logging
logger = logging.getLogger(__name__)

# Marge de sécurité RAM (en GB) pour l'OS et les autres apps
SYSTEM_RAM_BUFFER_GB = 1.0


class ResourceCheckResult:
    def __init__(
        self,
        allowed: bool,
        message: str,
        ram_required_gb: float = 0.0,
        ram_available_gb: float = 0.0,
    ):
        self.allowed = allowed
        self.message = message
        self.ram_required_gb = ram_required_gb
        self.ram_available_gb = ram_available_gb


class ResourceManager:
    """
    Garde-fou pour la gestion des ressources système (RAM).
    Empêche le lancement de processus si la RAM est insuffisante.
    """

    @staticmethod
    def get_available_ram_gb() -> float:
        """Retourne la RAM disponible réelle en GB."""
        return psutil.virtual_memory().available / (1024**3)

    @staticmethod
    def estimate_model_ram(model_tag: str) -> float:
        """
        Estime la RAM nécessaire pour un modèle spécifique.
        Utilise les données empiriques de models.json si disponibles (audit),
        sinon fait une estimation heuristique basée sur la taille du fichier.
        """
        friendly_name = get_friendly_name_from_tag(model_tag)
        info = MODELS_DB.get(friendly_name)

        if info:
            # 1. Priorité : Donnée d'audit réelle (stress test)
            benchmark_stats = info.get("benchmark_stats", {})
            if benchmark_stats and "ram_usage_gb" in benchmark_stats:
                # On ajoute 10% de marge de sécurité sur la valeur mesurée
                return float(benchmark_stats["ram_usage_gb"]) * 1.1

            # 2. Fallback : Taille du fichier sur disque (approximation grossière pour GGUF)
            # Pour un GGUF chargé en RAM, c'est souvent taille_disque + 0.5/1GB de overhead
            if "size_gb" in info:
                try:
                    size_str = info["size_gb"].replace(" GB", "")
                    return float(size_str) + 1.0
                except ValueError:
                    pass

        # 3. Dernier recours : Valeur par défaut conservatrice
        return 4.0

    @classmethod
    def check_resources(cls, model_tag: str, n_instances: int = 1) -> ResourceCheckResult:
        """
        Vérifie si le système a assez de ressources pour lancer N instances du modèle.

        Args:
            model_tag: Tag du modèle (ex: 'qwen2.5:1.5b')
            n_instances: Nombre d'agents simultanés prévus

        Returns:
            ResourceCheckResult: Verdict (Autorisé/Refusé) avec détails.
        """
        # 1. Estimation du besoin
        unit_ram = cls.estimate_model_ram(model_tag)
        total_ram_needed = unit_ram * n_instances

        # 2. Vérification disponibilité
        available_ram = cls.get_available_ram_gb()

        # On soustrait le buffer système de la RAM dispo pour être sûr
        safe_available_ram = available_ram - SYSTEM_RAM_BUFFER_GB

        if safe_available_ram >= total_ram_needed:
            msg = (
                f"✅ Ressources suffisantes. "
                f"Besoin: {total_ram_needed:.2f}GB ({n_instances}x {unit_ram:.2f}GB). "
                f"Dispo (safe): {safe_available_ram:.2f}GB."
            )
            logger.info(msg)
            return ResourceCheckResult(True, msg, total_ram_needed, available_ram)
        else:
            msg = (
                f"⛔ RAM Insuffisante ! Risque de crash. Essayez de changer de modèle ou de Reset la mémoire. "
                f"Besoin: {total_ram_needed:.2f}GB. "
                f"Dispo réelle: {available_ram:.2f}GB (Buffer sécu {SYSTEM_RAM_BUFFER_GB}GB déduit)."
            )
            logger.warning(msg)
            return ResourceCheckResult(False, msg, total_ram_needed, available_ram)
