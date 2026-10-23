"""Réglages de la base documentaire que l'UI modifie (story 4.3, AD-15).

`wavelocalai.toml` (`[rag]`) donne les défauts, lus une fois au démarrage ; ce que l'utilisateur
change à l'écran (modèle d'embedding, découpe, nombre d'extraits, stratégie par défaut) vit dans la
table `preferences`, clé `rag.settings`, et **prime** sur le `.toml` pour ces seules clés. L'app
n'écrit jamais `wavelocalai.toml`. Une valeur absente des préférences, ou devenue invalide, retombe
sur le `.toml`.

`effective` rend les réglages en vigueur ; l'ingestion les lit à chaque import (découpe, modèle par
défaut) et la question à chaque run (`top_k`) : un changement vaut dès le suivant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wavelocalai.config import RagSettings
from wavelocalai.rag.strategies import MAX_TOP_K, STRATEGIES
from wavelocalai.store.preferences import PreferenceStore

PREF_KEY = "rag.settings"

# Bornes de l'API : celles de `RagSettings` (le `.toml` les respecte aussi).
CHUNK_SIZE_RANGE = (100, 8000)
TOP_K_RANGE = (1, MAX_TOP_K)
OVERLAP_MIN = 0


@dataclass(frozen=True)
class RagTunables:
    embedding_model: str | None  # `None` : le modèle de la base, sinon le premier installé
    chunk_size: int
    chunk_overlap: int
    top_k: int
    strategy: str


def _valid_int(value: Any, low: int, high: int | None = None) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= low
        and (high is None or value <= high)
    )


def effective(rag: RagSettings, preferences: PreferenceStore | None) -> RagTunables:
    """Les réglages en vigueur : préférences d'abord, `.toml` pour tout le reste."""
    stored = preferences.get(PREF_KEY) if preferences is not None else None
    stored = stored if isinstance(stored, dict) else {}
    size = stored.get("chunk_size")
    if not _valid_int(size, *CHUNK_SIZE_RANGE):
        size = rag.chunk_size
    overlap = stored.get("chunk_overlap")
    if not _valid_int(overlap, OVERLAP_MIN):
        overlap = rag.chunk_overlap
    if overlap >= size:  # `.toml` modifié depuis : le recouvrement reste sous la taille
        overlap = size // 2
    top_k = stored.get("top_k")
    if not _valid_int(top_k, *TOP_K_RANGE):
        top_k = rag.top_k
    strategy = stored.get("strategy")
    if strategy not in STRATEGIES:
        strategy = STRATEGIES[0]
    model = stored.get("embedding_model")
    if not isinstance(model, str) or not model.strip():
        model = rag.embedding_model
    return RagTunables(model, size, overlap, top_k, strategy)


def stored_overrides(preferences: PreferenceStore | None) -> dict[str, Any]:
    """Ce que l'utilisateur a choisi (rien du `.toml`), pour fusionner une mise à jour partielle."""
    stored = preferences.get(PREF_KEY) if preferences is not None else None
    return dict(stored) if isinstance(stored, dict) else {}
