"""Détection des MoE par scripts/build_catalog.py."""

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "build_catalog.py"
_SPEC = importlib.util.spec_from_file_location("build_catalog", _PATH)
build_catalog = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(build_catalog)


@pytest.mark.parametrize(
    ("tag", "name", "expected"),
    [
        ("qwen3.6:35b-a3b", "Qwen 3.6 35B", True),
        ("lfm2.5:24b-a2b-q4_K_M", "LFM 2.5 24B", True),
        ("lfm2.5:8b-a1b-q4_K_M", "LFM 2.5 8B", True),
        ("nemotron-3.5-lightning:30b-a3b-q4_K_M", "Nemotron 3.5 Lightning", True),
        ("granite4.2:8b", "Granite 4.2 MoE", True),
        ("gemma4:e2b-it-qat", "Gemma 4 E2B", False),
        ("qwen3.5:4b", "Qwen 3.5 4B", False),
        ("ling3-tiny:8b-q4_k_m", "Ling 3 Tiny", False),
    ],
)
def test_is_moe(tag, name, expected):
    assert build_catalog.is_moe(tag, name) is expected
