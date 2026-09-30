"""
Tests des aides aux graphiques (src/app/charts.py, story 10) : couleur liée à l'entité,
échelles honnêtes, étiquettes dans le cadre, historique d'émissions par session.

Usage: python -m pytest tests/unit/test_charts.py -v
"""

from datetime import datetime, timedelta
from pathlib import Path

import importlib.util
import sys
from types import SimpleNamespace

import pandas as pd
import pytest
import streamlit

import src.app.charts as charts

from src.app.charts import (
    BUBBLE_MAX_PX,
    BUBBLE_MIN_PX,
    DEFAULT_HISTORY_WINDOW,
    ENTITY_SLOTS_KEY,
    HISTORY_WINDOWS,
    THEME_CATEGORY_TOKENS,
    THEME_GRAY_TOKEN,
    THEME_SURFACE_TOKEN,
    THEME_TEXT_TOKEN,
    bubble_sizes,
    empty_window_text,
    entity_slots,
    ink_expr,
    label_side,
    palette_size,
    prepare_emissions_history,
    remember_entity_slots,
    size_legend_text,
    slot_color,
    slot_symbol,
    stacked_labels,
    vega_color_domain,
    zero_based_range,
)
from src.app.formatting import NBSP, NNBSP

NOW = datetime(2026, 9, 27, 12, 0)


# ---------------------------------------------------------------------------
# Palette du thème
# ---------------------------------------------------------------------------


def test_palette_size_reads_theme():
    """Charte : quatre couleurs catégorielles, en clair comme en sombre (config.toml)."""
    assert palette_size() == 4


def test_theme_tokens_are_replaced_by_streamlit_frontend():
    """Les jetons passés à Plotly sont ceux que le navigateur remplace par la palette et le
    fond du thème affiché : un changement de version de Streamlit qui les abandonnerait
    afficherait du noir. Vérifié dans le bundle livré avec la version installée."""
    js_dir = Path(streamlit.__file__).parent / "static" / "static" / "js"
    bundle = "".join(p.read_text(encoding="utf-8") for p in js_dir.glob("PlotlyChart*.js"))
    assert "chartCategoricalColors" in bundle
    for token in (
        *THEME_CATEGORY_TOKENS[:4],
        THEME_SURFACE_TOKEN,
        THEME_GRAY_TOKEN,
        THEME_TEXT_TOKEN,
    ):
        assert f"`{token}`" in bundle


def test_slot_color_and_symbol_beyond_palette():
    """Au-delà de la palette, la couleur revient mais la forme change (jamais une teinte
    générée)."""
    assert slot_color(0, 4) == THEME_CATEGORY_TOKENS[0]
    assert slot_color(5, 4) == THEME_CATEGORY_TOKENS[1]
    assert slot_symbol(0, 4) == "circle"
    assert slot_symbol(5, 4) == "square"


# ---------------------------------------------------------------------------
# Couleur liée à l'entité
# ---------------------------------------------------------------------------


def test_entity_slots_follow_selection_order():
    assert entity_slots(["A", "B", "C"]) == {"A": 0, "B": 1, "C": 2}


def test_entity_slots_survive_filter():
    """A, B, C puis B, C : B et C gardent leur place (donc leur couleur)."""
    first = entity_slots(["A", "B", "C"])
    assert entity_slots(["B", "C"], first) == {"B": 1, "C": 2}


def test_entity_slots_new_entity_avoids_absent_ones():
    """Un nouveau modèle prend une place libre, pas celle d'un modèle momentanément absent."""
    assert entity_slots(["B", "C", "D"], {"A": 0, "B": 1, "C": 2}) == {"B": 1, "C": 2, "D": 3}
    # Palette pleine : une place d'absent est reprise plutôt qu'une couleur en double.
    previous = {"A": 0, "B": 1, "C": 2, "D": 3}
    assert entity_slots(["B", "E"], previous) == {"B": 1, "E": 0}


def test_entity_slots_never_share_a_slot():
    """Deux entités affichées ne partagent jamais une place, même en conflit d'historique."""
    slots = entity_slots(["A", "D"], {"A": 0, "D": 0})
    assert slots == {"A": 0, "D": 1}
    many = entity_slots([f"M{i}" for i in range(6)], n_colors=4)
    assert sorted(many.values()) == [0, 1, 2, 3, 4, 5]


