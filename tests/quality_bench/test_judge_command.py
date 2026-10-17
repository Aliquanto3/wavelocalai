"""Commande ``judge`` avec le juge local ``winnow`` (contrat ``/v1/systemone``) sur une campagne
synthétique : lignes par critère, reprise, refus au lancement, pannes, manifeste et passage de
``grade`` de ``awaiting_judgment`` à ``ok`` (AD-12, AD-13, AD-16)."""

from __future__ import annotations

import json

import httpx2
import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.jsonl import read_jsonl, rewrite_jsonl
from scripts.quality_bench.common.manifest import blocking_hash
from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.judge import commands

from .judge_fakes import (
    ANSWER_MARK,
    CAMPAIGN,
    PROBABILITIES,
    SET_ID,
    FakeServer,
    build_campaign,
    systemone_answers,
)

JUDGE_ID = "winnow"


@pytest.fixture
def _reset_logging():
    yield
    from scripts.quality_bench.common.logs import setup_logging

    setup_logging("test", None)


@pytest.fixture
def server(monkeypatch, _reset_logging):
    fake = FakeServer()
    monkeypatch.setattr(commands, "make_transport", fake.transport)
    monkeypatch.setattr(commands, "SLEEP", lambda seconds: None)
    return fake


def _run(judge=JUDGE_ID, *extra):
    from scripts.quality_bench.__main__ import main

    return main(["judge", "--campaign", CAMPAIGN, "--judge", judge, *extra])


def _lines():
    return read_jsonl(paths.judgment_path(CAMPAIGN, JUDGE_ID))


def test_winnow_writes_one_line_per_criterion(server):
    campaign = build_campaign()
    assert _run() == 0
    lines = _lines()
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    manifest_path = paths.judgment_manifest_path(CAMPAIGN, JUDGE_ID)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate(manifest)
    assert manifest["phase"] == "judgment"
    assert manifest["blocking"]["generation_manifest"] == campaign["generation_hash"]
    assert manifest["blocking"]["judge"]["id"] == JUDGE_ID
    assert manifest["blocking"]["judge"]["model"] == "winnow-e4b"
    for line in lines:
        validate(line)
        assert line["manifest"] == blocking_hash(manifest)
        assert line["probability"] == PROBABILITIES[line["criterion"]]
        assert line["verdict"] is (line["probability"] >= 0.5)
        assert line["cost_usd"] == 0 and line["attempts"] == 1 and line["error"] is None
    # Une requête par ligne de génération, tous ses critères en questions noul.
    bodies = server.systemone_bodies()
    assert len(bodies) == len(campaign["writing_keys"])
    for body in bodies:
        assert [q["type"] for q in body["questions"]] == ["noul"] * 4
        assert [q["id"] for q in body["questions"]] == ["c1", "c2", "c3", "c4"]
        assert body["model"] == "winnow-e4b"
        assert ANSWER_MARK in body["messages"][-1]["content"]  # réponse verbatim
        assert "user : Question synthétique writing-fr" in body["messages"][-1]["content"]
    # Tokens de la requête répartis sur ses lignes, somme conservée.
    per_request = [x["tokens"] for x in lines if x["generation_key"] == campaign["writing_keys"][0]]
    assert sum(t["input"] for t in per_request) == 801
    assert sum(t["output"] for t in per_request) == 5
    # /api/ps avant tout appel, keep_alive: 0 à la fin.
    paths_seen = [path for path, _ in server.requests]
    assert paths_seen[0] == "/api/ps"
    assert server.unloads == ["winnow-e4b"]
    log = paths.log_path(CAMPAIGN, "judge").read_text(encoding="utf-8")
    assert ANSWER_MARK not in log and "Question synthétique" not in log
    assert "Critère synthétique" not in log


