"""Commandes ``calibrate`` et ``calibrate-sample`` (CAP-6) sur une campagne synthétique de
quatre modèles (un Qwen) jugée par winnow, haiku, mimo et haiku-replay : matrice entrées-sorties
de la story 9, valeurs calculées à la main, deux passes identiques octet pour octet, aucun texte
de question ni de sortie hors de ``labels-todo-<c>.md``."""

from __future__ import annotations

import codecs
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.canonical import canonical_bytes, pretty_bytes
from scripts.quality_bench.common.jsonl import read_jsonl, rewrite_jsonl
from scripts.quality_bench.common.manifest import blocking_hash
from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.report import calibration
from scripts.quality_bench.stats.wilson import wilson_interval

from .factories import HASH_A, HASH_B, JUDGE, manifest
from .report_factories import SECRET_OUTPUT, SECRET_QUESTION, make_campaign

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = "calib-test"
FAMILIES = ["qwen", "mistral", "gemma", "llama"]
QWEN_TAG, OTHER_TAG = "model-0:4b", "model-1:4b"
HUMAN = [True] * 5 + [False] * 5
# Probabilités de Winnow sur les dix unités étiquetées de chaque groupe (verdict = p ≥ 0,5).
WINNOW_P = {
    "qwen": [0.9, 0.8, 0.6, 0.55, 0.3, 0.2, 0.1, 0.45, 0.7, 0.52],
    "other": [0.95, 0.4, 0.62, 0.9, 0.85, 0.05, 0.35, 0.6, 0.15, 0.48],
}
# Erreurs de Haiku sur les unités étiquetées : (groupe, rang) → verdict contraire à l'humain.
HAIKU_WRONG = {("qwen", 4), ("other", 1), ("other", 7)}
MARGINS = "0,0.1,0.5"


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    from scripts.quality_bench.common.logs import setup_logging

    setup_logging("test", None)


# -- Fabrique -------------------------------------------------------------------------------


def _judge_block(judge_id: str, **overrides):
    block = {**JUDGE, "id": judge_id, **overrides}
    if judge_id.startswith("winnow"):
        block.update(endpoint="http://127.0.0.1:11434", model="winnow-e4b", settings={})
    if judge_id.startswith("mimo"):
        block.update(endpoint="https://api.xiaomimimo.com/v1", model="mimo-v2.6-pro")
    return block


def write_judge(campaign, judge_id, generation_hash, verdicts, *, batches=None, **block):
    """Dossier ``judgment-<id>/`` : manifeste, ``judgment.jsonl`` (clé → (verdict,
    probabilité, coût), verdict ``None`` = ligne ``error``) et ``batches.jsonl`` facultatif
    (coûts des lots relevés)."""
    judgment_manifest = manifest(campaign=campaign, phase="judgment")
    judgment_manifest["blocking"]["judge"] = _judge_block(judge_id, **block)
    judgment_manifest["blocking"]["generation_manifest"] = generation_hash
    validate(judgment_manifest)
    path = paths.judgment_manifest_path(campaign, judge_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty_bytes(judgment_manifest))
    manifest_hash = blocking_hash(judgment_manifest)
    lines = []
    for key in sorted(verdicts):
        verdict, probability, cost = verdicts[key]
        generation_key, criterion = key.rsplit("|", 1)
        lines.append(
            {
                "schema": "qb.judgment/1",
                "key": key,
                "generation_key": generation_key,
                "manifest": manifest_hash,
                "criterion": criterion,
                "judge": judge_id,
                "verdict": verdict,
                "probability": probability,
                "tokens": {"input": 100, "output": 1},
                "cost_usd": cost,
                "attempts": 1,
                "error": None if verdict is not None else "verdict illisible",
                "created_at": "2026-10-12T08:00:00Z",
            }
        )
    for line in lines:
        validate(line)
    rewrite_jsonl(paths.judgment_path(campaign, judge_id), lines)
    paths.batches_path(campaign, judge_id).unlink(missing_ok=True)
    if batches is not None:
        records = []
        for index, cost in enumerate(batches):
            common = {
                "schema": "qb.batch/1",
                "batch_id": f"msgbatch_{index}",
                "judge": judge_id,
                "manifest": manifest_hash,
                "created_at": "2026-10-12T08:00:00Z",
            }
            records.append(
                {
                    **common,
                    "key": f"msgbatch_{index}|submitted",
                    "status": "submitted",
                    "keys": [lines[0]["key"]],
                    "estimate_usd": 1.0,
                }
            )
            records.append(
                {
                    **common,
                    "key": f"msgbatch_{index}|collected",
                    "status": "collected",
                    "counts": {"succeeded": 1, "errored": 0, "canceled": 0, "expired": 0},
                    "tokens": {"input": 1, "output": 1},
                    "cost_usd": cost,
                    "outcomes": {},
                }
            )
        for record in records:
            validate(record)
        rewrite_jsonl(paths.batches_path(campaign, judge_id), records)
    return manifest_hash


def unit_keys(synthetic) -> list[str]:
    keys = []
    for line in synthetic.generation:
        if line["usage"] != "writing" or line["status"] != "ok":
            continue
        for criterion in synthetic.questions[line["question_id"]]["criteria"]:
            keys.append(f"{line['key']}|{criterion['id']}")
    return sorted(keys)