def test_vega_color_domain_keeps_places():
    """Domaine de couleur Vega : chaque entité à sa place, places vides invisibles."""
    domain = vega_color_domain({"B": 1, "C": 2})
    assert domain[1:] == ["B", "C"]
    assert domain[0] not in {"B", "C"} and not domain[0].strip("⁣")
    assert vega_color_domain({}) == []


# ---------------------------------------------------------------------------
# Échelles et étiquettes
# ---------------------------------------------------------------------------


def test_zero_based_range_is_never_tight():
    """5,8 à 6 tokens/s : l'axe part de 0, pas de 5,8."""
    assert zero_based_range([5.8, 5.9, 6.0]) == pytest.approx([0, 6.9])
    assert zero_based_range([None, float("nan")]) == [0, 1]
    assert zero_based_range([3.8], headroom=0.25) == pytest.approx([0, 4.75])


def test_stacked_labels_do_not_overlap():
    """Trois points proches (5,8 à 6 tokens/s, notes 91, 85, 72) : étiquettes à gauche
    (vers l'intérieur), empilées à 13 unités d'écart au moins, depuis le point le plus haut."""
    labels = stacked_labels([(6.0, 91), (5.9, 85), (5.8, 72)], 6.9)
    assert [label.side for label in labels] == ["left"] * 3
    assert [label.y for label in labels] == pytest.approx([91, 78, 65])


def test_stacked_labels_stay_inside_the_axis():
    """Points serrés en bas de l'échelle : la pile remonte pour rester dans [0 ; 100]."""
    labels = stacked_labels([(6.0, 5), (5.9, 4), (5.8, 3)], 6.9)
    ys = sorted(label.y for label in labels)
    assert ys == pytest.approx([0, 13, 26])
    # Point dans la moitié gauche : étiquette à droite ; sans coordonnées : pas d'étiquette.
    right, missing = stacked_labels([(1.0, 50), (None, 80)], 6.9)
    assert right.side == "right" and right.y == 50
    assert missing is None


def test_stacked_labels_high_and_low_points():
    """Notes 100, 5 et 4 : le haut reste à 100, aucune étiquette sous 0, écart gardé."""
    labels = stacked_labels([(6.0, 100), (5.9, 5), (5.8, 4)], 6.9)
    assert [label.y for label in labels] == pytest.approx([100, 13, 0])


def test_stacked_labels_many_labels_tighten_the_gap():
    """9 étiquettes d'un même côté : l'écart se resserre (100 / 8 = 12,5) pour tenir dans
    [0 ; 100], sans chevauchement."""
    labels = stacked_labels([(6.0, 50 - i * 0.1) for i in range(9)], 6.9)
    ys = sorted(label.y for label in labels)
    assert min(ys) >= 0 and max(ys) <= 100
    steps = [b - a for a, b in zip(ys[:-1], ys[1:], strict=True)]
    assert min(steps) == pytest.approx(12.5)


def test_label_side():
    assert label_side(3.8, 4.75) == "left"
    assert label_side(1.0, 4.75) == "right"
    assert label_side(1.0, 0) == "right"


def test_bubble_sizes_area_proportional():
    """Surface proportionnelle au CO₂ : 4 fois plus de CO₂ = 2 fois le diamètre."""
    assert bubble_sizes([10, 40, None]) == pytest.approx(
        [BUBBLE_MAX_PX / 2, BUBBLE_MAX_PX, BUBBLE_MIN_PX]
    )
    assert bubble_sizes([0.001, 1000])[0] == BUBBLE_MIN_PX


def test_size_legend_text():
    assert size_legend_text([0.0076, 1.14], "mg") == (
        f"Taille du point : CO₂ de la réponse, de 7,6{NBSP}mgCO₂ à 1{NNBSP}140{NBSP}mgCO₂."
    )
    assert size_legend_text([0.0076], "mg") == (
        f"Taille du point : CO₂ de la réponse, 7,6{NBSP}mgCO₂."
    )


# ---------------------------------------------------------------------------
# Historique des émissions
# ---------------------------------------------------------------------------


def _history(rows):
    """DataFrame au format de read_app_emissions : (horodatage, grammes)."""
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime([ts for ts, _ in rows]),
            "project_name": "wavelocal_session",
            "emissions": [g / 1000 for _, g in rows],
            "emissions_g": [g for _, g in rows],
        }
    )


