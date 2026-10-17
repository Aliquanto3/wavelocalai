"""Comptage déterministe en français et vérification des critères de rédaction (AD-10).

Un critère de rédaction qui demande de compter porte un ``check`` (``questions/checks.py``) :
``evaluate_checks(checks, answer)`` rend son verdict par le code, sans juge. Les règles ci-dessous
sont celles de ``questions/SOURCES.md`` (section « Comptage en français ») ; elles ne dépendent ni
d'une locale, ni d'un modèle de langue, ni d'une bibliothèque : mêmes entrées, mêmes verdicts.

- **Texte :** normalisé en NFC, fins de ligne en ``\\n``, caractères de largeur nulle et trait
  d'union conditionnel retirés. L'espace insécable (U+00A0, U+202F) est une espace.
- **Mot :** suite d'au moins un caractère alphanumérique entre deux espaces. L'élision et le
  trait d'union ne coupent pas (« l'école », « peut-être », « c'est-à-dire » : un mot) ; un nombre
  écrit avec des espaces compte pour autant de mots (« 1 450 » : deux) ; la ponctuation isolée
  (« : », « — », « » ») et un marqueur de liste en début de ligne ne comptent pas.
- **Phrase :** la ligne coupe toujours. Dans une ligne, ``.``, ``!``, ``?`` ou ``…`` (suivis de
  guillemets ou parenthèses fermants éventuels) terminent une phrase quand une espace ou la fin
  de ligne suit, sauf si le mot qui précède est une abréviation française courante ou une initiale
  (« M. », « Mme », « p. ex. », « Paul D. »), ou si la suite commence par une minuscule (« etc. et »,
  « Vraiment ? » dit-elle). ``:`` et ``;`` ne terminent rien ; « 4.2 » ne coupe pas ; un titre
  Markdown, une ligne en gras seule ou un filet horizontal ne sont pas des phrases.
- **Paragraphe :** bloc séparé du suivant par au moins une ligne vide ; les blocs qui ne sont que
  des titres Markdown, des lignes en gras seules ou des filets horizontaux ne comptent pas.
- **Ligne :** ligne non vide. **Élément de liste :** ligne qui commence par une puce (``- * • + –
  —``) ou un numéro (``1.`` ou ``1)``) suivi d'une espace ; une ligne indentée qui suit prolonge
  l'élément.
- **Corps d'un courriel (``scope: body``) :** la réponse privée de la ligne « Objet : » (parmi les
  trois premières lignes non vides), de la formule d'appel (premier paragraphe d'une ligne, au plus
  huit mots, sans point final) et de la formule de politesse avec sa signature (un des trois
  derniers paragraphes contient « cordialement », « salutations », « agréer »… et fait au plus
  quatre lignes et 45 mots, les paragraphes qui le suivent étant des signatures : au plus trois
  lignes, 15 mots, sans ponctuation finale de phrase). Sans formule de politesse trouvée, rien
  n'est retiré à la fin.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from ..questions.checks import APPROX_TOLERANCE, CheckError, as_checks, validate_check

_INVISIBLE = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))
_BULLET_RE = re.compile(r"^\s*[-*•+–—]\s+")
_DASH_RE = re.compile(r"^\s*[-–—]\s+")
_NUMBER_RE = re.compile(r"^\s*(\d+)[.)]\s+")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
_TITLE_RE = re.compile(
    r"^\s*(?:#{1,6}\s+.*|\*\*[^*]+\*\*:?|__[^_]+__:?|(?:-{3,}|\*{3,}|_{3,}|={3,}))\s*$"
)
_TERMINATOR_RE = re.compile(r"[.!?…]+[\"»”’)\]]*(?=\s|$)")
_PREVIOUS_WORD_RE = re.compile(r"([^\W\d_][\w'’-]*|\d+)$")
_ABBREVIATIONS = frozenset(
    {
        *("m", "mm", "mme", "mmes", "mlle", "mlles", "dr", "drs", "pr", "prs", "st", "ste"),
        *("sts", "stes", "cie", "tél", "tel", "réf", "ref", "ex", "cf", "av", "bd", "env"),
        *("vs", "fig", "éd", "vol", "chap", "art", "no", "prof"),
    }
)
_SUBJECT_RE = re.compile(r"^[\s*_#>]*(?:objet|subject)\s*[:：]", re.IGNORECASE)
_GREETING_RE = re.compile(
    r"^[\s*_]*(?:bonjour|bonsoir|salut|madame|monsieur|mesdames|messieurs|chers?|chères?)\b",
    re.IGNORECASE,
)
_CLOSING_RE = re.compile(
    r"cordialement|salutations|agréer|respectueusement|sincèrement|amicalement|bien à vous|"
    r"bien à toi|à bientôt",
    re.IGNORECASE,
)
_SENTENCE_END = ".?…!"
_GREETING_MAX_WORDS = 8
_CLOSING_MAX_LINES, _CLOSING_MAX_WORDS = 4, 45
_SIGNATURE_MAX_LINES, _SIGNATURE_MAX_WORDS = 3, 15
_CLOSING_WINDOW = 3


# -- Texte ----------------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """NFC, fins de ligne ``\\n``, caractères de largeur nulle retirés, espaces de bord retirés."""
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _strip_marker(line: str) -> str:
    """Ligne sans marqueur de liste ni dièses de titre en début de ligne."""
    for pattern in (_BULLET_RE, _NUMBER_RE, _HEADING_RE):
        match = pattern.match(line)
        if match:
            return line[match.end() :]
    return line


def _has_alnum(text: str) -> bool:
    return any(char.isalnum() for char in text)


def count_words(text: str) -> int:
    """Nombre de mots de ``text`` (règle du module)."""
    total = 0
    for line in text.split("\n"):
        total += sum(1 for token in _strip_marker(line).split() if _has_alnum(token))
    return total


# -- Phrases --------------------------------------------------------------------------------


def _is_boundary(line: str, start: int, end: int) -> bool:
    """La suite de terminaisons ``line[start:end]`` ferme-t-elle une phrase ?"""
    # La typographie française met une espace avant le guillemet fermant (« Vraiment ? »).
    after = line[end:].lstrip("»”)]   ")
    if after and after[0].islower():
        return False
    if line[start : start + 1] == "." and line[start:end].rstrip('"»”’)]') == ".":
        match = _PREVIOUS_WORD_RE.search(line[:start])
        if match:
            word = match.group(1)
            if word.casefold() in _ABBREVIATIONS or (len(word) == 1 and word.isupper()):
                return False
    return True


def _split_line(line: str) -> list[str]:
    parts: list[str] = []
    begin = 0
    for match in _TERMINATOR_RE.finditer(line):
        if _is_boundary(line, match.start(), match.end()):
            parts.append(line[begin : match.end()])
            begin = match.end()
    parts.append(line[begin:])
    return [part.strip() for part in parts if _has_alnum(part)]


def sentences(text: str) -> list[str]:
    """Phrases de ``text`` dans l'ordre (règle du module)."""
    result: list[str] = []
    for line in text.split("\n"):
        if not line.strip() or _TITLE_RE.match(line):
            continue
        result.extend(_split_line(_strip_marker(line).strip()))
    return result