def labeled_keys(keys):
    """Dix premières unités du modèle Qwen et dix du premier modèle non-Qwen."""
    return {
        "qwen": [k for k in keys if k.split("|")[1] == QWEN_TAG][:10],
        "other": [k for k in keys if k.split("|")[1] == OTHER_TAG][:10],
    }


def label_line(key, label, **overrides):
    record = {
        "schema": "qb.label/1",
        "key": key,
        "label": label,
        "author": None if label is None else "Anaël",
        "labeled_at": None if label is None else "2026-10-12",
        "note": None,
    }
    record.update(overrides)
    return record


def write_labels(records, *, raw: bytes | None = None):
    path = paths.labels_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        path.write_bytes(raw)
        return
    path.write_bytes(b"".join(canonical_bytes(r) + b"\n" for r in records))


@pytest.fixture
def env(tmp_path, monkeypatch):
    synthetic = make_campaign(
        tmp_path, monkeypatch, campaign=CAMPAIGN, n_models=4, think_off_only=(), families=FAMILIES
    )
    keys = unit_keys(synthetic)
    labeled = labeled_keys(keys)
    human = {}
    for group_keys in labeled.values():
        for index, key in enumerate(group_keys):
            human[key] = HUMAN[index]
    generation_hash = synthetic.generation_hash

    winnow = dict.fromkeys(keys, (True, 0.9, 0.0))
    haiku = dict.fromkeys(keys, (True, None, 0.0001))
    mimo = dict.fromkeys(keys, (True, None, 0.0002))
    for group, group_keys in labeled.items():
        for index, key in enumerate(group_keys):
            p = WINNOW_P[group][index]
            winnow[key] = (p >= 0.5, p, 0.0)
            wrong = (group, index) in HAIKU_WRONG
            haiku[key] = (HUMAN[index] != wrong, None, 0.0001)
            if group == "qwen":
                mimo[key] = (HUMAN[index], None, 0.0002)
    mimo[labeled["qwen"][0]] = (None, None, 0.0002)  # ligne error
    del mimo[labeled["other"][9]]  # étiquetée sans ligne
    replay = dict(haiku)
    flips = [k for k in keys if k not in human][:3]
    replay[flips[0]] = (False, None, 0.0001)
    replay[flips[1]] = (False, None, 0.0001)
    haiku[flips[2]] = (False, None, 0.0001)  # faux → vrai au rejeu
    shutil.rmtree(paths.judgment_dir(CAMPAIGN, "haiku"))
    write_judge(CAMPAIGN, "winnow", generation_hash, winnow)
    write_judge(CAMPAIGN, "haiku", generation_hash, haiku, batches=[0.03, 0.018])
    write_judge(CAMPAIGN, "haiku-replay", generation_hash, replay, batches=[0.048])
    write_judge(CAMPAIGN, "mimo", generation_hash, mimo)
    write_labels([label_line(k, v) for k, v in sorted(human.items())])
    return {
        "synthetic": synthetic,
        "keys": keys,
        "labeled": labeled,
        "human": human,
        "verdicts": {"winnow": winnow, "haiku": haiku, "mimo": mimo, "haiku-replay": replay},
        "tmp_path": tmp_path,
    }


def _run(*extra):
    from scripts.quality_bench.__main__ import main

    return main(["calibrate", "--campaign", CAMPAIGN, *extra])


def _sample(*extra, campaign=CAMPAIGN):
    from scripts.quality_bench.__main__ import main

    return main(["calibrate-sample", "--campaign", campaign, *extra])


def _report():
    return json.loads(paths.calibration_report_path(CAMPAIGN, ".json").read_text(encoding="utf-8"))


def _markdown():
    return paths.calibration_report_path(CAMPAIGN, ".md").read_text(encoding="utf-8")


def _log(command="calibrate", campaign=CAMPAIGN):
    return paths.log_path(campaign, command).read_text(encoding="utf-8")


def _outputs_exist():
    return [paths.calibration_report_path(CAMPAIGN, s).exists() for s in (".md", ".json")]


def _config(report, config_id):
    return next(c for c in report["configurations"] if c["id"] == config_id)


def _margin(report, margin):
    return next(m for m in report["cascade"]["margins"] if m["margin"] == margin)


def _assert_refused(code, *extra):
    assert _run(*extra) == code
    assert _outputs_exist() == [False, False]


# -- Calibration complète -------------------------------------------------------------------


