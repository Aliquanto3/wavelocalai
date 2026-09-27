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
    format_date,
    format_duration,
    format_gb,
    format_number,
    format_percent,
    format_significant,
    format_time,
    format_unit,
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
