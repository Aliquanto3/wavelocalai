"""`POST /api/rag/eval/runs` : fidélité, pertinence et précision du contexte, de bout en bout (7.1).

L'app est la vraie (hub, store, index vectoriel, services d'ingestion et d'évaluation, juge, flux
SSE) ; les modèles évalués, le juge et l'embedding sont des `fake` scriptés. Aucun Ollama, aucun
réseau, aucun cloud réel.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.evaluation import prompts
from wavelocalai.evaluation.judge import Judge
from wavelocalai.models.fake import (
    FakeChatModel,
    Sleep,
    fake_embedders,
    fake_models,
    fake_vector,
)
from wavelocalai.models.port import ModelRef, TextDelta
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.eval_snapshot import METRICS, NOT_EVALUATED_STOPPED, measure_totals
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from .conftest import parse_sse
from .test_rag_run_api import CARS, CATS, QUESTION, _files

BASE = f"http://127.0.0.1:{TEST_PORT}"
QUESTIONS = [QUESTION, "Que fait le chat la nuit ?"]
ANSWER = "Le chat dort sur le canapé [1]. Il chasse les souris la nuit. Il a trois ans."
CLAIMS = ["Le chat dort sur le canapé.", "Le chat chasse les souris.", "Le chat a trois ans."]
RETRIEVED = ["Où dort le chat ?", "Le chat dort-il sur le canapé ?", "Que fait le chat la nuit ?"]
SECRET_QUESTION = "Question-unique-7-1 : où le chat range-t-il ses billes ?"
SCHEMAS = {
    "claims": prompts.CLAIMS_SCHEMA,
    "verdict": prompts.VERDICT_SCHEMA,
    "questions": prompts.QUESTIONS_SCHEMA,
    "useful": prompts.USEFUL_SCHEMA,
}


def _verdict(request) -> dict:
    text = request.messages[-1].content
    if "trois ans" in text:
        return {"verdict": "non appuyée", "support": None, "reason": "Absent des extraits."}
    return {"verdict": "appuyée", "support": 1, "reason": "Dit dans l'extrait 1."}


DEFAULT_REPLIES: dict[str, Any] = {
    "claims": {"claims": CLAIMS},
    "verdict": _verdict,
    "questions": {"questions": RETRIEVED},
    "useful": {"useful": [1], "reason": "Le premier extrait répond."},
}


class SchemaJudge(FakeChatModel):
    """Un juge qui répond selon le schéma demandé : un dict (JSON), un texte, une fonction de la
    requête ou une exception à lever. `calls` garde le nom de chaque appel, dans l'ordre."""

    def __init__(self, tag: str = "fake:j", origin: str = "local", **replies: Any) -> None:
        super().__init__([], ModelRef(tag, "fake", origin, "chat"))
        self.replies = {**DEFAULT_REPLIES, **replies}
        self.calls: list[str] = []
        self.sleep = 0.0
        self.freeze_after: int | None = None  # à partir du (n+1)-ième appel, le juge se fige

    async def stream(self, request):
        name = next(n for n, schema in SCHEMAS.items() if schema is request.response_schema)
        self.calls.append(name)
        frozen = self.freeze_after is not None and len(self.calls) > self.freeze_after
        reply = self.replies[name]
        if callable(reply):
            reply = reply(request)
        if isinstance(reply, BaseException):
            self.script = [reply]
        else:
            text = reply if isinstance(reply, str) else json.dumps(reply)
            wait = 5.0 if frozen else self.sleep
            self.script = [Sleep(wait), TextDelta(text)] if wait else [TextDelta(text)]
        async for chunk in super().stream(request):
            yield chunk


def local(tag: str, *words: str) -> FakeChatModel:
    return FakeChatModel([TextDelta(w) for w in words], ModelRef(tag, "fake", "local", "chat"))


def cloud(tag: str, *words: str) -> FakeChatModel:
    return FakeChatModel([TextDelta(w) for w in words], ModelRef(tag, "fake", "cloud", "chat"))


@contextlib.asynccontextmanager
async def eval_app(tmp_path: Path, *fakes: FakeChatModel, docs: bool = True, **settings):
    """App de test avec `fakes` (modèles évalués et juges) et, par défaut, une base de deux
    documents indexée par l'embedding `fake`."""
    config = make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}, **settings)
    every = [*fakes, *fake_models(config).values(), *fake_embedders(config).values()]
    registry = ModelRegistry(config, extra_refs={m.ref.tag: m.ref for m in every})
    app = create_app(config, registry=registry)
    app.state.models.update({m.ref.tag: m for m in fakes})
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            if docs:
                started = await client.post(
                    "/api/rag/documents", files=_files(**{"chats.txt": CATS, "voitures.txt": CARS})
                )
                assert started.status_code == 200, started.text
                assert (await _ended(client, started.json()["run_id"]))["status"] == "ok"
            yield app, client


