"""Référence d'un modèle résolu par le registre (AD-8, AD-9).

Les ports `ChatModel` et `Embedder` s'ajoutent ici avec l'adaptateur Ollama (story 2.1) : cette
story ne livre que la référence, que `registry.resolve` rend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Origin = Literal["local", "cloud", "unknown"]
Kind = Literal["chat", "embedding", "reranker"]


@dataclass(frozen=True)
class ModelRef:
    tag: str
    provider: str
    origin: Origin
    kind: Kind
