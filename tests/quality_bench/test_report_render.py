"""Rendu du rapport (AD-6) : nombres au format français, ``report.md`` et SVG produits depuis
un petit résumé ``qb.report/1`` construit à la main."""

from __future__ import annotations

import re
import unicodedata

import pytest

from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.report.charts import PRIMARY, _x, charts, scope_chart
from scripts.quality_bench.report.markdown import (
    fr_decimal,
    fr_int,
    fr_interval,
    fr_percent,
    fr_points,
    fr_pvalue,
    render,
)

NBSP = " "


@pytest.mark.parametrize(
    "function, value, expected",
    [
        (fr_decimal, 0.6241, "0,624"),
        (fr_decimal, -0.0001, "0,000"),
        (fr_decimal, -0.25, "−0,250"),
        (fr_decimal, None, "—"),
        (fr_percent, 0.624, f"62,4{NBSP}%"),
        (fr_percent, None, "—"),
        (fr_points, 0.125, f"+12,5{NBSP}pts"),
        (fr_points, -0.05, f"−5,0{NBSP}pts"),
        (fr_points, 0.0, f"0,0{NBSP}pts"),
        (fr_int, 12345, "12 345"),
        (fr_pvalue, 0.0004, f"<{NBSP}0,001"),
        (fr_pvalue, 0.0234, "0,023"),
        (fr_pvalue, None, "—"),
    ],
)
def test_french_number_formats(function, value, expected):
    assert function(value) == expected


def test_french_intervals():
    assert fr_interval(0.5, 0.75) == f"[50,0{NBSP}% ; 75,0{NBSP}%]"
    assert fr_interval(-0.1, 0.2, points=True) == f"[−10,0{NBSP}pts ; +20,0{NBSP}pts]"
    assert fr_interval(None, 0.2) == "—"


def _model(model, mean, low, high, rank, group, **extra):
    entry = {
        "model": model,
        "mean": mean,
        "n": 40,
        "excluded": 0,
        "se": 0.05,
        "ci_low": low,
        "ci_high": high,
        "sim_ci_low": low,
        "sim_ci_high": high,
        "rank": rank,
        "group": group,
        "graded": 40,
        "truncated": 2,
        "truncation_rate": 0.05,
    }
    entry.update(extra)
    return entry


def _summary():
    scope = {
        "usage": "reasoning",
        "method": "mcnemar",
        "units": 40,
        "leader": "alpha:4b",
        "models": [
            _model("alpha:4b", 0.75, 0.6, 0.86, 1, 1),
            _model("beta:1b", 0.4, 0.26, 0.56, 2, 2),
            _model("gamma:1b", None, None, None, None, None, n=0, excluded=40, se=None),
        ],
        "comparisons": [
            {
                "model": "beta:1b",
                "n": 40,
                "diff": 0.35,
                "se": 0.08,
                "ci_low": 0.19,
                "ci_high": 0.51,
                "bootstrap_ci_low": None,
                "bootstrap_ci_high": None,
                "correlation": 0.12,
                "b": 16,
                "c": 2,
                "p": 0.0007,
                "p_holm": 0.0014,
                "reject": True,
            }
        ],
        "matrix": [
            {
                "a": "alpha:4b",
                "b": "beta:1b",
                "n": 40,
                "diff": 0.35,
                "p": 0.0007,
                "p_bh": 0.0021,
                "reject": True,
            }
        ],
        "continuous": None,
    }
    summary = {
        "schema": "qb.report/1",
        "campaign": "pilot-20261015",
        "partial": True,
        "set": {"id": "set-v1", "hash": "a" * 64},
        "generation_manifest": "b" * 64,
        "judgment_manifest": None,
        "k": 1,
        "method": {"alpha": 0.05, "bootstrap_resamples": 2000, "bootstrap_seed": 20261011},
        "completeness": {
            "expected": 120,
            "retained": 118,
            "generation_missing": 2,
            "generation_discordant": 0,
            "grading_missing": 0,
            "grading_discordant": 0,
            "awaiting_judgment": 0,
            "config_discordant": False,
        },
        "models": [
            {"tag": tag, "digest": "sha256:" + "c" * 64, "family": "qwen", "tracks": ["think_off"]}
            for tag in ("alpha:4b", "beta:1b", "gamma:1b")
        ],
        "tracks": [
            {
                "track": "think_off",
                "scopes": [dict(scope, usage=None, method="paired_z"), scope],
                "k_bonferroni": {
                    "leader": "alpha:4b",
                    "usages": 1,
                    "alpha_per_test": 0.05,
                    "models": [{"model": "beta:1b", "wins": 1, "tests": 1}],
                },
                "spearman": {
                    "status": "computed",
                    "variant": "non_reasoning",
                    "n": 9,
                    "models": ["alpha:4b"],
                    "rho": 0.7,
                    "p": 0.018,
                    "ci_low": 0.21,
                    "ci_high": 0.93,
                    "conclusion": "concordant",
                },
            }
        ],
        "aa_reference": {
            "path": "references/aa-2026-10-01.json",
            "sha256": "d" * 64,
            "date": "2026-10-01",
        },
    }
    validate(summary)
    return summary


