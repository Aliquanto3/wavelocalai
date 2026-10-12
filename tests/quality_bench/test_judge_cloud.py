"""Juges cloud (AD-15, AD-16) : Haiku par Message Batches (faux client), MiMo par le SDK
``openai`` réel sur ``httpx2.MockTransport``. Aucun réseau, aucune vraie clé."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx2
import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.jsonl import read_jsonl
from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.judge import commands, mimo

from .judge_fakes import (
    ANSWER_MARK,
    CAMPAIGN,
    FakeAnthropic,
    build_campaign,
    default_outcome,
    message,
)

FAKE_KEY = "cle-de-test-jamais-ecrite"


@pytest.fixture
def _reset_logging():
    yield
    from scripts.quality_bench.common.logs import setup_logging

    setup_logging("test", None)


@pytest.fixture
def haiku(monkeypatch, _reset_logging):
    fake = FakeAnthropic()
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setattr(commands, "make_anthropic_client", lambda judge, key: fake)
    monkeypatch.setattr(commands, "SLEEP", lambda seconds: None)
    return fake


def _run(judge, *extra):
    from scripts.quality_bench.__main__ import main

    return main(["judge", "--campaign", CAMPAIGN, "--judge", judge, *extra])


def _lines(judge):
    return read_jsonl(paths.judgment_path(CAMPAIGN, judge))


def _batches():
    return read_jsonl(paths.batches_path(CAMPAIGN, "haiku"))


def _no_secret_written(judge):
    for path in paths.campaign_dir(CAMPAIGN).rglob("*"):
        if path.is_file():
            assert FAKE_KEY not in path.read_text(encoding="utf-8", errors="replace"), path


# --- Haiku ------------------------------------------------------------------------------------


def test_haiku_nominal(haiku):
    campaign = build_campaign()
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    lines = _lines("haiku")
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    per_line = (1000 * 0.10 + 100 * 0.50) / 1_000_000 * 0.5  # usage × prix × remise de lot
    for line in lines:
        validate(line)
        assert line["verdict"] is (line["criterion"] != "c3")
        assert line["tokens"] == {"input": 1000, "output": 100}
        assert line["cost_usd"] == pytest.approx(per_line)
        assert line["attempts"] == 1 and line["probability"] is None
    # Une requête par critère, sans paramètre d'échantillonnage ni préremplissage.
    ((batch_id, requests),) = haiku.batches.created
    assert [r["custom_id"] for r in requests] == [str(i) for i in range(len(requests))]
    for request in requests:
        params = request["params"]
        assert not {"temperature", "top_p", "top_k"} & set(params)
        assert [m["role"] for m in params["messages"]] == ["user"]
        assert params["model"] == "claude-haiku-5-5" and params["max_tokens"] == 2048
        assert params["output_config"]["effort"] == "low"
        assert params["output_config"]["format"]["type"] == "json_schema"
        assert params["thinking"] == {"type": "adaptive"}
    batches = _batches()
    assert [b["status"] for b in batches] == ["submitted", "collected"]
    assert batches[0]["keys"] == [line["key"] for line in lines]  # ordre des custom_id
    assert batches[1]["cost_usd"] == pytest.approx(per_line * len(lines))
    for batch in batches:
        validate(batch)
    manifest = json.loads(
        paths.judgment_manifest_path(CAMPAIGN, "haiku").read_text(encoding="utf-8")
    )
    settings = manifest["blocking"]["judge"]["settings"]
    assert settings["effort"] == "low" and settings["thinking"] == {"type": "adaptive"}
    assert settings["max_tokens"] == 2048 and "temperature" not in settings
    prices = manifest["informative"]["prices"]
    assert prices["judge"] == "haiku" and prices["checked"] and prices["source"]
    _no_secret_written("haiku")
    log = paths.log_path(CAMPAIGN, "judge").read_text(encoding="utf-8")
    assert ANSWER_MARK not in log and "Critère synthétique" not in log


def test_submitted_written_before_waiting(haiku):
    build_campaign()
    seen = []

    def check(batch_id, polls):
        seen.append([b["status"] for b in _batches()])

    haiku.batches.on_retrieve = check
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    assert seen[0] == ["submitted"]


def test_stop_during_wait_then_resume_reads_batch(haiku):
    """Critère d'acceptation : arrêt par STOP pendant l'attente d'un lot, puis reprise sans
    resoumission ni clé écrite deux fois."""
    campaign = build_campaign()
    stop_path = paths.judgment_stop_path(CAMPAIGN, "haiku")
    haiku.batches.pending_polls = 2
    haiku.batches.on_retrieve = lambda batch_id, polls: stop_path.touch() if polls == 1 else None
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    assert len(haiku.batches.created) == 1
    assert [b["status"] for b in _batches()] == ["submitted"]
    assert _lines("haiku") == []
    assert not stop_path.exists()

    haiku.batches.on_retrieve = None
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    assert len(haiku.batches.created) == 1  # aucun lot resoumis
    lines = _lines("haiku")
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    assert len({line["key"] for line in lines}) == len(lines)
    assert [b["status"] for b in _batches()] == ["submitted", "collected"]
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    assert len(haiku.batches.created) == 1


def test_expired_batches_are_resubmitted_then_exit_1(haiku):
    build_campaign()
    haiku.batches.outcome = lambda params, number: type("R", (), {"type": "expired"})()
    assert _run("haiku", "--max-cost-usd", "0.25") == 1
    assert _lines("haiku") == []
    assert len(haiku.batches.created) == 3  # max_attempts
    statuses = [b["status"] for b in _batches()]
    assert statuses == ["submitted", "collected"] * 3
    assert set(_batches()[1]["outcomes"].values()) == {"transient"}


def test_expired_once_then_succeeds_counts_attempts(haiku):
    campaign = build_campaign(writing=1)
    from .judge_fakes import default_outcome

    def outcome(params, number):
        if number == 1:
            return type("R", (), {"type": "expired"})()
        return default_outcome(params, number)

    haiku.batches.outcome = outcome
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    lines = _lines("haiku")
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    assert {line["attempts"] for line in lines} == {2}


def test_unreadable_verdict_writes_error_lines(haiku):
    campaign = build_campaign(writing=1)
    haiku.batches.outcome = lambda params, number: type(
        "R", (), {"type": "succeeded", "message": message("pas du JSON")}
    )()
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    lines = _lines("haiku")
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    for line in lines:
        validate(line)
        assert line["verdict"] is None and line["attempts"] == 3
        assert line["error"] == "verdict illisible (JSON invalide)"
    assert len(haiku.batches.created) == 3


def test_refusal_and_truncation_are_unit_failures(haiku):
    build_campaign(writing=1)
    haiku.batches.outcome = lambda params, number: type(
        "R", (), {"type": "succeeded", "message": message("", stop_reason="refusal")}
    )()
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    assert {line["error"] for line in _lines("haiku")} == {"refus du modèle (refusal)"}


def test_private_question_is_never_sent(haiku):
    build_campaign(private=True)
    assert _run("haiku", "--max-cost-usd", "0.25") == 1
    assert haiku.batches.created == []
    assert not paths.judgment_dir(CAMPAIGN, "haiku").exists()


def test_private_question_is_allowed_for_local_judge(monkeypatch, _reset_logging):
    from .judge_fakes import FakeServer

    fake = FakeServer()
    monkeypatch.setattr(commands, "make_transport", fake.transport)
    build_campaign(private=True)
    assert _run("winnow") == 0


def test_cost_cap_stops_before_any_call(haiku):
    build_campaign()
    assert _run("haiku", "--max-cost-usd", "0.0001") == 3
    assert haiku.batches.created == []
    assert _lines("haiku") == []


def test_cost_cap_counts_this_launch_spending(haiku, monkeypatch):
    """Lots de 4 requêtes : le second dépasse le plafond (dépense réelle + estimation)."""
    from scripts.quality_bench.common import config as config_module

    original = config_module.load_judges

    def small_batches(path):
        judges = original(path)
        judges["haiku"].options["batch_size"] = 4
        return judges

    monkeypatch.setattr(config_module, "load_judges", small_batches)
    build_campaign(writing=2)
    # Un lot est estimé à ≈ 0,0021 $ et coûte 0,0003 $ : 0,0023 $ laisse passer le premier,
    # pas le second (0,0003 $ dépensés + 0,0021 $ estimés).
    assert _run("haiku", "--max-cost-usd", "0.0023") == 3
    assert len(haiku.batches.created) == 1
    assert len(_lines("haiku")) == 4


def test_cloud_judge_requires_max_cost(haiku):
    build_campaign()
    assert _run("haiku") == 2
    assert not paths.judgment_dir(CAMPAIGN, "haiku").exists()


def test_missing_api_key_exits_2(haiku, monkeypatch):
    build_campaign()
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert _run("haiku", "--max-cost-usd", "1") == 2
    assert haiku.batches.created == []


# --- MiMo -------------------------------------------------------------------------------------


def _completion(content='{"verdict": true}', finish_reason="stop"):
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "mimo-v2.6-pro",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 500, "completion_tokens": 20, "total_tokens": 520},
    }


@pytest.fixture
def mimo_server(monkeypatch, _reset_logging):
    state = {"requests": [], "respond": lambda body: httpx2.Response(200, json=_completion())}

    def handler(request):
        body = json.loads(request.content)
        state["requests"].append((request, body))
        return state["respond"](body)

    def make(judge, key):
        http_client = httpx2.Client(transport=httpx2.MockTransport(handler))
        return mimo.make_client(judge, key, http_client=http_client)

    monkeypatch.setenv("MIMO_API_KEY", FAKE_KEY)
    monkeypatch.setattr(commands, "make_openai_client", make)
    monkeypatch.setattr(commands, "SLEEP", lambda seconds: None)
    return state


def test_mimo_nominal(mimo_server):
    campaign = build_campaign(writing=1)
    assert _run("mimo", "--max-cost-usd", "0.25") == 0
    lines = _lines("mimo")
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    for line in lines:
        validate(line)
        assert line["verdict"] is True and line["tokens"] == {"input": 500, "output": 20}
        assert line["cost_usd"] == pytest.approx((500 * 0.435 + 20 * 0.87) / 1_000_000)
    assert len(mimo_server["requests"]) == 4  # une requête par critère
    request, body = mimo_server["requests"][0]
    assert request.url.host == "api.xiaomimimo.com"
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert body["model"] == "mimo-v2.6-pro"
    assert not {"temperature", "top_p", "thinking"} & set(body)
    _no_secret_written("mimo")


def test_mimo_down_exits_1_without_lines(mimo_server):
    build_campaign(writing=1)
    mimo_server["respond"] = lambda body: httpx2.Response(503, json={"error": "indisponible"})
    assert _run("mimo", "--max-cost-usd", "0.25") == 1
    assert _lines("mimo") == []
    assert len(mimo_server["requests"]) == 3  # max_attempts, sans relance du SDK


def test_mimo_truncation_and_unreadable_are_unit_failures(mimo_server):
    build_campaign(writing=1)
    responses = iter(
        [_completion("", finish_reason="length")] + [_completion("oui")] * 2 + [_completion()] * 9
    )
    mimo_server["respond"] = lambda body: httpx2.Response(200, json=next(responses))
    assert _run("mimo", "--max-cost-usd", "0.25") == 0
    lines = sorted(_lines("mimo"), key=lambda line: line["key"])
    assert lines[0]["error"] == "verdict illisible (JSON invalide)"
    assert lines[0]["tokens"] == {"input": 1500, "output": 60}  # trois essais facturés
    assert all(line["verdict"] is True for line in lines[1:])


def test_mimo_thinking_sent_only_when_set(mimo_server, monkeypatch):
    from scripts.quality_bench.common import config as config_module

    original = config_module.load_judges

    def with_thinking(path):
        judges = original(path)
        judges["mimo"].options["thinking"] = {"type": "disabled"}
        return judges

    monkeypatch.setattr(config_module, "load_judges", with_thinking)
    build_campaign(writing=1)
    assert _run("mimo", "--max-cost-usd", "0.25") == 0
    _, body = mimo_server["requests"][0]
    assert body["thinking"] == {"type": "disabled"}


# --- Haiku : erreurs de l'API, résultats en erreur, relance ----------------------------------

_BATCH_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages/batches")


def _status_error(status):
    import anthropic

    response = httpx2.Response(status, request=_BATCH_REQUEST, json={"error": {}})
    classes = {400: anthropic.BadRequestError, 429: anthropic.RateLimitError}
    error_class = classes.get(status, anthropic.InternalServerError)
    return error_class("erreur simulée", response=response, body=None)


def _errored(error_type):
    return SimpleNamespace(
        type="errored", error=SimpleNamespace(error=SimpleNamespace(type=error_type))
    )


def test_relaunch_after_exhausted_transient_resubmits(haiku):
    """Clés sans résultat après max_attempts lots : code 1, puis une relance les rejuge."""
    campaign = build_campaign(writing=1)
    haiku.batches.outcome = lambda params, number: SimpleNamespace(type="expired")
    assert _run("haiku", "--max-cost-usd", "0.25") == 1
    haiku.batches.outcome = default_outcome
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    lines = _lines("haiku")
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    assert {line["attempts"] for line in lines} == {4}  # tous les lots soumis comptent
    assert len(haiku.batches.created) == 4


def test_errored_invalid_request_writes_error_lines(haiku):
    campaign = build_campaign(writing=1)
    haiku.batches.outcome = lambda params, number: _errored("invalid_request_error")
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    lines = _lines("haiku")
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    assert {line["error"] for line in lines} == {"requête refusée (invalid_request_error)"}
    assert {line["attempts"] for line in lines} == {3}


def test_errored_other_type_is_transient(haiku):
    build_campaign(writing=1)
    haiku.batches.outcome = lambda params, number: _errored("overloaded_error")
    assert _run("haiku", "--max-cost-usd", "0.25") == 1
    assert _lines("haiku") == []
    assert len(haiku.batches.created) == 3


def test_max_tokens_is_a_unit_failure(haiku):
    build_campaign(writing=1)
    haiku.batches.outcome = lambda params, number: SimpleNamespace(
        type="succeeded", message=message("", stop_reason="max_tokens")
    )
    assert _run("haiku", "--max-cost-usd", "0.25") == 0
    assert {line["error"] for line in _lines("haiku")} == {"sortie tronquée (max_tokens)"}


def test_unknown_result_type_is_transient(haiku):
    build_campaign(writing=1)
    haiku.batches.outcome = lambda params, number: SimpleNamespace(type="inconnu")
    assert _run("haiku", "--max-cost-usd", "0.25") == 1
    collected = [line for line in _batches() if line["status"] == "collected"]
    assert len(collected) == 3
    for line in collected:
        validate(line)
        assert set(line["outcomes"].values()) == {"transient"}


@pytest.mark.parametrize("status", [429, 500])
def test_submission_is_never_retried(haiku, status):
    """Soumission non idempotente : une panne à la création n'est pas relancée."""
    build_campaign(writing=1)
    calls = []

    def failing(*, requests):
        calls.append(requests)
        raise _status_error(status)

    haiku.batches.create = failing
    assert _run("haiku", "--max-cost-usd", "0.25") == 1
    assert len(calls) == 1
    assert _batches() == []


