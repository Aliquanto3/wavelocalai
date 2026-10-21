"""Le vrai reranker fastembed, s'il est déjà dans le cache du dossier de données (story 4.7 ; fastembed
en dépendance de base depuis la story 9.5, D-R6).

Ce test ne télécharge rien : il saute si le modèle n'est pas dans `data/models/fastembed` (ou le
dossier de `WAVELOCALAI_RERANK_CACHE`). Pour le jouer : remplir le cache comme l'explique le README
(« Reranker local »), par exemple via le bouton « Installer le reranker » de l'écran Modèles.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from wavelocalai.config import load_settings
from wavelocalai.rag.rerank import RerankerService, cache_dir

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


def _service() -> RerankerService:
    settings = load_settings(ROOT / "wavelocalai.toml", environ={})
    override = os.environ.get("WAVELOCALAI_RERANK_CACHE")
    cache = Path(override) if override else cache_dir(settings.data_dir)
    return RerankerService(settings.rag.reranker_model, cache)


def test_the_real_reranker_puts_the_relevant_text_first_or_is_skipped():
    service = _service()
    status = service.status()
    if not status.available:
        pytest.skip(f"reranker local absent : {status.reason}")
    texts = [
        "La voiture électrique recharge sa batterie sur une borne rapide.",
        "Le chat domestique dort sur le canapé du salon.",
    ]
    scores = asyncio.run(service.score("Où dort le chat ?", texts))
    if scores is None:
        pytest.skip(f"reranker local non chargeable : {service.status().reason}")
    assert len(scores) == 2 and scores[1] > scores[0]
