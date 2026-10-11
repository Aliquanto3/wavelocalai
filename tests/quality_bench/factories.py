"""Enregistrements valides de référence (exemples d'AD-7 et AD-8), copiés à chaque appel."""

from __future__ import annotations

import copy
from typing import Any

HASH_A = "a" * 64
HASH_B = "b" * 64

_GENERATION: dict[str, Any] = {
    "schema": "qb.generation/1",
    "key": "pilot-20261015|qwen3.5:4b|think_on|tools/bfcl-multi/0042|0",
    "manifest": HASH_A,
    "campaign": "pilot-20261015",
    "model": "qwen3.5:4b",
    "digest": "sha256:" + "c" * 64,
    "track": "think_on",
    "question_id": "tools/bfcl-multi/0042",
    "usage": "tools",
    "group": "bfcl-multi/conv-17",
    "unit": "tools/bfcl-multi/0042",
    "prompt_hash": HASH_B,
    "seed": 0,
    "epoch": 0,
    "think": True,
    "backend": "ollama",
    "ollama_version": "0.40.2",
    "num_ctx": 16384,
    "num_predict": 2048,
    "status": "ok",
    "output": [
        {"turn": 0, "role": "assistant", "content": "…", "thinking": "…", "tool_calls": []},
        {"turn": 0, "role": "tool", "content": "…"},
        {"turn": 1, "role": "user", "content": "…"},
    ],
    "call_cap_reached": False,
    "tokens": {
        "prompt": 0,
        "prompt_cached": 0,
        "completion": 0,
        "thinking_est": 0,
        "answer_est": 0,
    },
    "durations_ns": {"total": 0, "load": 0, "prompt_eval": 0, "eval": 0},
    "wall_s": 0.0,
    "calls": 1,
    "attempts": 1,
    "error": None,
    "created_at": "2026-10-15T08:12:03Z",
}


def model_resolved(index: int = 0) -> dict[str, Any]:
    return {
        "tag": f"model-{index}:4b",
        "digest": f"sha256:{index:064d}",
        "family": "qwen",
        "capabilities": ["completion", "thinking", "tools"],
        "tracks": ["think_off", "think_on"],
        "think_off": False,
        "think_on": True,
        "num_ctx_max": 32768,
    }


_MANIFEST: dict[str, Any] = {
    "schema": "qb.manifest/1",
    "phase": "generation",
    "campaign": "pilot-20261015",
    "created_at": "2026-10-15T08:00:00Z",
    "blocking": {
        "set": {"id": "set-v1", "hash": HASH_A, "n": {"think_off": 800, "think_on": 400}},
        "generation": {"hash": HASH_B, "resolved": {}},
        "models_resolved": [model_resolved(i) for i in range(5)],
        "ollama_version": "0.40.2",
        "machine": "tour-rtx3050",
        "harness_hash": HASH_A,
        "judge": None,
        "generation_manifest": None,
    },
    "informative": {
        "python": "3.12.8",
        "packages": {},
        "code_commit": "cba5aa6",
        "nvidia_driver": None,
        "ollama_env": {},
        "checklist": {},
        "prices": None,
    },
}

JUDGE = {
    "id": "haiku",
    "config_hash": HASH_A,
    "endpoint": "https://api.anthropic.com",
    "model": "claude-haiku-5-5",
    "settings": {"effort": "low"},
    "prompt_template_hash": HASH_B,
    "weights_sha256": None,
    "server_version": None,
}


def generation_record(**overrides: Any) -> dict[str, Any]:
    record = copy.deepcopy(_GENERATION)
    record.update(overrides)
    return record


def manifest(**overrides: Any) -> dict[str, Any]:
    record = copy.deepcopy(_MANIFEST)
    record.update(overrides)
    return record


_QUESTION: dict[str, Any] = {
    "schema": "qb.question/1",
    "id": "reasoning/bbeh-mini/0001",
    "usage": "reasoning",
    "group": "bbeh-mini/0001",
    "unit": "reasoning/bbeh-mini/0001",
    "source": "bbeh-mini",
    "license": "CC-BY-4.0",
    "private": False,
    "generator": None,
    "generator_seed": None,
    "num_ctx": 8192,
    "est_prompt_tokens": 120,
    "messages": [{"role": "user", "content": "Combien font 2 + 2 ? Réponds par un nombre."}],
    "turns": None,
    "tools": None,
    "format": None,
    "env": None,
    "grader": {"name": "exact_answer", "params": {}},
    "target": "4",
    "criteria": None,
}


def question(**overrides: Any) -> dict[str, Any]:
    """Question ``qb.question/1`` valide (source ``bbeh-mini``), empreintes recalculées après
    application de ``overrides``."""
    from scripts.quality_bench.questions.schema import with_hashes

    record = copy.deepcopy(_QUESTION)
    record.update(overrides)
    return with_hashes(record)
