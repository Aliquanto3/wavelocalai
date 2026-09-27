"""
Graphiques lisibles et justes (EXPERIENCE.md, « Chiffres » et « Graphiques ») : couleur liée à
l'entité, historique d'émissions par session, échelles et étiquettes des matrices.

- Couleurs : jetons de la palette du thème actif (`chartCategoricalColors`), jamais un hex.
  Plotly reçoit les jetons que Streamlit remplace côté navigateur par la palette du thème
  affiché (clair ou sombre, y compris après un changement de thème) ; Vega-Lite reçoit un
  domaine de couleur ordonné par entité, que Streamlit colore avec la même palette.
- Couleur par entité : un modèle (clé : son tag) garde sa place dans la palette d'une
  comparaison à l'autre et d'une page à l'autre (`entity_slots`, registre de session
  unique), quels que soient son rang, les modèles filtrés ou ceux en échec.
- Historique : une barre par session, dans l'unité CO₂ de la règle (`common_co2_unit`),
  sur une fenêtre de temps ; aucune liaison entre deux mesures.

Le module importe streamlit (configuration, session, jetons du thème Plotly). Lisent la
configuration : `palette_size` et `ink_expr` ; la session : `remember_entity_slots` ; l'heure
et le fuseau de la machine : `prepare_emissions_history` quand `now` ou `tz` n'est pas donné.
Les autres fonctions sont pures.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from dateutil import tz as dateutil_tz

from src.app.formatting import co2_in_unit, common_co2_unit, format_co2, pluralize

try:
    # Module interne de Streamlit (version figée par constraints.txt) : s'il disparaît, les
    # pages se chargent quand même, avec les couleurs du thème par défaut (ordre des traces).
    from streamlit.elements.lib import streamlit_plotly_theme as _plotly_theme
except ImportError:  # pragma: no cover - dépend de la version de Streamlit
    _plotly_theme = None

# ---------------------------------------------------------------------------
# Palette du thème
# ---------------------------------------------------------------------------

# Jetons de Streamlit pour Plotly : « catégorie 0 » à « catégorie 9 », remplacés dans le
# navigateur par chartCategoricalColors du thème affiché (thème « streamlit » de
# st.plotly_chart, par défaut). Ce ne sont pas des couleurs : aucune ne s'affiche telle quelle.
# Sans le module (repli) : aucun jeton, Plotly garde les couleurs par défaut du thème.
THEME_CATEGORY_TOKENS: tuple[str, ...] = (
    tuple(getattr(_plotly_theme, f"CATEGORY_{i}") for i in range(10)) if _plotly_theme else ()
)
# Fond du thème affiché (anneau de 2 px autour des points qui se chevauchent).
THEME_SURFACE_TOKEN: str | None = getattr(_plotly_theme, "BG_COLOR", None)
# Gris du thème affiché (traits qui relient une étiquette à son point, non textuels).
THEME_GRAY_TOKEN: str | None = getattr(_plotly_theme, "GRAY_70", None)
# Texte du thème affiché (gris très foncé en clair, très clair en sombre) : étiquettes
# directes, jamais dans la couleur de la série.
THEME_TEXT_TOKEN: str | None = getattr(_plotly_theme, "GRAY_90", None)
# Taille de la palette par défaut de Streamlit (et nombre de jetons « catégorie »).
DEFAULT_PALETTE_SIZE = 10

# Codage secondaire au-delà de la palette : la couleur revient, la forme change (jamais une
# teinte générée). L'étoile est réservée au vainqueur de l'Arène.
SECONDARY_SYMBOLS = ("circle", "square", "diamond", "triangle-up")

_PALETTE_OPTIONS = (
    "theme.chartCategoricalColors",
    "theme.light.chartCategoricalColors",
    "theme.dark.chartCategoricalColors",
)


def palette_size() -> int:
    """Nombre de couleurs de la palette catégorielle configurée (4 pour la charte), la plus
    courte des palettes claire et sombre ; 10 (palette par défaut de Streamlit) sinon."""
    sizes = []
    for option in _PALETTE_OPTIONS:
        try:
            colors = st.get_option(option)
        except Exception:  # option inconnue d'une autre version de Streamlit
            continue
        if colors:
            sizes.append(len(colors))
    return max(1, min([*sizes, DEFAULT_PALETTE_SIZE]))


def slot_color(slot: int, n_colors: int) -> str | None:
    """Jeton de couleur Plotly de la place `slot` (la palette recommence au-delà) ; None sans
    jetons (couleur par défaut du thème)."""
    if not THEME_CATEGORY_TOKENS:
        return None
    return THEME_CATEGORY_TOKENS[slot % min(n_colors, len(THEME_CATEGORY_TOKENS))]


def slot_symbol(slot: int, n_colors: int) -> str:
    """Forme de la place `slot` : cercle pour les premières, puis carré, losange…"""
    return SECONDARY_SYMBOLS[(slot // n_colors) % len(SECONDARY_SYMBOLS)]


def entity_slots(
    names: Iterable[str], previous: Mapping[str, int] | None = None, n_colors: int = 4
) -> dict[str, int]:
    """
    Place dans la palette de chaque entité (modèle), stable d'une comparaison à l'autre.

    - Une entité déjà vue garde sa place si aucune autre entité affichée ne l'occupe.
    - Une nouvelle entité prend la première place libre, en évitant d'abord les places
      retenues par des entités absentes (elles la retrouveront si elles reviennent).
    - Jamais deux entités affichées à la même place : au-delà de la palette, la place
      suivante (même couleur, autre forme).

    Args:
        names: entités affichées, dans l'ordre stable de la sélection (pas du classement).
        previous: places déjà attribuées (session).
        n_colors: taille de la palette.
    """
    previous = dict(previous or {})
    unique = list(dict.fromkeys(names))
    slots: dict[str, int] = {}
    taken: set[int] = set()
    for name in unique:
        slot = previous.get(name)
        if slot is not None and slot not in taken:
            slots[name] = slot
            taken.add(slot)
    reserved = {slot for name, slot in previous.items() if name not in slots}
    for name in unique:
        if name in slots:
            continue
        free = [i for i in range(n_colors) if i not in taken and i not in reserved]
        if not free:
            free = [i for i in range(n_colors) if i not in taken]
        slot = free[0] if free else next(i for i in range(n_colors, 10**6) if i not in taken)
        slots[name] = slot
        taken.add(slot)
    return slots


# Registre unique des places dans la palette, par tag de modèle : un modèle garde sa couleur
# dans l'Arène comme dans l'évaluation de la qualité.
ENTITY_SLOTS_KEY = "chart_entity_slots"


def remember_entity_slots(tags: Iterable[str]) -> dict[str, int]:
    """`entity_slots` des modèles `tags`, mémorisées dans la session (registre unique
    ENTITY_SLOTS_KEY, commun à toutes les pages) : un modèle garde sa couleur d'une
    comparaison et d'une page à l'autre, tant que la session reste ouverte."""
    previous = st.session_state.get(ENTITY_SLOTS_KEY) or {}
    slots = entity_slots(tags, previous, palette_size())
    st.session_state[ENTITY_SLOTS_KEY] = {**previous, **slots}
    return slots


def vega_color_domain(slots: Mapping[str, int]) -> list[str]:
    """Domaine de couleur Vega-Lite où chaque entité est à sa place : la palette du thème
    (range « category ») associe la i-ème valeur du domaine à la i-ème couleur. Les places
    vides reçoivent une valeur invisible, jamais présente dans les données ni la légende."""
    if not slots:
        return []
    by_slot = {slot: name for name, slot in slots.items()}
    return [by_slot.get(i, "⁣" * (i + 1)) for i in range(max(by_slot) + 1)]


def ink_expr() -> dict | None:
    """Couleur de texte du thème affiché, en expression Vega : l'encre claire ou sombre de
    config.toml qui contraste le plus avec le fond du graphique (signal `background`, posé
    par Streamlit). Aucune couleur en dur ; None si le thème n'en définit pas."""
    try:
        light = st.get_option("theme.light.textColor") or st.get_option("theme.textColor")
        dark = st.get_option("theme.dark.textColor") or st.get_option("theme.textColor")
    except Exception:
        return None
    if not light or not dark:
        return None
    return {
        "expr": f"contrast(background, '{light}') >= contrast(background, '{dark}') "
        f"? '{light}' : '{dark}'"
    }