async def _ended(client, run_id, timeout=10.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] not in ("running", "awaiting_approval"):
                return snapshot
            await asyncio.sleep(0.02)


async def _events(client, run_id):
    response = await client.get(f"/api/runs/{run_id}/events")
    return [f["data"] for f in parse_sse(response.text)[0]]


async def _until(app, run_id, predicate, timeout=5.0):
    async with asyncio.timeout(timeout):
        while True:
            events = await app.state.hub.events_after(run_id)
            if predicate(events):
                return events
            await asyncio.sleep(0.01)


async def _post(client, models, questions=None, **body):
    payload = {"questions": questions or QUESTIONS[:1], "models": list(models), **body}
    return await client.post("/api/rag/eval/runs", json=payload)


async def _run(client, models, questions=None, **body):
    response = await _post(client, models, questions, **body)
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    return run_id, await _ended(client, run_id), await _events(client, run_id)


def _of(events, type_, **match):
    return [
        e["data"]
        for e in events
        if e["type"] == type_ and all(e["data"].get(k) == v for k, v in match.items())
    ]


def _metric(events, lane, metric, question_index=0):
    found = _of(events, "eval_metric", lane=lane, metric=metric, question_index=question_index)
    assert len(found) == 1, (lane, metric, found)
    return found[0]


def _status(events, lane):
    return [e["status"] for e in _of(events, "lane_status", lane=lane)]


def _relevance_expected() -> int:
    cosines = []
    base = fake_vector(QUESTION)
    for text in RETRIEVED:
        other = fake_vector(text)
        cosines.append(sum(a * b for a, b in zip(base, other, strict=True)))
    return int(100 * (sum(cosines) / len(cosines)) + 0.5)


async def test_two_models_answer_on_the_same_extracts_then_the_judge_scores_three_metrics(tmp_path):
    a, b = local("fake:a", ANSWER), local("fake:b", ANSWER)
    judge = SchemaJudge()
    async with eval_app(tmp_path, a, b, judge) as (app, client):
        response = await _post(client, ["fake:a", "fake:b"], judge="fake:j")
        assert response.status_code == 200, response.text
        assert set(response.json()) == {"run_id"}
        run_id = response.json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)

    assert snapshot["kind"] == "eval" and snapshot["status"] == "ok"
    assert snapshot["conversation_id"] is None and snapshot["metrics"] is None
    types = [e["type"] for e in events]
    assert types[:2] == ["run_started", "eval_questions"] and types[-1] == "run_ended"
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["data"]["kind"] == "eval"
    assert events[0]["data"]["models"] == ["fake:a", "fake:b"]
    assert "question" not in json.dumps(events[0]["data"]["params"]).lower().replace(
        "question_count", ""
    )
    assert events[1]["data"] == {"questions": QUESTIONS[:1]}
    info = _of(events, "judge")[0]
    assert info["model"] == "fake:j" and info["chosen"] == "request" and info["single_judge"]

    # Les extraits sont cherchés une fois (une recherche par question), avant toute réponse.
    steps = _of(events, "retrieval_step")
    assert [(s["strategy"], s["step"], s["question_index"]) for s in steps] == [
        ("naive", "embedding", 0),
        ("naive", "search", 0),
    ]
    sources = _of(events, "sources")
    assert len(sources) == 1 and sources[0]["question_index"] == 0
    assert sources[0]["strategy"] == "naive" and sources[0]["sources"][0]["text"] == CATS
    assert types.index("sources") < types.index("eval_answer")
    # Les deux modèles reçoivent les mêmes extraits, dans la même invite.
    assert a.requests[0].messages[-1].content == b.requests[0].messages[-1].content
    assert CATS in a.requests[0].messages[-1].content

    count = len(sources[0]["sources"])
    for lane in ("fake:a", "fake:b"):
        assert _status(events, lane) == ["waiting", "generating", "judging", "done"]
        answer = _of(events, "eval_answer", lane=lane)[0]
        assert (
            answer["text"] == ANSWER and answer["error"] is None and answer["question_index"] == 0
        )
        metrics = _of(events, "metrics", lane=lane)
        assert len(metrics) == 1 and metrics[0]["question_index"] == 0 and metrics[0]["tps"]
        assert not _of(events, "token", lane=lane)  # silencieux : le texte part dans `eval_answer`
        faith = _metric(events, lane, "faithfulness")
        assert faith["score"] == 67 and faith["question_count"] == 1
        assert [v["verdict"] for v in faith["verdicts"]] == ["appuyée", "appuyée", "non appuyée"]
        assert [v["claim"] for v in faith["verdicts"]] == CLAIMS
        assert [v["support"] for v in faith["verdicts"]] == [1, 1, None]
        assert faith["aggregate"] == {
            "score": 67,
            "evaluated": 1,
            "not_evaluated": 0,
            "pending": 0,
            "total": 1,
        }
        assert "2 affirmations sur 3 appuyées" in faith["reason"]
        rel = _metric(events, lane, "relevance")
        assert rel["score"] == _relevance_expected() and rel["questions"] == RETRIEVED
        assert rel["verdicts"] is None
        prec = _metric(events, lane, "context_precision")
        assert prec["score"] == round(100 / count) and prec["useful"] == [1]
        assert prec["reason"] == "Le premier extrait répond."
    # Chaque métrique est publiée avant la clôture de sa lane, dans l'ordre de la notation.
    for lane in ("fake:a", "fake:b"):
        order = [e["metric"] for e in _of(events, "eval_metric", lane=lane)]
        assert order == list(METRICS)

    # Feuilles : une `embedding` par recherche et par pertinence, une `generation` par modèle, des
    # `judge` pour chaque appel du juge (1 + 3 + 1 + 1 par réponse), toutes sous la racine (AD-5).
    kids = snapshot["children"]
    kinds = [c["kind"] for c in kids]
    assert kinds.count("generation") == 2 and kinds.count("embedding") == 3
    assert kinds.count("judge") == 12 and all(c["parent_run_id"] == run_id for c in kids)
    assert all(c["metrics"]["co2"] is not None for c in kids)
    assert judge.calls.count("claims") == 2 and judge.calls.count("verdict") == 6

    # La base garde les notes ; l'instantané les rend avec leur résumé.
    assert snapshot["partial"] is False and snapshot["erased"] is False
    assert snapshot["config"] == {
        "questions": QUESTIONS[:1],
        "models": ["fake:a", "fake:b"],
        "judge": "fake:j",
        "allow_cloud": False,
    }
    assert len(snapshot["evaluations"]) == 6
    assert snapshot["summary"]["fake:a"]["faithfulness"]["score"] == 67
    assert snapshot["summary"]["fake:b"]["context_precision"]["total"] == 1
    assert "missing" not in snapshot