def test_complete_calibration_matches_hand_computed_values(env):
    assert _run("--cascade-margins", MARGINS) == 0
    report = _report()
    n_units = len(env["keys"])
    assert report["units"]["total"] == n_units == 96
    assert report["units"]["qwen"] == 24 and report["units"]["non_qwen"] == 72
    assert report["labels"] == {
        "file_present": True,
        "lines": 20,
        "used": 20,
        "true": 10,
        "false": 10,
        "undecidable": 0,
        "to_label": 0,
        "other_campaigns": 0,
    }
    # haiku-replay ne sert qu'à la stabilité : ce n'est pas une configuration.
    assert [c["id"] for c in report["configurations"]] == [
        "winnow",
        "winnow-cascade-haiku",
        "mimo",
        "haiku",
    ]

    winnow = _config(report, "winnow")
    assert winnow["agreement"]["n"] == 20 and winnow["agreement"]["agree"] == 15
    assert winnow["agreement"]["rate"] == pytest.approx(0.75)
    low, high = wilson_interval(15, 20)
    assert winnow["agreement"]["ci_low"] == pytest.approx(low)
    assert winnow["agreement"]["ci_high"] == pytest.approx(high)
    assert winnow["agreement"]["lenient"] == 3 and winnow["agreement"]["severe"] == 2
    assert winnow["qwen_bias"]["qwen"]["rate"] == pytest.approx(0.7)
    assert winnow["qwen_bias"]["non_qwen"]["rate"] == pytest.approx(0.8)
    assert winnow["qwen_bias"]["bias"] == pytest.approx(-0.1)
    assert winnow["qwen_bias"]["qwen"]["lenient"] == 2
    assert winnow["cost"] == {
        "source": "judgments",
        "total_usd": 0.0,
        "lines": 96,
        "per_judgment_usd": 0.0,
        "projected_usd": 0.0,
    }
    assert winnow["counting"]["counting"]["n"] == 0  # critères synthétiques sans comptage

    haiku = _config(report, "haiku")
    assert haiku["agreement"]["agree"] == 17 and haiku["agreement"]["n"] == 20
    assert haiku["qwen_bias"]["bias"] == pytest.approx(0.1)
    assert haiku["cost"]["source"] == "batches"
    assert haiku["cost"]["total_usd"] == pytest.approx(0.048)
    assert haiku["cost"]["per_judgment_usd"] == pytest.approx(0.0005)
    assert haiku["cost"]["projected_usd"] == pytest.approx(5.5)

    mimo = _config(report, "mimo")
    assert mimo["coverage"] == {
        "units": 96,
        "lines": 95,
        "verdicts": 94,
        "errors": 1,
        "missing": 1,
        "share": pytest.approx(95 / 96),
    }
    assert mimo["agreement"]["n"] == 18 and mimo["agreement"]["agree"] == 14
    assert mimo["agreement"]["labeled_without_line"] == 1
    assert mimo["agreement"]["labeled_error"] == 1
    assert mimo["qwen_bias"]["bias"] == pytest.approx(1 - 5 / 9)
    assert mimo["cost"]["total_usd"] == pytest.approx(95 * 0.0002)
    assert mimo["cost"]["projected_usd"] == pytest.approx(2.2)

    # Cascade : marge 0 = Winnow seul, 0,1 = 4 escalades, 0,5 = tout à Haiku.
    zero, tenth, half = (_margin(report, m) for m in (0.0, 0.1, 0.5))
    assert zero["id"] == "winnow-cascade-haiku@0.50-0.50" and zero["escalated"] == 0
    assert zero["agreement"]["agree"] == 15 and zero["cost"]["total_usd"] == 0.0
    assert tenth["id"] == "winnow-cascade-haiku@0.40-0.60"
    assert tenth["escalated"] == 4 and tenth["escalated_share"] == pytest.approx(4 / 96)
    assert tenth["agreement"]["agree"] == 16 and tenth["qwen_bias"]["bias"] == pytest.approx(0)
    assert tenth["cost"]["total_usd"] == pytest.approx(0.002)
    assert tenth["cost"]["projected_usd"] == pytest.approx(0.002 / 96 * 11_000)
    assert half["id"] == "winnow-cascade-haiku@0.00-1.00" and half["escalated"] == 96
    assert half["agreement"]["agree"] == 17

    (stability,) = [s for s in report["stability"] if s["judge"] == "haiku"]
    assert stability["status"] == "computed"
    assert stability["n"] == 96 and stability["identical"] == 93 and stability["changed"] == 3
    assert stability["true_to_false"] == 2 and stability["false_to_true"] == 1
    statuses = {s["judge"]: s["status"] for s in report["stability"]}
    assert statuses == {"winnow": "replay_absent", "mimo": "replay_absent", "haiku": "computed"}
    assert report["proposal"] is None
    markdown = _markdown()
    for title in (
        "## Étiquettes",
        "## Configurations",
        "## Détail de l'accord",
        "## Cascade Winnow → Haiku",
        "## Stabilité au rejeu",
        "## Proposition",
    ):
        assert title in markdown
    assert "75,0" in markdown and "seuil non fixé" in markdown
    assert "−10,0" in markdown


def test_thresholds_give_admissible_configurations_and_a_proposal(env):
    assert (
        _run("--cascade-margins", MARGINS, "--min-agreement", "0.8", "--max-qwen-bias", "0.05") == 0
    )
    report = _report()
    proposal = report["proposal"]
    assert proposal["status"] == "proposed"
    assert proposal["id"] == "winnow-cascade-haiku@0.40-0.60"
    assert proposal["admissible"] == ["winnow-cascade-haiku@0.40-0.60"]
    haiku = _config(report, "haiku")
    assert haiku["admissibility"] == {"agreement": True, "qwen_bias": False, "admissible": False}
    assert "Proposition (accord maximal" in _markdown()
    assert "jamais un choix appliqué" in _markdown()


def test_one_threshold_alone_gives_no_recommendation(env):
    assert _run("--min-agreement", "0.8") == 0
    report = _report()
    assert report["proposal"] is None
    assert _config(report, "haiku")["admissibility"] == {
        "agreement": True,
        "qwen_bias": None,
        "admissible": None,
    }
    assert "seuil non fixé" in _markdown()


def test_default_margins_cover_zero_to_half(env):
    assert _run() == 0
    margins = [m["margin"] for m in _report()["cascade"]["margins"]]
    assert margins == pytest.approx([i / 100 for i in range(0, 51, 5)])
    assert _report()["settings"]["projected_judgments"] == 11_000