# ---------------------------------------------------------------------------
# Échelles et étiquettes des matrices
# ---------------------------------------------------------------------------


def _finite(values: Iterable) -> list[float]:
    numbers = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            numbers.append(number)
    return numbers


def zero_based_range(values: Iterable, headroom: float = 0.15) -> list[float]:
    """Axe honnête : de 0 au maximum plus une marge (jamais resserré sur les seules valeurs).
    [0, 1] sans valeur positive."""
    numbers = _finite(values)
    top = max(numbers, default=0.0)
    return [0.0, top * (1 + headroom) if top > 0 else 1.0]


def label_side(x, x_upper: float) -> str:
    """Côté de l'étiquette d'un point pour qu'elle reste dans le cadre : « left » dans la
    moitié droite de l'axe, « right » sinon."""
    numbers = _finite([x])
    if not numbers or x_upper <= 0:
        return "right"
    return "left" if numbers[0] > x_upper / 2 else "right"


@dataclass
class PointLabel:
    """Étiquette d'un point : ordonnée de l'étiquette (unités de l'axe y) et côté du point
    où elle se place (« left » ou « right »), reliée au point par un trait."""

    y: float
    side: str


def stacked_labels(
    points: list[tuple],
    x_upper: float,
    y_low: float = 0.0,
    y_high: float = 100.0,
    gap: float = 13.0,
) -> list[PointLabel | None]:
    """
    Étiquettes lisibles de points proches (5,8 à 6 tokens/s sur un axe depuis 0) : chaque
    étiquette se place du côté intérieur de l'axe x (`label_side`), et les étiquettes d'un
    même côté s'empilent à `gap` unités d'écart au moins, en partant du point le plus haut,
    sans sortir de [y_low ; y_high] (l'écart se resserre si elles sont trop nombreuses pour
    tenir). None pour un point sans coordonnées.
    """
    labels: list[PointLabel | None] = [None] * len(points)
    groups: dict[str, list[tuple[float, int]]] = {}
    for i, (x, y) in enumerate(points):
        xs, ys = _finite([x]), _finite([y])
        if xs and ys:
            groups.setdefault(label_side(xs[0], x_upper), []).append((ys[0], i))
    for side, members in groups.items():
        members.sort(key=lambda m: -m[0])
        step = min(gap, (y_high - y_low) / max(1, len(members) - 1))
        # Descente depuis le point le plus haut : chaque étiquette sous la précédente.
        stack: list[float] = []
        for y, _ in members:
            y = min(max(y, y_low), y_high)
            stack.append(y if not stack else min(y, stack[-1] - step))
        # Remontée depuis le bas : aucune étiquette sous y_low, écart conservé.
        stack[-1] = max(stack[-1], y_low)
        for k in range(len(stack) - 2, -1, -1):
            stack[k] = max(stack[k], stack[k + 1] + step)
        for (_, i), label_y in zip(members, stack, strict=True):
            labels[i] = PointLabel(y=label_y, side=side)
    return labels


