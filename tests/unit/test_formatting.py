"""
Tests des formats d'affichage fr-FR (src/app/formatting.py), matrice de la story 3.
Usage: python -m pytest tests/unit/test_formatting.py -v
"""

from datetime import date, datetime, time

import pytest

from src.app.formatting import (
    MISSING,
    NBSP,
    NNBSP,
    co2_in_unit,
    co2_unit,
    common_co2_unit,
    format_co2,
    format_date,
    format_duration,
    format_gb,
    format_number,
    format_percent,
    format_significant,
    format_throughput,
    format_time,
    format_unit,
    grams_to_kg,
    mg_to_grams,
    pluralize,
)


def test_percent():
    assert format_percent(8.1) == f"8,1{NBSP}%"


def test_thousands_use_narrow_no_break_space():
    assert format_number(12345.6) == f"12{NNBSP}345,6"
    assert format_number(1234567, 0) == f"1{NNBSP}234{NNBSP}567"


def test_memory_in_go_never_gb():
    assert format_gb(13.8) == f"13,8{NBSP}Go"
    assert "GB" not in format_gb(13.8)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (72, f"1{NBSP}min 12{NBSP}s"),
        (0.66, f"0,66{NBSP}s"),
        (12.345, f"12,3{NBSP}s"),
        (5, f"5{NBSP}s"),
        (59.94, f"59,9{NBSP}s"),
        # Unité choisie après arrondi : 59,97 s s'afficherait « 60 s ».
        (59.97, f"1{NBSP}min"),
        (60, f"1{NBSP}min"),
        (120, f"2{NBSP}min"),
        (3725, f"1{NBSP}h 2{NBSP}min"),
    ],
)
def test_duration(seconds, expected):
    assert format_duration(seconds) == expected


def test_date_and_time():
    moment = datetime(2026, 9, 26, 9, 15)

    assert format_date(moment) == f"26{NBSP}sept.{NBSP}2026"
    assert format_date(date(2026, 2, 3)) == f"3{NBSP}févr.{NBSP}2026"
    assert format_time(moment) == "09:15"
    assert format_time(time(9, 15)) == "09:15"


def test_date_accepts_pandas_timestamp():
    pd = pytest.importorskip("pandas")

    stamp = pd.Timestamp("2026-09-26 09:15")

    assert format_date(stamp) == f"26{NBSP}sept.{NBSP}2026"
    assert format_time(stamp) == "09:15"


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, f"0{NBSP}extrait"), (1, f"1{NBSP}extrait"), (3, f"3{NBSP}extraits")],
)
def test_pluralize(count, expected):
    assert pluralize(count, "extrait") == expected


def test_pluralize_agrees_with_rounded_count():
    """L'accord suit le nombre affiché : 1,97 s'affiche « 2 », donc au pluriel."""
    assert pluralize(1.97, "extrait") == f"2{NBSP}extraits"
    assert pluralize(1.5, "extrait") == f"1,5{NBSP}extrait"


def test_negative_zero_is_normalized():
    assert format_number(-0.01) == "0,0"
    assert format_number(-0.4, 0) == "0"
    assert format_unit(-0.001, "Go", 2) == f"0,00{NBSP}Go"
    assert format_significant(-0.0) == "0"


def test_pluralize_irregular_and_thousands():
    assert pluralize(2, "extrait ajouté", "extraits ajoutés") == f"2{NBSP}extraits ajoutés"
    assert pluralize(1200, "document") == f"1{NNBSP}200{NBSP}documents"


def test_significant_digits():
    assert format_significant(0.66) == "0,66"
    assert format_significant(0.123456) == "0,123"
    assert format_significant(1234.5) == f"1{NNBSP}234"
    assert format_significant(0) == "0"


@pytest.mark.parametrize(
    "call",
    [
        lambda v: format_number(v),
        lambda v: format_significant(v),
        lambda v: format_unit(v, "mg"),
        lambda v: format_percent(v),
        lambda v: format_gb(v),
        lambda v: format_duration(v),
        lambda v: format_date(v),
        lambda v: format_time(v),
        lambda v: pluralize(v, "extrait"),
    ],
)
@pytest.mark.parametrize(
    "value",
    [None, float("nan"), float("inf"), float("-inf"), "abc", "nan", "inf", "-inf"],
)
def test_missing_value_is_dash(call, value):
    """Valeur absente, illisible ou non finie : « — », sans exception."""
    assert call(value) == MISSING


