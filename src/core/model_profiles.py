# src/core/model_profiles.py
"""
Profils de consommation mémoire des modèles.
Utilisé pour les estimations pre-flight et le sizing.
"""

from dataclasses import dataclass


@dataclass
class ModelMemoryProfile:
    """Profil mémoire estimé pour un modèle."""

    base_ram_gb: float  # RAM de base requise
    context_overhead_gb: float = 0.25  # Overhead par agent/contexte
    description: str = ""


# Profils par pattern de nom de modèle
MODEL_MEMORY_PROFILES: dict[str, ModelMemoryProfile] = {
    # Modèles ~7B
    "7b": ModelMemoryProfile(4.5, 0.25, "Modèles 7B standard (Mistral, Llama)"),
    "8b": ModelMemoryProfile(4.5, 0.25, "Modèles 8B standard"),
    "mistral": ModelMemoryProfile(4.5, 0.25, "Mistral (défaut 7B)"),
    # Modèles ~3B
    "3b": ModelMemoryProfile(2.0, 0.2, "Modèles 3B"),
    # Modèles ~2B
    "2b": ModelMemoryProfile(1.8, 0.2, "Modèles 2B (Gemma, Phi)"),
    "gemma": ModelMemoryProfile(1.8, 0.2, "Gemma (défaut 2B)"),
    # Modèles ~1B
    "1b": ModelMemoryProfile(0.8, 0.15, "Modèles 1B"),
    "tiny": ModelMemoryProfile(0.8, 0.15, "Modèles Tiny"),
    "1.5b": ModelMemoryProfile(1.0, 0.15, "Modèles 1.5B (Qwen)"),
    # Modèles plus gros
    "13b": ModelMemoryProfile(8.0, 0.3, "Modèles 13B"),
    "70b": ModelMemoryProfile(40.0, 0.5, "Modèles 70B"),
}

# Profil par défaut si aucun pattern ne match
DEFAULT_PROFILE = ModelMemoryProfile(4.0, 0.25, "Profil par défaut (supposé 7B)")

# Overhead framework constant
FRAMEWORK_OVERHEAD_GB = 0.5


def get_model_memory_profile(model_tag: str) -> ModelMemoryProfile:
    """
    Récupère le profil mémoire d'un modèle basé sur son tag.

    Args:
        model_tag: Tag du modèle (ex: "qwen2.5:1.5b", "mistral:7b")

    Returns:
        ModelMemoryProfile correspondant
    """
    tag_lower = model_tag.lower()

    # Cherche un pattern correspondant
    for pattern, profile in MODEL_MEMORY_PROFILES.items():
        if pattern in tag_lower:
            return profile

    return DEFAULT_PROFILE


def estimate_mission_ram_gb(model_tag: str, num_agents: int = 1) -> float:
    """
    Estime la RAM totale requise pour une mission multi-agents.

    Args:
        model_tag: Tag du modèle utilisé
        num_agents: Nombre d'agents dans l'équipe

    Returns:
        float: RAM estimée en GB
    """
    profile = get_model_memory_profile(model_tag)

    model_ram = profile.base_ram_gb
    agent_overhead = num_agents * profile.context_overhead_gb

    return FRAMEWORK_OVERHEAD_GB + model_ram + agent_overhead


def get_ram_risk_level(required_gb: float, available_gb: float) -> str:
    """
    Évalue le niveau de risque RAM.

    Returns:
        str: "safe", "warning", "critical"
    """
    ratio = required_gb / available_gb if available_gb > 0 else float("inf")

    if ratio < 0.7:
        return "safe"
    elif ratio < 0.9:
        return "warning"
    else:
        return "critical"
