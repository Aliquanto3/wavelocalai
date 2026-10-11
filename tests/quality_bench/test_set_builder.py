"""Construction du jeu (AD-4, AD-5, AD-6) : cœur pur ``assemble`` et commande ``build-set``,
sur des entrées synthétiques seulement."""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import textwrap
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.canonical import canonical_bytes, pretty_bytes, sha256_bytes
from scripts.quality_bench.common.config import load_set
from scripts.quality_bench.common.jsonl import read_jsonl, rewrite_jsonl
from scripts.quality_bench.common.locks import FileLock
from scripts.quality_bench.questions import set_builder
from scripts.quality_bench.questions.generators import oneruler_fr
from scripts.quality_bench.questions.schema import (
    REFUSED_SOURCES,
    SOURCES,
    QuestionError,
    set_hash,
    with_hashes,
)
from scripts.quality_bench.questions.set_builder import (
    SetBuildError,
    assemble,
    draw_whole_groups,
    index_rows,
)

from .set_factories import set_v1, synthetic_candidates, synthetic_question

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def config():
    return set_v1()


@pytest.fixture(scope="module")
def candidates(config):
    return synthetic_candidates(config)


@pytest.fixture(scope="module")
def assembled(config, candidates):
    return assemble(config, candidates)


def _bytes(questions, tracks):
    return (
        b"".join(canonical_bytes(q) + b"\n" for q in questions),
        pretty_bytes(tracks),
        b"".join(canonical_bytes(row) + b"\n" for row in index_rows(questions)),
    )


def test_set_v1_composition(config):
    assert config.set_id == "set-v1"
    assert sum(config.think_off.values()) == 800
    assert sum(config.think_on.values()) == 400
    assert config.think_off == {
        "reasoning": 130,
        "instructions": 130,
        "tools": 130,
        "extraction": 110,
        "rag": 110,
        "abstention": 110,
        "writing": 80,
    }
    assert config.think_on == {
        "reasoning": 65,
        "instructions": 65,
        "tools": 65,
        "extraction": 55,
        "rag": 55,
        "abstention": 55,
        "writing": 40,
    }
    order = [entry.source for entry in config.sources]
    assert order.index("tools-fr") < order.index("bfcl-live")


def test_assemble_is_reproducible_with_expected_counts(config, candidates, assembled):
    questions, tracks = assembled
    again = assemble(config, candidates)
    assert _bytes(*again) == _bytes(questions, tracks)
    assert len(questions) == len(tracks["think_off"]) == 800
    assert len(tracks["think_on"]) == 400
    assert [q["id"] for q in questions] == sorted(q["id"] for q in questions)
    by_usage = Counter(q["usage"] for q in questions)
    assert dict(by_usage) == config.think_off
    on = set(tracks["think_on"])
    assert on <= set(tracks["think_off"])
    on_usage = Counter(q["usage"] for q in questions if q["id"] in on)
    assert dict(on_usage) == config.think_on
    by_source = Counter(q["source"] for q in questions)
    assert by_source == {entry.source: entry.count for entry in config.sources}


def test_other_seed_changes_sample_and_think_on(config, candidates, assembled):
    other = dataclasses.replace(config, seed=config.seed + 1)
    questions, tracks = assemble(other, candidates)
    assert tracks["think_on"] != assembled[1]["think_on"]
    assert [q["id"] for q in questions] != [q["id"] for q in assembled[0]]
    _check_whole_groups(questions, tracks)


def _check_whole_groups(questions, tracks):
    on = set(tracks["think_on"])
    groups = defaultdict(set)
    for question in questions:
        groups[question["group"]].add(question["id"] in on)
    assert all(len(states) == 1 for states in groups.values())


def test_groups_are_whole_and_var_math_units_hold_three_variants(assembled):
    questions, tracks = assembled
    _check_whole_groups(questions, tracks)
    units = defaultdict(list)
    for question in questions:
        if question["source"] == "var-math-fr":
            units[question["unit"]].append(question)
    assert len(units) == 20
    for unit, members in units.items():
        assert len(members) == 3
        assert {m["group"] for m in members} == {unit}


def test_translations_exclude_their_origin_group(assembled):
    questions, _ = assembled
    tools_fr = {q["group"] for q in questions if q["source"] == "tools-fr"}
    live = {q["group"] for q in questions if q["source"] == "bfcl-live"}
    assert tools_fr and not tools_fr & live


