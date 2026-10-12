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
    assert generation["min_prefill_tok_s"] == 50
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
        "  min_prefill_tok_s: 0\n",
        "  min_prefill_tok_s: -5\n",
        "  min_prefill_tok_s: true\n",
        "  min_prefill_tok_s: .nan\n",
        '  min_prefill_tok_s: "50"\n',
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


# --- YAML de jeu : load_set ------------------------------------------------------------------

from scripts.quality_bench.common.config import load_set  # noqa: E402
from scripts.quality_bench.questions.schema import REFUSED_SOURCES, SOURCES  # noqa: E402

SET = """\
set: s1
seed: 3
sources:
  - {source: var-math-fr, count: 6, generator_seed: 1, generator_params: {variants: 3}}
  - {source: bbeh-mini, count: 4}
  - {source: piaf, count: 5, per_group: 1}
think_on: {reasoning: 5, rag: 2}
"""


def test_load_set_resolves_counts(tmp_path):
    config = load_set(_write(tmp_path, SET, "s1.yaml"), SOURCES, REFUSED_SOURCES)
    assert config.set_id == "s1" and config.seed == 3
    assert config.think_off == {"reasoning": 10, "rag": 5}
    assert config.think_on == {"reasoning": 5, "rag": 2}
    var_math, bbeh, piaf = config.sources
    assert (var_math.generator_seed, var_math.generator_params) == (1, {"variants": 3})
    assert (bbeh.usage, bbeh.generator_seed, bbeh.per_group) == ("reasoning", None, None)
    assert piaf.per_group == 1
    assert var_math.exclude == bbeh.exclude == piaf.exclude == ()


def test_load_set_reads_exclude(tmp_path):
    text = SET.replace("count: 4}", "count: 4, exclude: [reasoning/bbeh-mini/0002]}", 1)
    config = load_set(_write(tmp_path, text, "s1.yaml"), SOURCES, REFUSED_SOURCES)
    assert config.sources[1].exclude == ("reasoning/bbeh-mini/0002",)
    assert config.sources[0].exclude == ()


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("seed: 3", "seed: 3\nextra: 1", "inconnues"),
        ("count: 4}", "count: 4, colour: 1}", "inconnues"),
        ("reasoning: 5", "reasoning: 11", "think_off"),
        ("rag: 2", "rag: 2, tools: 1", "think_on.tools"),
        ("rag: 2", "chat: 1", "inconnues"),
        ("bbeh-mini", "musr", "refusée"),
        ("bbeh-mini", "squad", "inconnue"),
        (", generator_seed: 1", "", "generator_seed"),
        ("count: 4}", "count: 4, generator_seed: 2}", "interdit"),
        ("count: 4}", "count: 0}", "count"),
        ("per_group: 1", "per_group: 0", "per_group"),
        (
            "  - {source: piaf, count: 5, per_group: 1}\n",
            "  - {source: bbeh-mini, count: 1}\n",
            "double",
        ),
        ("seed: 3\n", "", "seed"),
        (
            "count: 4}",
            "count: 4, exclude: [reasoning/bbeh-mini/0001, reasoning/bbeh-mini/0001]}",
            r"sources\[1\]\.exclude : identifiants en double",
        ),
    ],
)
def test_load_set_refuses_invalid_yaml(tmp_path, old, new, message):
    path = _write(tmp_path, SET.replace(old, new, 1), "s1.yaml")
    with pytest.raises(ConfigError, match=message):
        load_set(path, SOURCES, REFUSED_SOURCES)


def test_load_set_requires_file_name_to_match(tmp_path):
    with pytest.raises(ConfigError, match="nom du fichier"):
        load_set(_write(tmp_path, SET, "s2.yaml"), SOURCES, REFUSED_SOURCES)


