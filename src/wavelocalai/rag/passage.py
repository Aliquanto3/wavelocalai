"""Règles de présentation d'une source : libellé de pertinence et passage à surligner (story 4.4).

Deux fonctions pures, sans base ni modèle, testables ligne à ligne.

**Libellé de pertinence** (`relevance_label`). La distance cosinus de l'index (0 = même direction)
devient une similarité `s = 1 - distance`, ramenée dans [0, 1] (une similarité négative vaut 0).
Deux seuils, `rag.relevance_very_close` (0,70) et `rag.relevance_close` (0,60), donnent le libellé :
`s >= 0,70` « très proche », `s >= 0,60` « proche », sinon « éloignée » (seuils inclus dans la
classe haute). La règle ne regarde que le score de l'extrait, jamais les autres résultats : deux
questions comparent donc leurs libellés. Elle est monotone, un rang plus bas n'a jamais un meilleur
libellé. Les seuils sont ceux d'un modèle d'embedding de la famille `nomic-embed-text` ; un autre
modèle se règle dans `wavelocalai.toml`.

**Passage** (`pick_passage`, D-21). Le serveur désigne la **phrase de l'extrait qui partage le plus
de termes avec la question**, ou `None` (pas de surlignage) :

1. L'extrait est découpé en phrases : fin après `. ! ? …` suivi d'un espace, et à chaque saut de
   ligne. Les espaces de bord sont écartés des positions.
2. Les termes de la question et de chaque phrase sont normalisés : minuscules, accents retirés, mots
   d'au moins 3 lettres ou chiffres, hors mots vides (français et anglais), tronqués à 6 caractères
   (un pluriel ou une conjugaison proche reste le même terme : « voiture » et « voitures »).
3. Une phrase marque autant de points que de termes distincts de la question qu'elle contient. La
   phrase de plus haut score gagne ; à égalité, la plus proche du début de l'extrait.
4. `None` si aucune phrase n'a de point, ou si la phrase gagnante est tout l'extrait (rien à mettre
   en valeur).

Les positions sont des indices de `str` Python (points de code) dans le `text` de l'extrait, `end`
exclu : `text[start:end]` est la phrase. Elles ne comptent pas en unités UTF-16 : pour un texte
qui contient des caractères hors du plan multilingue de base (emoji), le front doit convertir.
"""

from __future__ import annotations

import re
import unicodedata

LABEL_VERY_CLOSE = "très proche"
LABEL_CLOSE = "proche"
LABEL_FAR = "éloignée"
LABELS = (LABEL_VERY_CLOSE, LABEL_CLOSE, LABEL_FAR)

TERM_LENGTH = 6  # un terme est tronqué à ce nombre de caractères
MIN_TERM_LENGTH = 3

_STOPWORD_TEXT = (
    "alors aussi avec avoir cette ces chez comme dans des donc elle elles est était etre "
    "être faire fait les leur leurs lui mais mes mon nos notre par pas pour que quel "
    "quelle quelles quels qui sans ses son sont sur tes ton tous tout tres très une vos "
    "votre vous the and are for from has have how that this was were what when where which "
    "who why with you your"
)
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_BOUNDARY = re.compile(r"(?<=[.!?…])\s+|\s*\n\s*")


def similarity(distance: float) -> float:
    """Similarité cosinus brute (`1 - distance`), qui peut être négative."""
    return 1.0 - distance


def relevance_label(distance: float, very_close: float, close: float) -> str:
    """Libellé de pertinence d'un extrait d'après sa distance cosinus (règle du module)."""
    score = min(1.0, max(0.0, similarity(distance)))
    if score >= very_close:
        return LABEL_VERY_CLOSE
    if score >= close:
        return LABEL_CLOSE
    return LABEL_FAR


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def terms(text: str) -> set[str]:
    """Termes distincts d'un texte : normalisés, sans mots vides, tronqués."""
    found: set[str] = set()
    for word in _WORD.findall(_fold(text)):
        if len(word) >= MIN_TERM_LENGTH and word not in _STOPWORDS:
            found.add(word[:TERM_LENGTH])
    return found


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Positions `(start, end)` des phrases non vides de `text`, espaces de bord écartés."""
    raw: list[tuple[int, int]] = []
    position = 0
    for boundary in _BOUNDARY.finditer(text):
        raw.append((position, boundary.start()))
        position = boundary.end()
    raw.append((position, len(text)))
    spans: list[tuple[int, int]] = []
    for start, end in raw:
        segment = text[start:end]
        stripped = segment.strip()
        if stripped:
            begin = start + len(segment) - len(segment.lstrip())
            spans.append((begin, begin + len(stripped)))
    return spans


def pick_passage(question: str, text: str) -> dict[str, int] | None:
    """`{start, end}` de la phrase de `text` la plus proche de `question`, ou `None` (règle du
    module)."""
    wanted = terms(question)
    if not wanted:
        return None
    best: tuple[int, int, int] | None = None  # (score, start, end)
    for start, end in sentence_spans(text):
        score = len(wanted & terms(text[start:end]))
        if score > 0 and (best is None or score > best[0]):
            best = (score, start, end)  # à égalité, la première phrase est gardée
    if best is None:
        return None
    _, start, end = best
    whole = text.strip()
    if end - start >= len(whole):
        return None  # la phrase est tout l'extrait : rien à mettre en valeur
    return {"start": start, "end": end}