# Diamètres des points de l'Arène (px) : au moins 10 px pour rester visible et cliquable.
BUBBLE_MIN_PX = 10.0
BUBBLE_MAX_PX = 44.0


def bubble_sizes(values: Iterable) -> list[float]:
    """Diamètre de chaque point : surface proportionnelle à la valeur (CO₂), le plus gros à
    BUBBLE_MAX_PX, jamais sous BUBBLE_MIN_PX ; valeur absente = BUBBLE_MIN_PX."""
    values = list(values)
    top = max(_finite(values), default=0.0)
    sizes = []
    for value in values:
        numbers = _finite([value])
        if not numbers or top <= 0 or numbers[0] <= 0:
            sizes.append(BUBBLE_MIN_PX)
        else:
            sizes.append(max(BUBBLE_MIN_PX, BUBBLE_MAX_PX * math.sqrt(numbers[0] / top)))
    return sizes


def size_legend_text(values_g: Iterable, unit: str) -> str:
    """Légende de taille : « Taille du point : CO₂ de la réponse, de 7,6 mgCO₂ à
    1 140 mgCO₂. » (une seule valeur : « … CO₂ de la réponse, 7,6 mgCO₂. »)."""
    numbers = _finite(values_g)
    if not numbers:
        return "Taille du point : CO₂ de la réponse."
    low, high = min(numbers), max(numbers)
    if format_co2(low, unit) == format_co2(high, unit):
        return f"Taille du point : CO₂ de la réponse, {format_co2(high, unit)}."
    return (
        f"Taille du point : CO₂ de la réponse, de {format_co2(low, unit)} "
        f"à {format_co2(high, unit)}."
    )


