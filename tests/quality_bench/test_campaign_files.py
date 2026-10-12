"""Fichiers réels du pilote (story 8) : ``campaigns/pilot-20261012.yaml``, son rejeu et
``pilot.yaml`` se chargent et respectent la spec (modeles.md, rejeu sous-ensemble du pilote)."""

from __future__ import annotations

import copy
import re

import pytest

from scripts.quality_bench.common import config, paths
from scripts.quality_bench.common.config import DEFAULT_GENERATION

PILOT = "pilot-20261012"
REPLAY = f"{PILOT}-replay"
MODELES = paths.REPO_ROOT / "_bmad-output/specs/spec-benchmark-qualite-difficile/modeles.md"


def _modeles_rows():
    """Lignes du tableau « Les 20 modèles de la campagne » : (tag, rôle)."""
    text = MODELES.read_text(encoding="utf-8")
    table = text.split("## Les 20 modèles de la campagne", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in table.splitlines():
        match = re.match(r"\|[^|]+\| `([^`]+)` \|.*\|\s*([^|]*?)\s*\|$", line)
        if match:
            rows.append((match.group(1), match.group(2).strip()))
    return rows


@pytest.fixture(scope="module")
def campaigns():
    return {c: config.load_campaign(paths.campaign_config_path(c)) for c in (PILOT, REPLAY)}


def test_modeles_table_is_parsed():
    rows = _modeles_rows()
    assert len(rows) == 20
    assert sum(1 for _, role in rows if role == "pilote") == 4


def test_both_campaigns_load_with_the_same_generation_but_selection(campaigns):
    pilot, replay = campaigns[PILOT], campaigns[REPLAY]
    assert pilot.set_id == replay.set_id == "set-v1"
    assert pilot.grading == replay.grading == {"judge": "haiku"}
    without = []
    for campaign in (pilot, replay):
        generation = copy.deepcopy(campaign.generation)
        generation.pop("selection")
        without.append(generation)
    assert without[0] == without[1]
    assert pilot.generation["request"]["k"] == 1
    assert pilot.generation["caps"] == DEFAULT_GENERATION["caps"]
    assert pilot.generation["num_ctx_tiers"] == DEFAULT_GENERATION["num_ctx_tiers"]


def test_replay_counts_are_within_the_pilot(campaigns):
    pilot = campaigns[PILOT].generation["selection"]["groups"]
    replay = campaigns[REPLAY].generation["selection"]["groups"]
    assert pilot["seed"] == replay["seed"]
    assert set(replay["per_usage"]) == set(pilot["per_usage"])
    for usage, counts in replay["per_usage"].items():
        mine = pilot["per_usage"][usage]
        assert counts["think_on"] <= mine["think_on"]
        assert counts["think_off"] <= mine["think_off"]
        # Groupes sans think_on : préfixe plus court aussi.
        assert counts["think_off"] - counts["think_on"] <= mine["think_off"] - mine["think_on"]


THINK_ON_ONLY = "LiquidAI/lfm2.5-2.6b"


def test_campaign_models_are_the_four_pilot_models_of_modeles_md(campaigns):
    expected = [tag for tag, role in _modeles_rows() if role == "pilote"]
    for campaign in campaigns.values():
        models = campaign.generation["models"]
        assert sorted(model["tag"] for model in models) == sorted(expected)
        for model in models:
            # LFM 2.5 2.6B ne publie que think true dans /api/show (Ollama 0.40.2) : piste
            # think_on seulement, le préflight refusant think false.
            expected_tracks = (
                ["think_on"] if model["tag"] == THINK_ON_ONLY else ["think_off", "think_on"]
            )
            assert model["tracks"] == expected_tracks
            assert (model["think_off"], model["think_on"]) == (False, True)


def test_real_pilot_settings():
    settings = config.load_pilot_settings(paths.pilot_settings_path())
    rows = _modeles_rows()
    assert list(settings.full_models) == [tag for tag, _ in rows]
    pilot_tags = {tag for tag, role in rows if role == "pilote"}
    assert pilot_tags <= set(settings.full_models)
    assert settings.old_bench_path.is_file()
    assert settings.catalog_path.is_file()
    assert settings.budget_hours == 144.0
    assert settings.think_on_n == 330
    assert [caps["think_on"] for caps in settings.reduction_caps] == [
        {"reasoning": 3072, "default": 1536},
        {"reasoning": 2048, "default": 1024},
    ]


def test_full_models_resolve_to_the_old_bench_through_the_catalog():
    """Lecture seule de l'ancien banc et du catalogue réels : chacun des 20 tags a un débit de
    décodage, de préremplissage et une durée de chargement ; 15 déclarent ``thinking``."""
    import json

    from scripts.quality_bench.report.pilot import old_bench_by_tag

    settings = config.load_pilot_settings(paths.pilot_settings_path())
    old = json.loads(settings.old_bench_path.read_text(encoding="utf-8"))
    catalog = json.loads(settings.catalog_path.read_text(encoding="utf-8"))
    entries = old_bench_by_tag(old, catalog, settings.full_models)
    assert len(entries) == 20
    for tag, entry in entries.items():
        rate = entry.rate
        assert rate.known, (tag, rate.reason)
        assert rate.decode > 0 and rate.prefill > 0 and rate.load_s is not None, tag
    assert sum(1 for entry in entries.values() if entry.rate.thinking) == 15
