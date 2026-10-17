"""Commande ``pilot --campaign <c>`` (CAP-8) sur des campagnes synthétiques : pilote et rejeu
écrits par ``make_campaign`` puis retouchés (tokens, durées), chauffes, journal, ancien banc,
catalogue, indice AA et ``pilot.yaml`` sous ``tmp_path``. Matrice entrées-sorties de la story 8,
deux passes identiques octet pour octet, aucun texte de question ni de sortie."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.canonical import pretty_bytes
from scripts.quality_bench.common.jsonl import read_jsonl, rewrite_jsonl
from scripts.quality_bench.common.schemas import validate

from .report_factories import (
    JUDGE_ID,
    SECRET_OUTPUT,
    SECRET_QUESTION,
    aa_reference,
    make_campaign,
    write_aa_reference,
)

ROOT = Path(__file__).resolve().parents[2]
PILOT = "pilot-test"
REPLAY = f"{PILOT}-replay"
TAGS = [f"model-{i}:4b" for i in range(4)]
NAMES = {tag: f"Modèle {i}" for i, tag in enumerate(TAGS)}
# Débits de l'ancien banc des modèles synthétiques (décodage, préremplissage).
RATES = {TAGS[0]: (100.0, 3000.0), TAGS[1]: (80.0, 2500.0), TAGS[2]: (60.0, 2000.0)}
RATES[TAGS[3]] = (40.0, 1500.0)
REPLAY_USAGES = ("reasoning", "instructions", "rag", "writing")
REPLAY_SELECTION = {
    "groups": {"seed": 3, "per_usage": {u: {"think_off": 4, "think_on": 2} for u in REPLAY_USAGES}}
}
COMPLETION = {"reasoning": 300, "instructions": 200, "rag": 60, "writing": 400}


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    from scripts.quality_bench.common.logs import setup_logging

    setup_logging("test", None)


# -- Fabrique -------------------------------------------------------------------------------


def _retouch(campaign: str) -> None:
    """Tokens, durées et appels déterministes sur chaque ligne de génération requêtée."""
    lines = read_jsonl(paths.generation_path(campaign))
    for line in lines:
        if line["status"] == "context_exceeded":
            continue
        model = TAGS.index(line["model"])
        think = line["track"] == "think_on"
        completion = COMPLETION[line["usage"]] * (3 if think else 1) + 10 * model
        prompt = 500 + 100 * model
        decode, prefill = RATES[line["model"]]
        prompt_eval = int(prompt / prefill * 1e9)
        evaluation = int(completion / decode * 1e9)
        line["tokens"] = {
            "prompt": prompt,
            "prompt_cached": 50 if line["usage"] == "rag" else 0,
            "completion": completion,
            "thinking_est": completion // 2 if think else 0,
            "answer_est": completion // 2 if think else completion,
        }
        line["durations_ns"] = {
            "total": prompt_eval + evaluation,
            "load": 0,
            "prompt_eval": prompt_eval,
            "eval": evaluation,
        }
        line["wall_s"] = round((prompt_eval + evaluation) / 1e9 * 1.25, 6)
        line["calls"] = 1
        line["num_ctx"] = 8192  # palier des questions synthétiques
        validate(line)
    rewrite_jsonl(paths.generation_path(campaign), lines)


def _warmups(campaign: str, manifest_hash: str) -> None:
    records = []
    for i, tag in enumerate(TAGS):
        for num_ctx, prompt_tokens, factor in ((4096, 1024, 1.1), (8192, 2048, 1.0)):
            records.append(
                {
                    "schema": "qb.warmup/1",
                    "key": f"{campaign}|{tag}|{num_ctx}|{len(records)}",
                    "manifest": manifest_hash,
                    "campaign": campaign,
                    "model": tag,
                    "num_ctx": num_ctx,
                    "prompt_tokens": prompt_tokens,
                    "size": 1000,
                    "size_vram": 1000,
                    "prefill_tok_s": RATES[tag][1] * factor,
                    "load_ns": 1_000_000 * (i + 1),
                    "created_at": "2026-10-12T08:00:00Z",
                }
            )
    rewrite_jsonl(paths.warmups_path(campaign), records)


def _references(tmp_path: Path, *, budget: float = 144, extra_models=()) -> dict[str, Path]:
    refs = tmp_path / "refs"
    refs.mkdir(exist_ok=True)
    old = {
        "machine": "tour-test",
        "models": {
            NAMES[tag]: {
                "avg_tokens_per_second": RATES[tag][0],
                "prefill_tokens_per_second": RATES[tag][1],
                "prefill_prompt_tokens": 2000,
                "load_time_ms": 1500,
                "quality_scores": {
                    "reasoning_avg": 0.9 - 0.2 * i,
                    "instruction_following_avg": 0.8 - 0.1 * i,
                    "abstention_avg": 1.0,
                },
                "tool_capability": {"success_rate": 1.0},
                "json_capability": {"schema_compliance_rate": 1.0},
                "needle_in_haystack": {"ctx_4k": True, "ctx_8k": i < 2, "ctx_16k": i < 1},
            }
            for i, tag in enumerate(TAGS)
        },
    }
    catalog = {
        "models": {
            NAMES[tag]: {"ollama_tag": tag, "capabilities": ["chat", "tools", "thinking"]}
            for tag in TAGS
        }
    }
    files = {"old": refs / "old-bench.json", "catalog": refs / "catalog.json"}
    files["old"].write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    files["catalog"].write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    models = "\n".join(f"  - {tag}" for tag in [*TAGS, *extra_models])
    files["settings"] = refs / "pilot.yaml"
    files["settings"].write_text(
        textwrap.dedent(
            f"""\
            old_bench: {files['old'].as_posix()}
            catalog: {files['catalog'].as_posix()}
            budget_hours: {budget}
            ceiling: 0.9
            floor: 0.1
            reduction:
              caps:
                - {{think_on: {{reasoning: 600, default: 400}}}}
                - {{think_on: {{reasoning: 300, default: 200}}}}
              think_on_n: 10
            full_models:
            """
        )
        + models
        + "\n",
        encoding="utf-8",
    )
    return files


@pytest.fixture
def env(tmp_path, monkeypatch):
    pilot = make_campaign(tmp_path, monkeypatch, campaign=PILOT, n_models=4, think_off_only=())
    replay = make_campaign(
        tmp_path,
        monkeypatch,
        campaign=REPLAY,
        n_models=4,
        think_off_only=(),
        selection=REPLAY_SELECTION,
    )
    for synthetic in (pilot, replay):
        _retouch(synthetic.campaign)
    _warmups(PILOT, pilot.generation_hash)
    log = paths.log_path(PILOT, "generate")
    log.write_text(
        "2026-10-12T08:00:00 WARNING [generate] x : clé : Ollama ne répond plus, attente\n"
        "2026-10-12T08:00:01 INFO [generate] x : reprise\n",
        encoding="utf-8",
    )
    files = _references(tmp_path)
    monkeypatch.setattr(paths, "pilot_settings_path", lambda: files["settings"])
    return {"pilot": pilot, "replay": replay, "files": files, "tmp_path": tmp_path}


def _run(*extra):
    from scripts.quality_bench.__main__ import main

    return main(["pilot", "--campaign", PILOT, *extra])


def _report():
    return json.loads(paths.pilot_report_path(PILOT, ".json").read_text(encoding="utf-8"))


def _markdown():
    return paths.pilot_report_path(PILOT, ".md").read_text(encoding="utf-8")


def _log():
    return paths.log_path(PILOT, "pilot").read_text(encoding="utf-8")


def _outputs_exist():
    return [paths.pilot_report_path(PILOT, suffix).exists() for suffix in (".md", ".json")]


def _track(section, track):
    return next(block for block in section if block["track"] == track)


# -- Pilote et rejeu complets ---------------------------------------------------------------


def test_complete_pilot_writes_every_section(env):
    assert _run() == 0
    report = _report()
    for key in (
        "discordance",
        "ceiling_floor",
        "stability",
        "tokens",
        "projection",
        "order",
        "aa",
        "writing",
        "deferred",
        "references",
    ):
        assert key in report
    assert report["completeness"]["pilot"]["complete"] is True
    assert report["completeness"]["replay"]["complete"] is True
    stability = report["stability"]
    assert stability["status"] == "computed"
    assert stability["joined"] == stability["replay_lines"] > 0
    assert stability["excluded"] == {"unmatched": 0, "digest": 0, "prompt_hash": 0}
    for block in stability["tracks"]:
        assert block["output_changed"] == 0
        assert block["score_changed"] == 0
    # ψ global : deux pistes, 6 paires de 4 modèles.
    for track in ("think_off", "think_on"):
        scope = _track(report["discordance"], track)["scopes"][0]
        assert scope["scope"] == "global"
        assert len(scope["pairs"]) == 6
    markdown = _markdown()
    for title in (
        "## Discordance entre modèles (ψ)",
        "## Stabilité au rejeu",
        "## Tokens et troncature",
        "## Projection de durée de la campagne complète",
        "## Cohérence d'ordre",
        "## Rédaction (provisoire)",
        "## Points à trancher au pilote (deferred-work.md)",
    ):
        assert title in markdown
    deferred = report["deferred"]
    assert deferred["retries"][0] == {
        "campaign": PILOT,
        "log_lines": 1,
        "attempts_over_one": 0,
        "error_lines": 0,
    }
    assert deferred["retries"][1]["log_lines"] is None  # journal du rejeu absent
    assert any(e["source"] == "bfcl-multi" for e in deferred["context_exceeded"]["by_source"])
    rag = next(e for e in deferred["prefix_cache"] if e["usage"] == "rag")
    assert rag["lines_with_cache"] == rag["lines"]
    assert rag["cached_share"] == pytest.approx(50 / 650, rel=0.2)


def test_reports_and_log_hold_no_question_text_nor_output(env):
    assert _run() == 0
    for text in (_markdown(), json.dumps(_report(), ensure_ascii=False), _log()):
        assert SECRET_QUESTION not in text
        assert SECRET_OUTPUT not in text
    assert "created_at" not in _markdown()
    assert "created_at" not in json.dumps(_report())


def test_reference_files_are_never_modified(env):
    before = {name: path.read_bytes() for name, path in env["files"].items()}
    generation = paths.generation_path(PILOT).read_bytes()
    assert _run() == 0
    assert {name: path.read_bytes() for name, path in env["files"].items()} == before
    assert paths.generation_path(PILOT).read_bytes() == generation
    written = sorted(p.name for p in paths.campaign_dir(PILOT).iterdir())
    assert written == sorted(
        [
            "generation.jsonl",
            "grading.jsonl",
            "judgment-haiku",
            "log-generate.log",
            "log-pilot.log",
            "manifest.json",
            "pilot-report.json",
            "pilot-report.md",
            "warmups.jsonl",
        ]
    )


def test_two_cli_passes_are_byte_identical(env):
    """Deux processus distincts (graine de hachage différente) : rapports identiques."""
    config_dir = env["pilot"].config_dir
    settings = env["files"]["settings"]
    script = textwrap.dedent(
        f"""
        import sys
        from pathlib import Path
        from scripts.quality_bench.common import paths
        paths.campaign_config_path = lambda c: Path({str(config_dir)!r}) / f"{{c}}.yaml"
        paths.pilot_settings_path = lambda: Path({str(settings)!r})
        from scripts.quality_bench.__main__ import main
        sys.exit(main(["pilot", "--campaign", {PILOT!r}]))
        """
    )
    outputs = []
    for seed in ("1", "2"):
        environ = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", script], cwd=ROOT, env=environ, capture_output=True, timeout=300
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", "replace")[-2000:]
        outputs.append(
            [paths.pilot_report_path(PILOT, suffix).read_bytes() for suffix in (".md", ".json")]
        )
    assert outputs[0] == outputs[1]
    leftovers = [p.name for p in paths.campaign_dir(PILOT).iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


# -- Rejeu ----------------------------------------------------------------------------------


def test_replay_without_configuration_is_absent(env):
    (env["replay"].config_dir / f"{REPLAY}.yaml").unlink()
    assert _run() == 0
    report = _report()
    assert report["stability"]["status"] == "absent"
    assert report["completeness"]["replay"] is None
    assert "Rejeu absent" in _markdown()


def test_replay_without_manifest_is_absent(env):
    paths.generation_manifest_path(REPLAY).unlink()
    assert _run() == 0
    assert _report()["stability"]["status"] == "absent"


def test_references_record_settings_and_replay_manifest(env):
    from scripts.quality_bench.common.canonical import sha256_bytes

    assert _run() == 0
    references = _report()["references"]
    settings = env["files"]["settings"]
    assert references["settings"]["sha256"] == sha256_bytes(settings.read_bytes())
    assert references["settings"]["path"].endswith("refs/pilot.yaml")
    assert references["replay_generation_manifest"] == env["replay"].generation_hash
    (env["replay"].config_dir / f"{REPLAY}.yaml").unlink()
    assert _run() == 0
    assert _report()["references"]["replay_generation_manifest"] is None


def test_replay_with_another_generation_section_is_refused(env, tmp_path, monkeypatch):
    make_campaign(
        tmp_path,
        monkeypatch,
        campaign=REPLAY,
        n_models=4,
        think_off_only=(),
        k=2,
        selection=REPLAY_SELECTION,
    )
    _assert_refused(1)
    assert "generation.resolved.request.k" in _log()


def test_replay_equal_to_the_campaign_exits_2(env):
    _assert_refused(2, "--replay", PILOT)
    assert "identique" in _log()


def test_retry_message_matches_both_runner_log_calls():
    from scripts.quality_bench.report.pilot_commands import RETRY_MESSAGE

    source = (ROOT / "scripts/quality_bench/generation/runner.py").read_text(encoding="utf-8")
    calls = [
        line for line in source.splitlines() if "logger.warning(" in line and RETRY_MESSAGE in line
    ]
    assert len(calls) == 2, calls
    assert any("pendant la chauffe" in line for line in calls)  # chauffe
    assert any("%s : Ollama ne répond plus, attente" in line for line in calls)  # question


def test_unrequested_pairs_and_status_changes_are_counted_apart(env):
    lines = read_jsonl(paths.generation_path(REPLAY))
    target = next(
        line for line in lines if line["usage"] == "reasoning" and line["track"] == "think_off"
    )
    target.update(status="context_exceeded", calls=0, output=[], context_limit="bench")
    rewrite_jsonl(paths.generation_path(REPLAY), lines)
    grading = read_jsonl(paths.grading_path(REPLAY))
    for line in grading:
        if line["key"] == target["key"]:
            line.update(
                status="context_exceeded",
                context_limit="bench",
                score=None,
                success=None,
                metrics={},
            )
    rewrite_jsonl(paths.grading_path(REPLAY), grading)
    assert _run() == 0
    block = _track(_report()["stability"]["tracks"], "think_off")
    assert block["not_requested"] == 1
    assert block["requested_pairs"] == block["joined"] - 1
    assert block["status_changed"] == 1
    assert block["output_changed"] == 0  # la paire non requêtée n'entre pas dans le taux
    assert "Statuts changés" in _markdown()


def test_explicit_replay_campaign(env):
    assert _run("--replay", "absent-replay") == 0
    assert _report()["stability"]["status"] == "absent"
    assert _report()["replay_campaign"] == "absent-replay"


def test_replay_key_missing_from_the_pilot_is_excluded_and_counted(env):
    replay_line = read_jsonl(paths.generation_path(REPLAY))[0]
    pilot_key = replay_line["key"].replace(REPLAY, PILOT, 1)
    for path in (paths.generation_path(PILOT), paths.grading_path(PILOT)):
        rewrite_jsonl(path, [line for line in read_jsonl(path) if line["key"] != pilot_key])
    assert _run() == 0
    report = _report()
    assert report["stability"]["excluded"]["unmatched"] == 1
    assert report["stability"]["joined"] == report["stability"]["replay_lines"] - 1
    assert report["completeness"]["pilot"]["complete"] is False
    assert report["completeness"]["pilot"]["generation_missing"] == 1


def test_changed_output_and_score_are_counted_apart(env):
    lines = read_jsonl(paths.generation_path(REPLAY))
    binary = next(
        line for line in lines if line["usage"] == "reasoning" and line["track"] == "think_off"
    )
    other = next(line for line in lines if line["usage"] == "rag" and line["track"] == "think_off")
    other["output"] = [
        {"turn": 0, "role": "assistant", "content": "autre", "thinking": None, "tool_calls": []}
    ]
    rewrite_jsonl(paths.generation_path(REPLAY), lines)
    grading = read_jsonl(paths.grading_path(REPLAY))
    for line in grading:
        if line["key"] == binary["key"]:
            line["score"] = 1.0 - line["score"]
            line["success"] = not line["success"]
    rewrite_jsonl(paths.grading_path(REPLAY), grading)
    assert _run() == 0
    block = _track(_report()["stability"]["tracks"], "think_off")
    assert block["output_changed"] == 1
    assert block["score_changed"] == 1
    rate = 1 / block["scored_pairs"]
    assert block["score_changed_rate"] == pytest.approx(rate)
    assert block["ratio_to_psi"] == pytest.approx(rate / block["psi_mean_global"])


# -- Projection -----------------------------------------------------------------------------


def test_projection_under_budget_proposes_nothing(env):
    assert _run() == 0
    projection = _report()["projection"]
    assert projection["over_budget"] is False
    assert projection["reduction"] is None
    assert projection["complete"] is True
    assert "aucune réduction nécessaire" in _markdown()
    assert "Proposition de réduction" not in _markdown()


def test_projection_over_budget_publishes_the_proposal(env, monkeypatch):
    files = _references(env["tmp_path"], budget=0.001)
    monkeypatch.setattr(paths, "pilot_settings_path", lambda: files["settings"])
    assert _run() == 0
    projection = _report()["projection"]
    assert projection["over_budget"] is True
    steps = [s["step"] for s in projection["reduction"]["scenarios"]]
    assert steps == ["caps", "caps", "thinking_only", "think_on_n"]
    assert projection["reduction"]["proposal"] is True
    markdown = _markdown()
    assert "### Proposition de réduction" in markdown
    assert "Proposition seulement, rien n'est appliqué" in markdown


def test_unknown_rate_marks_the_total_incomplete(env, monkeypatch):
    files = _references(env["tmp_path"], extra_models=["inconnu:1b"])
    monkeypatch.setattr(paths, "pilot_settings_path", lambda: files["settings"])
    assert _run() == 0
    projection = _report()["projection"]
    unknown = next(m for m in projection["models"] if m["tag"] == "inconnu:1b")
    assert unknown["known"] is False
    assert unknown["reason"] == "absent du catalogue"
    assert projection["complete"] is False
    assert "débit inconnu (absent du catalogue)" in _markdown()
    assert "total incomplet" in _markdown()
    # Total connu sous le budget mais incomplet : aucune conclusion, aucune proposition.
    assert projection["over_budget"] is False
    assert projection["conclusion"] == "undetermined"
    assert projection["reduction"] is None
    assert "Indéterminé (débits manquants)" in _markdown()
    assert "aucune réduction nécessaire" not in _markdown()


# -- Indice AA, rédaction --------------------------------------------------------------------


def test_without_aa_reference(env):
    assert _run() == 0
    assert _report()["aa"]["status"] == "absent"
    assert "Indice AA absent" in _markdown()


def test_with_aa_reference(env):
    entries = [
        {"tag": TAGS[0], "index": 20.0, "status": "measured", "variant": "reasoning"},
        {"tag": TAGS[1], "index": 18.0, "status": "measured", "variant": "reasoning"},
        {"tag": TAGS[2], "index": 15.0, "status": "estimated", "variant": "reasoning"},
    ]
    write_aa_reference(aa_reference("2026-10-01", entries))
    assert _run() == 0
    aa = _report()["aa"]
    assert aa["status"] == "computed"
    block = _track(aa["tracks"], "think_on")
    assert block["models"] == 2
    statuses = {e["model"]: e["status"] for e in block["entries"]}
    assert statuses == {
        TAGS[0]: "measured",
        TAGS[1]: "measured",
        TAGS[2]: "estimated",
        TAGS[3]: "absent",
    }
    assert block["concordant"] + block["discordant"] + block["tied"] == 1


def test_awaiting_judgment_is_counted_apart(env):
    pilot = env["pilot"]
    first_writing = [
        line["key"]
        for line in pilot.grading
        if "|writing/" in line["key"] and f"|{TAGS[0]}|think_off|" in line["key"]
    ][:2]
    for line in pilot.grading:
        if line["key"] in first_writing:
            line.update(
                status="awaiting_judgment",
                score=None,
                success=None,
                judgment_manifest=None,
                metrics={},
            )
    pilot.write_grading()
    assert _run() == 0
    writing = _report()["writing"]
    assert writing["status"] == "provisional"
    assert writing["awaiting_judgment"] == 2
    entry = next(
        e for e in _track(writing["tracks"], "think_off")["models"] if e["model"] == TAGS[0]
    )
    assert entry["awaiting_judgment"] == 2
    assert entry["scored"] == entry["expected"] - 2
    assert entry["available"] == entry["expected"]
    scores = [
        pilot.scores[key]
        for key in pilot.scores
        if "|writing/" in key and f"|{TAGS[0]}|think_off|" in key and key not in first_writing
    ]
    assert entry["mean"] == pytest.approx(sum(scores) / len(scores))
    assert "(provisoire)" in _markdown()


def test_without_judgment_the_writing_is_not_graded(env):
    pilot = env["pilot"]
    shutil.rmtree(paths.judgment_dir(PILOT, JUDGE_ID))
    for line in pilot.grading:
        if "|writing/" in line["key"]:
            line.update(
                status="awaiting_judgment",
                score=None,
                success=None,
                judgment_manifest=None,
                metrics={},
            )
    pilot.write_grading()
    assert _run() == 0
    writing = _report()["writing"]
    assert writing["status"] == "not_graded"
    entry = _track(writing["tracks"], "think_off")["models"][0]
    assert entry["scored"] == 0
    assert entry["available"] == entry["expected"] > 0
    assert "non notée" in _markdown()


# -- Entrées incohérentes et configuration -------------------------------------------------


def _assert_refused(code, *extra):
    assert _run(*extra) == code
    assert _outputs_exist() == [False, False]


def test_warmup_out_of_schema_is_refused(env):
    lines = read_jsonl(paths.warmups_path(PILOT))
    lines[0]["prefill_tok_s"] = "rapide"
    rewrite_jsonl(paths.warmups_path(PILOT), lines)
    _assert_refused(1)
    assert "warmups.jsonl ligne 1" in _log()


def test_generation_line_out_of_schema_is_refused(env):
    lines = read_jsonl(paths.generation_path(PILOT))
    del lines[0]["tokens"]
    rewrite_jsonl(paths.generation_path(PILOT), lines)
    _assert_refused(1)


def test_replay_on_another_set_is_refused(env, tmp_path, monkeypatch):
    make_campaign(
        tmp_path,
        monkeypatch,
        campaign=REPLAY,
        n_models=4,
        think_off_only=(),
        small=True,
        set_id="other-set",
    )
    _assert_refused(1)
    assert "jeu différent" in _log()


@pytest.mark.parametrize("content", ["ceci n'est pas du JSON", "[1, 2]", '{"models": []}'])
def test_unreadable_old_bench_is_refused(env, content):
    env["files"]["old"].write_text(content, encoding="utf-8")
    _assert_refused(1)
    assert "ancien banc illisible" in _log()


def test_missing_catalog_is_refused(env):
    env["files"]["catalog"].unlink()
    _assert_refused(1)
    assert "catalogue absent" in _log()


def test_missing_pilot_settings_exits_2(env):
    env["files"]["settings"].unlink()
    _assert_refused(2)


def test_invalid_pilot_settings_exits_2(env):
    path = env["files"]["settings"]
    path.write_text(path.read_text(encoding="utf-8") + "unknown: 1\n", encoding="utf-8")
    _assert_refused(2)


def test_missing_campaign_configuration_exits_2(env):
    (env["pilot"].config_dir / f"{PILOT}.yaml").unlink()
    _assert_refused(2)


def test_invalid_replay_configuration_exits_2(env):
    path = env["replay"].config_dir / f"{REPLAY}.yaml"
    path.write_text("set: [\n", encoding="utf-8")
    _assert_refused(2)


def test_bad_replay_identifier_exits_2(env):
    _assert_refused(2, "--replay", "../ailleurs")


def test_json_report_is_written_canonically(env):
    """Le rapport JSON est la forme lisible du dictionnaire (clés triées, sans NaN)."""
    assert _run() == 0
    data = paths.pilot_report_path(PILOT, ".json").read_bytes()
    assert data == pretty_bytes(json.loads(data))


def test_campaign_before_context_limit_is_refused_with_code_2(env):
    """Manifeste sans models_resolved[].context_length (pilot-20261012) : code 2, message clair."""
    manifest_path = paths.generation_manifest_path(PILOT)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for model in manifest["blocking"]["models_resolved"]:
        del model["context_length"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert _run() == 2
    assert _outputs_exist() == [False, False]
    assert "campagne antérieure à context_limit" in _log()