def test_submission_connection_error_is_not_retried(haiku):
    import anthropic

    build_campaign(writing=1)
    calls = []

    def failing(*, requests):
        calls.append(requests)
        raise anthropic.APIConnectionError(request=_BATCH_REQUEST)

    haiku.batches.create = failing
    assert _run("haiku", "--max-cost-usd", "0.25") == 1
    assert len(calls) == 1


def test_submission_refused_exits_1(haiku):
    build_campaign(writing=1)
    calls = []

    def refused(*, requests):
        calls.append(requests)
        raise _status_error(400)

    haiku.batches.create = refused
    assert _run("haiku", "--max-cost-usd", "0.25") == 1
    assert len(calls) == 1


def test_retrieve_rate_limited_is_retried_then_exit_1(haiku):
    build_campaign(writing=1)
    calls = []

    def limited(batch_id):
        calls.append(batch_id)
        raise _status_error(429)

    haiku.batches.retrieve = limited
    assert _run("haiku", "--max-cost-usd", "0.25") == 1
    assert len(calls) == 3  # max_attempts
    assert [line["status"] for line in _batches()] == ["submitted"]  # relu à la reprise
    assert _lines("haiku") == []


# --- MiMo : plafond, relance réussie, clé refusée --------------------------------------------


def test_mimo_cost_cap_stops_before_any_call(mimo_server):
    build_campaign(writing=1)
    assert _run("mimo", "--max-cost-usd", "0.0001") == 3
    assert mimo_server["requests"] == []
    assert _lines("mimo") == []


