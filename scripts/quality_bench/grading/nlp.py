"""Données NLTK des vérificateurs de consignes : seul module qui touche à ``nltk.data.path``.

Les vérificateurs empruntés (IFBench, M-IFEval FR) lisent ``punkt``, ``punkt_tab``,
``stopwords`` et ``averaged_perceptron_tagger_eng``, téléchargés avant campagne par
``fetch-nltk`` sous ``$QUALITY_BENCH_DATA/nltk_data`` (AD-15). Le gestionnaire de contexte
``bench_data()`` restreint la recherche de NLTK à ce seul dossier le temps des vérifications,
puis rend ``nltk.data.path`` tel qu'il était (aucun état global durable) : une ressource absente
lève ``LookupError``, que le correcteur rend en erreur du banc. Rien n'est jamais téléchargé.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import nltk

from ..common import paths

RESOURCES = (
    "tokenizers/punkt",
    "tokenizers/punkt_tab",
    "corpora/stopwords",
    "taggers/averaged_perceptron_tagger_eng",
)
FETCH_COMMAND = r".venv-quality\Scripts\python -m scripts.quality_bench fetch-nltk"


@contextmanager
def bench_data() -> Iterator[str]:
    """``nltk.data.path`` réduit à ``$QUALITY_BENCH_DATA/nltk_data`` (relu à chaque appel : les
    tests redirigent la racine des données), restauré à la sortie ; rend le dossier."""
    directory = str(paths.nltk_data_dir())
    saved = list(nltk.data.path)
    nltk.data.path[:] = [directory]
    try:
        yield directory
    finally:
        nltk.data.path[:] = saved


def missing_resources() -> list[str]:
    """Ressources NLTK du banc absentes du dossier du banc (liste vide si tout est là)."""
    missing = []
    with bench_data():
        for resource in RESOURCES:
            try:
                nltk.data.find(resource)
            except LookupError:
                missing.append(resource)
    return missing