def test_real_set_v1_loads():
    from scripts.quality_bench.common.paths import set_config_path

    config = load_set(set_config_path("set-v1"), SOURCES, REFUSED_SOURCES)
    assert sum(config.think_off.values()) == 800 and sum(config.think_on.values()) == 400
    exclude = {entry.source: entry.exclude for entry in config.sources if entry.exclude}
    assert exclude == {
        "bfcl-live": (
            "tools/bfcl-live/0107",
            "tools/bfcl-live/0113",
            "tools/bfcl-live/0766",
            "tools/bfcl-live/1121",
            "tools/bfcl-live/1223",
        )
    }


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("{source: bbeh-mini, count: 4}", "{source: [bbeh-mini], count: 4}", "chaîne"),
        ("generator_params: {variants: 3}", "generator_params: []", "generator_params"),
        ("generator_params: {variants: 3}", "generator_params: 0", "generator_params"),
        ("generator_params: {variants: 3}", "generator_params: false", "generator_params"),
        ("rag: 2", "rag: 2, tools: abc", "think_on.tools"),
        ("rag: 2", "rag: 2, tools: 0.0", "think_on.tools"),
        ("count: 4}", "count: 4, exclude: reasoning/bbeh-mini/0001}", r"sources\[1\]\.exclude"),
        ("count: 4}", "count: 4, exclude: {a: 1}}", r"sources\[1\]\.exclude"),
        ("count: 4}", "count: 4, exclude: null}", r"sources\[1\]\.exclude"),
        ("count: 4}", "count: 4, exclude: [1]}", r"sources\[1\]\.exclude"),
        ("count: 4}", "count: 4, exclude: ['']}", r"sources\[1\]\.exclude"),
        ("count: 4}", "count: 4, exclude: [' ']}", r"sources\[1\]\.exclude"),
        ("count: 4}", "count: 4, exclude: [null]}", r"sources\[1\]\.exclude"),
    ],
)
def test_load_set_refuses_malformed_values(tmp_path, old, new, message):
    path = _write(tmp_path, SET.replace(old, new, 1), "s1.yaml")
    with pytest.raises(ConfigError, match=message):
        load_set(path, SOURCES, REFUSED_SOURCES)


def test_load_set_accepts_explicit_zero_think_on_for_absent_usage(tmp_path):
    path = _write(tmp_path, SET.replace("rag: 2", "rag: 2, tools: 0", 1), "s1.yaml")
    assert "tools" not in load_set(path, SOURCES, REFUSED_SOURCES).think_on


def test_unreadable_yaml_is_a_config_error_without_excerpt(tmp_path):
    path = _write(tmp_path, "set: s1\nseed: [3\nsecret: VALEUR-SECRETE\n", "s1.yaml")
    with pytest.raises(ConfigError, match="YAML illisible") as caught:
        load_set(path, SOURCES, REFUSED_SOURCES)
    assert "VALEUR-SECRETE" not in str(caught.value) and "ligne" in str(caught.value)


@pytest.mark.parametrize("value", ["12.5", "80"])
def test_min_prefill_accepts_positive_numbers(tmp_path, value):
    text = MINIMAL.replace("generation:\n", f"generation:\n  min_prefill_tok_s: {value}\n")
    config = load_campaign(_write(tmp_path, text))
    assert config.generation["min_prefill_tok_s"] == float(value)
    default = load_campaign(_write(tmp_path, MINIMAL, "b.yaml"))
    assert config.generation_hash != default.generation_hash


@pytest.mark.parametrize("value", ["50", "50.0"])
def test_explicit_min_prefill_default_keeps_the_hash(tmp_path, value):
    text = MINIMAL.replace("generation:\n", f"generation:\n  min_prefill_tok_s: {value}\n")
    explicit = load_campaign(_write(tmp_path, text))
    default = load_campaign(_write(tmp_path, MINIMAL, "b.yaml"))
    assert explicit.generation["min_prefill_tok_s"] == 50.0
    assert isinstance(explicit.generation["min_prefill_tok_s"], float)
    assert explicit.generation_hash == default.generation_hash


# --- Sélection par groupes entiers (mode groups, story 8) ----------------------------------


def _with_selection(tmp_path, selection, name="pilot-20261015.yaml"):
    text = MINIMAL.replace("generation:\n", f"generation:\n  selection: {selection}\n")
    return load_campaign(_write(tmp_path, text, name))


def test_selection_groups_is_resolved(tmp_path):
    config = _with_selection(
        tmp_path,
        "{groups: {seed: 8, per_usage: {reasoning: {think_off: 70, think_on: 36}, "
        "writing: {think_on: 0, think_off: 4}}}}",
    )
    assert config.generation["selection"] == {
        "groups": {
            "seed": 8,
            "per_usage": {
                "reasoning": {"think_off": 70, "think_on": 36},
                "writing": {"think_off": 4, "think_on": 0},
            },
        }
    }


def test_selection_groups_hash_ignores_key_order(tmp_path):
    a = _with_selection(
        tmp_path,
        "{groups: {seed: 8, per_usage: {rag: {think_off: 2, think_on: 1}, "
        "tools: {think_off: 3, think_on: 0}}}}",
        "a.yaml",
    )
    b = _with_selection(
        tmp_path,
        "{groups: {per_usage: {tools: {think_on: 0, think_off: 3}, "
        "rag: {think_on: 1, think_off: 2}}, seed: 8}}",
        "b.yaml",
    )
    assert a.generation_hash == b.generation_hash


