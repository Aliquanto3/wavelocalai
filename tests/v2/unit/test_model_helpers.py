"""Classement des modèles, mémoire du poste, catalogue versionné et faits d'Ollama."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from wavelocalai.hardware.memory import (
    FIT_MARGIN,
    SIZE_TO_LOADED,
    SYSTEM_RAM_BUFFER_GB,
    MemoryAdvisor,
    MemoryReading,
    estimate_needed_gb,
    fits_in_memory,
    read_memory,
)
from wavelocalai.models.catalog import load_catalog, parse_size_gb
from wavelocalai.models.classify import (
    is_dedicated_reasoning,
    is_embedding_model,
    is_remote_tag,
    is_reranker_model,
    parse_params_b,
)
from wavelocalai.models.facts import InMemoryFactsStore, ModelFacts, facts_from_ollama
from wavelocalai.models.run_stats import InMemoryRunStats

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ({"model": "nomic-embed-text:latest"}, True),
        ({"name": "BGE-Embed-Large"}, True),
        ({"model": "x:1b", "details": {"family": "nomic-bert"}}, True),
        ({"model": "qwen3.5:2b", "details": {"family": "qwen35"}}, False),
        ({"model": "llama3.2:3b"}, False),
    ],
)
def test_is_embedding_model_follows_the_v1_rule(model, expected):
    assert is_embedding_model(model) is expected


def test_reranker_remote_and_reasoning_markers():
    assert is_reranker_model("BAAI/bge-reranker-base") and not is_reranker_model("qwen3.5:2b")
    assert is_remote_tag({"model": "glm-4.6:cloud"})
    assert is_remote_tag({"model": "gpt-oss:120b-cloud"})
    assert is_remote_tag({"model": "x", "remote_host": "https://ollama.com"})
    assert not is_remote_tag({"model": "qwen3.5:2b"})
    assert is_dedicated_reasoning("lfm2.5-thinking:1.2b") and not is_dedicated_reasoning(
        "qwen3.5:2b"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2.3B", 2.3),
        ("873.44M", 0.87344),
        ("137M", 0.137),
        ("1,2B", 1.2),
        ("?", None),
        (None, None),
    ],
)
def test_parse_params_b(text, expected):
    result = parse_params_b(text)
    assert result == pytest.approx(expected) if expected else result is None


def test_parse_size_gb():
    assert parse_size_gb("0.7 GB") == 0.7 and parse_size_gb("350 MB") == pytest.approx(0.35)
    assert parse_size_gb("n/a") is None and parse_size_gb(0) is None


def test_estimate_needed_prefers_measure_then_catalog_then_ollama_size():
    assert estimate_needed_gb(measured_loaded_gb=2.0, download_gb=1.0, download_bytes=10**9) == 2.0
    assert estimate_needed_gb(download_gb=2.0, download_bytes=10**9) == pytest.approx(
        2.0 * SIZE_TO_LOADED
    )
    assert estimate_needed_gb(download_bytes=1024**3) == pytest.approx(SIZE_TO_LOADED)
    assert estimate_needed_gb() is None


def test_fits_rule_is_the_v1_rule():
    available = 10.0
    limit = (available - SYSTEM_RAM_BUFFER_GB) / FIT_MARGIN
    assert fits_in_memory(limit - 0.01, available) is True
    assert fits_in_memory(limit + 0.01, available) is False
    assert fits_in_memory(None, available) is None  # inconnu : ni oui ni non


def test_advisor_uses_the_injected_reading():
    advisor = MemoryAdvisor(lambda: MemoryReading(total_gb=16.0, available_gb=4.0))
    small = advisor.assess(download_bytes=1024**3)
    big = advisor.assess(download_bytes=8 * 1024**3)
    assert small.fits is True and small.available_gb == 4.0
    assert big.fits is False and big.needed_gb == pytest.approx(10.0)
    assert advisor.assess().fits is None


def test_read_memory_returns_this_machine():
    reading = read_memory()
    assert 0 < reading.available_gb <= reading.total_gb


def test_real_catalog_is_read_without_being_written():
    path = REPO / "config" / "models_catalog.json"
    before = path.read_bytes()
    catalog = load_catalog(path)
    entry = catalog.find("granite4:350m")
    assert entry is not None and entry.editor == "IBM" and entry.params_total_b == 0.35
    assert entry.size_gb == 0.7 and "tools" in entry.capabilities
    assert len(catalog) > 10
    assert path.read_bytes() == before


def test_missing_or_broken_catalog_is_empty(tmp_path):
    assert len(load_catalog(tmp_path / "absent.json")) == 0
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert len(load_catalog(broken)) == 0
    broken.write_text(json.dumps({"models": []}), encoding="utf-8")
    assert len(load_catalog(broken)) == 0


def test_facts_from_ollama_reads_show_and_listing():
    listed = {
        "model": "lfm2.5:8b-a1b-q4_K_M",
        "digest": "abc",
        "size": 5_156_075_525,
        "details": {"family": "lfm2moe", "parameter_size": "8.5B", "quantization_level": "Q4_K_M"},
    }
    show = {
        "capabilities": ["completion", "tools", "thinking"],
        "model_info": {
            "general.architecture": "lfm2moe",
            "general.parameter_count": 8_467_856_832,
            "lfm2moe.context_length": 128000,
            "lfm2moe.expert_count": 32,
            "lfm2moe.expert_used_count": 4,
        },
    }
    facts = facts_from_ollama(listed, show, now=1.0)
    assert facts.capabilities == ("completion", "tools", "thinking")
    assert facts.params_total_b == pytest.approx(8.4679, abs=1e-3)
    assert (facts.expert_count, facts.expert_used_count, facts.context_length) == (32, 4, 128000)
    without_show = facts_from_ollama(listed, None, now=1.0)
    assert without_show.params_total_b == 8.5 and without_show.capabilities == ()


def test_facts_store_keeps_one_row_per_tag_and_digest():
    store = InMemoryFactsStore()
    old = facts_from_ollama({"model": "m", "digest": "d1"}, None, now=1.0)
    new = facts_from_ollama({"model": "m", "digest": "d2"}, None, now=2.0)
    store.put(old)
    store.put(new)
    assert store.get("m", "d1") == old and store.get("m", "d2") == new
    assert store.latest_per_tag() == [new]


def test_run_stats_median_keeps_only_ok_ollama_eval_leaves():
    stats = InMemoryRunStats()
    assert stats.median_tps("m") is None
    for tps in (10.0, 30.0, 20.0):
        stats.record_leaf("m", tps)
    stats.record_leaf("m", 999.0, status="failed")
    stats.record_leaf("m", 999.0, tps_source="wallclock")
    stats.record_leaf("m", None)
    assert stats.median_tps("m") == 20.0


def test_model_facts_migration_matches_the_dataclass():
    sql = (REPO / "src/wavelocalai/store/migrations/0002_model_facts.sql").read_text("utf-8")
    db = sqlite3.connect(":memory:")
    db.executescript(sql)
    columns = [row[1] for row in db.execute("PRAGMA table_info(model_facts)")]
    primary = [row[1] for row in db.execute("PRAGMA table_info(model_facts)") if row[5]]
    assert columns == list(ModelFacts.__dataclass_fields__)
    assert sorted(primary) == ["digest", "tag"]