async def test_a_set_of_questions_gives_a_mean_and_the_detail_by_question(tmp_path):
    a = local("fake:a", ANSWER)
    judge = SchemaJudge()
    async with eval_app(tmp_path, a, judge) as (_, client):
        _, snapshot, events = await _run(client, ["fake:a"], QUESTIONS, judge="fake:j")
    assert snapshot["status"] == "ok" and len(_of(events, "sources")) == 2
    first, second = (_metric(events, "fake:a", "faithfulness", i) for i in (0, 1))
    assert first["question_count"] == second["question_count"] == 2
    # En cours : la deuxième question n'est pas « non évaluée », elle attend sa note.
    assert first["aggregate"] == {
        "score": 67, "evaluated": 1, "not_evaluated": 0, "pending": 1, "total": 2
    }  # fmt: skip
    assert second["aggregate"] == {
        "score": 67,
        "evaluated": 2,
        "not_evaluated": 0,
        "pending": 0,
        "total": 2,
    }
    assert {m["question_index"] for m in _of(events, "metrics", lane="fake:a")} == {0, 1}
    assert snapshot["summary"]["fake:a"]["relevance"]["total"] == 2
    assert [r["question_index"] for r in snapshot["evaluations"]][:2] == [0, 0]
    assert snapshot["config"]["questions"] == QUESTIONS


async def test_a_set_publishes_the_mean_rate_and_total_co2_of_each_model(tmp_path):
    """Revue 7.3 (AD-20) : le débit moyen et le CO2 total d'un jeu viennent du serveur, au fil
    des `metrics` (`lane_measures`) et dans l'instantané (`measures`), sans calcul à l'écran."""
    a = local("fake:a", ANSWER)
    async with eval_app(tmp_path, a, SchemaJudge()) as (_, client):
        _, snapshot, events = await _run(client, ["fake:a"], QUESTIONS, judge="fake:j")
    first, second = _of(events, "metrics", lane="fake:a")
    assert first["lane_measures"]["answered"] == 1 and first["lane_measures"]["total"] == 2
    final = second["lane_measures"]
    assert final["answered"] == 2 and final["tps_measured"] == 2
    assert final["tps"] == pytest.approx((first["tps"] + second["tps"]) / 2)
    assert snapshot["measures"] == {"fake:a": final}