# ---------------------------------------------------------------------------
# Historique des émissions (Sobriété et matériel)
# ---------------------------------------------------------------------------

ALL_WINDOW = "Tout"
HISTORY_WINDOWS: dict[str, timedelta | None] = {
    "7 derniers jours": timedelta(days=7),
    "30 derniers jours": timedelta(days=30),
    ALL_WINDOW: None,
}
DEFAULT_HISTORY_WINDOW = "7 derniers jours"
EMPTY_WINDOW_TEXT = "Aucune session sur cette période."


def empty_window_text(older_count: int) -> str:
    """Fenêtre vide : le dire, et signaler les sessions plus anciennes s'il y en a."""
    if older_count <= 0:
        return EMPTY_WINDOW_TEXT
    older = pluralize(older_count, "session plus ancienne", "sessions plus anciennes")
    return f"{EMPTY_WINDOW_TEXT} {older} : choisissez « {ALL_WINDOW} » pour les afficher."


# Place d'un horodatage : 1/60 de la période affichée, 80 % de l'écart avec l'horodatage
# voisin au plus (deux barres ne se touchent jamais).
_BAR_SHARE = 1 / 60
_BAR_GAP_SHARE = 0.8
# Période minimale de l'axe (« Tout » avec une seule session, ou des sessions rapprochées).
_MIN_SPAN = timedelta(days=1)
# Marge de part et d'autre de la période (la barre de la dernière session reste entière).
_SPAN_PADDING = 0.03


@dataclass
class EmissionsHistory:
    """Sessions de la fenêtre, prêtes à tracer.

    `sessions` : colonnes `timestamp` (heure locale), `co2` (dans `unit`), `emissions_g`,
    `hover` (date numérique et CO₂ en fr-FR), `width_ms` et `offset_ms` (largeur et
    décalage de la barre sur l'axe du temps, en ms).
    `x_range` : période affichée (bornes de l'axe du temps).
    `older_count` : sessions antérieures à la fenêtre (non affichées).
    `all_time` : fenêtre « Tout ».
    """

    sessions: pd.DataFrame
    unit: str
    x_range: tuple[datetime, datetime]
    older_count: int = 0
    all_time: bool = False

    @property
    def empty(self) -> bool:
        return self.sessions.empty

    @property
    def show_year(self) -> bool:
        """Année sur l'axe : fenêtre « Tout » (période quelconque) ou à cheval sur deux
        années."""
        start, end = self.x_range
        return self.all_time or start.year != end.year


def _local_naive(timestamps: pd.Series, tz=None) -> pd.Series:
    """Horodatages en heure locale sans fuseau (CodeCarbon écrit l'heure locale). Un
    horodatage avec fuseau est converti dans `tz` (fuseau de la machine par défaut), avec le
    décalage de sa propre date (heure d'été comprise), pas celui du moment présent."""
    stamps = pd.to_datetime(timestamps, errors="coerce")
    if getattr(stamps.dt, "tz", None) is not None:
        stamps = stamps.dt.tz_convert(tz or dateutil_tz.tzlocal()).dt.tz_localize(None)
    return stamps


