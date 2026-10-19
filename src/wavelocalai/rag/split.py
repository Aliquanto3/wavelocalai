"""Découpe récursive d'un texte en extraits (AD-4 : sans dépendance de la v1 ni de langchain).

Même idée que `RecursiveCharacterTextSplitter` de la v1 : on coupe au séparateur le plus fort qui
reste dans le texte (paragraphe, ligne, phrase, mot, caractère), on recolle les morceaux jusqu'à
`size` caractères, et deux extraits voisins partagent jusqu'à `overlap` caractères. Le séparateur
reste au bout du morceau qu'il termine. Une page de PDF se découpe seule : un extrait ne chevauche
jamais deux pages, sa page est exacte.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from wavelocalai.rag.extract import Page

SEPARATORS = ("\n\n", "\n", ". ", " ", "")


@dataclass(frozen=True)
class ChunkDraft:
    position: int  # rang dans le document, à partir de 0
    page: int | None
    text: str


def _pieces(text: str, separator: str) -> list[str]:
    if not separator:
        return list(text)
    parts = re.split(f"({re.escape(separator)})", text)
    pieces = [
        parts[i] + (parts[i + 1] if i + 1 < len(parts) else "") for i in range(0, len(parts), 2)
    ]
    return [p for p in pieces if p]


def _merge(pieces: Sequence[str], size: int, overlap: int) -> list[str]:
    """Recolle des morceaux de moins de `size` caractères ; chaque extrait reprend la fin du
    précédent (au plus `overlap` caractères)."""
    chunks: list[str] = []
    window: list[str] = []
    total = 0
    for piece in pieces:
        if window and total + len(piece) > size:
            chunks.append("".join(window))
            while window and (total > overlap or total + len(piece) > size):
                total -= len(window.pop(0))
        window.append(piece)
        total += len(piece)
    if window:
        chunks.append("".join(window))
    return chunks


def _split(text: str, separators: Sequence[str], size: int, overlap: int) -> list[str]:
    separator = next((s for s in separators if not s or s in text), "")
    rest = separators[separators.index(separator) + 1 :]
    chunks: list[str] = []
    small: list[str] = []
    for piece in _pieces(text, separator):
        if len(piece) <= size:
            small.append(piece)
            continue
        chunks.extend(_merge(small, size, overlap))
        small = []
        chunks.extend(_split(piece, rest, size, overlap) if rest else [piece])
    chunks.extend(_merge(small, size, overlap))
    return chunks


def split_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    """Extraits de `text` (au plus `size` caractères chacun), sans extrait vide."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("size > 0 et 0 <= overlap < size attendus")
    return [c.strip() for c in _split(text, SEPARATORS, size, overlap) if c.strip()]


def split_pages(pages: Sequence[Page], size: int = 800, overlap: int = 100) -> list[ChunkDraft]:
    """Extraits numérotés de tout le document, page par page."""
    drafts: list[ChunkDraft] = []
    for page in pages:
        for text in split_text(page.text, size, overlap):
            drafts.append(ChunkDraft(len(drafts), page.number, text))
    return drafts