def test_nat_is_dash():
    pd = pytest.importorskip("pandas")

    assert format_date(pd.NaT) == MISSING
    assert format_time(pd.NaT) == MISSING
    assert format_number(pd.NaT) == MISSING
    assert format_duration(pd.NaT) == MISSING


# ---------------------------------------------------------------------------
# CO₂ (story 6) : grammes du suivi → mg / g / kg, une unité par comparaison
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("grams", "expected"),
    [
        (0.42, f"420{NBSP}mgCO₂"),
        (0.5, f"500{NBSP}mgCO₂"),
        (12, f"12{NBSP}gCO₂"),
        (1234, f"1,23{NBSP}kgCO₂"),
        (0.0076, f"7,6{NBSP}mgCO₂"),
        (0, f"0{NBSP}mgCO₂"),
        # Unité choisie après arrondi à trois chiffres significatifs.
        (0.9996, f"1{NBSP}gCO₂"),
        (999.6, f"1{NBSP}kgCO₂"),
        (1000, f"1{NBSP}kgCO₂"),
    ],
)
def test_co2_unit_rule(grams, expected):
    assert format_co2(grams) == expected


@pytest.mark.parametrize("value", [None, "abc", float("nan"), float("inf")])
def test_co2_missing(value):
    assert format_co2(value) == MISSING


def test_co2_subscript_and_no_ascii_co2():
    assert "CO₂" in format_co2(0.42)
    assert "CO2" not in format_co2(0.42)


def test_co2_imposed_unit():
    assert format_co2(0.0076, "g") == f"0,0076{NBSP}gCO₂"
    assert format_co2(1.14, "mg") == f"1{NNBSP}140{NBSP}mgCO₂"


def test_grams_to_kg():
    """GreenTracker.stop() renvoie des grammes : 0,42 g = 0,00042 kg."""
    assert grams_to_kg(0.42) == pytest.approx(0.00042)
    assert grams_to_kg(1234) == pytest.approx(1.234)
    assert grams_to_kg(None) is None


def test_mg_to_grams():
    assert mg_to_grams(420) == pytest.approx(0.42)
    assert mg_to_grams("x") is None


def test_co2_unit_choice():
    assert co2_unit(0.42) == "mg"
    assert co2_unit(12) == "g"
    assert co2_unit(1234) == "kg"
    assert co2_unit(None) == "mg"


def test_common_co2_unit_same_for_all_rows():
    """Arène à 3 modèles : une seule unité, celle de la plus petite valeur non nulle ; la plus
    petite garde ses chiffres significatifs (≤ 3 décimales, limite des tableaux Streamlit)."""
    values = [0.0076, 0.42, 1.14]
    unit = common_co2_unit(values)
    assert unit == "mg"
    assert [format_co2(v, unit) for v in values] == [
        f"7,6{NBSP}mgCO₂",
        f"420{NBSP}mgCO₂",
        f"1{NNBSP}140{NBSP}mgCO₂",
    ]
    assert [round(co2_in_unit(v, unit), 3) for v in values] == [7.6, 420, 1140]
    assert common_co2_unit([1.14, 11.4]) == "g"
    assert common_co2_unit([1500, 3000]) == "kg"
    # Zéro et valeurs absentes ignorés.
    assert common_co2_unit([0, None, 12]) == "g"
    assert common_co2_unit([0, None]) == "mg"
    assert common_co2_unit([]) == "mg"


def test_throughput():
    assert format_throughput(78.5) == f"78,5{NBSP}tokens/s"
    assert format_throughput(25, estimated=True) == f"25,0{NBSP}tokens/s (estimé)"
    assert format_throughput(None, estimated=True) == MISSING


def test_co2_in_unit():
    assert co2_in_unit(0.42, "mg") == pytest.approx(420)
    assert co2_in_unit(1234, "kg") == pytest.approx(1.234)
    assert co2_in_unit(None, "mg") is None
    assert co2_in_unit(1, "t") is None