def test_measure_totals_says_how_many_answers_were_measured():
    events = [
        {"tps": 30.0, "co2": {"mg": 1.5, "estimated": False}},
        {"tps": 10.0, "co2": {"mg": None, "estimated": False}},
        {"tps": None, "co2": {"mg": 2.0, "estimated": True}},
    ]
    assert measure_totals(events, 4) == {
        "tps": 20.0,
        "tps_measured": 2,
        "co2": {"mg": 3.5, "measured": 2, "estimated": True, "unmeasurable": False},
        "answered": 3,
        "total": 4,
    }
    unmeasured = measure_totals([{"tps": None, "co2": {"mg": None}}], 1)
    assert unmeasured["tps"] is None and unmeasured["co2"]["mg"] is None
    assert unmeasured["co2"]["unmeasurable"] is True
    assert measure_totals([], 2)["co2"] == {
        "mg": None, "measured": 0, "estimated": False, "unmeasurable": False
    }  # fmt: skip


async def test_a_partly_unscored_set_says_how_many_questions_were_not_evaluated(tmp_path):
    """« sur 8 questions (1 non évaluée) » : la moyenne ne porte que sur les questions notées."""
    judge = SchemaJudge()
    fail = ProviderError("ollama_down", "Ollama ne répond pas")
    calls = {"n": 0}

    def claims(request):
        calls["n"] += 1
        return fail if calls["n"] == 2 else {"claims": CLAIMS}  # la deuxième question

    judge.replies["claims"] = claims
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (_, client):
        _, snapshot, events = await _run(client, ["fake:a"], QUESTIONS, judge="fake:j")
    second = _metric(events, "fake:a", "faithfulness", 1)
    assert second["score"] is None and second["reason"] == "non évalué : juge indisponible"
    assert second["aggregate"] == {
        "score": 67,
        "evaluated": 1,
        "not_evaluated": 1,
        "pending": 0,
        "total": 2,
    }
    assert snapshot["summary"]["fake:a"]["faithfulness"] == second["aggregate"]
    rows = [r for r in snapshot["evaluations"] if r["metric"] == "faithfulness"]
    assert [r["score"] for r in rows] == [67, None]


@pytest.mark.parametrize(
    ("replies", "reason"),
    [
        ({"claims": ProviderError("ollama_down", "x")}, "non évalué : juge indisponible"),
        ({"claims": "ceci n'est pas du JSON"}, "non évalué : sortie du juge invalide"),
        ({"claims": ProviderError("invalid_output", "x")}, "non évalué : sortie du juge invalide"),
        ({"claims": {"claims": []}}, "non évalué : aucune affirmation à vérifier"),
        ({"claims": {"claims": CLAIMS}, "verdict": "non"}, "non évalué : sortie du juge invalide"),
        (
            {
                "claims": {"claims": CLAIMS},
                "verdict": {"verdict": "peut-être", "support": 1, "reason": "x"},
            },
            "non évalué : sortie du juge invalide",
        ),
    ],
)
async def test_a_failing_judge_never_gives_zero_on_the_faithfulness(tmp_path, replies, reason):
    judge = SchemaJudge(**replies)
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (_, client):
        _, snapshot, events = await _run(client, ["fake:a"], judge="fake:j")
    faith = _metric(events, "fake:a", "faithfulness")
    assert faith["score"] is None and faith["reason"] == reason and faith["verdicts"] is None
    assert snapshot["status"] == "ok"
    # Les autres métriques sont notées : un incident ne coule que sa propre note.
    assert _metric(events, "fake:a", "relevance")["score"] is not None
    assert _metric(events, "fake:a", "context_precision")["score"] is not None


async def test_the_other_metrics_have_their_own_not_evaluated_reasons(tmp_path):
    judge = SchemaJudge(
        questions={"questions": []}, useful="pas du JSON"
    )  # rien à comparer, sortie invalide
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (_, client):
        _, _, events = await _run(client, ["fake:a"], judge="fake:j")
    rel = _metric(events, "fake:a", "relevance")
    assert rel["score"] is None and "aucune question retrouvée" in rel["reason"]
    prec = _metric(events, "fake:a", "context_precision")
    assert prec["score"] is None and prec["reason"] == "non évalué : sortie du juge invalide"
    assert _metric(events, "fake:a", "faithfulness")["score"] == 67


