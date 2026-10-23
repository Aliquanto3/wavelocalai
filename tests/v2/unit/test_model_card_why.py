"""« Pourquoi ce débit ? » (story 5.6, revue) : le débit mesuré y est écrit comme le front l'écrit
(`formatRate`, trois chiffres significatifs), jamais arrondi à l'entier (0,4 n'est pas « 0 »)."""

from __future__ import annotations

import pytest

from wavelocalai.models.card import NBSP, CardSource, why_lines


def _source(tps: float) -> CardSource:
    return CardSource(
        tag="mid:7b", name="Moyen 7B", editor=None, origin="local", installed=True,
        in_catalog=True, digest="d", architecture="dense", params_total_b=7.0,
        params_active_b=7.0, quantization="Q4_K_M", context_length=None, license=None,
        tools_verified=None, reasoning=None, size_gb=4.7, needed_gb=5.0, required_gb=None,
        short_gb=None, fits=True, throughput_tps=tps,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("tps", "shown"), [(12.7, "12,7"), (0.4, "0,4"), (128.4, "128"), (13.84, "13,8"), (2.0, "2")]
)
def test_the_measured_throughput_keeps_three_significant_digits(tps, shown):
    text = "\n".join(why_lines(_source(tps), vram_gb=None))
    assert f"débit mesuré de {shown}{NBSP}tokens/s" in text