def test_grade_reads_winnow_verdicts(server, tmp_path, monkeypatch):
    """Critère d'acceptation : la rédaction passe de awaiting_judgment à ok (score attendu)."""
    campaign = build_campaign()
    config_dir = tmp_path / "campaigns_yaml"
    config_dir.mkdir()
    yaml_text = (
        f"set: {SET_ID}\n"
        "generation:\n"
        "  models:\n"
        '    - {tag: "m:1b", family: qwen, tracks: [think_off], think_off: false, '
        "num_ctx_max: 32768}\n"
        f"grading:\n  judge: {JUDGE_ID}\n"
    )
    (config_dir / f"{CAMPAIGN}.yaml").write_text(yaml_text, encoding="utf-8")
    monkeypatch.setattr(paths, "campaign_config_path", lambda c: config_dir / f"{c}.yaml")
    from scripts.quality_bench.__main__ import main

    assert main(["grade", "--campaign", CAMPAIGN]) == 0
    before = {r["key"]: r for r in read_jsonl(paths.grading_path(CAMPAIGN))}
    assert all(before[key]["status"] == "awaiting_judgment" for key in campaign["writing_keys"])

    assert _run() == 0
    assert main(["grade", "--campaign", CAMPAIGN]) == 0
    after = {r["key"]: r for r in read_jsonl(paths.grading_path(CAMPAIGN))}
    judgment_hash = blocking_hash(
        json.loads(paths.judgment_manifest_path(CAMPAIGN, JUDGE_ID).read_text(encoding="utf-8"))
    )
    for key in campaign["writing_keys"]:
        assert (after[key]["status"], after[key]["score"], after[key]["success"]) == (
            "ok",
            0.75,
            None,
        )
        assert after[key]["judgment_manifest"] == judgment_hash
    truncated = [r for r in after.values() if r["status"] == "truncated"]
    assert truncated and truncated[0]["judgment_manifest"] is None


def test_resume_judges_only_missing_keys(server):
    campaign = build_campaign(writing=3)
    stop_path = paths.judgment_stop_path(CAMPAIGN, JUDGE_ID)
    # STOP posé pendant la première requête : elle se termine et s'écrit, puis arrêt propre.
    server.on_systemone = lambda count: stop_path.touch() if count == 1 else None
    assert _run() == 0
    first = _lines()
    assert len(first) == 4 and not stop_path.exists()
    assert len(server.systemone_bodies()) == 1
    server.on_systemone = None
    assert _run() == 0
    lines = _lines()
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    assert len({line["key"] for line in lines}) == len(lines)
    assert len(server.systemone_bodies()) == 3  # 1 + 2 : aucune clé rejugée
    assert _run() == 0
    assert len(server.systemone_bodies()) == 3
    assert server.unloads == ["winnow-e4b"] * 3


def test_generation_model_loaded_refuses_launch(server):
    build_campaign()
    server.loaded = ["qwen3.5:4b"]
    assert _run() == 1
    assert not paths.judgment_dir(CAMPAIGN, JUDGE_ID).exists()
    assert server.systemone_bodies() == [] and server.unloads == []


def test_foreign_gpu_process_refuses_local_judge(server, monkeypatch, capsys):
    from scripts.quality_bench.common import gpu

    from .gpu_fakes import LLAMA_SERVER_LINE, FakeSmi

    build_campaign()
    monkeypatch.setattr(gpu, "RUN", FakeSmi(apps=[LLAMA_SERVER_LINE], used=[6187]))
    assert _run() == 1
    assert "llama-server.exe" in capsys.readouterr().err
    assert not paths.judgment_dir(CAMPAIGN, JUDGE_ID).exists()
    assert server.systemone_bodies() == []


def test_unreadable_ps_still_applies_the_gpu_process_rule(server, monkeypatch):
    from scripts.quality_bench.common import gpu
    from scripts.quality_bench.judge import commands as judge_commands
    from scripts.quality_bench.ollama.client import OllamaUnavailableError

    from .gpu_fakes import LLAMA_SERVER_LINE, FakeSmi

    class DeadPs:
        def ps(self):
            raise OllamaUnavailableError("injoignable")

    build_campaign()
    monkeypatch.setattr(gpu, "RUN", FakeSmi(apps=[LLAMA_SERVER_LINE], used=[6187]))
    with pytest.raises(judge_commands.JudgeLaunchError, match="llama-server"):
        judge_commands.check_judge_gpu(CAMPAIGN, DeadPs())
    monkeypatch.setattr(gpu, "RUN", FakeSmi(apps=[], used=[6187]))
    result = judge_commands.check_judge_gpu(CAMPAIGN, DeadPs())  # règle de mémoire sautée
    assert result["used_mib"] == 6187