def test_history_values_in_rule_unit():
    """0,42 g, 0,63 g et 1,2 g : mg (unité de la plus petite), 420, 630 et 1 200."""
    df = _history(
        [
            (NOW - timedelta(hours=3), 0.42),
            (NOW - timedelta(hours=2), 0.63),
            (NOW - timedelta(hours=1), 1.2),
        ]
    )
    history = prepare_emissions_history(df, DEFAULT_HISTORY_WINDOW, NOW)
    assert history.unit == "mg"
    assert list(history.sessions["co2"]) == pytest.approx([420, 630, 1200])
    # Date numérique dans l'info-bulle (jamais « Sep 27 »).
    assert history.sessions["hover"][0] == f"27/09/2026 09:00<br>420{NBSP}mgCO₂"


def test_history_bars_do_not_touch():
    """Sessions à 09:00 et 11:00 : chaque barre s'arrête avant sa voisine (trou visible)."""
    df = _history([(datetime(2026, 9, 27, 9), 0.42), (datetime(2026, 9, 27, 11), 0.63)])
    history = prepare_emissions_history(df, DEFAULT_HISTORY_WINDOW, NOW)
    widths = list(history.sessions["width_ms"])
    gap_ms = 2 * 3600 * 1000
    assert widths[0] / 2 + widths[1] / 2 < gap_ms
    assert min(widths) > 0


def test_history_same_timestamp_sessions_side_by_side():
    """Deux sessions au même horodatage, une troisième deux heures plus tard : les deux
    premières se partagent leur place côte à côte, sans recouvrir la troisième."""
    t = datetime(2026, 9, 27, 9)
    df = _history([(t, 0.42), (t, 0.63), (t + timedelta(hours=2), 1.2)])
    sessions = prepare_emissions_history(df, DEFAULT_HISTORY_WINDOW, NOW).sessions
    widths, offsets = list(sessions["width_ms"]), list(sessions["offset_ms"])
    # Bords [début ; fin] de chaque barre, en ms depuis t.
    edges = [
        (x * 3_600_000 + offset, x * 3_600_000 + offset + width)
        for x, offset, width in zip((0, 0, 2), offsets, widths, strict=True)
    ]
    assert edges[0][1] <= edges[1][0]  # côte à côte, sans superposition
    assert edges[1][1] < edges[2][0]  # un vide avant la session suivante
    assert widths[0] == pytest.approx(widths[1])
    assert edges[0][0] == pytest.approx(-(edges[1][1]))  # groupe centré sur t


def test_history_year_on_long_periods():
    """L'année s'affiche sur l'axe pour « Tout » ou à cheval sur deux années, pas sur
    7 jours dans une même année."""
    df = _history([(NOW - timedelta(days=100), 1.2), (NOW - timedelta(days=1), 0.42)])
    assert prepare_emissions_history(df, "Tout", NOW).show_year
    assert not prepare_emissions_history(df, "7 derniers jours", NOW).show_year
    new_year = datetime(2027, 1, 2, 12)
    df = _history([(new_year - timedelta(days=3), 0.42)])
    assert prepare_emissions_history(df, "7 derniers jours", new_year).show_year


@pytest.mark.parametrize(
    ("window", "expected"),
    [("7 derniers jours", [420]), ("30 derniers jours", [630, 420]), ("Tout", [1200, 630, 420])],
)
def test_history_window(window, expected):
    """Sessions sur 40 jours : seules celles de la fenêtre choisie."""
    df = _history(
        [
            (NOW - timedelta(days=40), 1.2),
            (NOW - timedelta(days=10), 0.63),
            (NOW - timedelta(days=1), 0.42),
        ]
    )
    history = prepare_emissions_history(df, window, NOW)
    assert list(history.sessions["co2"]) == pytest.approx(expected)
    start, end = history.x_range
    duration = HISTORY_WINDOWS[window]
    if duration is not None:
        # L'axe couvre toute la fenêtre, même sans session à ses bords.
        assert start <= NOW - duration and end >= NOW


def test_history_empty_window():
    """Fenêtre vide, sessions plus anciennes : le message les compte et invite à « Tout »."""
    df = _history([(NOW - timedelta(days=40), 0.42), (NOW - timedelta(days=41), 0.5)])
    history = prepare_emissions_history(df, "7 derniers jours", NOW)
    assert history.empty
    assert history.older_count == 2
    assert empty_window_text(history.older_count) == (
        f"Aucune session sur cette période. 2{NBSP}sessions plus anciennes : choisissez "
        "« Tout » pour les afficher."
    )
    assert empty_window_text(0) == "Aucune session sur cette période."