async def test_an_empty_answer_is_not_evaluated_and_the_judge_is_not_called(tmp_path):
    empty = FakeChatModel([], ModelRef("fake:e", "fake", "local", "chat"))
    judge = SchemaJudge()
    async with eval_app(tmp_path, empty, local("fake:a", ANSWER), judge) as (_, client):
        _, snapshot, events = await _run(client, ["fake:e", "fake:a"], judge="fake:j")
    for metric in METRICS:
        got = _metric(events, "fake:e", metric)
        assert got["score"] is None and got["reason"] == "non évalué : réponse vide"
    assert _status(events, "fake:e")[-1] == "done"
    assert snapshot["summary"]["fake:e"]["faithfulness"]["score"] is None
    assert judge.calls.count("claims") == 1  # la seule réponse non vide


async def test_a_model_that_fails_is_not_evaluated_and_the_others_go_on(tmp_path):
    broken = FakeChatModel(
        [ProviderError("ollama_down", "Ollama ne répond pas")],
        ModelRef("fake:x", "fake", "local", "chat"),
    )
    slow = FakeChatModel(
        [Sleep(0.3), TextDelta("tard")], ModelRef("fake:s", "fake", "local", "chat")
    )
    judge = SchemaJudge()
    async with eval_app(
        tmp_path, broken, slow, local("fake:a", ANSWER), judge, delays={"lane_timeout_s": 0.1}
    ) as (_, client):
        _, snapshot, events = await _run(client, ["fake:x", "fake:s", "fake:a"], judge="fake:j")
    assert snapshot["status"] == "ok"
    assert _status(events, "fake:x") == ["waiting", "generating", "failed"]
    assert _status(events, "fake:s") == ["waiting", "generating", "timeout"]
    failed = _of(events, "lane_status", lane="fake:x", status="failed")[0]
    assert failed["error"]["code"] == "ollama_down"
    answer = _of(events, "eval_answer", lane="fake:x")[0]
    assert answer["text"] is None and answer["error"]["code"] == "ollama_down"
    assert _metric(events, "fake:x", "faithfulness")["reason"] == "non évalué : réponse en échec"
    assert _metric(events, "fake:s", "relevance")["reason"] == "non évalué : délai dépassé"
    assert _metric(events, "fake:a", "faithfulness")["score"] == 67
    assert _status(events, "fake:a")[-1] == "done"


async def test_no_judge_gives_not_evaluated_everywhere_but_still_answers(tmp_path):
    async with eval_app(tmp_path, local("fake:a", ANSWER)) as (app, client):
        # Aucun juge nommé et aucun défaut `judge` ne sert : le juge par défaut est introuvable.
        app.state.defaults = None
        app.state.evaluation._defaults = None
        _, snapshot, events = await _run(client, ["fake:a"])
    assert _of(events, "judge")[0]["model"] is None
    assert _of(events, "eval_answer", lane="fake:a")[0]["text"] == ANSWER
    for metric in METRICS:
        got = _metric(events, "fake:a", metric)
        assert got["score"] is None and got["reason"] == "non évalué : juge indisponible"
    assert snapshot["status"] == "ok"


async def test_the_default_judge_is_used_when_none_is_named(tmp_path):
    judge = SchemaJudge("fake:default")
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (app, client):
        app.state.evaluation._defaults = _Defaults("fake:default")
        _, _, events = await _run(client, ["fake:a"])
    info = _of(events, "judge")[0]
    assert info["model"] == "fake:default" and info["chosen"] == "default"
    assert _metric(events, "fake:a", "faithfulness")["score"] == 67


class _Defaults:
    def __init__(self, tag: str) -> None:
        self.tag = tag

    async def get(self, purpose: str, allow_cloud: bool = False):
        from wavelocalai.models.defaults import ModelDefault

        return ModelDefault(purpose=purpose, tags=[self.tag], reason="test", source="rule")


# --- refus avant toute écriture ----------------------------------------------------------------


async def _no_run_written(app) -> None:
    assert app.state.store.read("SELECT count(*) AS n FROM runs WHERE kind = 'eval'")[0]["n"] == 0


@pytest.mark.parametrize("count", [0, 5])
async def test_one_to_four_models_at_most_otherwise_422(tmp_path, count):
    fakes = [local(f"fake:m{i}", ANSWER) for i in range(count)]
    async with eval_app(tmp_path, *fakes, SchemaJudge()) as (app, client):
        response = await _post(client, [f.ref.tag for f in fakes], judge="fake:j")
        assert response.status_code == 422 and response.json()["code"] == "invalid_request"
        await _no_run_written(app)


