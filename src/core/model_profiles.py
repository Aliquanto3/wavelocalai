# src/core/model_profiles.py
"""
Profils de consommation mémoire des modèles.

NOTE: Ce module est conservé pour rétrocompatibilité.
Les constantes sont définies dans constants.py.
"""

from src.core.constants import MEMORY_PROFILES, ModelMemoryProfile

# Rétrocompatibilité : exposer les anciens noms
MODEL_MEMORY_PROFILES: dict[str, ModelMemoryProfile] = {
    "1b": MEMORY_PROFILES.PROFILE_1B,
    "1.5b": MEMORY_PROFILES.PROFILE_1_5B,
    "2b": MEMORY_PROFILES.PROFILE_2B,
    "3b": MEMORY_PROFILES.PROFILE_3B,
    "7b": MEMORY_PROFILES.PROFILE_7B,
    "8b": MEMORY_PROFILES.PROFILE_8B,
    "13b": MEMORY_PROFILES.PROFILE_13B,
    "70b": MEMORY_PROFILES.PROFILE_70B,
    "mistral": MEMORY_PROFILES.PROFILE_7B,
    "gemma": MEMORY_PROFILES.PROFILE_2B,
    "tiny": MEMORY_PROFILES.PROFILE_1B,
}

DEFAULT_PROFILE = MEMORY_PROFILES.DEFAULT
FRAMEWORK_OVERHEAD_GB = MEMORY_PROFILES.FRAMEWORK_OVERHEAD_GB


def get_model_memory_profile(model_tag: str) -> ModelMemoryProfile:
    """Récupère le profil mémoire d'un modèle basé sur son tag."""
    tag_lower = model_tag.lower()
    for pattern, profile in MODEL_MEMORY_PROFILES.items():
        if pattern in tag_lower:
            return profile
    return DEFAULT_PROFILE


def estimate_mission_ram_gb(model_tag: str, num_agents: int = 1) -> float:
    """Estime la RAM totale requise pour une mission multi-agents."""
    profile = get_model_memory_profile(model_tag)
    return FRAMEWORK_OVERHEAD_GB + profile.base_ram_gb + (num_agents * profile.context_overhead_gb)


def get_ram_risk_level(required_gb: float, available_gb: float) -> str:
    """Évalue le niveau de risque RAM."""
    if available_gb <= 0:
        return "critical"
    ratio = required_gb / available_gb
    if ratio < 0.7:
        return "safe"
    elif ratio < 0.9:
        return "warning"
    return "critical"