def test_per_group_caps_piaf(assembled):
    questions, _ = assembled
    piaf = Counter(q["group"] for q in questions if q["source"] == "piaf")
    assert len(piaf) == 50 and set(piaf.values()) == {1}


def test_draw_whole_groups_skips_a_group_that_overflows():
    import random

    groups = {"a": [1, 2, 3], "b": [1], "c": [1, 2]}
    taken = draw_whole_groups(groups, 3, random.Random(0), "x")
    assert sum(len(groups[g]) for g in taken) == 3


def test_unreachable_count_names_the_source(config, candidates):
    short = dict(candidates)
    short["bbeh-mini"] = candidates["bbeh-mini"][:10]
    with pytest.raises(SetBuildError, match="bbeh-mini"):
        assemble(config, short)


def test_no_whole_group_combination_reaches_the_count(config, candidates):
    odd = dict(candidates)
    odd["var-math-fr"] = list(candidates["var-math-fr"])  # groupes de 3
    entries = [
        dataclasses.replace(e, count=61) if e.source == "var-math-fr" else e for e in config.sources
    ]
    with pytest.raises(SetBuildError, match="var-math-fr"):
        assemble(dataclasses.replace(config, sources=tuple(entries)), odd)


def test_unreachable_think_on_names_the_usage(config, candidates):
    bad = dataclasses.replace(config, think_on={**config.think_on, "reasoning": 64})
    # 60 questions VAR-MATH en groupes de 3 + 70 groupes d'une question : 64 reste atteignable,
    # mais pas avec seulement des groupes de 3.
    only_var_math = dataclasses.replace(
        bad,
        sources=tuple(e for e in config.sources if e.source == "var-math-fr"),
        think_off={"reasoning": 60},
        think_on={"reasoning": 31},
    )
    with pytest.raises(SetBuildError, match="think_on de l'usage reasoning"):
        assemble(only_var_math, candidates)


def test_unit_across_groups_refused(config, candidates):
    broken = dict(candidates)
    first, second = candidates["bbeh-mini"][:2]
    shared = dict(second, unit=first["unit"])
    broken["bbeh-mini"] = [first, with_hashes(shared)] + candidates["bbeh-mini"][2:]
    small = dataclasses.replace(
        config,
        sources=tuple(
            dataclasses.replace(e, count=len(broken["bbeh-mini"]))
            for e in config.sources
            if e.source == "bbeh-mini"
        ),
        think_off={"reasoning": len(broken["bbeh-mini"])},
        think_on={"reasoning": 0},
    )
    with pytest.raises(SetBuildError, match="à cheval"):
        assemble(small, broken)


def test_insufficient_tier_refused(config, candidates):
    broken = dict(candidates)
    question = dict(candidates["ifbench"][0], est_prompt_tokens=4000)  # 4000 × 1,25 + 2048
    broken["ifbench"] = [with_hashes(question)]
    small = dataclasses.replace(
        config,
        sources=tuple(
            dataclasses.replace(e, count=1) for e in config.sources if e.source == "ifbench"
        ),
        think_off={"instructions": 1},
        think_on={"instructions": 0},
    )
    with pytest.raises(SetBuildError, match="palier"):
        assemble(small, broken)


def test_set_hash_follows_ad4(assembled):
    questions, tracks = assembled
    from scripts.quality_bench.common.canonical import sha256_hex

    pairs = sorted([q["id"], q["question_hash"]] for q in questions)
    assert set_hash(questions, tracks) == sha256_hex({"questions": pairs, "tracks": tracks})


def test_index_rows_whitelist(assembled):
    rows = index_rows(assembled[0])
    for row in rows:
        public = {"prompt_hash", "target_hash"}
        base = {
            "schema",
            "id",
            "usage",
            "group",
            "unit",
            "source",
            "license",
            "private",
            "question_hash",
        }
        assert set(row) == (base if row["private"] else base | public)
    assert any(row["private"] for row in rows) and any(not row["private"] for row in rows)


# --- Coquille et commande build-set (jeu réduit, sources synthétiques sur disque) ----------

SMALL_SET = """\
set: small
seed: 7
sources:
  - {source: var-math-fr, count: 6, generator_seed: 1, generator_params: {variants: 3}}
  - {source: bbeh-mini, count: 4}
  - {source: writing-fr, count: 3}
think_on: {reasoning: 4, writing: 1}
"""