async def test_four_models_are_accepted(tmp_path):
    fakes = [local(f"fake:m{i}", ANSWER) for i in range(4)]
    async with eval_app(tmp_path, *fakes, SchemaJudge()) as (_, client):
        _, snapshot, events = await _run(client, [f.ref.tag for f in fakes], judge="fake:j")
    assert snapshot["status"] == "ok" and len(_of(events, "eval_metric")) == 12


async def test_bad_requests_are_refused_before_any_run(tmp_path):
    async with eval_app(tmp_path, local("fake:a", ANSWER), SchemaJudge()) as (app, client):
        for questions in ([], [" "], ["ok", ""], ["x"] * 21, ["x" * 20_001]):
            response = await client.post(
                "/api/rag/eval/runs", json={"questions": questions, "models": ["fake:a"]}
            )
            assert response.status_code == 422, questions
            assert response.json()["code"] == "invalid_request"
        twice = await _post(client, ["fake:a", "fake:a"], judge="fake:j")
        assert twice.status_code == 422
        unknown = await _post(client, ["fake:nope"], judge="fake:j")
        assert unknown.status_code == 404 and unknown.json()["code"] == "model_not_found"
        no_judge = await _post(client, ["fake:a"], judge="fake:nope")
        assert no_judge.status_code == 404
        await _no_run_written(app)


async def test_a_cloud_model_or_judge_needs_allow_cloud(tmp_path):
    async with eval_app(
        tmp_path, local("fake:a", ANSWER), cloud("fake/c", ANSWER), SchemaJudge("fake/j", "cloud")
    ) as (app, client):
        refused = await _post(client, ["fake:a", "fake/c"])
        assert refused.status_code == 403 and refused.json()["code"] == "cloud_not_allowed"
        assert refused.json()["detail"]["tag"] == "fake/c"
        judge = await _post(client, ["fake:a"], judge="fake/j")
        assert judge.status_code == 403 and judge.json()["code"] == "cloud_not_allowed"
        await _no_run_written(app)


async def test_an_empty_base_is_refused_with_rag_base_empty(tmp_path):
    async with eval_app(tmp_path, local("fake:a", ANSWER), SchemaJudge(), docs=False) as (
        app,
        client,
    ):
        response = await _post(client, ["fake:a"], judge="fake:j")
        assert response.status_code == 409 and response.json()["code"] == "rag_base_empty"
        await _no_run_written(app)


async def test_a_second_evaluation_while_one_runs_is_run_busy(tmp_path):
    judge = SchemaJudge()
    judge.sleep = 0.3
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (app, client):
        first = await _post(client, ["fake:a"], judge="fake:j")
        assert first.status_code == 200
        busy = await _post(client, ["fake:a"], judge="fake:j")
        assert busy.status_code == 409 and busy.json()["code"] == "run_busy"
        assert busy.json()["detail"]["run_id"] == first.json()["run_id"]
        await client.post(f"/api/runs/{first.json()['run_id']}/cancel")


# --- local en séquence, cloud en parallèle (AD-14) ---------------------------------------------


async def test_locals_answer_one_after_the_other_and_the_cloud_in_parallel(tmp_path):
    a = FakeChatModel([Sleep(0.15), TextDelta(ANSWER)], ModelRef("fake:a", "fake", "local", "chat"))
    b = FakeChatModel([Sleep(0.02), TextDelta(ANSWER)], ModelRef("fake:b", "fake", "local", "chat"))
    c = FakeChatModel([TextDelta(ANSWER)], ModelRef("fake/c", "fake", "cloud", "chat"))
    async with eval_app(tmp_path, a, b, c, SchemaJudge()) as (app, client):
        run_id, snapshot, events = await _run(
            client, ["fake:a", "fake:b", "fake/c"], QUESTIONS, judge="fake:j", allow_cloud=True
        )
        assert snapshot["status"] == "ok"

    def at(type_, lane, **match):
        for i, e in enumerate(events):
            data = e["data"]
            if (
                e["type"] == type_
                and data.get("lane") == lane
                and all(data.get(k) == v for k, v in match.items())
            ):
                return i
        raise AssertionError((type_, lane, match))

    # Le second modèle local ne commence qu'après toutes les réponses du premier (pas de chargement
    # alterné entre deux questions) ; le cloud répond sans attendre la place.
    assert at("eval_answer", "fake:a", question_index=1) < at(
        "lane_status", "fake:b", status="generating"
    )
    assert at("eval_answer", "fake/c", question_index=1) < at(
        "eval_answer", "fake:a", question_index=1
    )
    # La notation ne commence qu'une fois toutes les réponses données.
    last_answer = max(i for i, e in enumerate(events) if e["type"] == "eval_answer")
    assert last_answer < min(i for i, e in enumerate(events) if e["type"] == "eval_metric")
    assert _status(events, "fake:b") == ["waiting", "generating", "judging", "done"]
    cloud_leaves = [c for c in snapshot["children"] if c["model"] == "fake/c"]
    assert {c["metrics"]["origin"] for c in cloud_leaves if c["kind"] == "generation"} == {"cloud"}


