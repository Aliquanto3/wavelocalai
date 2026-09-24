# src/core/constants.py
"""
Constantes centralisées pour WaveLocalAI.

Ce module est la SOURCE UNIQUE DE VÉRITÉ pour toutes les constantes.
Ne pas dupliquer ces valeurs ailleurs.
"""

from dataclasses import dataclass
from typing import Final

# =============================================================================
# 1. CONSTANTES GREEN IT / CARBONE
# =============================================================================


@dataclass(frozen=True)
class GreenITConstants:
    """Constantes pour le calcul d'impact carbone."""

    # Mix électrique (gCO2/kWh)
    FRANCE_CO2_PER_KWH: float = 52.0
    EU_AVG_CO2_PER_KWH: float = 276.0
    WORLD_AVG_CO2_PER_KWH: float = 475.0

    # PUE (Power Usage Effectiveness)
    PUE_LOCAL: float = 1.0
    PUE_DATACENTER_EFFICIENT: float = 1.2
    PUE_DATACENTER_AVERAGE: float = 1.5

    # Consommation par token (Wh) - Estimations théoriques
    WH_PER_TOKEN_LOCAL_CPU: float = 0.0001
    WH_PER_TOKEN_LOCAL_GPU: float = 0.00005
    WH_PER_TOKEN_API_ESTIMATE: float = 0.0003

    # Facteurs Mistral API (basés sur documentation publique)
    MISTRAL_SMALL_WH_PER_1K_TOKENS: float = 0.15
    MISTRAL_LARGE_WH_PER_1K_TOKENS: float = 0.45
    MISTRAL_DATACENTER_CO2_PER_KWH: float = 50.0  # France

    # --- EcoLogits / Calibration scientifique ---
    # Source : GenAI Impact / EcoLogits (https://ecologits.ai)
    # Formule : E = N_tokens * (alpha * P_actifs + beta)
    ECOLOGITS_ALPHA: float = 8.91e-5  # Pente (Wh par milliard de paramètres)
    ECOLOGITS_BETA: float = 1.43e-3  # Ordonnée à l'origine (overhead fixe)

    # Données de référence (ACV Mistral Juillet 2025)
    REF_MODEL_PARAMS_B: float = 123.0  # Mistral Large 2
    REF_OUTPUT_TOKENS: float = 400.0  # Scénario de référence
    REF_CARBON_G: float = 1.14  # gCO2e (Scope 3 complet)

    # --- Local (Fallback) ---
    # Moyenne observée sur laptop pro (M2/Intel i7) pour SLM 7B
    LOCAL_THEORETICAL_G_PER_TOKEN: float = 0.00019  # 0.19 mg/token


# =============================================================================
# 2. CONSTANTES RESSOURCES SYSTÈME
# =============================================================================


@dataclass(frozen=True)
class ResourceConstants:
    """Seuils de ressources pour le monitoring."""

    # Seuils CPU (%)
    CPU_WARNING_THRESHOLD: int = 70
    CPU_CRITICAL_THRESHOLD: int = 90

    # Seuils RAM (%)
    RAM_WARNING_THRESHOLD: int = 75
    RAM_CRITICAL_THRESHOLD: int = 90

    # Seuils disque (%)
    DISK_WARNING_THRESHOLD: int = 80
    DISK_CRITICAL_THRESHOLD: int = 95

    # Timeouts (secondes)
    DEFAULT_INFERENCE_TIMEOUT: int = 120
    DEFAULT_AGENT_TIMEOUT: int = 300
    CALCULATOR_TIMEOUT: int = 2


# =============================================================================
# 3. CONSTANTES UI / AFFICHAGE
# =============================================================================


@dataclass(frozen=True)
class UIConstants:
    """Constantes pour l'interface utilisateur."""

    # Pagination
    DEFAULT_PAGE_SIZE: int = 10
    MAX_PAGE_SIZE: int = 100

    # Chat
    MAX_CHAT_HISTORY: int = 50
    MAX_MESSAGE_LENGTH: int = 10000

    # Affichage sources RAG
    MAX_SOURCES_DISPLAY: int = 5
    SOURCE_PREVIEW_LENGTH: int = 300