def test_mimo_cost_cap_stops_after_some_calls(mimo_server):
    """Estimation d'environ 0,002 $ par appel, coût réel 0,00023 $ : le plafond de 0,0025 $
    laisse passer quelques appels, puis arrête sans envoi de plus."""
    build_campaign(writing=1)
    assert _run("mimo", "--max-cost-usd", "0.0025") == 3
    lines = _lines("mimo")
    assert 0 < len(lines) < 4
    assert len(mimo_server["requests"]) == len(lines)


def test_mimo_retry_then_success_counts_attempts_and_tokens(mimo_server):
    build_campaign(writing=1)
    responses = iter([_completion("", finish_reason="length")] + [_completion()] * 4)
    mimo_server["respond"] = lambda body: httpx2.Response(200, json=next(responses))
    assert _run("mimo", "--max-cost-usd", "0.25") == 0
    lines = sorted(_lines("mimo"), key=lambda line: line["key"])
    assert lines[0]["attempts"] == 2 and lines[0]["verdict"] is True
    assert lines[0]["tokens"] == {"input": 1000, "output": 40}  # deux essais facturés
    assert lines[0]["cost_usd"] == pytest.approx(2 * (500 * 0.435 + 20 * 0.87) / 1_000_000)
    assert all(line["attempts"] == 1 for line in lines[1:])


