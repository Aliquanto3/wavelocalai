"""Détecteur de boucle de l'Arène (story 9.2) : un modèle qui répète le même fragment final est
arrêté avant le délai de lane (`delays.lane_timeout_s`), plutôt que de tourner jusqu'au bout.

Pur et sans état partagé entre lanes : `repeated_tail` regarde la fin d'un texte accumulé et dit si
elle est faite du même fragment répété au moins `min_repeats` fois sur une fenêtre d'au moins
`window_chars` caractères (réglages `[arena]` de `wavelocalai.toml`). La comparaison est exacte
(caractère pour caractère) ; le fragment fait de `MIN_FRAGMENT_CHARS` à `MAX_PERIOD_CHARS`
caractères (un paragraphe entier répété est vu) et doit être du texte : au moins `MIN_LETTER_RATIO`
de lettres. Une liste, un tableau Markdown ou du code ont des lignes voisines mais rarement
identiques ; et des lignes de données identiques (matrice de zéros, CSV chiffré, grille ASCII,
tableau de « Oui ») sont surtout faites de chiffres, d'espaces et de séparateurs : faux positifs à
zéro sur ces cas (`tests/v2/unit/test_loop_detector.py`). Limite acceptée : une boucle dont un
compteur change à chaque tour (« Étape 1… Étape 2… ») n'est pas une répétition exacte, et reste au
plafond `arena.max_tokens`.

`LoopDetector.feed` reçoit les morceaux un à un, garde une fin bornée du texte et ne vérifie
qu'après un lot de caractères nouveaux : ni réassemblage de toute la réponse à chaque jeton, ni
travail qui grandit avec elle.
"""

from __future__ import annotations

from itertools import accumulate

# En dessous, une répétition (ponctuation, puce, espace) n'est pas une boucle : elle resterait
# fréquente dans un texte normal (listes, tableaux, code).
MIN_FRAGMENT_CHARS = 8
# Plus long fragment cherché : un paragraphe répété (~400 caractères) doit être vu, et la fenêtre
# analysée (`min_repeats × MAX_PERIOD_CHARS`) reste bornée, quelle que soit la longueur de la réponse.
MAX_PERIOD_CHARS = 1000
# Part de lettres sous laquelle un fragment est de la donnée structurée (chiffres, séparateurs).
MIN_LETTER_RATIO = 0.5
_STRIDE_CHARS = 20  # nouveaux caractères avant de revérifier (`LoopDetector`)


def _max_period(window_chars: int) -> int:
    return max(MAX_PERIOD_CHARS, window_chars)


def repeated_tail(text: str, *, min_repeats: int, window_chars: int) -> bool:
    """`True` si la fin de `text` est composée du même fragment de texte répété au moins
    `min_repeats` fois, sur une fenêtre d'au moins `window_chars` caractères."""
    tail = text[-(min_repeats * _max_period(window_chars)) :]
    length = len(tail)
    max_period = min(length // min_repeats, _max_period(window_chars))
    letters: list[int] | None = None  # lettres cumulées de `tail`, calculées au premier besoin
    for period in range(MIN_FRAGMENT_CHARS, max_period + 1):
        if tail[-1] != tail[-1 - period]:  # filtre bon marché avant de comparer des fragments
            continue
        fragment = tail[length - period :]
        repeats = 1
        pos = length - period
        while pos - period >= 0 and tail.startswith(fragment, pos - period):
            repeats += 1
            pos -= period
        if repeats < min_repeats or repeats * period < window_chars:
            continue
        if letters is None:
            letters = list(accumulate(map(str.isalpha, tail), initial=0))
        if letters[length] - letters[length - period] >= MIN_LETTER_RATIO * period:
            return True
    return False


class LoopDetector:
    """Vérifie le texte d'une lane à mesure qu'il arrive (`feed`, un morceau à la fois) : au plus
    une vérification tous les `_STRIDE_CHARS` caractères nouveaux, sur une fin de texte bornée.
    `reset` repart de zéro (nouvelle tentative de la lane)."""

    def __init__(self, min_repeats: int, window_chars: int) -> None:
        self._min_repeats = min_repeats
        self._window_chars = window_chars
        self._keep = min_repeats * _max_period(window_chars)
        self._parts: list[str] = []
        self._pending = 0

    def reset(self) -> None:
        self._parts = []
        self._pending = 0

    def feed(self, piece: str) -> bool:
        self._parts.append(piece)
        self._pending += len(piece)
        if self._pending < _STRIDE_CHARS:
            return False
        self._pending = 0
        tail = "".join(self._parts)[-self._keep :]
        self._parts = [tail]
        return repeated_tail(tail, min_repeats=self._min_repeats, window_chars=self._window_chars)