# =============================================================================
# 4. CONSTANTES RAG
# =============================================================================


@dataclass(frozen=True)
class RAGConstants:
    """Constantes pour le pipeline RAG."""

    # Chunking
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 100

    # Retrieval
    DEFAULT_TOP_K: int = 4
    RERANK_FETCH_MULTIPLIER: int = 2

    # Seuils qualité
    MIN_RELEVANCE_SCORE: float = 0.3

    # Self-RAG
    SELF_RAG_MAX_LOOPS: int = 2

    # Modèles par défaut
    DEFAULT_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    DEFAULT_GRADER_MODEL: str = "qwen2.5:1.5b"


# =============================================================================
# 5. CONSTANTES RATE LIMITING
# =============================================================================


@dataclass(frozen=True)
class RateLimitConstants:
    """Limites de débit par provider."""

    # Ollama (Local)
    OLLAMA_RPM: int = 1000
    OLLAMA_CONCURRENT: int = 5

    # Mistral API
    MISTRAL_RPM: int = 60
    MISTRAL_TPM: int = 100_000
    MISTRAL_CONCURRENT: int = 10

    # OpenAI API
    OPENAI_RPM: int = 60
    OPENAI_TPM: int = 90_000
    OPENAI_CONCURRENT: int = 10

    # Anthropic API
    ANTHROPIC_RPM: int = 60
    ANTHROPIC_TPM: int = 100_000
    ANTHROPIC_CONCURRENT: int = 5


# =============================================================================
# 6. PROFILS MÉMOIRE MODÈLES
# =============================================================================


@dataclass(frozen=True)
class ModelMemoryProfile:
    """Profil mémoire pour un type de modèle."""

    base_ram_gb: float
    context_overhead_gb: float
    description: str


@dataclass(frozen=True)
class MemoryProfiles:
    """Profils de consommation mémoire par taille de modèle."""

    PROFILE_1B: ModelMemoryProfile = ModelMemoryProfile(0.8, 0.15, "Modèles 1B")
    PROFILE_1_5B: ModelMemoryProfile = ModelMemoryProfile(1.0, 0.15, "Modèles 1.5B")
    PROFILE_2B: ModelMemoryProfile = ModelMemoryProfile(1.8, 0.2, "Modèles 2B")
    PROFILE_3B: ModelMemoryProfile = ModelMemoryProfile(2.0, 0.2, "Modèles 3B")
    PROFILE_7B: ModelMemoryProfile = ModelMemoryProfile(4.5, 0.25, "Modèles 7B")
    PROFILE_8B: ModelMemoryProfile = ModelMemoryProfile(4.5, 0.25, "Modèles 8B")
    PROFILE_13B: ModelMemoryProfile = ModelMemoryProfile(8.0, 0.3, "Modèles 13B")
    PROFILE_70B: ModelMemoryProfile = ModelMemoryProfile(40.0, 0.5, "Modèles 70B")

    DEFAULT: ModelMemoryProfile = ModelMemoryProfile(4.0, 0.25, "Profil par défaut")

    # Overhead framework (LangChain, ChromaDB, etc.)
    FRAMEWORK_OVERHEAD_GB: float = 0.5


# =============================================================================
# INSTANCES GLOBALES (IMMUTABLES)
# =============================================================================

GREEN_IT: Final[GreenITConstants] = GreenITConstants()
RESOURCES: Final[ResourceConstants] = ResourceConstants()
UI: Final[UIConstants] = UIConstants()
RAG: Final[RAGConstants] = RAGConstants()
RATE_LIMITS: Final[RateLimitConstants] = RateLimitConstants()
MEMORY_PROFILES: Final[MemoryProfiles] = MemoryProfiles()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Dataclasses
    "GreenITConstants",
    "ResourceConstants",
    "UIConstants",
    "RAGConstants",
    "RateLimitConstants",
    "ModelMemoryProfile",
    "MemoryProfiles",
    # Instances
    "GREEN_IT",
    "RESOURCES",
    "UI",
    "RAG",
    "RATE_LIMITS",
    "MEMORY_PROFILES",
]
