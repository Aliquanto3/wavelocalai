"""Commande ``grade --campaign <c>`` (AD-3, AD-10, AD-16) sur une campagne synthétique :
manifeste, ``generation.jsonl`` couvrant chaque correcteur et chaque statut, verdicts
synthétiques, deux passes identiques octet pour octet et matrice d'incohérences."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.canonical import pretty_bytes, utc_now
from scripts.quality_bench.common.jsonl import read_jsonl, rewrite_jsonl
from scripts.quality_bench.common.manifest import blocking_hash
from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.questions.schema import set_hash

from .conftest import REAL_NLTK_DATA
from .factories import JUDGE, manifest
from .grading_factories import (
    CWE_WORDS,
    GOOD_STEPS,
    answer_output,
    assistant,
    generation_for,
    questions,
    run_conversation,
    tool_call,
)

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = "grade-test"
SET_ID = "small-grade"
JUDGE_ID = "haiku"
CAMPAIGN_YAML = f"""\
set: {SET_ID}
generation:
  models:
    - {{tag: "m:1b", family: qwen, tracks: [think_off], think_off: false, num_ctx_max: 32768}}
grading:
  judge: {JUDGE_ID}
"""

# (question, sortie, statut de génération, borne d'appels) → (statut, score, success).
CASES = {
    "bbeh": ("bbeh", "The answer is: (a)", "ok", False, ("ok", 1.0, True)),
    "var_math": ("var_math", "La réponse est : 1 234", "ok", False, ("ok", 1.0, True)),
    "ifbench": ("ifbench", "La banane, la pomme", "ok", False, ("ok", 0.0, False)),
    "mifeval": ("mifeval", "Une phrase.", "ok", False, ("ok", 1.0, True)),
    "bfcl_ast": ("bfcl_ast", "call", "ok", False, ("ok", 1.0, True)),
    "bfcl_multi": ("bfcl_multi", "conversation", "ok", False, ("ok", 1.0, True)),
    "irrelevance": ("irrelevance", "Je ne peux pas.", "ok", False, ("ok", 1.0, True)),
    "jsonschema": ("jsonschema", "pas du JSON", "ok", False, ("non_compliant", 0.0, False)),
    "extraction": (
        "extraction",
        '{"nom": "Jeanne Martin", "age": 40, "actif": true}',
        "ok",
        False,
        ("ok", 1.0, True),
    ),
    "piaf": ("piaf", "Eiffel", "ok", False, ("ok", 1.0, True)),
    "niah": ("niah", "1234567", "ok", False, ("ok", 1.0, True)),
    "none": ("none", "aucun", "ok", False, ("ok", 1.0, True)),
    "cwe": ("cwe", " ".join(CWE_WORDS), "ok", False, ("ok", 1.0, True)),
    "abstention": ("abstention", "Paris", "ok", False, ("ok", 0.0, False)),
    "writing": ("writing", "Texte.", "ok", False, ("ok", 0.75, None)),
}
# Statuts de génération et borne d'appels, sur d'autres graines de questions déjà présentes.
STATUS_CASES = {
    ("piaf", 1): ("truncated", False, ("truncated", 0.0, False)),
    ("writing", 1): ("truncated", False, ("truncated", 0.0, None)),
    ("piaf", 2): ("context_exceeded", False, ("context_exceeded", None, None)),
    ("piaf", 3): ("error", False, ("error", None, None)),
    ("bfcl_multi", 1): ("ok", True, ("non_compliant", 0.0, False)),
    ("writing", 2): ("ok", False, ("awaiting_judgment", None, None)),
    ("writing", 3): ("ok", False, ("error", None, None)),
}


def _output(name, question, content):
    if content == "call":
        call = tool_call("weather_get", {"city": "Paris", "days": 2.5})
        return [assistant(tool_calls=[call])]
    if content == "conversation":
        return run_conversation(question, GOOD_STEPS)
    return answer_output(content)


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty_bytes(obj))


def _campaign_lines(qs, manifest_hash):
    """Lignes de génération : une par cas, puis une par cas de statut (autre graine)."""
    lines = []
    expected = {}
    for name, (qname, content, status, cap, outcome) in CASES.items():
        question = qs[qname]
        line = generation_for(
            question,
            _output(name, question, content),
            status=status,
            call_cap_reached=cap,
            manifest=manifest_hash,
            campaign=CAMPAIGN,
        )
        lines.append(line)
        expected[line["key"]] = outcome
    for (qname, seed), (status, cap, outcome) in STATUS_CASES.items():
        question = qs[qname]
        content = "conversation" if qname == "bfcl_multi" else "Texte."
        line = generation_for(
            question,
            _output(qname, question, content),
            status=status,
            call_cap_reached=cap,
            manifest=manifest_hash,
            campaign=CAMPAIGN,
            seed=seed,
        )
        lines.append(line)
        expected[line["key"]] = outcome
    return lines, expected


def _judgment_line(generation_key, criterion, verdict, judgment_hash, error=None):
    return {
        "schema": "qb.judgment/1",
        "key": f"{generation_key}|{criterion}",
        "generation_key": generation_key,
        "manifest": judgment_hash,
        "criterion": criterion,
        "judge": JUDGE_ID,
        "verdict": verdict,
        "probability": None,
        "tokens": {"input": 10, "output": 1},
        "cost_usd": 0.0,
        "attempts": 1,
        "error": error,
        "created_at": utc_now(),
    }


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    """Campagne synthétique complète ; rend (attendus, chemins utiles)."""
    config_dir = tmp_path / "campaigns_yaml"
    config_dir.mkdir()
    (config_dir / f"{CAMPAIGN}.yaml").write_text(CAMPAIGN_YAML, encoding="utf-8")
    monkeypatch.setattr(paths, "campaign_config_path", lambda c: config_dir / f"{c}.yaml")
    monkeypatch.setattr(paths, "nltk_data_dir", lambda: REAL_NLTK_DATA)

    qs = questions()
    question_list = sorted(qs.values(), key=lambda q: q["id"])
    tracks = {"think_off": [q["id"] for q in question_list], "think_on": []}
    rewrite_jsonl(paths.set_questions_path(SET_ID), question_list)
    _write_json(paths.set_tracks_path(SET_ID), tracks)

    generation_manifest = manifest(campaign=CAMPAIGN)
    generation_manifest["blocking"]["set"] = {
        "id": SET_ID,
        "hash": set_hash(question_list, tracks),
        "n": {"think_off": len(question_list), "think_on": 0},
    }
    validate(generation_manifest)
    _write_json(paths.generation_manifest_path(CAMPAIGN), generation_manifest)
    generation_hash = blocking_hash(generation_manifest)
    lines, expected = _campaign_lines(qs, generation_hash)
    rewrite_jsonl(paths.generation_path(CAMPAIGN), lines)

    judgment_manifest = manifest(campaign=CAMPAIGN, phase="judgment")
    judgment_manifest["blocking"]["judge"] = dict(JUDGE)
    judgment_manifest["blocking"]["generation_manifest"] = generation_hash
    validate(judgment_manifest)
    _write_json(paths.judgment_manifest_path(CAMPAIGN, JUDGE_ID), judgment_manifest)
    judgment_hash = blocking_hash(judgment_manifest)
    writing_keys = sorted(k for k in expected if "/writing-fr/" in k)
    full, missing, failing = writing_keys[0], writing_keys[2], writing_keys[3]
    assert expected[full] == ("ok", 0.75, None)
    judgments = [
        _judgment_line(full, f"c{i}", verdict, judgment_hash)
        for i, verdict in enumerate((True, True, False, True), start=1)
    ]
    judgments += [_judgment_line(missing, f"c{i}", True, judgment_hash) for i in (1, 2, 3)]
    judgments += [
        _judgment_line(failing, "c1", True, judgment_hash),
        _judgment_line(failing, "c2", None, judgment_hash, error="panne du juge"),
    ]
    rewrite_jsonl(paths.judgment_path(CAMPAIGN, JUDGE_ID), judgments)
    return {
        "expected": expected,
        "config_dir": config_dir,
        "generation_hash": generation_hash,
        "judgment_hash": judgment_hash,
        "lines": lines,
        "judgments": judgments,
        "manifest": generation_manifest,
        "questions": question_list,
    }


@pytest.fixture
def _reset_logging():
    yield
    from scripts.quality_bench.common.logs import setup_logging

    setup_logging("test", None)


def _run(campaign_id=CAMPAIGN):
    from scripts.quality_bench.__main__ import main

    return main(["grade", "--campaign", campaign_id])


def test_grade_writes_one_sorted_line_per_generation(campaign, _reset_logging):
    assert _run() == 0
    records = read_jsonl(paths.grading_path(CAMPAIGN))
    assert [r["key"] for r in records] == sorted(campaign["expected"])
    generation_status = {line["key"]: line["status"] for line in campaign["lines"]}
    for record in records:
        validate(record)
        assert (record["status"], record["score"], record["success"]) == (
            campaign["expected"][record["key"]]
        ), record["key"]
        assert record["generation_manifest"] == campaign["generation_hash"]
        # Rédaction jugée seulement : une sortie non ok n'est jamais jugée.
        judged = record["grader"] == "judge_criteria@1" and generation_status[record["key"]] == "ok"
        assert record["judgment_manifest"] == (campaign["judgment_hash"] if judged else None)
    truncated_writing = [
        r for r in records if r["grader"] == "judge_criteria@1" and r["status"] == "truncated"
    ]
    assert truncated_writing and truncated_writing[0]["judgment_manifest"] is None
    assert {r["grader"].split("@")[0] for r in records} == {
        "exact_answer",
        "ifbench",
        "mifeval_fr",
        "bfcl_ast",
        "bfcl_state",
        "bfcl_irrelevance",
        "json_schema",
        "squad_f1",
        "oneruler_niah",
        "oneruler_cwe",
        "abstention_marker",
        "judge_criteria",
    }
    log = paths.log_path(CAMPAIGN, "grade").read_text(encoding="utf-8")
    assert "lignes corrigées" in log and "awaiting_judgment 1" in log
    for question in campaign["questions"]:  # jamais de contenu de question ni de réponse
        assert question["messages"][0]["content"] not in log
    assert "Jeanne" not in log and "banane" not in log


def test_two_cli_passes_are_byte_identical(campaign):
    """Deux processus distincts (graine de hachage différente) : octets identiques."""
    script = textwrap.dedent(
        f"""
        import sys
        from pathlib import Path
        from scripts.quality_bench.common import paths
        paths.campaign_config_path = lambda c: Path({str(campaign["config_dir"])!r}) / f"{{c}}.yaml"
        paths.nltk_data_dir = lambda: Path({str(REAL_NLTK_DATA)!r})
        from scripts.quality_bench.__main__ import main
        sys.exit(main(["grade", "--campaign", {CAMPAIGN!r}]))
        """
    )
    outputs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, timeout=300
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")[-2000:]
        outputs.append(paths.grading_path(CAMPAIGN).read_bytes())
    assert outputs[0] == outputs[1]
    assert outputs[0].count(b"\n") == len(campaign["expected"])
    assert b"created_at" not in outputs[0]


def _assert_refused(code, _reset_logging=None):
    assert _run() == code
    assert not paths.grading_path(CAMPAIGN).exists()


def test_question_missing_from_set_is_refused(campaign, _reset_logging):
    lines = [dict(line) for line in campaign["lines"]]
    lines[0]["question_id"] = "reasoning/bbeh-mini/9999"
    rewrite_jsonl(paths.generation_path(CAMPAIGN), lines)
    _assert_refused(1)


def test_prompt_hash_mismatch_is_refused(campaign, _reset_logging):
    lines = [dict(line) for line in campaign["lines"]]
    lines[0]["prompt_hash"] = "f" * 64
    rewrite_jsonl(paths.generation_path(CAMPAIGN), lines)
    _assert_refused(1)


def test_set_hash_mismatch_is_refused(campaign, _reset_logging):
    tracks_path = paths.set_tracks_path(SET_ID)
    _write_json(tracks_path, {"think_off": [], "think_on": []})
    _assert_refused(1)


def test_generation_line_of_another_manifest_is_refused(campaign, _reset_logging):
    lines = [dict(line) for line in campaign["lines"]]
    lines[-1]["manifest"] = "e" * 64
    rewrite_jsonl(paths.generation_path(CAMPAIGN), lines)
    _assert_refused(1)


def test_generation_line_off_schema_is_refused(campaign, _reset_logging):
    lines = [dict(line) for line in campaign["lines"]]
    lines[0]["status"] = "unknown"
    rewrite_jsonl(paths.generation_path(CAMPAIGN), lines)
    _assert_refused(1)


def test_judgment_line_of_another_manifest_is_refused(campaign, _reset_logging):
    judgments = [dict(line) for line in campaign["judgments"]]
    judgments[0]["manifest"] = "d" * 64
    rewrite_jsonl(paths.judgment_path(CAMPAIGN, JUDGE_ID), judgments)
    _assert_refused(1)


def test_judgment_line_off_schema_is_refused(campaign, _reset_logging):
    judgments = [dict(line) for line in campaign["judgments"]]
    judgments[0]["verdict"] = None  # verdict nul sans erreur
    rewrite_jsonl(paths.judgment_path(CAMPAIGN, JUDGE_ID), judgments)
    _assert_refused(1)


def test_judgment_of_another_generation_manifest_is_refused(campaign, _reset_logging):
    judgment_manifest = manifest(campaign=CAMPAIGN, phase="judgment")
    judgment_manifest["blocking"]["judge"] = dict(JUDGE)
    judgment_manifest["blocking"]["generation_manifest"] = "c" * 64
    _write_json(paths.judgment_manifest_path(CAMPAIGN, JUDGE_ID), judgment_manifest)
    _assert_refused(1)


def test_missing_generation_manifest_is_refused(campaign, _reset_logging):
    paths.generation_manifest_path(CAMPAIGN).unlink()
    _assert_refused(1)


def test_missing_campaign_config_exits_2(campaign, _reset_logging):
    (campaign["config_dir"] / f"{CAMPAIGN}.yaml").unlink()
    _assert_refused(2)


def test_invalid_campaign_config_exits_2(campaign, _reset_logging):
    (campaign["config_dir"] / f"{CAMPAIGN}.yaml").write_text("set: x\n", encoding="utf-8")
    _assert_refused(2)


def test_without_judgment_folder_writing_awaits(campaign, _reset_logging):
    for path in paths.judgment_dir(CAMPAIGN, JUDGE_ID).iterdir():
        path.unlink()
    paths.judgment_dir(CAMPAIGN, JUDGE_ID).rmdir()
    assert _run() == 0
    records = read_jsonl(paths.grading_path(CAMPAIGN))
    writing = [r for r in records if r["grader"] == "judge_criteria@1"]
    ok_writing = [r for r in writing if r["status"] != "truncated"]
    assert ok_writing and all(r["status"] == "awaiting_judgment" for r in ok_writing)
    assert all(r["judgment_manifest"] is None for r in records)


def test_other_judges_are_never_read(campaign, _reset_logging):
    """Seul le dossier du juge retenu est lu : un autre dossier, même illisible, est ignoré."""
    other = paths.judgment_dir(CAMPAIGN, "mimo")
    other.mkdir(parents=True)
    (other / "judgment.jsonl").write_bytes(b"pas du JSON\n")
    assert _run() == 0


def test_grade_rewrites_previous_file_entirely(campaign, _reset_logging):
    paths.grading_path(CAMPAIGN).write_bytes(b'{"key": "ancienne"}\n')
    assert _run() == 0
    keys = [r["key"] for r in read_jsonl(paths.grading_path(CAMPAIGN))]
    assert "ancienne" not in keys and len(keys) == len(campaign["expected"])


# --- Refus documentés (code 1, rien n'est écrit) ------------------------------------------


def _rewrite_generation(lines):
    rewrite_jsonl(paths.generation_path(CAMPAIGN), lines)


def _rewrite_judgments(judgments):
    rewrite_jsonl(paths.judgment_path(CAMPAIGN, JUDGE_ID), judgments)


def _first_non_writing(campaign):
    return next(line for line in campaign["lines"] if "/writing-fr/" not in line["key"])


def test_missing_nltk_data_is_refused(campaign, monkeypatch, tmp_path, _reset_logging):
    monkeypatch.setattr(paths, "nltk_data_dir", lambda: tmp_path / "sans_nltk")
    _assert_refused(1)
    log = paths.log_path(CAMPAIGN, "grade").read_text(encoding="utf-8")
    assert "tokenizers/punkt" in log and "fetch-nltk" in log


def test_duplicate_generation_key_is_refused(campaign, _reset_logging):
    _rewrite_generation([*campaign["lines"], campaign["lines"][0]])
    _assert_refused(1)


def test_generation_line_of_another_campaign_is_refused(campaign, _reset_logging):
    lines = [dict(line) for line in campaign["lines"]]
    lines[0]["campaign"] = "autre-campagne"
    _rewrite_generation(lines)
    _assert_refused(1)


def test_generation_usage_mismatch_is_refused(campaign, _reset_logging):
    lines = [dict(line) for line in campaign["lines"]]
    lines[0]["usage"] = "rag" if lines[0]["usage"] != "rag" else "reasoning"
    _rewrite_generation(lines)
    _assert_refused(1)


def test_generation_manifest_with_wrong_phase_is_refused(campaign, _reset_logging):
    wrong = dict(campaign["manifest"], phase="judgment")
    wrong["blocking"] = {**wrong["blocking"], "judge": dict(JUDGE), "generation_manifest": "c" * 64}
    validate(wrong)
    _write_json(paths.generation_manifest_path(CAMPAIGN), wrong)
    _assert_refused(1)


def test_config_set_different_from_manifest_set_is_refused(campaign, _reset_logging):
    (campaign["config_dir"] / f"{CAMPAIGN}.yaml").write_text(
        CAMPAIGN_YAML.replace(f"set: {SET_ID}", "set: autre-jeu"), encoding="utf-8"
    )
    _assert_refused(1)


def test_judgment_lines_without_manifest_are_refused(campaign, _reset_logging):
    paths.judgment_manifest_path(CAMPAIGN, JUDGE_ID).unlink()
    _assert_refused(1)


def test_judgment_manifest_of_another_judge_is_refused(campaign, _reset_logging):
    judgment_manifest = manifest(campaign=CAMPAIGN, phase="judgment")
    judgment_manifest["blocking"]["judge"] = {**JUDGE, "id": "mimo"}
    judgment_manifest["blocking"]["generation_manifest"] = campaign["generation_hash"]
    _write_json(paths.judgment_manifest_path(CAMPAIGN, JUDGE_ID), judgment_manifest)
    _assert_refused(1)


def test_duplicate_judgment_line_is_refused(campaign, _reset_logging):
    _rewrite_judgments([*campaign["judgments"], campaign["judgments"][0]])
    _assert_refused(1)


def test_judgment_of_a_non_writing_question_is_refused(campaign, _reset_logging):
    generation_key = _first_non_writing(campaign)["key"]
    extra = _judgment_line(generation_key, "c1", True, campaign["judgment_hash"])
    _rewrite_judgments([*campaign["judgments"], extra])
    _assert_refused(1)


def test_judgment_of_an_unknown_criterion_is_refused(campaign, _reset_logging):
    first = campaign["judgments"][0]
    extra = _judgment_line(first["generation_key"], "c9", True, campaign["judgment_hash"])
    _rewrite_judgments([*campaign["judgments"], extra])
    _assert_refused(1)