# -- Paragraphes, lignes, éléments de liste --------------------------------------------------


def _blocks(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text.strip()) if block.strip()]


def paragraphs(text: str) -> list[str]:
    """Paragraphes de ``text`` (blocs qui ne sont pas que des titres)."""
    return [
        block
        for block in _blocks(text)
        if not all(_TITLE_RE.match(line) for line in block.split("\n") if line.strip())
    ]


def lines(text: str) -> list[str]:
    """Lignes non vides, sans marqueur de liste."""
    return [_strip_marker(line).strip() for line in text.split("\n") if line.strip()]


def _marker_pattern(marker: str) -> tuple[re.Pattern[str], ...]:
    return {
        "bullet": (_BULLET_RE,),
        "dash": (_DASH_RE,),
        "number": (_NUMBER_RE,),
        "any": (_BULLET_RE, _NUMBER_RE),
    }[marker]


def list_items(text: str, marker: str = "any", sequential: bool = False) -> list[str] | None:
    """Éléments de liste de ``text`` ; ``None`` si ``sequential`` et que les numéros ne lisent
    pas 1, 2, 3… dans l'ordre."""
    patterns = _marker_pattern(marker)
    items: list[str] = []
    numbers: list[int] = []
    open_item = False
    for line in text.split("\n"):
        match = next((m for m in (p.match(line) for p in patterns) if m), None)
        if match:
            items.append(line[match.end() :].strip())
            number = _NUMBER_RE.match(line)
            if number:
                numbers.append(int(number.group(1)))
            open_item = True
        elif line.strip() and line[:1] in " \t" and open_item:
            items[-1] = f"{items[-1]} {line.strip()}"
        else:
            open_item = False
    if sequential and numbers != list(range(1, len(items) + 1)):
        return None
    return items


# -- Périmètres -----------------------------------------------------------------------------


def _is_greeting(block: str) -> bool:
    if "\n" in block or len(block.split()) > _GREETING_MAX_WORDS or block[-1] in _SENTENCE_END:
        return False
    return block[-1] in ",:!" or _GREETING_RE.match(block) is not None


