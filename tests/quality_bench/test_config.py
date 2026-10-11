"""Configuration de campagne : valeurs par défaut d'AD-8, clés inconnues refusées."""

import textwrap

import pytest

from scripts.quality_bench.common.canonical import sha256_hex
from scripts.quality_bench.common.config import ConfigError, load_campaign

MINIMAL = """\
set: set-v1
generation:
  models:
    - {tag: "qwen3.5:4b", family: qwen, tracks: [think_off, think_on], think_off: false, think_on: true, num_ctx_max: 32768}
"""


def _write(tmp_path, text, name="pilot-20261015.yaml"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def test_defaults_applied(tmp_path):
    config = load_campaign(_write(tmp_path, MINIMAL))
    generation = config.generation
    assert config.campaign == "pilot-20261015"
    assert config.set_id == "set-v1"
    assert generation["request"] == {"temperature": 0, "seed_base": 0, "k": 1}
    assert generation["caps"] == {
        "think_on": {"reasoning": 4096, "default": 2048},
        "think_off": {"default": 2048},
    }
    assert generation["num_ctx_tiers"] == [4096, 8192, 16384, 32768]
    assert generation["max_attempts"] == 3
    assert generation["max_consecutive_errors"] == 5
    assert generation["ollama_wait_s"] == 600
    assert generation["max_tool_calls_per_turn"] == 8
    assert generation["selection"] is None
    assert generation["models"] == [
        {
            "tag": "qwen3.5:4b",
            "family": "qwen",
            "tracks": ["think_off", "think_on"],
            "num_ctx_max": 32768,
            "think_off": False,
            "think_on": True,
        }
    ]
    assert config.grading == {"judge": None}
    assert config.generation_hash == sha256_hex(generation)


def test_hash_ignores_comments_order_and_explicit_defaults(tmp_path):
    base = load_campaign(_write(tmp_path, MINIMAL, "a.yaml"))
    explicit = load_campaign(
        _write(
            tmp_path,
            """\
            # commentaire
            generation:
              max_attempts: 3   # valeur par défaut rendue explicite
              request: {k: 1}
              caps: {think_on: {reasoning: 4096}}
              models:
                - {num_ctx_max: 32768, think_on: true, think_off: false, tracks: [think_on, think_off], family: qwen, tag: "qwen3.5:4b"}
            set: set-v1
            grading: {judge: haiku}
            """,
            "b.yaml",
        )
    )
    assert explicit.generation_hash == base.generation_hash
    assert explicit.grading == {"judge": "haiku"}  # non bloquante : hors de l'empreinte


def test_hash_changes_with_generation_value(tmp_path):
    base = load_campaign(_write(tmp_path, MINIMAL, "a.yaml"))
    changed = load_campaign(
        _write(
            tmp_path, MINIMAL.replace("generation:\n", "generation:\n  max_attempts: 4\n"), "b.yaml"
        )
    )
    assert changed.generation_hash != base.generation_hash


def test_partial_caps_merged_with_defaults(tmp_path):
    text = MINIMAL.replace(
        "generation:\n", "generation:\n  caps: {think_on: {reasoning: 8192, writing: 3000}}\n"
    )
    caps = load_campaign(_write(tmp_path, text)).generation["caps"]
    assert caps["think_on"] == {"reasoning": 8192, "default": 2048, "writing": 3000}
    assert caps["think_off"] == {"default": 2048}


@pytest.mark.parametrize(
    "selection, expected",
    [
        ("{ids: [a/b/1, a/b/2]}", {"ids": ["a/b/1", "a/b/2"]}),
        ("{sample: {per_usage: 20, seed: 7}}", {"sample": {"per_usage": 20, "seed": 7}}),
        ("null", None),
    ],
)
def test_selection_forms(tmp_path, selection, expected):
    text = MINIMAL.replace("generation:\n", f"generation:\n  selection: {selection}\n")
    assert load_campaign(_write(tmp_path, text)).generation["selection"] == expected


@pytest.mark.parametrize(
    "insert",
    [
        "  unknown_key: 1\n",
        "  request: {temperature: 0, top_p: 0.9}\n",
        "  request: {temperature: 0.7}\n",
        "  caps: {think_maybe: {default: 1}}\n",
        "  caps: {think_on: {chat: 1}}\n",
        "  num_ctx_tiers: [8192, 4096]\n",
        "  max_attempts: 0\n",
        "  max_attempts: 2.5\n",
        "  selection: {ids: [], sample: {}}\n",
        "  selection: {sample: {per_usage: 20}}\n",
    ],
)
def test_invalid_generation_refused(tmp_path, insert):
    text = MINIMAL.replace("generation:\n", "generation:\n" + insert)
    with pytest.raises(ConfigError):
        load_campaign(_write(tmp_path, text))


@pytest.mark.parametrize(
    "model",
    [
        '{tag: "m", family: f, tracks: [think_off], think_off: false}',  # num_ctx_max absent
        '{tag: "m", family: f, tracks: [think_off], num_ctx_max: 1}',  # think_off implicite
        '{tag: "m", family: f, tracks: [], num_ctx_max: 1}',
        '{tag: "m", family: f, tracks: [think_maybe], num_ctx_max: 1}',
        '{tag: "m|x", family: f, tracks: [think_off], think_off: null, num_ctx_max: 1}',
        '{tag: "m", family: f, tracks: [think_off], think_off: null, num_ctx_max: 1, quant: q4}',
        '{tag: "m", family: f, tracks: [think_off], think_off: 1, num_ctx_max: 1}',
    ],
)
def test_invalid_model_refused(tmp_path, model):
    text = f"set: set-v1\ngeneration:\n  models:\n    - {model}\n"
    with pytest.raises(ConfigError):
        load_campaign(_write(tmp_path, text))


def test_model_without_thinking_has_null_think(tmp_path):
    text = 'set: s\ngeneration:\n  models:\n    - {tag: "m", family: f, tracks: [think_off], think_off: null, num_ctx_max: 8192}\n'
    model = load_campaign(_write(tmp_path, text)).generation["models"][0]
    assert model["think_off"] is None and model["think_on"] is None


@pytest.mark.parametrize(
    "text",
    [
        MINIMAL + "extra: 1\n",
        MINIMAL + "grading: {judge: haiku, weights: 1}\n",
        "generation:\n  models: []\nset: s\n",
        "set: s\n",
        MINIMAL + "set: set-v2\n",  # clé en double
        "- a\n- b\n",
    ],
)
def test_invalid_top_level_refused(tmp_path, text):
    with pytest.raises(ConfigError):
        load_campaign(_write(tmp_path, text))


@pytest.mark.parametrize(
    "text, name",
    [
        (MINIMAL.replace("set: set-v1", "set: ../set-v1"), "c.yaml"),
        (MINIMAL + "grading: {judge: 'a b'}\n", "c.yaml"),
        (MINIMAL, ".hidden.yaml"),
    ],
)
def test_invalid_identifiers_raise_config_error(tmp_path, text, name):
    with pytest.raises(ConfigError):
        load_campaign(_write(tmp_path, text, name))


def test_duplicate_model_tags_refused(tmp_path):
    line = '    - {tag: "m", family: f, tracks: [think_off], think_off: null, num_ctx_max: 1}\n'
    with pytest.raises(ConfigError, match="double"):
        load_campaign(_write(tmp_path, "set: s\ngeneration:\n  models:\n" + line + line))