@pytest.fixture
def small_set(tmp_path, monkeypatch):
    """Jeu ``small`` : YAML temporaire, candidats bbeh-mini et fichier VAR-MATH synthétiques."""
    config_dir = tmp_path / "sets_yaml"
    config_dir.mkdir()
    (config_dir / "small.yaml").write_text(SMALL_SET, encoding="utf-8")
    monkeypatch.setattr(paths, "set_config_path", lambda set_id: config_dir / f"{set_id}.yaml")
    rewrite_jsonl(
        paths.candidates_path("bbeh-mini"),
        [synthetic_question("bbeh-mini", n) for n in range(1, 9)],
    )
    _write_var_math(paths.private_source_path("var-math-fr"))
    return config_dir / "small.yaml"


def _write_var_math(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        textwrap.dedent(
            """\
            schema: qb.var_math/1
            problems:
            """
        )
        + "".join(
            f"  - {{number: {n}, text: 'Synthétique {n} : {{a}} fois {{b}} ?', "
            "params: {a: {min: 2, max: 30}, b: {min: 2, max: 30}}, constraints: ['a < b'], "
            "answer: 'a * b'}\n"
            for n in range(1, 4)
        ),
        encoding="utf-8",
    )


@pytest.fixture
def _reset_logging():
    yield
    from scripts.quality_bench.common.logs import setup_logging

    setup_logging("test", None)


def _outputs(set_id="small"):
    return (
        paths.set_questions_path(set_id),
        paths.set_tracks_path(set_id),
        paths.set_index_path(set_id),
    )


def test_cli_build_set_writes_three_files(small_set, _reset_logging):
    from scripts.quality_bench.__main__ import main

    assert main(["build-set", "--set", "small"]) == 0
    questions_path, tracks_path, index_path = _outputs()
    questions = read_jsonl(questions_path)
    assert len(questions) == 13
    assert [q["id"] for q in questions] == sorted(q["id"] for q in questions)
    tracks = __import__("json").loads(tracks_path.read_text(encoding="utf-8"))
    assert len(tracks["think_on"]) == 5
    rows = read_jsonl(index_path)
    assert len(rows) == 13 and all(r["schema"] == "qb.set_index/1" for r in rows)
    log = paths.sets_log_path("build-set").read_text(encoding="utf-8")
    assert set_hash(questions, tracks) in log
    assert "var-math-fr : fichier privé lu, sha256" in log
    assert "Synthétique" not in log  # jamais de contenu de question privée
    assert not paths.machine_lock_path().read_bytes()  # verrou relâché
    leftovers = [p.name for p in paths.sets_dir().iterdir() if p.name.startswith(".")]
    assert not leftovers


def test_build_set_is_byte_identical_across_roots(small_set, tmp_path, monkeypatch):
    digests = []
    for name in ("a", "b"):
        data = tmp_path / f"root-{name}"
        exports = tmp_path / f"exports-{name}"
        if name == "b":
            # mêmes entrées dans une autre racine
            import shutil

            shutil.copytree(tmp_path / "root-a" / "sources", data / "sources")
            shutil.copytree(tmp_path / "root-a" / "private", data / "private")
        monkeypatch.setenv("QUALITY_BENCH_DATA", str(data))
        monkeypatch.setenv("QUALITY_BENCH_EXPORTS", str(exports))
        if name == "a":
            rewrite_jsonl(
                paths.candidates_path("bbeh-mini"),
                [synthetic_question("bbeh-mini", n) for n in range(1, 9)],
            )
            _write_var_math(paths.private_source_path("var-math-fr"))
        set_builder.build_set("small")
        digests.append([sha256_bytes(p.read_bytes()) for p in _outputs()])
    assert digests[0] == digests[1]


def test_existing_set_is_refused_and_nothing_written(small_set, _reset_logging):
    from scripts.quality_bench.__main__ import main

    paths.set_index_dir("small").mkdir(parents=True)
    assert main(["build-set", "--set", "small"]) == 1
    assert not paths.set_dir("small").exists()
    assert "déjà construit" in paths.sets_log_path("build-set").read_text(encoding="utf-8")


def test_busy_machine_refused(small_set, _reset_logging):
    from scripts.quality_bench.__main__ import main

    with FileLock(paths.machine_lock_path()):
        assert main(["build-set", "--set", "small"]) == 1
    assert not paths.set_dir("small").exists() and not paths.set_index_dir("small").exists()
    assert "Verrou occupé" in paths.sets_log_path("build-set").read_text(encoding="utf-8")