def _bar_geometry_ms(stamps: list[pd.Timestamp], span: timedelta) -> tuple[list, list]:
    """Largeur et décalage de chaque barre (ms). La place d'un horodatage vaut 1/60 de la
    période, 80 % de l'écart avec l'horodatage distinct le plus proche au plus : jamais
    jusqu'à la voisine, même au prix d'une barre fine (valeurs dans la vue tableau). Des
    sessions au même horodatage se partagent cette place, côte à côte."""
    span_ms = span.total_seconds() * 1000
    distinct = sorted(set(stamps))
    place: dict = {}
    for u, stamp in enumerate(distinct):
        neighbours = distinct[max(0, u - 1) : u] + distinct[u + 1 : u + 2]
        gaps = [abs((n - stamp).total_seconds()) * 1000 for n in neighbours]
        place[stamp] = min([span_ms * _BAR_SHARE, *(_BAR_GAP_SHARE * g for g in gaps)])
    counts = {stamp: stamps.count(stamp) for stamp in distinct}
    seen: dict = {}
    widths, offsets = [], []
    for stamp in stamps:
        total, k = place[stamp], counts[stamp]
        j = seen.get(stamp, 0)
        seen[stamp] = j + 1
        widths.append(total / k)
        offsets.append(-total / 2 + j * total / k)
    return widths, offsets


def prepare_emissions_history(
    df: pd.DataFrame,
    window: str = DEFAULT_HISTORY_WINDOW,
    now: datetime | None = None,
    tz=None,
) -> EmissionsHistory:
    """
    Sessions de `df` (sortie de `read_app_emissions` : `timestamp`, `emissions_g`) sur la
    fenêtre `window` (clé de HISTORY_WINDOWS ; « Tout » par défaut si inconnue), dans l'unité
    CO₂ commune à ces sessions (mg sous 1 g…).

    Une barre par session, centrée sur son horodatage, sans liaison avec la voisine : une
    période sans mesure reste vide. `now` et `tz` (fuseau des horodatages qui en portent un)
    valent par défaut l'heure et le fuseau de la machine.
    """
    now = now or datetime.now()
    duration = HISTORY_WINDOWS.get(window)
    data = pd.DataFrame(
        {
            "timestamp": _local_naive(df["timestamp"], tz),
            "emissions_g": pd.to_numeric(df["emissions_g"], errors="coerce"),
        }
    ).dropna()
    older_count = 0
    if duration is not None:
        in_window = data["timestamp"] >= now - duration
        older_count = int((~in_window).sum())
        data = data[in_window]
    data = data.sort_values("timestamp").reset_index(drop=True)

    unit = common_co2_unit(data["emissions_g"])
    if duration is not None:
        start, end = now - duration, max([now, *data["timestamp"]])
    elif not data.empty:
        start, end = data["timestamp"].min(), data["timestamp"].max()
    else:
        start, end = now - _MIN_SPAN, now
    start, end = pd.Timestamp(start).to_pydatetime(), pd.Timestamp(end).to_pydatetime()
    if end - start < _MIN_SPAN:
        middle = start + (end - start) / 2
        start, end = middle - _MIN_SPAN / 2, middle + _MIN_SPAN / 2
    padding = (end - start) * _SPAN_PADDING
    x_range = (start - padding, end + padding)

    stamps = list(data["timestamp"])
    data["co2"] = [co2_in_unit(g, unit) for g in data["emissions_g"]]
    # Date numérique (« 27/09/2026 09:00 ») : jamais le nom du mois en anglais.
    data["hover"] = [
        f"{ts:%d/%m/%Y %H:%M}<br>{format_co2(g, unit)}"
        for ts, g in zip(stamps, data["emissions_g"], strict=True)
    ]
    data["width_ms"], data["offset_ms"] = _bar_geometry_ms(stamps, x_range[1] - x_range[0])
    return EmissionsHistory(
        sessions=data,
        unit=unit,
        x_range=x_range,
        older_count=older_count,
        all_time=duration is None,
    )