def test_gpu_check_result_is_in_the_judgment_manifest(server):
    build_campaign()
    assert _run() == 0
    manifest = json.loads(
        paths.judgment_manifest_path(CAMPAIGN, JUDGE_ID).read_text(encoding="utf-8")
    )
    assert manifest["informative"]["checklist"]["gpu_check"]["enabled"] is True


def test_judge_model_loaded_is_accepted(server):
    build_campaign()
    server.loaded = ["winnow-e4b:latest"]
    assert _run() == 0


def test_ollama_unreachable_only_warns(server):
    campaign = build_campaign()
    server.ollama_down = True
    assert _run() == 0
    assert sorted(line["key"] for line in _lines()) == campaign["expected_keys"]


def test_service_down_writes_no_line_and_exits_1(server):
    build_campaign()

    def down(body, fake):
        return httpx2.ConnectError("connexion refusée")

    server.responder = down
    assert _run() == 1
    assert _lines() == []
    assert len(server.systemone_bodies()) == 3  # max_attempts
    assert server.unloads == ["winnow-e4b"]  # déchargement à toute sortie


def test_server_error_is_transient(server):
    build_campaign()
    server.responder = lambda body, fake: httpx2.Response(503, json={"error": "surcharge"})
    assert _run() == 1
    assert _lines() == []


def test_unreadable_answer_writes_error_lines(server):
    campaign = build_campaign(writing=1)
    server.responder = lambda body, fake: {"answers": [{"id": "c1", "noul": 2.0}], "usage": {}}
    assert _run() == 0
    lines = _lines()
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    for line in lines:
        assert line["verdict"] is None and line["probability"] is None
        assert line["attempts"] == 3 and "illisible" in line["error"]


def test_client_error_is_a_unit_failure(server):
    build_campaign(writing=1)
    server.responder = lambda body, fake: httpx2.Response(400, json={"error": "trop long"})
    assert _run() == 0
    assert all(line["error"] == "requête refusée (statut 400)" for line in _lines())


def test_answers_matched_by_position_without_id(server):
    build_campaign(writing=1)

    def positional(body, fake):
        return {"answers": [{"type": "noul", "noul": 0.9}] * len(body["questions"])}

    server.responder = positional
    assert _run() == 0
    assert all(line["verdict"] is True for line in _lines())


def test_manifest_mismatch_refuses_resume(server):
    build_campaign()
    assert _run() == 0
    manifest_path = paths.judgment_manifest_path(CAMPAIGN, JUDGE_ID)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["blocking"]["judge"]["prompt_template_hash"] = "f" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert _run() == 1


def test_null_endpoint_exits_2(server):
    build_campaign()
    assert _run("decider", "--max-cost-usd", "1") == 2
    assert not paths.judgment_dir(CAMPAIGN, "decider").exists()


def test_unknown_judge_exits_2(server):
    build_campaign()
    assert _run("inconnu") == 2


def test_inconsistent_generation_exits_1(server):
    campaign = build_campaign()
    lines = [dict(line) for line in campaign["lines"]]
    lines[0]["manifest"] = "e" * 64
    rewrite_jsonl(paths.generation_path(CAMPAIGN), lines)
    assert _run() == 1
    assert not paths.judgment_dir(CAMPAIGN, JUDGE_ID).exists()


def test_set_hash_mismatch_exits_1(server):
    build_campaign()
    paths.set_tracks_path(SET_ID).write_text('{"think_off": [], "think_on": []}', encoding="utf-8")
    assert _run() == 1


def test_stop_present_at_launch_is_removed(server):
    campaign = build_campaign()
    stop_path = paths.judgment_stop_path(CAMPAIGN, JUDGE_ID)
    stop_path.parent.mkdir(parents=True)
    stop_path.touch()
    assert _run() == 0
    assert sorted(line["key"] for line in _lines()) == campaign["expected_keys"]


@pytest.mark.parametrize("status", [401, 403, 404])
def test_missing_model_or_path_stops_without_lines(server, status):
    """Modèle non importé, chemin ou clé refusés : panne de configuration, aucune ligne."""
    build_campaign(writing=1)
    server.responder = lambda body, fake: httpx2.Response(status, json={"error": "introuvable"})
    assert _run() == 1
    assert _lines() == []
    assert len(server.systemone_bodies()) == 1  # sans nouvel essai