def test_reports_and_log_hold_no_question_text_nor_output(env):
    assert _run() == 0
    for text in (_markdown(), json.dumps(_report(), ensure_ascii=False), _log()):
        assert SECRET_QUESTION not in text
        assert SECRET_OUTPUT not in text
        assert "français" not in text  # texte des critères
    assert "created_at" not in _markdown()


def test_inputs_are_never_modified_and_nothing_is_written_elsewhere(env):
    before = {p: p.read_bytes() for p in paths.data_root().rglob("*") if p.is_file()}
    assert _run() == 0
    after = {p: p.read_bytes() for p in paths.data_root().rglob("*") if p.is_file()}
    for path, data in before.items():
        assert after[path] == data, path
    added = sorted(p.relative_to(paths.data_root()).as_posix() for p in set(after) - set(before))
    assert added == [
        f"campaigns/{CAMPAIGN}/calibration-report.json",
        f"campaigns/{CAMPAIGN}/calibration-report.md",
        f"campaigns/{CAMPAIGN}/log-calibrate.log",
    ]
    assert not paths.machine_lock_path().exists()


def test_two_cli_passes_are_byte_identical(env):
    """Deux processus distincts (graine de hachage différente) : rapports identiques."""
    config_dir = env["synthetic"].config_dir
    script = textwrap.dedent(
        f"""
        import sys
        from pathlib import Path
        from scripts.quality_bench.common import paths
        paths.campaign_config_path = lambda c: Path({str(config_dir)!r}) / f"{{c}}.yaml"
        from scripts.quality_bench.__main__ import main
        sys.exit(main(["calibrate", "--campaign", {CAMPAIGN!r}, "--min-agreement", "0.8",
                       "--max-qwen-bias", "0.05"]))
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
            [paths.calibration_report_path(CAMPAIGN, s).read_bytes() for s in (".md", ".json")]
        )
    assert outputs[0] == outputs[1]
    leftovers = [p.name for p in paths.campaign_dir(CAMPAIGN).iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


# -- Étiquettes -----------------------------------------------------------------------------


def test_without_labels_file_reports_cost_escalation_and_stability(env):
    paths.labels_path().unlink()
    assert _run("--min-agreement", "0.8", "--max-qwen-bias", "0.05") == 0
    report = _report()
    assert report["labels"]["file_present"] is False
    haiku = _config(report, "haiku")
    assert haiku["agreement"]["n"] == 0 and haiku["agreement"]["rate"] is None
    assert haiku["cost"]["total_usd"] == pytest.approx(0.048)
    assert report["cascade"]["status"] == "computed"
    assert report["stability"][-1]["status"] == "computed"
    assert report["proposal"]["status"] == "none_admissible"
    markdown = _markdown()
    assert "étiquettes absentes" in markdown.lower()


def test_only_null_labels_are_counted_to_label(env):
    write_labels([label_line(k, None) for k in env["keys"][:5]])
    assert _run() == 0
    labels = _report()["labels"]
    assert labels["to_label"] == 5 and labels["used"] == 0
    assert "étiquettes absentes" in _markdown()


def test_other_campaigns_and_undecidable_are_ignored_and_counted(env):
    other = "other-camp|model-9:4b|think_off|writing/writing-fr/0000|0|c1"
    records = [label_line(k, v) for k, v in sorted(env["human"].items())]
    records.append(label_line(other, True))
    records.append(label_line(env["keys"][-1], "undecidable"))
    records.append(label_line(env["keys"][-2], True, labeled_at="2026-10-12T09:30:00Z"))
    write_labels(records)
    assert _run() == 0
    labels = _report()["labels"]
    assert labels["other_campaigns"] == 1 and labels["undecidable"] == 1
    assert labels["used"] == 21


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("bom", "BOM"),
        ("no_newline", "sans fin de ligne"),
        ("schema", "labels.jsonl ligne 2 : hors schéma"),
        ("no_author", "labels.jsonl ligne 2 : hors schéma"),
        ("duplicate", "labels.jsonl ligne 2 : clé en double"),
        ("unknown", "labels.jsonl ligne 2 : clé"),
        ("garbage", "ligne 2 illisible"),
    ],
)
def test_invalid_labels_are_refused_with_the_line(env, case, message):
    keys = env["keys"]
    good = canonical_bytes(label_line(keys[0], True)) + b"\n"
    second = {
        "schema": label_line(keys[1], True, extra=1),
        "no_author": label_line(keys[1], True, author=None),
        "duplicate": label_line(keys[0], False),
        "unknown": label_line(
            f"{CAMPAIGN}|model-0:4b|think_off|writing/writing-fr/9999|0|c1", True
        ),
    }
    if case == "bom":
        raw = codecs.BOM_UTF8 + good
    elif case == "no_newline":
        raw = good + canonical_bytes(label_line(keys[1], True))
    elif case == "garbage":
        raw = good + b"{pas du json\n"
    else:
        raw = good + canonical_bytes(second[case]) + b"\n"
    write_labels([], raw=raw)
    _assert_refused(1)
    assert message in _log()


def test_copied_labels_todo_is_accepted_as_to_label(env):
    """Acceptation : ``calibrate-sample`` puis copie de ``labels-todo-<c>.jsonl`` sans rien
    remplir (``labels.jsonl`` encore absent) : code 0, tout est « à étiqueter »."""
    paths.labels_path().unlink()
    assert _sample("--size", "40", "--seed", "3") == 0
    shutil.copyfile(paths.labels_todo_path(CAMPAIGN, ".jsonl"), paths.labels_path())
    assert _run() == 0
    labels = _report()["labels"]
    assert labels["to_label"] == 40 and labels["used"] == 0


def test_labels_todo_appended_to_existing_labels_has_no_duplicate(env):
    """Le tirage écarte les clés déjà présentes dans ``labels.jsonl`` : ajout sans doublon ;
    un second tirage écarte aussi les clés « à étiqueter » déjà ajoutées."""
    assert _sample("--size", "40", "--seed", "3") == 0
    todo = paths.labels_todo_path(CAMPAIGN, ".jsonl").read_bytes()
    with open(paths.labels_path(), "ab") as handle:
        handle.write(todo)
    drawn = {r["key"] for r in read_jsonl(paths.labels_todo_path(CAMPAIGN, ".jsonl"))}
    assert not drawn & set(env["human"])  # clés déjà étiquetées écartées
    assert _run() == 0
    labels = _report()["labels"]
    assert labels["to_label"] == len(drawn) and labels["used"] == 20
    assert _sample("--size", "40", "--seed", "3") == 0
    second = {r["key"] for r in read_jsonl(paths.labels_todo_path(CAMPAIGN, ".jsonl"))}
    assert second and not second & {r["key"] for r in read_jsonl(paths.labels_path())}
    assert "déjà présentes dans labels.jsonl" in _log("calibrate-sample")


def test_impossible_labeled_at_is_refused_with_the_line(env):
    keys = env["keys"]
    write_labels([label_line(keys[0], True), label_line(keys[1], False, labeled_at="2026-13-45")])
    _assert_refused(1)
    assert "labels.jsonl ligne 2 : labeled_at 2026-13-45" in _log()
    write_labels([label_line(keys[0], True, labeled_at="2026-10-12T25:00:00Z")])
    _assert_refused(1)
    assert "labels.jsonl ligne 1 : labeled_at" in _log()


# -- Juges ----------------------------------------------------------------------------------


def test_absent_winnow_makes_the_cascade_not_simulable(env):
    shutil.rmtree(paths.judgment_dir(CAMPAIGN, "winnow"))
    assert _run() == 0
    report = _report()
    assert _config(report, "winnow")["status"] == "absent"
    assert report["cascade"]["status"] == "not_simulable"
    assert report["cascade"]["missing"] == ["winnow"]
    assert "Cascade non simulable" in _markdown()


def test_directory_without_manifest_is_absent(env):
    paths.judgment_manifest_path(CAMPAIGN, "mimo").unlink()
    paths.judgment_path(CAMPAIGN, "mimo").unlink()
    assert _run() == 0
    assert _config(_report(), "mimo")["status"] == "absent"


def test_judgment_lines_without_manifest_are_refused(env):
    paths.judgment_manifest_path(CAMPAIGN, "mimo").unlink()
    _assert_refused(1)
    assert "judgment-mimo : judgment.jsonl sans manifest.json" in _log()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("manifest", HASH_A, "produite par un autre manifeste"),
        ("judge", "mimo", "juge mimo au lieu de haiku"),
        ("key", "msgbatch_0|submitted", "clé en double"),
    ],
)
def test_incoherent_batch_line_is_refused(env, field, value, message):
    path = paths.batches_path(CAMPAIGN, "haiku")
    lines = read_jsonl(path)
    lines[2][field] = value
    rewrite_jsonl(path, lines)
    _assert_refused(1)
    assert "judgment-haiku/batches.jsonl ligne 3" in _log()
    assert message in _log()


def test_discordant_judge_is_excluded_and_reported(env):
    path = paths.judgment_manifest_path(CAMPAIGN, "mimo")
    document = json.loads(path.read_text(encoding="utf-8"))
    document["blocking"]["generation_manifest"] = HASH_B
    path.write_bytes(pretty_bytes(document))
    assert _run() == 0
    report = _report()
    assert _config(report, "mimo")["status"] == "discordant"
    assert "agreement" not in _config(report, "mimo")
    assert "discordant" in _markdown()
    assert "autre manifeste de génération" in _log()


def test_other_judges_follow_in_alphabetical_order(env):
    generation_hash = env["synthetic"].generation_hash
    some = {env["keys"][0]: (True, None, 0.0)}
    write_judge(CAMPAIGN, "zeta", generation_hash, some)
    write_judge(CAMPAIGN, "decider", generation_hash, some)
    assert _run() == 0
    order = [c["id"] for c in _report()["configurations"]]
    assert order == ["winnow", "winnow-cascade-haiku", "mimo", "haiku", "decider", "zeta"]


def test_replay_with_other_settings_is_not_comparable(env):
    generation_hash = env["synthetic"].generation_hash
    write_judge(
        CAMPAIGN,
        "haiku-replay",
        generation_hash,
        env["verdicts"]["haiku-replay"],
        settings={"effort": "medium"},
    )
    assert _run() == 0
    (stability,) = [s for s in _report()["stability"] if s["judge"] == "haiku"]
    assert stability["status"] == "not_comparable"
    assert stability["field"] == "settings.effort"
    assert "rejeu non comparable (champ `settings.effort`)" in _markdown()


def test_replay_with_other_template_is_not_comparable(env):
    write_judge(
        CAMPAIGN,
        "haiku-replay",
        env["synthetic"].generation_hash,
        env["verdicts"]["haiku-replay"],
        prompt_template_hash=HASH_A,
    )
    assert _run() == 0
    (stability,) = [s for s in _report()["stability"] if s["judge"] == "haiku"]
    assert stability["field"] == "prompt_template_hash"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("manifest", HASH_A, "produite par un autre manifeste"),
        ("judge", "mimo", "juge mimo au lieu de haiku"),
        ("key", "unknown", "clé incohérente"),
    ],
)
def test_incoherent_judgment_line_is_refused(env, field, value, message):
    path = paths.judgment_path(CAMPAIGN, "haiku")
    lines = read_jsonl(path)
    lines[2][field] = value
    rewrite_jsonl(path, lines)
    _assert_refused(1)
    assert "judgment-haiku/judgment.jsonl ligne 3" in _log()
    assert message in _log()


def test_judgment_of_an_unknown_unit_is_refused(env):
    path = paths.judgment_path(CAMPAIGN, "haiku")
    lines = read_jsonl(path)
    key = f"{CAMPAIGN}|model-0:4b|think_off|writing/writing-fr/0000|0|c9"
    lines[0].update(key=key, criterion="c9")
    rewrite_jsonl(path, lines)
    _assert_refused(1)
    assert "inconnue des unités jugeables" in _log()


def test_duplicate_judgment_key_is_refused(env):
    path = paths.judgment_path(CAMPAIGN, "haiku")
    lines = read_jsonl(path)
    rewrite_jsonl(path, [*lines, lines[0]])
    _assert_refused(1)
    assert "clé en double" in _log()


def test_judgment_manifest_of_another_judge_is_refused(env):
    path = paths.judgment_manifest_path(CAMPAIGN, "mimo")
    document = json.loads(path.read_text(encoding="utf-8"))
    document["blocking"]["judge"]["id"] = "haiku"
    path.write_bytes(pretty_bytes(document))
    _assert_refused(1)
    assert "manifeste d'un autre juge" in _log()


# -- Configuration --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        ("--min-agreement", "1.5"),
        ("--max-qwen-bias", "-0.1"),
        ("--cascade-margins", "0,0.6"),
        ("--cascade-margins", "0.125"),
        ("--cascade-margins", "x"),
        ("--projected-judgments", "0"),
    ],
)
def test_out_of_bounds_settings_exit_2(env, extra):
    _assert_refused(2, *extra)


def test_missing_campaign_configuration_exits_2(env):
    (env["synthetic"].config_dir / f"{CAMPAIGN}.yaml").unlink()
    _assert_refused(2)
    assert "configuration de campagne absente" in _log()


# -- Échantillon ----------------------------------------------------------------------------


@pytest.fixture
def sample_env(tmp_path, monkeypatch):
    """Quatre modèles dont un Qwen, cinq seeds : 60 réponses de rédaction par modèle."""
    return make_campaign(
        tmp_path,
        monkeypatch,
        campaign="sample-test",
        n_models=4,
        think_off_only=(),
        k=5,
        families=FAMILIES,
    )


def _todo(campaign="sample-test"):
    return (
        paths.labels_todo_path(campaign, ".jsonl").read_bytes(),
        paths.labels_todo_path(campaign, ".md").read_bytes(),
    )


def test_sample_splits_half_qwen_one_criterion_per_response(sample_env):
    assert _sample("--size", "100", "--seed", "9", campaign="sample-test") == 0
    lines = read_jsonl(paths.labels_todo_path("sample-test", ".jsonl"))
    assert len(lines) == 100
    for line in lines:
        assert validate(line) == "qb.label/1"
        assert line["label"] is None and line["author"] is None and line["note"] is None
    models = [line["key"].split("|")[1] for line in lines]
    assert models.count("model-0:4b") == 50
    assert [models.count(f"model-{i}:4b") for i in (1, 2, 3)] == [17, 17, 16]
    responses = [line["key"].rsplit("|", 1)[0] for line in lines]
    assert len(set(responses)) == 100  # au plus un critère par réponse
    first = _todo()
    assert _sample("--size", "100", "--seed", "9", campaign="sample-test") == 0
    assert _todo() == first
    assert _sample("--size", "100", "--seed", "10", campaign="sample-test") == 0
    assert _todo() != first


def test_sample_markdown_holds_texts_without_model_or_key(sample_env):
    assert _sample("--size", "12", "--seed", "1", campaign="sample-test") == 0
    jsonl, markdown_bytes = _todo()
    markdown = markdown_bytes.decode("utf-8")
    lines = read_jsonl(paths.labels_todo_path("sample-test", ".jsonl"))
    assert markdown.count("\n## Item ") == len(lines) == 12
    assert SECRET_QUESTION in markdown and SECRET_OUTPUT in markdown
    assert "model-" not in markdown and "sample-test|" not in markdown
    first = lines[0]["key"].split("|")
    assert f"## Item 1\n\n- Question : `{first[3]}`" in markdown
    log = _log("calibrate-sample", "sample-test")
    assert SECRET_QUESTION not in log and SECRET_OUTPUT not in log
    assert SECRET_QUESTION.encode("utf-8") not in jsonl
    report_dir = paths.campaign_dir("sample-test")
    assert not (report_dir / "calibration-report.md").exists()


def test_sample_with_too_few_units_takes_the_whole_model_and_warns(sample_env):
    assert _sample("--size", "400", "--seed", "2", campaign="sample-test") == 0
    lines = read_jsonl(paths.labels_todo_path("sample-test", ".jsonl"))
    models = [line["key"].split("|")[1] for line in lines]
    assert models.count("model-0:4b") == 120  # quota 200, tout le modèle
    assert "quota de 200 non atteint" in _log("calibrate-sample", "sample-test")


def test_sample_is_reduced_to_keys_with_a_verdict_of_every_complete_judge(sample_env):
    keys = unit_keys(sample_env)
    some = dict.fromkeys(keys[::3], (True, 0.9, 0.0))
    winnow = {**dict.fromkeys(keys, (None, None, 0.0)), **some}  # error hors de some
    write_judge("sample-test", "winnow", sample_env.generation_hash, winnow)
    write_judge(
        "sample-test", "haiku-replay", sample_env.generation_hash, {keys[1]: (True, None, 0)}
    )
    assert _sample("--size", "30", "--seed", "4", campaign="sample-test") == 0
    lines = read_jsonl(paths.labels_todo_path("sample-test", ".jsonl"))
    assert {line["key"] for line in lines} <= set(some)


def test_sample_without_judgeable_unit_exits_1(tmp_path, monkeypatch):
    synthetic = make_campaign(tmp_path, monkeypatch, campaign="empty-test", n_models=1)
    for line in synthetic.generation:
        if line["usage"] == "writing":
            line["status"] = "error"
    synthetic.write_generation()
    assert _sample(campaign="empty-test") == 1
    assert not paths.labels_todo_path("empty-test", ".jsonl").exists()
    assert not paths.labels_todo_path("empty-test", ".md").exists()
    assert "aucune unité jugeable" in _log("calibrate-sample", "empty-test")


def test_sample_size_below_one_exits_2(sample_env):
    assert _sample("--size", "0", campaign="sample-test") == 2
    assert not paths.labels_todo_path("sample-test", ".jsonl").exists()


# -- Reprise des règles du juge -------------------------------------------------------------


def test_units_and_texts_match_the_judge_phase(env):
    """``judge/units.py`` et ``judge/prompt.py`` ne sont pas importables depuis ``report/`` :
    mêmes unités, même consigne, même réponse."""
    from scripts.quality_bench.judge import prompt, units
    from scripts.quality_bench.report.inputs import load_inputs

    judged = units.load_inputs(CAMPAIGN)
    inputs = load_inputs(CAMPAIGN, partial=True)
    ours, records = calibration.read_units(inputs)
    assert [u.key for u in ours] == [u.key for u in judged.units]
    for unit in judged.units:
        question = inputs.questions[unit.question_id]
        assert calibration.render_instruction(question["messages"]) == unit.instruction
        output = records[unit.generation_key]["output"]
        assert calibration.final_answer(output) == unit.answer
    for output in (
        [],
        [{"role": "user", "content": "x"}],
        [{"role": "assistant", "content": None}, {"role": "tool", "content": "y"}],
        [{"role": "assistant", "content": "a"}, {"role": "assistant", "content": "b"}],
    ):
        assert calibration.final_answer(output) == prompt.final_answer(output)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    assert calibration.render_instruction(messages) == prompt.render_instruction(messages)


def test_criteria_checked_by_code_are_not_calibration_units(env):
    """Un critère à ``check`` est vérifié par le code : ni jugé, ni étiqueté, ni calibré."""
    from scripts.quality_bench.report.inputs import load_inputs

    inputs = load_inputs(CAMPAIGN, partial=True)
    before, _ = calibration.read_units(inputs)
    assert any(unit.criterion == "c1" for unit in before)
    check = {"count": "words", "op": ">=", "n": 1}
    for question in inputs.questions.values():
        if question["criteria"]:
            question["criteria"][0] = {**question["criteria"][0], "check": check}
    after, _ = calibration.read_units(inputs)
    assert after and not any(unit.criterion == "c1" for unit in after)
    assert len(after) < len(before)


# -- Échantillon : tirages successifs et juges partiels -------------------------------------


def test_filled_labels_todo_blocks_a_new_draw(sample_env):
    assert _sample("--size", "10", "--seed", "1", campaign="sample-test") == 0
    path = paths.labels_todo_path("sample-test", ".jsonl")
    lines = read_jsonl(path)
    lines[3].update(label=True, author="Anaël", labeled_at="2026-10-12")
    rewrite_jsonl(path, lines)
    before = _todo()
    assert _sample("--size", "10", "--seed", "2", campaign="sample-test") == 1
    assert _todo() == before
    assert "contient déjà des étiquettes (ligne 4" in _log("calibrate-sample", "sample-test")


def test_todo_labeled_on_last_line_without_newline_blocks_a_new_draw(sample_env):
    assert _sample("--size", "10", "--seed", "1", campaign="sample-test") == 0
    path = paths.labels_todo_path("sample-test", ".jsonl")
    lines = read_jsonl(path)
    lines[-1].update(label=False, author="Anaël", labeled_at="2026-10-12")
    raw = b"\n".join(canonical_bytes(line) for line in lines)  # éditeur sans fin de ligne finale
    path.write_bytes(raw)
    assert _sample("--size", "10", "--seed", "2", campaign="sample-test") == 1
    assert path.read_bytes() == raw
    assert "sans fin de ligne" in _log("calibrate-sample", "sample-test")


def test_todo_with_author_but_no_label_blocks_a_new_draw(sample_env):
    assert _sample("--size", "10", "--seed", "1", campaign="sample-test") == 0
    path = paths.labels_todo_path("sample-test", ".jsonl")
    lines = read_jsonl(path)
    lines[1].update(note="à revoir")
    rewrite_jsonl(path, lines)
    assert _sample("--size", "10", "--seed", "2", campaign="sample-test") == 1
    assert "contient déjà des étiquettes (ligne 2" in _log("calibrate-sample", "sample-test")


def test_all_units_already_labeled_says_so(sample_env):
    write_labels([label_line(k, True) for k in unit_keys(sample_env)])
    assert _sample("--size", "10", "--seed", "1", campaign="sample-test") == 1
    assert "toutes déjà présentes dans labels.jsonl" in _log("calibrate-sample", "sample-test")


@pytest.mark.parametrize("value", ["2026-10-12T24:00:00Z", "2026-02-30", "2026-10-12T23:59:60Z"])
def test_unreal_labeled_at_is_refused_on_every_python(value):
    with pytest.raises(calibration.ReportError, match="pas une date réelle"):
        calibration._check_labeled_at(value, "ligne 1")
    calibration._check_labeled_at("2026-10-12T23:59:59Z", "ligne 1")


def test_partial_judge_is_ignored_and_error_keys_are_excluded(sample_env):
    keys = unit_keys(sample_env)
    qwen_keys = [k for k in keys if k.split("|")[1] == "model-0:4b"]
    winnow = dict.fromkeys(keys, (True, 0.9, 0.0))
    errored = qwen_keys[5]
    winnow[errored] = (None, None, 0.0)
    write_judge("sample-test", "winnow", sample_env.generation_hash, winnow)
    # MiMo arrêté par son plafond, dans l'ordre des clés : seul le premier modèle est jugé.
    mimo = dict.fromkeys(qwen_keys, (True, None, 0.0))
    write_judge("sample-test", "mimo", sample_env.generation_hash, mimo)
    assert _sample("--size", "400", "--seed", "4", campaign="sample-test") == 0
    drawn = [r["key"] for r in read_jsonl(paths.labels_todo_path("sample-test", ".jsonl"))]
    assert errored not in drawn
    assert sum(1 for k in drawn if k.split("|")[1] == "model-0:4b") == 119
    assert sum(1 for k in drawn if k.split("|")[1] != "model-0:4b") == 200
    log = _log("calibrate-sample", "sample-test")
    assert "judgment-mimo partiel (120 unités publiques sur 480)" in log


# -- Question privée et critère de comptage, de bout en bout --------------------------------

PRIVATE_TEXT = "Consigne privée témoin 51e0"
COUNTING = "Le texte compte-t-il exactement trois paragraphes ?"


@pytest.fixture
def mixed_env(tmp_path, monkeypatch):
    """Rédaction 0001 privée ; 0000 avec un critère de comptage (c1)."""
    return make_campaign(
        tmp_path,
        monkeypatch,
        campaign="mixed-test",
        n_models=4,
        think_off_only=(),
        families=FAMILIES,
        question_overrides={
            "writing/writing-fr/0001": {
                "private": True,
                "license": "private",
                "messages": [{"role": "user", "content": PRIVATE_TEXT}],
            },
            "writing/writing-fr/0000": {
                "criteria": [
                    {"id": "c1", "question": COUNTING},
                    {"id": "c2", "question": "Le texte reste-t-il en français ?"},
                ]
            },
        },
    )


def _mixed_report():
    from scripts.quality_bench.__main__ import main

    assert main(["calibrate", "--campaign", "mixed-test"]) == 0
    path = paths.calibration_report_path("mixed-test", ".json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_private_question_is_never_sampled_but_counted(mixed_env):
    assert _sample("--size", "400", "--seed", "1", campaign="mixed-test") == 0
    drawn = [r["key"] for r in read_jsonl(paths.labels_todo_path("mixed-test", ".jsonl"))]
    assert drawn and not any("|writing/writing-fr/0001|" in k for k in drawn)
    markdown = paths.labels_todo_path("mixed-test", ".md").read_text(encoding="utf-8")
    assert PRIVATE_TEXT not in markdown
    # 0001 en think_off et think_on : 4 modèles × 2 pistes × 2 critères.
    assert _mixed_report()["units"]["private"] == 16


def test_counting_criteria_agreement_end_to_end(mixed_env):
    keys = unit_keys(mixed_env)
    counting = [k for k in keys if "|writing/writing-fr/0000|" in k and k.endswith("|c1")]
    assert len(counting) == 8
    shutil.rmtree(paths.judgment_dir("mixed-test", "haiku"))
    haiku = dict.fromkeys(keys, (True, None, 0.0))
    haiku[counting[0]] = (False, None, 0.0)
    write_judge("mixed-test", "haiku", mixed_env.generation_hash, haiku)
    write_labels([label_line(k, True) for k in counting])
    report = _mixed_report()
    assert report["units"]["counting"] == 8
    block = _config(report, "haiku")["counting"]
    assert block["counting"]["n"] == 8 and block["counting"]["agree"] == 7
    assert block["other"]["n"] == 0