async def test_a_cloud_judge_is_allowed_with_allow_cloud(tmp_path):
    judge = SchemaJudge("fake/j", "cloud")
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (_, client):
        _, snapshot, events = await _run(client, ["fake:a"], judge="fake/j", allow_cloud=True)
    assert _of(events, "judge")[0]["origin"] == "cloud"
    assert _metric(events, "fake:a", "faithfulness")["score"] == 67
    assert {c["model"] for c in snapshot["children"] if c["kind"] == "judge"} == {"fake/j"}


# --- annulation, redémarrage, effacement -------------------------------------------------------


async def test_a_cancelled_evaluation_keeps_its_scores_and_says_the_rest_was_stopped(tmp_path):
    judge = SchemaJudge()
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (app, client):
        judge.freeze_after = 4  # une fidélité (1 + 3 appels) est notée, puis le juge se fige
        response = await _post(client, ["fake:a"], QUESTIONS, judge="fake:j")
        run_id = response.json()["run_id"]
        await _until(app, run_id, lambda ev: any(e["type"] == "eval_metric" for e in ev))
        cancelled = (await client.post(f"/api/runs/{run_id}/cancel")).json()
        assert cancelled["cancelled"] is True
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)

    assert snapshot["status"] == "cancelled" and snapshot["partial"] is True
    done = snapshot["evaluations"]
    assert done and all(r["score"] is not None for r in done)  # les notes déjà là sont gardées
    assert snapshot["erased"] is False
    missing = snapshot["missing"]
    assert len(done) + len(missing) == 1 * len(QUESTIONS) * len(METRICS)
    assert missing and all(
        m["score"] is None and m["reason"] == NOT_EVALUATED_STOPPED for m in missing
    )
    assert {(m["lane"], m["question_index"], m["metric"]) for m in missing}.isdisjoint(
        {(r["lane"], r["question_index"], r["metric"]) for r in done}
    )
    assert _status(events, "fake:a")[-1] == "cancelled"
    assert events[-1]["type"] == "run_ended" and events[-1]["data"]["status"] == "cancelled"
    # Jamais 0 pour une note manquante : aucune ligne `evaluations` à 0 qui n'ait été notée.
    summary = snapshot["summary"]["fake:a"]["faithfulness"]
    assert summary["evaluated"] + summary["not_evaluated"] == len(QUESTIONS)


async def test_an_evaluation_interrupted_by_a_restart_is_partial_too(tmp_path):
    judge = SchemaJudge()
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (app, client):
        judge.freeze_after = 4
        run_id = (await _post(client, ["fake:a"], QUESTIONS, judge="fake:j")).json()["run_id"]
        await _until(app, run_id, lambda ev: any(e["type"] == "eval_metric" for e in ev))
        await client.post(f"/api/runs/{run_id}/cancel")
        await _ended(client, run_id)
    # Arrêt brutal simulé : le run est resté `running`, sans `run_ended`.
    db = next((tmp_path / "data").glob("*.db"))
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE runs SET status = 'running', ended_at = NULL")
        conn.execute("DELETE FROM run_events WHERE type = 'run_ended'")
    async with eval_app(tmp_path, local("fake:a", ANSWER), docs=False) as (_, client):
        snapshot = (await client.get(f"/api/runs/{run_id}")).json()
        events = await _events(client, run_id)
    assert snapshot["status"] == "interrupted" and snapshot["partial"] is True
    assert snapshot["missing"] and all(m["score"] is None for m in snapshot["missing"])
    assert snapshot["evaluations"] and events[-1]["data"]["status"] == "interrupted"


