"""Noyau ``stats/`` (AD-17) : valeurs de référence calculées à la main ou par une formule
indépendante."""

from __future__ import annotations

import math

import pytest
from scipy.stats import t as student_t
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportion_confint

from scripts.quality_bench.stats.bootstrap import paired_bootstrap_ci
from scripts.quality_bench.stats.clustered import clustered_mean_se, mean_interval
from scripts.quality_bench.stats.groups import (
    approximate_ranks,
    bonferroni_alpha,
    indistinguishable_groups,
    leader_order,
)
from scripts.quality_bench.stats.mcnemar import (
    correlation,
    discordant_counts,
    mcnemar_exact,
    paired_difference,
    z_test,
)
from scripts.quality_bench.stats.multiple import benjamini_hochberg, bonferroni_wins, holm
from scripts.quality_bench.stats.spearman import conclusion, spearman_test
from scripts.quality_bench.stats.units import unit_scores
from scripts.quality_bench.stats.wilson import wilson_interval, z_value

Z95 = 1.959963984540054


# -- Unités ---------------------------------------------------------------------------------


def test_unit_is_the_minimum_of_its_questions():
    # Trois variantes VAR-MATH d'une même unité, dont une ratée : unité ratée.
    scores = unit_scores(["u", "u", "u", "v"], [0, 0, 0, 0], [1.0, 0.0, 1.0, 1.0])
    assert scores == {"u": 0.0, "v": 1.0}


def test_seeds_are_averaged_after_the_minimum():
    scores = unit_scores(["u", "u", "u", "u"], [0, 0, 1, 1], [1.0, 1.0, 1.0, 0.0])
    assert scores == {"u": 0.5}


def test_a_question_without_score_nulls_its_unit():
    scores = unit_scores(["u", "u", "v"], [0, 1, 0], [1.0, None, 0.25])
    assert scores == {"u": None, "v": 0.25}


# -- Wilson ---------------------------------------------------------------------------------


@pytest.mark.parametrize("successes, n", [(8, 10), (0, 12), (12, 12), (37, 120)])
def test_wilson_matches_statsmodels(successes, n):
    low, high = wilson_interval(successes, n)
    ref_low, ref_high = proportion_confint(successes, n, alpha=0.05, method="wilson")
    assert low == pytest.approx(ref_low, abs=1e-12)
    assert high == pytest.approx(ref_high, abs=1e-12)


def test_wilson_by_hand():
    # 8/10, z = 1,96 : centre (0,8 + 0,192)/1,384, demi-largeur 1,96·√(0,016 + 0,0096)/1,384.
    low, high = wilson_interval(8, 10)
    z = Z95
    centre = (0.8 + z * z / 20) / (1 + z * z / 10)
    half = z * math.sqrt(0.8 * 0.2 / 10 + z * z / 400) / (1 + z * z / 10)
    assert (low, high) == pytest.approx((centre - half, centre + half))
    assert (low, high) == pytest.approx((0.4902, 0.9433), abs=1e-4)


def test_wilson_without_units_is_undefined():
    assert all(math.isnan(v) for v in wilson_interval(0, 0))


def test_z_value():
    assert z_value(0.05) == pytest.approx(Z95)
    assert z_value(bonferroni_alpha(0.05, 5)) == pytest.approx(2.5758293, abs=1e-6)


# -- ET groupée -----------------------------------------------------------------------------


def test_clustered_se_by_hand():
    # x̄ = 0,75 ; sommes par groupe : a = 0,25 − 0,75 = −0,5, b = 0,25, c = 0,25.
    mean, se = clustered_mean_se([1, 0, 1, 1], ["a", "a", "b", "c"])
    assert mean == 0.75
    assert se == pytest.approx(math.sqrt(0.25 + 0.0625 + 0.0625) / 4)


def test_clustered_se_with_singleton_groups_is_the_naive_se():
    values = [1.0, 0.0, 1.0, 1.0, 0.0]
    mean, se = clustered_mean_se(values, list(range(5)))
    naive = math.sqrt(sum((v - mean) ** 2 for v in values)) / len(values)
    assert se == pytest.approx(naive)


def test_shared_context_inflates_the_se():
    values = [1, 1, 1, 0, 0, 0]
    _, independent = clustered_mean_se(values, list(range(6)))
    _, grouped = clustered_mean_se(values, ["a", "a", "a", "b", "b", "b"])
    assert grouped == pytest.approx(independent * math.sqrt(3))


def test_mean_interval_is_bounded():
    assert mean_interval(0.95, 0.05, Z95) == pytest.approx((0.95 - Z95 * 0.05, 1.0))
    assert all(math.isnan(v) for v in mean_interval(math.nan, 0.1, Z95))


# -- McNemar et différence appariée --------------------------------------------------------


