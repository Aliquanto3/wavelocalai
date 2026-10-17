"""Forme des critères de rédaction vérifiés par le code (``criteria[].check``, AD-5, AD-10).

Un critère qui demande de compter (mots, phrases, paragraphes, lignes, éléments de liste) ne va
pas au juge : le correcteur ``judge_criteria`` le vérifie par ``grading/counting.py``. Ce module
ne porte que la forme et sa validation (noyau pur, sans I/O) ; les règles de comptage vivent
dans ``grading/counting.py`` et sont décrites dans ``questions/SOURCES.md``.

```yaml
- {id: c2, question: "… moins de 120 mots ?", check: {count: words, scope: body, op: "<", n: 120}}
- {id: c4, question: "… entre 4 et 6 phrases ?", check: {count: sentences, op: between, min: 4, max: 6}}
- {id: c3, question: "… chaque phrase … moins de 20 mots ?", check: {count: words, per: sentence, op: "<", n: 20}}
- {id: c2, question: "… première phrase … moins de dix mots ?", check: {count: words, of: {sentence: 1}, op: "<", n: 10}}
- {id: c2, question: "… un seul paragraphe de 60 à 100 mots ?",
   check: [{count: paragraphs, op: "==", n: 1}, {count: words, op: between, min: 60, max: 100}]}
```

``check`` est un objet, ou une liste non vide d'objets qui doivent tous être vrais.

- ``count`` : ``words`` | ``sentences`` | ``paragraphs`` | ``lines`` | ``items``.
- ``scope`` (défaut ``text``, toute la réponse) : ``body`` (corps d'un courriel : sans objet,
  formule d'appel, formule de politesse ni signature) | ``before_last`` (tout sauf le dernier
  paragraphe).
- ``of`` : ``{paragraph: N}`` ou ``{sentence: N}`` (à partir de 1) : on compte dans cette seule
  unité du périmètre, et la vérification échoue si elle n'existe pas.
- ``per`` : ``sentence`` | ``paragraph`` | ``item`` | ``line`` : la borne vaut pour chaque unité du
  périmètre (au moins une unité), jamais pour leur total.
- ``marker`` (éléments de liste) : ``bullet`` | ``number`` | ``dash`` | ``any`` (défaut).
- ``sequential`` : éléments numérotés de 1 à N dans l'ordre (``marker: number``).
- ``op`` : ``<`` | ``<=`` | ``>`` | ``>=`` | ``==`` | ``between`` ; ``n`` pour les cinq premiers,
  ``min`` et ``max`` (inclus) pour ``between``.
- ``approx`` : le critère dit « environ » ; les bornes se relâchent de 10 %, arrondies vers
  l'extérieur (``APPROX_TOLERANCE``).
"""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from typing import Any

COUNTS = ("words", "sentences", "paragraphs", "lines", "items")
SCOPES = ("text", "body", "before_last")
OPERATORS = ("<", "<=", ">", ">=", "==", "between")
PER_UNITS = ("sentence", "paragraph", "item", "line")
OF_UNITS = ("sentence", "paragraph")
MARKERS = ("bullet", "number", "dash", "any")
APPROX_TOLERANCE = Fraction(1, 10)  # exact : 100 × 1,1 donne 110, jamais 111 (flottant)

CHECK_KEYS = frozenset(
    {"count", "scope", "of", "per", "marker", "sequential", "op", "n", "min", "max", "approx"}
)


class CheckError(ValueError):
    """Critère vérifié par le code mal formé (message sans texte de question)."""


def _integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CheckError(f"{name} : entier ≥ 0 attendu")
    return value


def as_checks(value: Any) -> list[Mapping[str, Any]]:
    """Les contrôles d'un critère : un objet, ou une liste non vide d'objets."""
    items = value if isinstance(value, list) else [value]
    if not items or not all(isinstance(item, Mapping) for item in items):
        raise CheckError("check : objet, ou liste non vide d'objets, attendu")
    return items


def validate_check(check: Mapping[str, Any]) -> None:
    """``CheckError`` au premier défaut d'un contrôle (voir la docstring du module)."""
    unknown = sorted(str(key) for key in check if key not in CHECK_KEYS)
    if unknown:
        raise CheckError(f"check : clés inconnues {unknown}")
    count = check.get("count")
    if count not in COUNTS:
        raise CheckError(f"check.count : {list(COUNTS)} attendu")
    if check.get("scope", "text") not in SCOPES:
        raise CheckError(f"check.scope : {list(SCOPES)} attendu")
    op = check.get("op")
    if op not in OPERATORS:
        raise CheckError(f"check.op : {list(OPERATORS)} attendu")
    if op == "between":
        low, high = _integer(check.get("min"), "check.min"), _integer(check.get("max"), "check.max")
        if low > high or "n" in check:
            raise CheckError("check : between demande min ≤ max et aucun n")
    else:
        _integer(check.get("n"), "check.n")
        if "min" in check or "max" in check:
            raise CheckError("check : min et max réservés à between")
    approx = check.get("approx", False)
    if not isinstance(approx, bool):
        raise CheckError("check.approx : booléen attendu")
    if "of" in check and "per" in check:
        raise CheckError("check : of et per sont exclusifs")
    sub = "of" in check or "per" in check
    if sub and count not in ("words", "sentences"):
        raise CheckError("check : of et per ne comptent que des mots ou des phrases")
    if "of" in check:
        of = check["of"]
        if not isinstance(of, Mapping) or len(of) != 1 or next(iter(of)) not in OF_UNITS:
            raise CheckError(f"check.of : {{paragraph|sentence: N}} attendu ({list(OF_UNITS)})")
        index = next(iter(of.values()))
        if not isinstance(index, int) or isinstance(index, bool) or index < 1:
            raise CheckError("check.of : rang entier ≥ 1 attendu")
        if next(iter(of)) == "sentence" and count == "sentences":
            raise CheckError("check : compter les phrases d'une phrase n'a pas de sens")
    if "per" in check:
        per = check["per"]
        if per not in PER_UNITS:
            raise CheckError(f"check.per : {list(PER_UNITS)} attendu")
        if per == "sentence" and count == "sentences":
            raise CheckError("check : compter les phrases de chaque phrase n'a pas de sens")
    marker = check.get("marker")
    if marker is not None:
        if marker not in MARKERS:
            raise CheckError(f"check.marker : {list(MARKERS)} attendu")
        if count != "items" and check.get("per") != "item":
            raise CheckError("check.marker : réservé aux éléments de liste")
    if "sequential" in check and (
        check["sequential"] is not True or count != "items" or marker != "number"
    ):
        raise CheckError("check.sequential : true, avec count items et marker number")


def validate_checks(value: Any) -> None:
    """Valide ``criteria[].check`` (objet ou liste d'objets)."""
    for check in as_checks(value):
        validate_check(check)
