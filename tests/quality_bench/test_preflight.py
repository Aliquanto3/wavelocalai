"""Préflight des modèles (AD-8, AD-9) : refus nommés, ``models_resolved``, contexte effectif."""

from __future__ import annotations

import pytest

from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.generation.preflight import (
    LaunchError,
    check_launch,
    effective_ctx_max,
    find_tag,
    resolve_model,
)

from .factories import manifest

TAG = "m-think:1b"
THINKING = ["completion", "tools", "thinking"]


def _cfg(**overrides):
    model = {
        "tag": TAG,
        "family": "qwen",
        "tracks": ["think_off", "think_on"],
        "num_ctx_max": 32768,
        "think_off": False,
        "think_on": True,
    }
    model.update(overrides)
    return model


def _show(capabilities=None, context_length=None, **extra):
    info = {"general.architecture": "llama"}
    if context_length is not None:
        info["llama.context_length"] = context_length
    return {
        "capabilities": THINKING if capabilities is None else capabilities,
        "model_info": info,
        **extra,
    }


def _tags(**extra):
    return [{"name": TAG, "model": TAG, "digest": "abc123", **extra}]


def test_resolved_model_has_sorted_capabilities_and_effective_context():
    resolved = resolve_model(_cfg(), _show(context_length=16384), _tags())
    assert resolved == {
        "tag": TAG,
        "digest": "abc123",
        "family": "qwen",
        "capabilities": ["completion", "thinking", "tools"],
        "tracks": ["think_off", "think_on"],
        "think_off": False,
        "think_on": True,
        "num_ctx_max": 16384,
    }
    record = manifest()
    record["blocking"]["models_resolved"] = [resolved]
    validate(record)


def test_model_without_thinking_on_think_off_only():
    resolved = resolve_model(
        _cfg(tracks=["think_off"], think_off=None, think_on=None),
        _show(["completion"]),
        _tags(),
    )
    assert resolved["think_off"] is None and resolved["tracks"] == ["think_off"]
    assert resolved["num_ctx_max"] == 32768  # contexte non déclaré : plafond configuré


@pytest.mark.parametrize(
    "declared, expected",
    [(None, 32768), (8192, 8192), (131072, 32768)],
)
def test_effective_ctx_max_is_the_minimum(declared, expected):
    assert effective_ctx_max(32768, _show(context_length=declared)) == expected


def test_effective_ctx_max_ignores_other_architecture_keys():
    show = {"model_info": {"general.architecture": "qwen3", "llama.context_length": 2048}}
    assert effective_ctx_max(32768, show) == 32768


def test_find_tag_accepts_implicit_latest():
    tags = [{"name": "LiquidAI/lfm2.5-2.6b:latest", "digest": "x"}]
    assert find_tag(tags, "LiquidAI/lfm2.5-2.6b") is tags[0]
    assert find_tag(tags, "LiquidAI/lfm2.5-2.6b:q4") is None


@pytest.mark.parametrize(
    "cfg, show, tags, reason",
    [
        (_cfg(), _show(), [], "absent de /api/tags"),
        (_cfg(), _show(), [{"name": TAG}], "aucun digest"),
        (_cfg(), _show(), [{"name": TAG, "digest": ""}], "aucun digest"),
        (_cfg(), _show(), _tags(remote_host="https://ollama.com"), "distant"),
        (_cfg(), _show(remote_host="https://ollama.com"), _tags(), "distant"),
        (_cfg(), _show(["completion", "thinking", "decision"]), _tags(), "decision"),
        (_cfg(), _show(["thinking", "tools"]), _tags(), "completion"),
        (_cfg(), _show(["completion", "tools"]), _tags(), "sans capacité « thinking »"),
        (_cfg(think_on=False), _show(), _tags(), "think_on = False"),
        (_cfg(think_on=None), _show(), _tags(), "think_on = None"),
        (_cfg(think_off=True), _show(), _tags(), "think_off = True"),
        (_cfg(tracks=["think_off"], think_off=True), _show(), _tags(), "think_off = True"),
        (_cfg(tracks=["think_off"], think_off=None), _show(), _tags(), "pas null"),
        (
            _cfg(tracks=["think_off"], think_off=False, think_on=None),
            _show(["completion"]),
            _tags(),
            "think null",
        ),
        (_cfg(think_on="high"), _show(), _tags(), "valeur think 'high'"),
        (_cfg(), {"capabilities": "completion"}, _tags(), "capacités illisibles"),
    ],
)
def test_launch_refusals_name_the_model_and_reason(cfg, show, tags, reason):
    with pytest.raises(LaunchError) as excinfo:
        resolve_model(cfg, show, tags)
    assert TAG in str(excinfo.value)
    assert reason in str(excinfo.value)


def _resolved(capabilities, tracks=("think_off", "think_on")):
    return {"tag": TAG, "capabilities": capabilities, "tracks": list(tracks)}


def test_think_value_outside_published_values_is_refused():
    # Ollama 0.40.2, LiquidAI/lfm2.5-2.6b : think false n'est pas une valeur permise.
    show = _show(thinking={"values": [True], "default": True})
    with pytest.raises(LaunchError, match=r"think_off.*thinking.values"):
        resolve_model(_cfg(), show, _tags())
    resolved = resolve_model(_cfg(tracks=["think_on"]), show, _tags())
    assert resolved["tracks"] == ["think_on"]


def test_published_think_values_allow_both_tracks():
    show = _show(thinking={"values": [False, True], "default": True})
    assert resolve_model(_cfg(), show, _tags())["tracks"] == ["think_off", "think_on"]
    # Liste absente ou illisible : aucun contrôle supplémentaire.
    assert resolve_model(_cfg(), _show(thinking=None), _tags())["think_off"] is False
    assert resolve_model(_cfg(), _show(thinking={"default": True}), _tags())["think_on"] is True


def test_tool_question_without_tools_capability_is_refused():
    questions = {"think_off": [{"id": "tools/bfcl-live/0001", "tools": [{"type": "function"}]}]}
    with pytest.raises(LaunchError, match="tools/bfcl-live/0001") as excinfo:
        check_launch([_resolved(["completion"], ["think_off"])], questions)
    assert TAG in str(excinfo.value)
    check_launch([_resolved(["completion", "tools"], ["think_off"])], questions)


def test_tool_question_only_on_track_the_model_skips():
    questions = {
        "think_off": [{"id": "rag/piaf/0001", "tools": None}],
        "think_on": [{"id": "tools/bfcl-live/0001", "tools": [{"type": "function"}]}],
    }
    check_launch([_resolved(["completion"], ["think_off"])], questions)
    with pytest.raises(LaunchError):
        check_launch([_resolved(["completion", "thinking"])], questions)