def test_mcnemar_exact_by_hand():
    # b = 8, c = 2 : p = 2·(C(10,0) + C(10,1) + C(10,2)) / 2^10 = 112/1024.
    assert mcnemar_exact(8, 2) == pytest.approx(112 / 1024)
    assert mcnemar_exact(2, 8) == pytest.approx(112 / 1024)
    assert mcnemar_exact(5, 5) == pytest.approx(1.0)
    assert mcnemar_exact(0, 0) == 1.0


def test_discordant_counts():
    assert discordant_counts([1, 1, 0, 0, 1], [0, 1, 1, 0, 0]) == (2, 1)


def test_paired_difference_by_hand():
    a = [1, 1, 1, 0]
    b = [0, 1, 0, 0]
    result = paired_difference(a, b, ["g1", "g1", "g2", "g3"], Z95)
    # d = (1, 0, 1, 0), d̄ = 0,5 ; groupes : g1 = 0,5 − 0,5 = 0, g2 = 0,5, g3 = −0,5.
    assert result.n == 4
    assert result.diff == 0.5
    assert result.se == pytest.approx(math.sqrt(0.5) / 4)
    assert (result.ci_low, result.ci_high) == pytest.approx(
        (0.5 - Z95 * result.se, 0.5 + Z95 * result.se)
    )
    # Pearson : a centré (0,25 ×3, −0,75), b centré (−0,25, 0,75, −0,25, −0,25).
    assert result.correlation == pytest.approx(1 / 3)


def test_correlation_of_a_constant_model_is_undefined():
    assert math.isnan(correlation([1, 1, 1], [0, 1, 0]))


def test_z_test():
    assert z_test(0.1, 0.05) == pytest.approx(0.0455003, abs=1e-6)
    assert z_test(0.0, 0.0) == 1.0
    assert z_test(0.2, 0.0) == 0.0
    assert math.isnan(z_test(math.nan, 0.1))


# -- Comparaisons multiples -----------------------------------------------------------------


def test_holm_by_hand():
    # Triées : 0,01·4 = 0,04 ; 0,02·3 = 0,06 ; 0,03·2 = 0,06 ; 0,04 → monotone : 0,06.
    reject, corrected = holm([0.03, 0.01, 0.04, 0.02])
    assert corrected == pytest.approx([0.06, 0.04, 0.06, 0.06])
    assert reject == [False, True, False, False]


def test_holm_is_not_holm_sidak():
    pvalues = [0.0127, 0.2, 0.3, 0.4]
    reject, corrected = holm(pvalues)
    sidak_reject, sidak_corrected, _, _ = multipletests(pvalues, alpha=0.05)  # défaut : Šidák
    # Holm : 0,0127·4 = 0,0508 > 0,05 ; Holm-Šidák : 1 − 0,9873^4 ≈ 0,0498 < 0,05.
    assert corrected[0] == pytest.approx(0.0508)
    assert sidak_corrected[0] == pytest.approx(1 - (1 - 0.0127) ** 4)
    assert reject[0] is False and bool(sidak_reject[0]) is True


def test_benjamini_hochberg_by_hand():
    # Triées 0,01 ; 0,03 ; 0,04 ; 0,5 → ·4/rang : 0,04 ; 0,06 ; 0,0533 ; 0,5 → minimum à droite.
    reject, corrected = benjamini_hochberg([0.01, 0.04, 0.03, 0.5])
    assert corrected == pytest.approx([0.04, 0.04 * 4 / 3, 0.04 * 4 / 3, 0.5])
    assert reject == [True, False, False, False]


def test_undefined_pvalues_are_left_out_of_the_correction():
    reject, corrected = holm([0.01, math.nan, 0.02])
    assert corrected[0] == pytest.approx(0.02) and math.isnan(corrected[1])
    assert reject == [True, False, True]


def test_bonferroni_wins():
    # m = 4 : seuil 0,0125 ; 0,01 gagné, 0,001 perdu (différence négative), 0,02 non significatif.
    assert bonferroni_wins([0.01, 0.001, 0.02, 0.0001], [0.1, -0.2, 0.3, 0.05]) == 2
    assert bonferroni_wins([], []) == 0


# -- Bootstrap ------------------------------------------------------------------------------


def test_paired_bootstrap_is_reproducible():
    a = [1, 0, 1, 1, 0.5, 0.25, 1, 0]
    b = [0, 0, 1, 0, 0.5, 0.0, 0, 0]
    groups = ["a", "a", "b", "c", "d", "d", "e", "f"]
    first = paired_bootstrap_ci(a, b, groups, seed=7)
    assert paired_bootstrap_ci(a, b, groups, seed=7) == first
    assert paired_bootstrap_ci(a, b, groups, seed=8) != first
    diff = sum(x - y for x, y in zip(a, b, strict=True)) / len(a)
    assert first[0] <= diff <= first[1]


def test_paired_bootstrap_of_identical_models_is_zero():
    values = [1, 0, 1, 0.5]
    assert paired_bootstrap_ci(values, values, [1, 2, 3, 4]) == (0.0, 0.0)
    assert all(math.isnan(v) for v in paired_bootstrap_ci([], [], []))


