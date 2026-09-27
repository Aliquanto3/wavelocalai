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


def format_throughput(tokens_per_second, estimated: bool = False) -> str:
    """Débit : « 78,5 tokens/s », suivi de « (estimé) » s'il est calculé sur la durée murale
    de l'appel plutôt que sur la seule génération."""
    text = format_unit(tokens_per_second, "tokens/s")
    return f"{text} (estimé)" if estimated and text != MISSING else text


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


# ---------------------------------------------------------------------------
# CO₂ (EXPERIENCE.md, « Chiffres ») : valeurs en grammes, comme GreenTracker.stop() et
# CarbonCalculator ; mg sous 1 g, g au-delà, kg au-delà de 1 000 g ; une seule unité dans une
# même comparaison.
# ---------------------------------------------------------------------------

# Grammes par unité affichable.
CO2_UNITS = {"mg": 1e-3, "g": 1.0, "kg": 1e3}
MG_PER_G = 1000.0
G_PER_KG = 1000.0


def mg_to_grams(milligrams) -> float | None:
    """Milligrammes → grammes : 420 → 0.42. None si la valeur est absente ou invalide."""
    number = _to_finite(milligrams)
    return None if number is None else number / MG_PER_G


def grams_to_kg(grams) -> float | None:
    """Grammes → kilogrammes : 0.42 → 0.00042. None si la valeur est absente ou invalide."""
    number = _to_finite(grams)
    return None if number is None else number / G_PER_KG


def _round_significant(number: float, digits: int = 3) -> float:
    """Arrondi à `digits` chiffres significatifs, comme l'affichage (partie entière gardée)."""
    return _round(number, _significant_decimals(number, digits))


def co2_unit(grams) -> str:
    """Unité d'une masse de CO₂ en grammes : « mg » sous 1 g, « g » jusqu'à 1 000 g exclus,
    « kg » au-delà. Choisie après arrondi : 0,9996 g s'affiche « 1 gCO₂ », pas « 1 000 mg ».
    « mg » pour une valeur absente."""
    number = _to_finite(grams)
    if number is None:
        return "mg"
    magnitude = abs(_round_significant(number))
    if magnitude < 1:
        return "mg"
    if magnitude < G_PER_KG:
        return "g"
    return "kg"


def common_co2_unit(values_g) -> str:
    """Unité commune à une comparaison (Arène, évaluation) : celle de la plus petite valeur
    non nulle, en grammes. Toutes les lignes s'affichent dans la même unité, et la plus petite
    garde ses trois chiffres significatifs avec au plus trois décimales (limite des colonnes
    `format="localized"` des tableaux Streamlit) : 7,6 mg et 1,14 g → « 7,6 » et « 1 140 » mg,
    jamais « 0,008 » g."""
    numbers = [abs(n) for n in (_to_finite(v) for v in values_g) if n]
    return co2_unit(min(numbers)) if numbers else "mg"


def co2_in_unit(grams, unit: str) -> float | None:
    """Masse de CO₂ en grammes exprimée dans `unit` (« mg », « g », « kg »)."""
    number = _to_finite(grams)
    if number is None or unit not in CO2_UNITS:
        return None
    return number / CO2_UNITS[unit]


def format_co2(grams, unit: str | None = None) -> str:
    """Masse de CO₂ donnée en grammes : 0.42 → « 420 mgCO₂ », 12 → « 12 gCO₂ »,
    1234 → « 1,23 kgCO₂ » (trois chiffres significatifs au plus). `unit` impose l'unité
    d'une comparaison (voir `common_co2_unit`). « — » pour une valeur absente."""
    chosen = unit if unit in CO2_UNITS else co2_unit(grams)
    value = co2_in_unit(grams, chosen)
    if value is None:
        return MISSING
    return f"{format_significant(value)}{NBSP}{chosen}CO₂"