@pytest.mark.parametrize("status", [401, 404])
def test_mimo_refused_key_or_model_stops_without_lines(mimo_server, status):
    build_campaign(writing=1)
    mimo_server["respond"] = lambda body: httpx2.Response(status, json={"error": "refusé"})
    assert _run("mimo", "--max-cost-usd", "0.25") == 1
    assert _lines("mimo") == []
    assert len(mimo_server["requests"]) == 1


# --- Decider hébergé (contrat /v1/systemone, juge cloud) ----------------------------------------


@pytest.fixture
def decider(monkeypatch, _reset_logging):
    """``decider`` avec un point d'accès hébergé fictif ; requêtes relevées avec leurs en-têtes."""
    import dataclasses

    from scripts.quality_bench.common import config as config_module

    from .judge_fakes import FakeServer

    original = config_module.load_judges

    def with_endpoint(path):
        judges = original(path)
        judges["decider"] = dataclasses.replace(
            judges["decider"], endpoint="https://decider.example"
        )
        return judges

    fake = FakeServer()
    seen = []

    def handler(request):
        seen.append(request)
        return fake(request)

    monkeypatch.setattr(config_module, "load_judges", with_endpoint)
    monkeypatch.setattr(commands, "make_transport", lambda: httpx2.MockTransport(handler))
    monkeypatch.setattr(commands, "SLEEP", lambda seconds: None)
    monkeypatch.setenv("PERPLEXITY_API_KEY", FAKE_KEY)
    return seen


def test_decider_hosted_nominal(decider):
    campaign = build_campaign(writing=1)
    assert _run("decider", "--max-cost-usd", "0.25") == 0
    lines = _lines("decider")
    assert sorted(line["key"] for line in lines) == campaign["expected_keys"]
    assert all(line["cost_usd"] > 0 for line in lines)
    assert [request.url.path for request in decider] == ["/v1/systemone"]  # ni /api/ps
    assert decider[0].url.host == "decider.example"
    assert decider[0].headers["authorization"] == f"Bearer {FAKE_KEY}"
    _no_secret_written("decider")


def test_decider_refuses_private_questions(decider):
    build_campaign(private=True)
    assert _run("decider", "--max-cost-usd", "0.25") == 1
    assert decider == []


def test_decider_requires_max_cost(decider):
    build_campaign(writing=1)
    assert _run("decider") == 2
    assert decider == []