# -- Classement -----------------------------------------------------------------------------


def test_approximate_ranks():
    ranks = approximate_ranks([0.8, 0.7, 0.3, math.nan], [0.95, 0.9, 0.5, math.nan])
    assert ranks == [1, 1, 3, None]


def test_leader_order_breaks_ties_by_configuration_order():
    assert leader_order([0.5, 0.7, 0.7, math.nan]) == [1, 2, 0]


def test_indistinguishable_groups_successive_leaders():
    means = [0.9, 0.85, 0.5, 0.45, math.nan]
    p = [[1.0] * 5 for _ in range(5)]
    d = [[means[i] - means[j] for j in range(5)] for i in range(5)]
    for i, j, value in [(0, 1, 0.5), (0, 2, 0.001), (0, 3, 0.001), (2, 3, 0.6)]:
        p[i][j] = p[j][i] = value
    assert indistinguishable_groups(means, d, p) == [1, 1, 2, 2, None]


def test_groups_use_holm_over_the_leader_comparisons():
    # 0,02 et 0,03 : Holm (0,04 puis 0,04) rejette les deux, sans correction 0,02 et 0,03.
    means = [0.9, 0.6, 0.5]
    d = [[means[i] - means[j] for j in range(3)] for i in range(3)]
    p = [[1.0, 0.02, 0.03], [0.02, 1.0, 0.9], [0.03, 0.9, 1.0]]
    assert indistinguishable_groups(means, d, p) == [1, 2, 2]
    # 0,03 et 0,04 : Holm 0,06 puis 0,06 : aucun rejet, un seul groupe.
    p = [[1.0, 0.03, 0.04], [0.03, 1.0, 0.9], [0.04, 0.9, 1.0]]
    assert indistinguishable_groups(means, d, p) == [1, 1, 1]


# -- Spearman -------------------------------------------------------------------------------


def _t_pvalue(rho, n):
    statistic = rho * math.sqrt((n - 2) / (1 - rho * rho))
    return float(student_t.sf(statistic, n - 2))


def test_spearman_one_sided_pvalue_matches_the_t_formula():
    scores = [0.1, 0.3, 0.2, 0.5, 0.4, 0.7, 0.6, 0.8, 0.9, 0.75]
    index = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    result = spearman_test(scores, index)
    ranks = [1, 3, 2, 5, 4, 7, 6, 9, 10, 8]
    d2 = sum((r - (i + 1)) ** 2 for i, r in enumerate(ranks))
    rho = 1 - 6 * d2 / (10 * (100 - 1))
    assert result.n == 10
    assert result.rho == pytest.approx(rho)
    assert result.p == pytest.approx(_t_pvalue(rho, 10))
    assert result.ci_low <= result.rho <= result.ci_high
    assert result.conclusion == "concordant"
    assert spearman_test(scores, index) == result  # graine fixée


@pytest.mark.parametrize(
    "n, rho, p, expected",
    [
        (7, 1.0, 0.0, "inconclusive"),
        (8, -0.7, 0.98, "investigate"),
        (8, 0.64, 0.04, "concordant"),
        (8, 0.5, 0.1, "not_significant"),
        (8, 0.64, 0.05, "not_significant"),
        (20, math.nan, math.nan, "inconclusive"),
    ],
)
def test_spearman_conclusion_thresholds(n, rho, p, expected):
    assert conclusion(n, rho, p) == expected


def test_spearman_thresholds_by_size():
    # n = 8 : ρ ≈ 0,64 est le seuil de significativité unilatéral (statistiques.md).
    assert _t_pvalue(0.66, 8) < 0.05 < _t_pvalue(0.60, 8)
    assert _t_pvalue(0.58, 10) < 0.05 < _t_pvalue(0.52, 10)


def test_spearman_negative_and_small_samples():
    assert spearman_test(range(8), range(8, 0, -1)).conclusion == "investigate"
    small = spearman_test([0.1, 0.2, 0.3, 0.4], [1, 2, 3, 4])
    assert small.rho == pytest.approx(1.0) and small.conclusion == "inconclusive"
    constant = spearman_test([0.5] * 9, list(range(9)))
    assert math.isnan(constant.rho) and constant.conclusion == "inconclusive"


def test_clustered_se_of_a_single_group_is_undefined():
    # Un seul groupe : Σ(x − x̄) y vaut 0 ; l'ET groupée est indéfinie, pas nulle.
    mean, se = clustered_mean_se([1, 0, 1], ["g", "g", "g"])
    assert mean == pytest.approx(2 / 3) and math.isnan(se)
    paired = paired_difference([1, 1, 1], [0, 1, 0], ["g", "g", "g"], Z95)
    assert paired.diff == pytest.approx(2 / 3) and math.isnan(paired.se)
    assert math.isnan(z_test(paired.diff, paired.se))