def test_history_all_single_session_has_readable_span():
    """« Tout » avec une seule session : axe d'au moins un jour, centré sur la session."""
    df = _history([(NOW, 0.42)])
    history = prepare_emissions_history(df, "Tout", NOW)
    start, end = history.x_range
    assert end - start >= timedelta(days=1)
    assert start < NOW < end


def test_history_timezone_aware_timestamps():
    """Horodatages avec fuseau : convertis dans le fuseau donné avec le décalage de leur
    propre date (heure d'été en juillet, d'hiver en janvier), puis sans fuseau."""
    df = _history([(datetime(2026, 1, 15, 10), 0.42), (datetime(2026, 7, 15, 10), 0.63)])
    df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
    history = prepare_emissions_history(df, "Tout", NOW, tz="Europe/Paris")
    stamps = history.sessions["timestamp"]
    assert stamps.dt.tz is None
    assert list(stamps) == [datetime(2026, 1, 15, 11), datetime(2026, 7, 15, 12)]


# ---------------------------------------------------------------------------
# Configuration, session et repli
# ---------------------------------------------------------------------------


def _fake_options(options: dict):
    def get_option(key):
        return options.get(key)

    return get_option


def test_ink_expr_from_theme(monkeypatch):
    """Encres claire et sombre du thème : expression exacte, choisie contre le fond."""
    options = {"theme.light.textColor": "#0A0A14", "theme.dark.textColor": "#F6F5FA"}
    monkeypatch.setattr(charts, "st", SimpleNamespace(get_option=_fake_options(options)))
    assert ink_expr() == {
        "expr": "contrast(background, '#0A0A14') >= contrast(background, '#F6F5FA') "
        "? '#0A0A14' : '#F6F5FA'"
    }


def test_ink_expr_falls_back_to_common_text_color(monkeypatch):
    options = {"theme.textColor": "#0A0A14"}
    monkeypatch.setattr(charts, "st", SimpleNamespace(get_option=_fake_options(options)))
    assert ink_expr() == {
        "expr": "contrast(background, '#0A0A14') >= contrast(background, '#0A0A14') "
        "? '#0A0A14' : '#0A0A14'"
    }


def test_ink_expr_none_without_text_color(monkeypatch):
    monkeypatch.setattr(charts, "st", SimpleNamespace(get_option=_fake_options({})))
    assert ink_expr() is None


def test_palette_size_without_theme_options(monkeypatch):
    """Aucune palette configurée : palette par défaut de Streamlit (10 couleurs)."""
    monkeypatch.setattr(charts, "st", SimpleNamespace(get_option=_fake_options({})))
    assert palette_size() == 10

    def unknown(key):
        raise RuntimeError(key)

    monkeypatch.setattr(charts, "st", SimpleNamespace(get_option=unknown))
    assert palette_size() == 10


def test_remember_entity_slots_merges_in_session(monkeypatch):
    """Registre unique de session, par tag : fusion, places gardées après un filtre."""
    session = {}
    monkeypatch.setattr(charts, "st", SimpleNamespace(session_state=session))
    monkeypatch.setattr(charts, "palette_size", lambda: 4)

    assert remember_entity_slots(["a:1b", "b:2b", "c:3b"]) == {"a:1b": 0, "b:2b": 1, "c:3b": 2}
    assert remember_entity_slots(["c:3b", "d:4b"]) == {"c:3b": 2, "d:4b": 3}
    assert session[ENTITY_SLOTS_KEY] == {"a:1b": 0, "b:2b": 1, "c:3b": 2, "d:4b": 3}


def test_size_legend_text_without_value():
    assert size_legend_text([None, float("nan")], "mg") == "Taille du point : CO₂ de la réponse."


def test_charts_load_without_streamlit_plotly_theme(monkeypatch):
    """Module interne de Streamlit absent : les pages se chargent, sans jetons (couleurs par
    défaut du thème)."""
    import streamlit.elements.lib as st_lib

    monkeypatch.setitem(sys.modules, "streamlit.elements.lib.streamlit_plotly_theme", None)
    monkeypatch.delattr(st_lib, "streamlit_plotly_theme", raising=False)
    spec = importlib.util.spec_from_file_location("charts_fallback", charts.__file__)
    fallback = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "charts_fallback", fallback)  # exigé par @dataclass
    spec.loader.exec_module(fallback)

    assert fallback.THEME_CATEGORY_TOKENS == ()
    assert fallback.THEME_SURFACE_TOKEN is None
    assert fallback.slot_color(2, 4) is None
    assert fallback.slot_symbol(5, 4) == "square"