def test_retry_then_success_counts_attempts(server):
    build_campaign(writing=1)
    calls = {"n": 0}

    def flaky(body, fake):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx2.Response(503, json={"error": "surcharge"})
        return systemone_answers(body)

    server.responder = flaky
    assert _run() == 0
    assert {line["attempts"] for line in _lines()} == {2}


def _write_campaign_yaml(tmp_path, monkeypatch):
    config_dir = tmp_path / "campaigns_yaml"
    config_dir.mkdir()
    (config_dir / f"{CAMPAIGN}.yaml").write_text(
        f"set: {SET_ID}\n"
        "generation:\n"
        "  models:\n"
        '    - {tag: "m:1b", family: qwen, tracks: [think_off], think_off: false, '
        "num_ctx_max: 32768}\n"
        f"grading:\n  judge: {JUDGE_ID}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "campaign_config_path", lambda c: config_dir / f"{c}.yaml")


def test_criteria_checked_by_code_are_never_submitted_to_the_judge(server):
    campaign = build_campaign(checked=True)
    assert _run() == 0
    keys = sorted(line["key"] for line in _lines())
    assert keys == campaign["expected_keys"] and keys
    assert not any(key.endswith("|c1") for key in keys)
    for body in server.systemone_bodies():
        assert [q["id"] for q in body["questions"]] == ["c2", "c3", "c4"]


def test_grade_combines_code_and_judge_verdicts(server, tmp_path, monkeypatch):
    campaign = build_campaign(checked=True)
    _write_campaign_yaml(tmp_path, monkeypatch)
    from scripts.quality_bench.__main__ import main

    assert main(["grade", "--campaign", CAMPAIGN]) == 0
    before = {r["key"]: r for r in read_jsonl(paths.grading_path(CAMPAIGN))}
    assert all(before[key]["status"] == "awaiting_judgment" for key in campaign["writing_keys"])
    assert _run() == 0
    assert main(["grade", "--campaign", CAMPAIGN]) == 0
    after = {r["key"]: r for r in read_jsonl(paths.grading_path(CAMPAIGN))}
    for key in campaign["writing_keys"]:
        # c1 (code : 4 mots, vrai) + c2 vrai, c3 faux, c4 vrai (juge) : 3 sur 4.
        assert (after[key]["status"], after[key]["score"]) == ("ok", 0.75)
        assert after[key]["grader"] == "judge_criteria@3"


def test_grade_ignores_a_stale_judgment_of_a_criterion_checked_by_code(
    server, tmp_path, monkeypatch
):
    campaign = build_campaign(checked=True)
    _write_campaign_yaml(tmp_path, monkeypatch)
    assert _run() == 0
    lines = _lines()
    # Verdict périmé (faux) sur c1, vérifié par le code : ignoré, compté au journal.
    forged = {
        **lines[0],
        "criterion": "c1",
        "key": f"{lines[0]['generation_key']}|c1",
        "verdict": False,
    }
    rewrite_jsonl(paths.judgment_path(CAMPAIGN, JUDGE_ID), [forged, *lines])
    from scripts.quality_bench.__main__ import main

    assert main(["grade", "--campaign", CAMPAIGN]) == 0
    log = paths.log_path(CAMPAIGN, "grade").read_text(encoding="utf-8")
    assert "1 verdicts ignorés sur des critères vérifiés par le code" in log
    after = {r["key"]: r for r in read_jsonl(paths.grading_path(CAMPAIGN))}
    for key in campaign["writing_keys"]:
        assert (after[key]["status"], after[key]["score"]) == ("ok", 0.75)  # c1 par le code


def test_ps_entry_without_name_is_ignored(server, monkeypatch):
    build_campaign(writing=1)

    def with_nameless(request):
        if request.url.path == "/api/ps":
            return httpx2.Response(200, json={"models": [{"size": 1}]})
        return server(request)

    monkeypatch.setattr(commands, "make_transport", lambda: httpx2.MockTransport(with_nameless))
    assert _run() == 0
    assert len(_lines()) == 4