def test_missing_candidates_name_the_file_and_fetch(small_set, _reset_logging):
    from scripts.quality_bench.__main__ import main

    paths.candidates_path("bbeh-mini").unlink()
    assert main(["build-set", "--set", "small"]) == 1
    log = paths.sets_log_path("build-set").read_text(encoding="utf-8")
    assert "candidates.jsonl" in log and "fetch --source bbeh-mini" in log
    assert not paths.set_dir("small").exists()


def test_missing_private_file_names_it(small_set, _reset_logging):
    from scripts.quality_bench.__main__ import main

    paths.private_source_path("var-math-fr").unlink()
    assert main(["build-set", "--set", "small"]) == 1
    assert "var-math-fr.yaml" in paths.sets_log_path("build-set").read_text(encoding="utf-8")
    assert not paths.set_index_dir("small").exists()


@pytest.mark.parametrize("tamper", ["absent", "altered"])
def test_oneruler_raw_files_are_verified_never_downloaded(small_set, tamper, _reset_logging):
    from scripts.quality_bench.__main__ import main

    text = SMALL_SET.replace(
        "  - {source: writing-fr, count: 3}\n",
        "  - {source: writing-fr, count: 3}\n"
        "  - {source: oneruler-fr-niah, count: 3, generator_seed: 2}\n",
    ).replace("writing: 1}", "writing: 1, rag: 0}")
    small_set.write_text(text, encoding="utf-8")
    if tamper == "altered":
        for remote in oneruler_fr.RAW_FILES:
            path = remote.local_path(paths.source_raw_dir("oneruler-fr"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"altered")
    assert main(["build-set", "--set", "small"]) == 1
    log = paths.sets_log_path("build-set").read_text(encoding="utf-8")
    assert "SourceIntegrityError" in log and "fetch --source oneruler-fr" in log
    assert not paths.set_dir("small").exists()
    if tamper == "altered":  # rien de supprimé ni retéléchargé
        for remote in oneruler_fr.RAW_FILES:
            assert remote.local_path(paths.source_raw_dir("oneruler-fr")).read_bytes() == (
                b"altered"
            )


@pytest.mark.parametrize(
    "replace, insert",
    [
        ("set: small", "set: other"),
        ("seed: 7", "seed: 7\nextra: 1"),
        ("reasoning: 4", "reasoning: 11"),
        ("count: 4}", "count: 4, generator_seed: 1}"),
        ("variants: 3", "variants: 3, colour: 1"),
        ("variants: 3", "variants: '3'"),
        ("variants: 3", "variants: 0"),
        ("variants: 3", "variants: true"),
        ("bbeh-mini", "musr"),
        ("bbeh-mini", "squad"),
    ],
)
def test_invalid_set_yaml_exits_2(small_set, replace, insert, _reset_logging):
    from scripts.quality_bench.__main__ import main

    small_set.write_text(SMALL_SET.replace(replace, insert, 1), encoding="utf-8")
    assert main(["build-set", "--set", "small"]) == 2
    assert not paths.set_dir("small").exists()


def test_cli_build_set_subprocess_refuses_when_busy(_isolated_data_root):
    with FileLock(paths.machine_lock_path()):
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "scripts.quality_bench", "build-set", "--set", "set-v1"],
            cwd=ROOT,
            capture_output=True,
            timeout=120,
        )
    assert result.returncode == 1
    assert "Verrou occupé" in result.stderr.decode("utf-8", "replace")
    assert not paths.set_dir("set-v1").exists()


def test_review_sample_writes_outside_the_repo(small_set, _reset_logging):
    from scripts.quality_bench.__main__ import main

    assert main(["review-sample", "--set", "small", "--per-source", "2", "--writing", "2"]) == 0
    private = paths.review_dir() / "private-sample.md"
    writing = paths.review_dir() / "writing-sample.md"
    assert private.is_file() and writing.is_file()
    assert private.read_text(encoding="utf-8").count("### reasoning/var-math-fr/") == 2
    text = writing.read_text(encoding="utf-8")
    assert text.count("### writing/writing-fr/") == 2 and "**Critères**" in text
    assert not paths.set_dir("small").exists()  # lecture seule : aucun jeu écrit
    assert paths.review_dir().is_relative_to(paths.data_root())


def test_load_set_refuses_refused_sources_by_name(tmp_path):
    path = tmp_path / "x.yaml"
    path.write_text(SMALL_SET.replace("set: small", "set: x").replace("bbeh-mini", "musr"), "utf-8")
    from scripts.quality_bench.common.config import ConfigError

    with pytest.raises(ConfigError, match="refusée"):
        load_set(path, SOURCES, REFUSED_SOURCES)