def _has_emoji(text):
    return any(unicodedata.category(char) == "So" for char in text)


def test_markdown_renders_leader_comparison_and_spearman():
    text = render(_summary())
    assert text.startswith("# Rapport de la campagne pilot-20261015\n")
    assert "**Rapport partiel**" in text
    assert (
        f"| 1 | 1 | `alpha:4b` | 75,0{NBSP}% | [60,0{NBSP}% ; 86,0{NBSP}%] | "
        f"[60,0{NBSP}% ; 86,0{NBSP}%] | 0,050 | 40 | 0 | 5,0{NBSP}% (2/40) |"
    ) in text
    assert (
        f"| `beta:1b` | 40 | +35,0{NBSP}pts | 0,080 | [+19,0{NBSP}pts ; +51,0{NBSP}pts] | 16 | 2 "
        f"| 0,12 | <{NBSP}0,001 | 0,001 | oui |"
    ) in text
    assert "m − 1 comparaisons au meneur" in text
    assert "- `alpha:4b` devant `beta:1b`" in text
    assert "- ρ = 0,700, p unilatérale = 0,018, IC bootstrap à 95 % [0,210 ; 0,930]" in text
    assert "concordant (ρ significativement positif)" in text
    assert "| `beta:1b` | 1 / 1 |" in text
    assert (
        "![Piste sans réflexion (think_off) : raisonnement](charts/think_off-reasoning.svg)" in text
    )
    assert not _has_emoji(text)


def test_svg_chart_follows_the_charter():
    summary = _summary()
    scope = summary["tracks"][0]["scopes"][1]
    svg = scope_chart("think_off", scope)
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"') and 'role="img"' in svg
    assert f'fill="{PRIMARY}"' in svg and PRIMARY == "#451DC7"
    label = re.search(r'aria-label="([^"]*)"', svg).group(1)
    assert label.startswith("Piste sans réflexion (think_off) : raisonnement.")
    assert f"alpha:4b : 75,0{NBSP}% (IC à 95 % de 60,0{NBSP}% à 86,0{NBSP}%)" in label
    assert "gamma:1b : sans score" in label
    assert "<title>Piste sans réflexion (think_off) : raisonnement</title>" in svg
    # Moyenne connue : 75 % placée à _x(0,75).
    assert f'<circle cx="{_x(0.75):.1f}"' in svg
    assert f">75,0{NBSP}%</text>" in svg
    assert ">sans score</text>" in svg  # colonne des valeurs du modèle sans score
    assert not _has_emoji(svg)
    assert set(charts(summary)) == {"think_off-global.svg", "think_off-reasoning.svg"}
