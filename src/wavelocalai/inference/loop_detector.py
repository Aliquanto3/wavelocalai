"""Détecteur de boucle de l'Arène (story 9.2) : un modèle qui répète le même fragment final est
arrêté avant le délai de lane (`delays.lane_timeout_s`), plutôt que de tourner jusqu'au bout.

Pur et sans état partagé entre lanes : `repeated_tail` regarde la fin d'un texte accumulé et dit si
elle est faite du même fragment répété au moins `min_repeats` fois sur une fenêtre d'au moins
`window_chars` caractères (réglages `[arena]` de `wavelocalai.toml`). La comparaison est exacte
(caractère pour caractère) et le fragment doit faire au moins `MIN_FRAGMENT_CHARS` : une liste, un
tableau Markdown ou du code ont des lignes voisines mais rarement identiques, et leurs puces ou
séparateurs (`- `, `| --- |`) sont trop courts pour passer ce plancher — faux positifs à zéro sur ces
trois cas (`tests/v2/unit/test_loop_detector.py`). `LoopDetector.feed` évite de refaire ce travail à
chaque caractère reçu : il ne vérifie qu'après un nouveau lot de texte.
"""

from __future__ import annotations

# En dessous, une répétition (ponctuation, puce, espace) n'est pas une boucle : elle resterait
# fréquente dans un texte normal (listes, tableaux, code).
MIN_FRAGMENT_CHARS = 8
# Borne le travail sur un texte déjà long : la fenêtre à comparer ne grandit pas avec la réponse.
_TAIL_FACTOR = 4
_STRIDE_CHARS = 20  # nouveaux caractères avant de revérifier (`LoopDetector`)


def repeated_tail(text: str, *, min_repeats: int, window_chars: int) -> bool:
    """`True` si la fin de `text` est composée du même fragment répété au moins `min_repeats` fois,
    sur une fenêtre d'au moins `window_chars` caractères (répétitions, pas seulement la dernière).
    """
    tail = text[-(window_chars * _TAIL_FACTOR) :]
    length = len(tail)
    max_period = length // min_repeats
    for period in range(MIN_FRAGMENT_CHARS, max_period + 1):
        fragment = tail[length - period :]
        repeats = 1
        pos = length - period
        while pos - period >= 0 and tail[pos - period : pos] == fragment:
            repeats += 1
            pos -= period
        if repeats >= min_repeats and repeats * period >= window_chars:
            return True
    return False


class LoopDetector:
    """Vérifie le texte accumulé d'une lane à mesure qu'il arrive (`feed`), sans refaire le travail
    de `repeated_tail` à chaque jeton : au plus une vérification tous les `_STRIDE_CHARS` caractères
    nouveaux."""

    def __init__(self, min_repeats: int, window_chars: int) -> None:
        self._min_repeats = min_repeats
        self._window_chars = window_chars
        self._checked_len = 0

    def feed(self, text: str) -> bool:
        if len(text) - self._checked_len < _STRIDE_CHARS:
            return False
        self._checked_len = len(text)
        return repeated_tail(text, min_repeats=self._min_repeats, window_chars=self._window_chars)