@pytest.mark.parametrize(
    "selection, message",
    [
        ("{groups: {seed: 8, per_usage: {}}}", "au moins un usage"),
        ("{groups: {seed: 8}}", "per_usage : obligatoire"),
        ("{groups: {per_usage: {rag: {think_off: 1, think_on: 0}}}}", "seed : obligatoire"),
        ("{groups: {seed: 8, extra: 1, per_usage: {rag: {think_off: 1, think_on: 0}}}}", "extra"),
        ("{groups: {seed: 8, per_usage: {chat: {think_off: 1, think_on: 0}}}}", "chat"),
        ("{groups: {seed: 8, per_usage: {rag: {think_off: 1, think_on: 0, x: 1}}}}", "'x'"),
        ("{groups: {seed: 8, per_usage: {rag: {think_off: 1}}}}", "think_on : obligatoire"),
        ("{groups: {seed: 8, per_usage: {rag: {think_off: -1, think_on: 0}}}}", "entier ≥ 0"),
        ("{groups: {seed: 8, per_usage: {rag: {think_off: 2, think_on: -1}}}}", "entier ≥ 0"),
        ("{groups: {seed: 8, per_usage: {rag: {think_off: 2, think_on: 3}}}}", "au-delà"),
        ("{groups: {seed: -1, per_usage: {rag: {think_off: 1, think_on: 0}}}}", "seed"),
        ("{groups: {seed: 8, per_usage: {rag: {think_off: 1.5, think_on: 0}}}}", "entier"),
        ("{groups: {seed: 8, per_usage: [rag]}}", "objet"),
        ("{groups: {seed: 8, per_usage: {rag: {think_off: 1, think_on: 0}}}, ids: [a]}", "attendu"),
    ],
)
def test_selection_groups_refused(tmp_path, selection, message):
    with pytest.raises(ConfigError, match=message):
        _with_selection(tmp_path, selection)


# --- pilot.yaml (story 8) ------------------------------------------------------------------

from scripts.quality_bench.common import paths  # noqa: E402
from scripts.quality_bench.common.config import load_pilot_settings  # noqa: E402

PILOT = """\
old_bench: benchmarks/results/ancien.json
catalog: /absolu/catalogue.json
budget_hours: 144
ceiling: 0.9
floor: 0.1
reduction:
  caps:
    - {think_on: {reasoning: 3072, default: 1536}}
  think_on_n: 330
full_models: [a:1b, b:2b]
"""


def test_load_pilot_settings(tmp_path):
    settings = load_pilot_settings(_write(tmp_path, PILOT, "pilot.yaml"))
    assert settings.old_bench == "benchmarks/results/ancien.json"
    assert settings.old_bench_path == paths.REPO_ROOT / "benchmarks/results/ancien.json"
    assert settings.catalog_path.is_absolute()
    assert settings.budget_hours == 144.0
    assert (settings.ceiling, settings.floor) == (0.9, 0.1)
    # Plafond candidat partiel, sans valeur par défaut : fusionné sur la campagne au pilote.
    assert settings.reduction_caps == ({"think_on": {"reasoning": 3072, "default": 1536}},)
    assert settings.think_on_n == 330
    assert settings.full_models == ("a:1b", "b:2b")


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("budget_hours: 144\n", "budget_hours: 144\nextra: 1\n", "extra"),
        ("budget_hours: 144\n", "", "budget_hours"),
        ("budget_hours: 144", "budget_hours: 0", "budget_hours"),
        ("ceiling: 0.9", "ceiling: 1.5", "ceiling"),
        ("floor: 0.1", "floor: 0.95", "floor"),
        ("think_on_n: 330", "think_on_n: 0", "think_on_n"),
        ("    - {think_on: {reasoning: 3072, default: 1536}}\n", "    []\n", "reduction.caps"),
        ("{think_on: {reasoning: 3072", "{think_on: {chat: 1, reasoning: 3072", "chat"),
        ("{think_on: {reasoning: 3072", "{think_maybe: {reasoning: 3072", "think_maybe"),
        ("{think_on: {reasoning: 3072, default: 1536}}", "{}", "au moins une piste"),
        ("{think_on: {reasoning: 3072, default: 1536}}", "{think_on: {}}", "au moins un plafond"),
        ("reasoning: 3072, default: 1536", "reasoning: 0, default: 1536", "entier ≥ 1"),
        ("  think_on_n: 330\n", "  think_on_n: 330\n  other: 1\n", "other"),
        ("[a:1b, b:2b]", "[a:1b, a:1b]", "double"),
        ("[a:1b, b:2b]", "[]", "full_models"),
        ("old_bench: benchmarks/results/ancien.json", "old_bench: ''", "old_bench"),
    ],
)
def test_invalid_pilot_settings_refused(tmp_path, old, new, message):
    assert old in PILOT
    with pytest.raises(ConfigError, match=message):
        load_pilot_settings(_write(tmp_path, PILOT.replace(old, new), "pilot.yaml"))


def test_missing_pilot_settings_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="absent"):
        load_pilot_settings(tmp_path / "pilot.yaml")