def _is_closing(block: str) -> bool:
    return (
        len(block.split("\n")) <= _CLOSING_MAX_LINES
        and len(block.split()) <= _CLOSING_MAX_WORDS
        and _CLOSING_RE.search(block) is not None
    )


def _is_signature(block: str) -> bool:
    block_lines = block.split("\n")
    return (
        len(block_lines) <= _SIGNATURE_MAX_LINES
        and len(block.split()) <= _SIGNATURE_MAX_WORDS
        and not any(line.rstrip()[-1:] in _SENTENCE_END for line in block_lines)
    )


def email_body(text: str) -> str:
    """Corps d'un courriel : sans « Objet : », formule d'appel, formule de politesse ni signature."""
    body_lines = text.split("\n")
    seen = 0
    for index, line in enumerate(body_lines):
        if not line.strip():
            continue
        seen += 1
        if seen > 3:
            break
        if _SUBJECT_RE.match(line):
            del body_lines[index]
            break
    blocks = _blocks("\n".join(body_lines))
    if blocks and _is_greeting(blocks[0]):
        blocks = blocks[1:]
    for offset in range(1, min(_CLOSING_WINDOW, len(blocks)) + 1):
        index = len(blocks) - offset
        if _is_closing(blocks[index]) and all(_is_signature(b) for b in blocks[index + 1 :]):
            blocks = blocks[:index]
            break
    return "\n\n".join(blocks)


def scoped(text: str, scope: str) -> str:
    """Périmètre ``scope`` de ``text`` (déjà normalisé)."""
    if scope == "body":
        return email_body(text)
    if scope == "before_last":
        return "\n\n".join(_blocks(text)[:-1])
    return text


# -- Vérification ---------------------------------------------------------------------------


def _measure(count: str, text: str, check: Mapping[str, Any]) -> int | None:
    if count == "words":
        return count_words(text)
    if count == "sentences":
        return len(sentences(text))
    if count == "paragraphs":
        return len(paragraphs(text))
    if count == "lines":
        return len(lines(text))
    found = list_items(text, check.get("marker", "any"), bool(check.get("sequential")))
    return None if found is None else len(found)


def _units(text: str, unit: str, check: Mapping[str, Any]) -> list[str]:
    if unit == "sentence":
        return sentences(text)
    if unit == "paragraph":
        return paragraphs(text)
    if unit == "line":
        return lines(text)
    return list_items(text, check.get("marker", "any")) or []


def _bounds(check: Mapping[str, Any]) -> tuple[int | None, int | None]:
    """Bornes entières incluses ``(bas, haut)`` de ``check`` ; ``approx`` relâche de 10 %."""
    op = check["op"]
    approx = bool(check.get("approx"))

    def low(value: int) -> int:
        return math.floor(value * (1 - APPROX_TOLERANCE)) if approx else value

    def high(value: int) -> int:
        return math.ceil(value * (1 + APPROX_TOLERANCE)) if approx else value

    if op == "between":
        return low(check["min"]), high(check["max"])
    n = check["n"]
    if op == "<":
        return None, high(n) - 1
    if op == "<=":
        return None, high(n)
    if op == ">":
        return low(n) + 1, None
    if op == ">=":
        return low(n), None
    return low(n), high(n)


def _holds(check: Mapping[str, Any], value: int | None) -> bool:
    if value is None:
        return False
    low, high = _bounds(check)
    return (low is None or value >= low) and (high is None or value <= high)


def evaluate_check(check: Mapping[str, Any], answer: str) -> bool:
    """Verdict d'un contrôle sur ``answer`` ; ``CheckError`` si le contrôle est mal formé."""
    validate_check(check)
    text = scoped(normalize_text(answer), check.get("scope", "text"))
    if "of" in check:
        unit, rank = next(iter(check["of"].items()))
        found = sentences(text) if unit == "sentence" else paragraphs(text)
        if rank > len(found):
            return False
        return _holds(check, _measure(check["count"], found[rank - 1], check))
    if "per" in check:
        found = _units(text, check["per"], check)
        return bool(found) and all(
            _holds(check, _measure(check["count"], unit, check)) for unit in found
        )
    return _holds(check, _measure(check["count"], text, check))


def evaluate_checks(value: Any, answer: str) -> bool:
    """Verdict de ``criteria[].check`` (un contrôle, ou tous ceux d'une liste)."""
    return all(evaluate_check(check, answer) for check in as_checks(value))


__all__ = [
    "CheckError",
    "count_words",
    "email_body",
    "evaluate_check",
    "evaluate_checks",
    "list_items",
    "normalize_text",
    "paragraphs",
    "sentences",
]
