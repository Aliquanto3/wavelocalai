"""
Formats d'affichage fr-FR : nombres, pourcentages, mémoire, durées, dates et pluriels.

Fonctions pures, sans streamlit (EXPERIENCE.md, section « Chiffres ») : virgule décimale,
espace fine insécable entre les milliers, espace insécable entre un nombre et son unité,
« — » pour une valeur absente, non numérique ou non finie (NaN, infini, NaT). Aucune
fonction ne lève d'exception.
"""

import math
from datetime import date, datetime, time

# Espace insécable (avant « % », « : » et entre un nombre et son unité).
NBSP = " "
# Espace fine insécable (séparateur des milliers).
NNBSP = " "
# Valeur absente ou non numérique.
MISSING = "—"
# layout.separators de Plotly : virgule décimale, espace fine insécable des milliers (sans
# charger de locale Plotly, servie par un CDN).
PLOTLY_SEPARATORS = "," + NNBSP

# Abréviations des mois selon l'usage de l'Imprimerie nationale (locale fr-FR).
_MONTHS_ABBR = (
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
)


def _to_finite(value) -> float | None:
    """Valeur en float fini, ou None si absente, non numérique, NaN ou infinie."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(number: float, decimals: int) -> float:
    """Arrondi à `decimals` décimales, sans zéro négatif (-0.01 → 0.0 et non -0.0)."""
    rounded = round(number, decimals)
    return 0.0 if rounded == 0 else rounded


def _significant_decimals(number: float, digits: int) -> int:
    """Nombre de décimales qui garde au plus `digits` chiffres significatifs."""
    if number == 0:
        return 0
    return max(0, digits - 1 - math.floor(math.log10(abs(number))))


def format_number(value, decimals: int = 1) -> str:
    """Nombre au format fr-FR : 12345.6 → « 12 345,6 » (espace fine insécable)."""
    number = _to_finite(value)
    if number is None:
        return MISSING
    text = f"{_round(number, decimals):,.{decimals}f}"
    # Format anglais « 12,345.6 » → « 12 345,6 ».
    return text.replace(",", NNBSP).replace(".", ",")


def format_significant(value, digits: int = 3) -> str:
    """Au plus `digits` chiffres significatifs, sans zéro final : 0.66 → « 0,66 »,
    12.345 → « 12,3 ». La partie entière n'est jamais arrondie : 1234.5 → « 1 234 »."""
    number = _to_finite(value)
    if number is None:
        return MISSING
    text = format_number(number, _significant_decimals(number, digits))
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


def format_unit(value, unit: str, decimals: int = 1) -> str:
    """Nombre suivi de son unité, séparés par une espace insécable : « 13,8 Go »."""
    number = format_number(value, decimals)
    return number if number == MISSING else f"{number}{NBSP}{unit}"


def format_percent(value, decimals: int = 1) -> str:
    """Pourcentage exprimé en points (8.1 pour 8,1 %) : « 8,1 % »."""
    return format_unit(value, "%", decimals)


def format_gb(value, decimals: int = 1) -> str:
    """Quantité de mémoire en gigaoctets : « 13,8 Go », jamais en unité anglaise."""
    return format_unit(value, "Go", decimals)


def format_duration(seconds) -> str:
    """Durée : « 0,66 s » sous la minute, « 1 min 12 s » au-delà, « 1 h 5 min » au-delà
    d'une heure. L'unité est choisie après arrondi : 59,97 s s'affiche « 1 min »."""
    total = _to_finite(seconds)
    if total is None:
        return MISSING
    if _round(total, _significant_decimals(total, 3)) < 60:
        return f"{format_significant(total)}{NBSP}s"

    whole = round(total)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}{NBSP}h {minutes}{NBSP}min" if minutes else f"{hours}{NBSP}h"
    return f"{minutes}{NBSP}min {secs}{NBSP}s" if secs else f"{minutes}{NBSP}min"


def _is_nat(value) -> bool:
    """pandas.NaT est une instance de datetime, mais différente d'elle-même."""
    return value != value  # noqa: PLR0124


def format_date(value) -> str:
    """Date : 2026-09-26 → « 26 sept. 2026 ». Accepte date, datetime et pandas.Timestamp."""
    if value is None or not isinstance(value, date) or _is_nat(value):
        return MISSING
    return f"{value.day}{NBSP}{_MONTHS_ABBR[value.month - 1]}{NBSP}{value.year}"


def format_time(value) -> str:
    """Heure : « 09:15 ». Accepte datetime, time et pandas.Timestamp."""
    if value is None or not isinstance(value, (datetime, time)) or _is_nat(value):
        return MISSING
    return f"{value.hour:02d}:{value.minute:02d}"


def pluralize(count, singular: str, plural: str | None = None) -> str:
    """Nombre et nom accordé : « 0 extrait », « 1 extrait », « 3 extraits ».

    En français, 0 et 1 (et toute valeur inférieure à 2) prennent le singulier. L'accord suit
    le nombre affiché, arrondi à une décimale : 1.97 → « 2 extraits ». `plural` vaut
    `singular + "s"` par défaut ; `singular` peut contenir plusieurs mots (« extrait ajouté »
    → passer `plural="extraits ajoutés"`).
    """
    number = _to_finite(count)
    if number is None:
        return MISSING
    shown = _round(number, 1)
    word = singular if abs(shown) < 2 else (plural or f"{singular}s")
    decimals = 0 if shown.is_integer() else 1
    return f"{format_number(shown, decimals)}{NBSP}{word}"