async def test_erasing_an_evaluation_removes_its_text_and_scores_and_keeps_the_runs(tmp_path):
    judge = SchemaJudge()
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (app, client):
        run_id, snapshot, _ = await _run(client, ["fake:a"], [SECRET_QUESTION], judge="fake:j")
        kids = len(snapshot["children"])
        assert (await client.delete(f"/api/rag/eval/runs/{run_id}")).status_code == 204
        assert (
            await client.delete(f"/api/rag/eval/runs/{run_id}")
        ).status_code == 204  # idempotent
        after = (await client.get(f"/api/runs/{run_id}")).json()
        store = app.state.store
        assert store.read("SELECT count(*) AS n FROM evaluations")[0]["n"] == 0
        assert (
            store.read("SELECT count(*) AS n FROM run_events WHERE run_id = ?", (run_id,))[0]["n"]
            == 0
        )
        assert (
            store.read(
                "SELECT count(*) AS n FROM runs WHERE id = ? OR parent_run_id = ?", (run_id, run_id)
            )[0]["n"]
            == kids + 1
        )

    assert after["erased"] is True and after["config"] is None and after["evaluations"] == []
    assert after["status"] == "ok" and len(after["children"]) == kids  # le registre carbone reste
    for path in (tmp_path / "data").glob("*.db*"):
        data = path.read_bytes()
        assert SECRET_QUESTION.encode() not in data, path.name  # ni dans le .db ni dans le -wal
        assert ANSWER.encode() not in data, path.name


async def test_past_evaluations_are_listed_newest_first_without_the_erased_ones(tmp_path):
    """Décision n° 14 : la 7.3 liste les évaluations passées, les plus récentes d'abord."""
    judge = SchemaJudge()
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (_, client):
        first, _, _ = await _run(client, ["fake:a"], [SECRET_QUESTION], judge="fake:j")
        second, _, _ = await _run(client, ["fake:a"], QUESTIONS, judge="fake:j")
        listed = (await client.get("/api/rag/eval/runs")).json()["runs"]
        assert [r["run_id"] for r in listed] == [second, first]
        assert listed[0]["models"] == ["fake:a"]  # une feuille par question, un modèle listé
        assert listed[0]["question_count"] == 2 and listed[0]["question"] == QUESTIONS[0]
        assert listed[0]["status"] == "ok" and listed[0]["ended_at"]
        limited = (await client.get("/api/rag/eval/runs?limit=1")).json()["runs"]
        assert [r["run_id"] for r in limited] == [second]
        assert (await client.get("/api/rag/eval/runs?limit=0")).status_code == 422
        assert (await client.delete(f"/api/rag/eval/runs/{first}")).status_code == 204
        after = (await client.get("/api/rag/eval/runs")).json()["runs"]
        assert [r["run_id"] for r in after] == [second]  # effacée : plus rien à rouvrir
        assert (await client.get("/api/arena/runs")).json()["runs"] == []  # pas une Arène


async def test_erasing_refuses_an_active_or_foreign_run(tmp_path):
    judge = SchemaJudge()
    judge.sleep = 0.3
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (_, client):
        run_id = (await _post(client, ["fake:a"], judge="fake:j")).json()["run_id"]
        busy = await client.delete(f"/api/rag/eval/runs/{run_id}")
        assert busy.status_code == 409 and busy.json()["code"] == "run_busy"
        await client.post(f"/api/runs/{run_id}/cancel")
        await _ended(client, run_id)
        missing = await client.delete("/api/rag/eval/runs/inconnu")
        assert missing.status_code == 404 and missing.json()["code"] == "run_not_found"


async def test_the_base_cannot_be_changed_while_an_evaluation_runs(tmp_path):
    judge = SchemaJudge()
    judge.sleep = 0.3
    async with eval_app(tmp_path, local("fake:a", ANSWER), judge) as (app, client):
        run_id = (await _post(client, ["fake:a"], judge="fake:j")).json()["run_id"]
        listed = (await client.get("/api/rag/documents")).json()["documents"]
        refused = await client.delete(f"/api/rag/documents/{listed[0]['id']}")
        assert refused.status_code == 409 and refused.json()["code"] == "base_in_use"
        assert refused.json()["detail"]["kind"] == "eval"
        await client.post(f"/api/runs/{run_id}/cancel")


async def test_the_judge_service_is_the_one_of_the_arena(tmp_path):
    async with eval_app(tmp_path, local("fake:a", ANSWER)) as (app, _):
        assert isinstance(app.state.evaluation._judge, Judge)


async def test_the_default_run_params_hold_no_typed_text(tmp_path):
    async with eval_app(tmp_path, local("fake:a", ANSWER), SchemaJudge()) as (app, client):
        run_id, snapshot, _ = await _run(client, ["fake:a"], [SECRET_QUESTION], judge="fake:j")
    assert SECRET_QUESTION not in json.dumps(snapshot["params"])
    assert set(snapshot["params"]) == {
        "allow_cloud", "judge", "embedding_model", "top_k", "question_count", "strategy",
    }  # fmt: skip