def test_generated_questions_carry_their_yaml_generator_seed(small_set, _reset_logging):
    from scripts.quality_bench.__main__ import main

    small_set.write_text(
        SMALL_SET.replace("variants: 3", "variants: 2").replace("count: 6", "count: 4"),
        encoding="utf-8",
    )
    assert main(["build-set", "--set", "small"]) == 0
    config = load_set(small_set, SOURCES, REFUSED_SOURCES)
    seeds = {entry.source: entry.generator_seed for entry in config.sources}
    questions = read_jsonl(paths.set_questions_path("small"))
    generated = [q for q in questions if q["generator"] is not None]
    assert generated and all(q["generator_seed"] == seeds[q["source"]] for q in generated)
    units = Counter(q["unit"] for q in questions if q["source"] == "var-math-fr")
    assert len(units) == 2 and set(units.values()) == {2}


def test_failed_rename_leaves_nothing(small_set, monkeypatch):
    real_rename = os.rename
    calls = []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError("renommage refusé (test)")
        return real_rename(src, dst)

    monkeypatch.setattr(set_builder.os, "rename", flaky)
    with pytest.raises(OSError):
        set_builder.build_set("small")
    assert len(calls) == 2
    for directory in (paths.set_dir("small"), paths.set_index_dir("small")):
        assert not directory.exists()
        assert not directory.with_name(f".{directory.name}.tmp").exists()


SECRET = "VALEUR-SECRETE-4242"


def test_private_value_never_reaches_the_build_log(small_set, _reset_logging):
    """Question d'extraction privée synthétique et mal formée : ni l'erreur ni le journal ne
    citent sa valeur."""
    from scripts.quality_bench.__main__ import main

    schema = {
        "type": "object",
        "properties": {"montant": {"type": "integer"}},
        "required": ["montant"],
        "additionalProperties": False,
    }
    schema_text = pretty_bytes(schema).decode("utf-8").rstrip("\n")
    document = (
        "schema: qb.house/1\nsource: extraction-fr\nquestions:\n"
        "  - number: 1\n    messages:\n      - role: user\n        content: |-\n"
        + "".join(f"          {line}\n" for line in ["Extrais.", *schema_text.splitlines()])
        + "    grader_params:\n      subset: extraction-fr\n"
        + "      schema: {type: object, properties: {montant: {type: integer}}, "
        "required: [montant], additionalProperties: false}\n"
        + f"    target: {{montant: {SECRET}}}\n"
    )
    path = paths.private_source_path("extraction-fr")
    path.write_text(document, encoding="utf-8")
    from scripts.quality_bench.questions.house import load_house

    with pytest.raises(QuestionError) as caught:
        load_house(path, "extraction-fr")
    assert "montant" in str(caught.value) and SECRET not in str(caught.value)
    small_set.write_text(
        SMALL_SET.replace(
            "  - {source: writing-fr, count: 3}\n",
            "  - {source: writing-fr, count: 3}\n  - {source: extraction-fr, count: 1}\n",
        ),
        encoding="utf-8",
    )
    assert main(["build-set", "--set", "small"]) == 1
    log = paths.sets_log_path("build-set").read_text(encoding="utf-8")
    assert "QuestionError" in log and SECRET not in log and "Traceback" not in log
    assert not paths.set_dir("small").exists()


def test_duplicate_key_in_a_source_file_is_a_build_error(small_set, _reset_logging):
    from scripts.quality_bench.__main__ import main

    path = paths.private_source_path("var-math-fr")
    path.write_text(path.read_text(encoding="utf-8") + "schema: qb.var_math/1\n", "utf-8")
    assert main(["build-set", "--set", "small"]) == 1
    log = paths.sets_log_path("build-set").read_text(encoding="utf-8")
    assert "SetBuildError" in log and "var-math-fr.yaml" in log
    assert "YAML de jeu invalide" not in log


def test_review_sample_refusal_has_no_traceback(small_set, _reset_logging):
    from scripts.quality_bench.__main__ import main

    paths.private_source_path("var-math-fr").unlink()
    assert main(["review-sample", "--set", "small"]) == 1
    log = paths.sets_log_path("review-sample").read_text(encoding="utf-8")
    assert "SetBuildError" in log and "Traceback" not in log
