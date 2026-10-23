"""Le juge de l'Arène (story 3.3) : `judging`, `judge_score`, « non évalué » jamais 0, fiabilité.

L'app est la vraie (hub, registre, service de l'Arène, service de notation, sémaphore, flux SSE) ;
les modèles et le juge sont des `FakeChatModel` scriptés. Aucun Ollama, aucun réseau.
"""

from __future__ import annotations

import json

import pytest

from wavelocalai.errors import AppError, ProviderError
from wavelocalai.evaluation.judge import DEFAULT_CRITERIA, JUDGE_SCHEMA
from wavelocalai.models.defaults import ModelDefault
from wavelocalai.models.fake import Sleep
from wavelocalai.models.port import LoadState
from wavelocalai.models.registry import ModelInfo, ModelList

from .test_arena_api import (
    PROMPT,
    _ended,
    _events,
    _post,
    _until,
    arena_app,
    cloud,
    index,
    local,
    say,
    statuses,
)


def verdict(score: int, reason: str = "Réponse claire.") -> list:
    return say(json.dumps({"score": score, "reason": reason}))


def scores(events) -> dict[str, dict]:
    return {e["data"]["lane"]: e["data"] for e in events if e["type"] == "judge_score"}


def judge_event(events) -> dict:
    return next(e["data"] for e in events if e["type"] == "judge")


def progress_events(events, lane: str | None = None) -> list[dict]:
    return [
        e["data"]
        for e in events
        if e["type"] == "judge_progress" and (lane is None or e["data"]["lane"] == lane)
    ]


class StubDefaults:
    def __init__(self, *tags: str) -> None:
        self.tags = list(tags)
        self.calls: list[tuple[str, bool]] = []

    async def get(self, purpose: str, allow_cloud: bool = False) -> ModelDefault:
        self.calls.append((purpose, allow_cloud))
        if not self.tags:
            raise AppError("no_model", "aucun modèle", purpose=purpose)
        return ModelDefault(purpose=purpose, tags=self.tags, reason="test", source="rule")


def listed(tag: str, params_b: float | None, origin: str = "local") -> ModelList:
    info = ModelInfo(
        tag=tag,
        name=tag,
        provider="fake",
        origin=origin,
        kind="chat",
        available=True,
        params_active_b=params_b,
        co2_method="codecarbon",
    )
    return ModelList(models=[info], ollama_up=True, refreshed_at=None)


async def test_each_finished_lane_is_judged_then_done_and_the_judge_is_a_silent_child(tmp_path):
    a, b = local("fake:a", say("Les ", "plantes")), local("fake:b", say("Elles mangent"))
    judge = local("fake:j", verdict(72))
    async with arena_app(tmp_path, a, b, judge) as (app, client):
        response = await _post(
            client, "fake:a", "fake:b", judge="fake:j", criteria=["clarté", "exactitude"]
        )
        run_id = response.json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)
        assert app.state.local_slot.acquired == 4  # 2 générations et 2 notations, une place chacune

    for lane in ("fake:a", "fake:b"):
        assert statuses(events, lane) == ["waiting", "generating", "judging", "done"]
        got = scores(events)[lane]
        assert (
            got["score"] == 72 and got["reason"] == "Réponse claire." and got["judge"] == "fake:j"
        )
        assert index(events, "lane_status", lane, "judging") < index(events, "judge_score", lane)
        assert index(events, "judge_score", lane) < index(events, "lane_status", lane, "done")
    assert snapshot["status"] == "ok"
    # Une feuille `judge` par réponse, enfant de l'Arène, mesurée comme les autres (AD-5, AD-10).
    kids = [c for c in snapshot["children"] if c["kind"] == "judge"]
    assert len(kids) == 2 and all(k["model"] == "fake:j" and k["status"] == "ok" for k in kids)
    assert all(k["parent_run_id"] == run_id for k in kids)
    assert all(k["metrics"]["co2"]["method"] == "codecarbon" for k in kids)
    # Appel silencieux : le juge n'a ni colonne, ni jetons, ni métriques dans le flux de l'Arène.
    assert not [e for e in events if e["data"].get("lane") == "fake:j"]
    assert not [e for e in events if e["type"] == "model_loading"]
    # Le juge reçoit la question, les critères, la réponse, et le schéma de sortie.
    request = judge.requests[0]
    assert request.response_schema == JUDGE_SCHEMA and request.temperature == 0.0
    prompt = request.messages[-1].content
    assert PROMPT in prompt and "- clarté" in prompt and "- exactitude" in prompt
    assert any(m in prompt for m in ("Les plantes", "Elles mangent"))


async def test_default_criteria_are_sent_when_none_are_given(tmp_path):
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    judge = local("fake:j", verdict(50))
    async with arena_app(tmp_path, a, b, judge) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    prompt = judge.requests[0].messages[-1].content
    assert all(f"- {c}" in prompt for c in DEFAULT_CRITERIA)
    assert judge_event(events)["default_criteria"] == list(DEFAULT_CRITERIA)
    assert [e for e in events if e["type"] == "question"][0]["data"]["criteria"] == []


async def test_an_empty_answer_is_not_evaluated_and_never_zero(tmp_path):
    a, b = local("fake:a", []), local("fake:b", say("B"))
    judge = local("fake:j", verdict(60))
    async with arena_app(tmp_path, a, b, judge) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    empty = scores(events)["fake:a"]
    assert empty["score"] is None and empty["reason"] == "non évalué : réponse vide"
    assert statuses(events, "fake:a") == ["waiting", "generating", "done"]  # pas de notation
    assert scores(events)["fake:b"]["score"] == 60
    assert len(judge.requests) == 1  # le juge n'est pas dérangé pour une réponse vide


@pytest.mark.parametrize(
    ("script", "reason"),
    [
        (say("pas du json"), "non évalué : sortie du juge invalide"),
        (say('{"score": 150, "reason": "trop"}'), "non évalué : sortie du juge invalide"),
        ([ProviderError("ollama_down", "Ollama éteint")], "non évalué : juge indisponible"),
        ([ProviderError("cloud_key_missing", "clé", provider="openai")], "juge indisponible"),
    ],
)
async def test_invalid_or_unavailable_judge_gives_null_with_a_reason_never_zero(
    tmp_path, script, reason
):
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    judge = local("fake:j", script)
    async with arena_app(tmp_path, a, b, judge) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)
    assert snapshot["status"] == "ok"  # l'orchestration aboutit, le juge en panne n'y change rien
    for lane in ("fake:a", "fake:b"):
        got = scores(events)[lane]
        assert got["score"] is None and reason in got["reason"]
        assert statuses(events, lane)[-1] == "done"  # la réponse reste lisible et terminée


async def test_a_judge_that_is_also_a_lane_keeps_that_lanes_own_metrics(tmp_path):
    a = local("fake:a", verdict(88))  # la réponse de A est elle-même un JSON de note
    b = local("fake:b", say("B"))
    async with arena_app(tmp_path, a, b) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:a")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    for lane in ("fake:a", "fake:b"):
        assert len([e for e in events if e["type"] == "metrics" and e["data"]["lane"] == lane]) == 1


async def test_without_any_judge_scores_are_not_evaluated(tmp_path):
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    async with arena_app(tmp_path, a, b) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    info = judge_event(events)
    assert info["model"] is None and info["single_judge"] is False and info["unreliable"] is None
    for lane in ("fake:a", "fake:b"):
        got = scores(events)[lane]
        assert got["score"] is None and got["reason"] == "non évalué : juge indisponible"
        assert got["judge"] is None


async def test_the_default_judge_is_used_and_a_small_one_is_flagged_unreliable(tmp_path):
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    judge = local("fake:j", verdict(40))
    async with arena_app(tmp_path, a, b, judge) as (app, client):
        defaults = app.state.arena._defaults = StubDefaults("fake:j")
        small = listed("fake:j", 1.5)

        async def list_small(*, allow_cloud: bool = False):
            return small

        app.state.registry.list_models = list_small
        run_id = (await _post(client, "fake:a", "fake:b", allow_cloud=False)).json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)
        root = app.state.store.read("SELECT params FROM runs WHERE id = ?", (run_id,))[0]
    assert defaults.calls == [("judge", False)]
    info = judge_event(events)
    assert info == {
        "model": "fake:j",
        "origin": "local",
        "params_active_b": 1.5,
        "unreliable": True,  # moins de ~4 milliards de paramètres actifs
        "single_judge": True,
        "chosen": "default",
        "default_criteria": list(DEFAULT_CRITERIA),
    }
    assert json.loads(root["params"])["judge"] == "fake:j"  # le juge retenu, pas seulement demandé
    assert scores(events)["fake:a"]["score"] == 40 and snapshot["status"] == "ok"


async def test_a_large_judge_is_not_flagged_and_unknown_size_counts_as_small(tmp_path):
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    judge = local("fake:j", verdict(90))
    results = {}
    async with arena_app(tmp_path, a, b, judge) as (app, client):
        for params_b in (8.0, None):
            model_list = listed("fake:j", params_b)

            async def list_models(*, allow_cloud: bool = False, _l=model_list):
                return _l

            app.state.registry.list_models = list_models
            run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
            await _ended(client, run_id)
            results[params_b] = judge_event(await _events(client, run_id))
    assert results[8.0]["unreliable"] is False and results[8.0]["chosen"] == "request"
    assert results[None]["unreliable"] is True and results[None]["params_active_b"] is None


async def test_a_cloud_judge_is_never_chosen_without_allow_cloud(tmp_path):
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    remote = cloud("fake/j", verdict(95))
    async with arena_app(tmp_path, a, b, remote) as (app, client):
        # Explicite : refusé avant tout appel.
        refused = await _post(client, "fake:a", "fake:b", judge="fake/j", allow_cloud=False)
        assert refused.status_code == 403 and refused.json()["code"] == "cloud_not_allowed"
        # Par défaut : même si le défaut visait un modèle cloud, le registre le refuse et il n'y a
        # pas de juge (jamais de repli silencieux vers le cloud).
        app.state.arena._defaults = StubDefaults("fake/j")
        run_id = (await _post(client, "fake:a", "fake:b", allow_cloud=False)).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
        assert remote.opened == 0
    assert judge_event(events)["model"] is None
    assert scores(events)["fake:a"]["reason"] == "non évalué : juge indisponible"


async def test_a_cloud_judge_with_allow_cloud_runs_in_parallel_without_the_slot(tmp_path):
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    remote = cloud("fake/j", verdict(77))
    async with arena_app(tmp_path, a, b, remote) as (app, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake/j")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
        assert app.state.local_slot.acquired == 2  # les deux générations seulement
    info = judge_event(events)
    assert info["origin"] == "cloud" and info["unreliable"] is False
    assert scores(events)["fake:a"]["score"] == 77


async def test_a_cloud_judge_leaf_is_estimated_by_ecologits_not_left_unmeasurable(tmp_path):
    from ..fake_cloud import MODELS

    tag = MODELS[0][1]  # un modèle que ecologits connaît
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    remote = cloud(tag, verdict(80))
    async with arena_app(tmp_path, a, b, remote) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge=tag)).json()["run_id"]
        snapshot = await _ended(client, run_id)
    kids = [c for c in snapshot["children"] if c["kind"] == "judge"]
    assert len(kids) == 2
    for kid in kids:
        co2 = kid["metrics"]["co2"]
        assert co2["method"] == "ecologits" and co2["estimated"] is True and co2["mg"] > 0


async def test_cancelling_during_judging_cancels_the_lane_and_the_judge_leaf(tmp_path):
    a, b = local("fake:a", say("A")), local("fake:b", say("B"))
    judge = local("fake:j", [Sleep(30)])
    async with arena_app(tmp_path, a, b, judge) as (app, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        await _until(
            app,
            run_id,
            lambda ev: any(
                e["type"] == "lane_status" and e["data"]["status"] == "judging" for e in ev
            ),
        )
        result = await client.post(f"/api/runs/{run_id}/cancel")
        assert result.json()["status"] == "cancelled"
        snapshot = (await client.get(f"/api/runs/{run_id}")).json()
        events = await _events(client, run_id)
        assert not app.state.local_slot.busy
    assert snapshot["status"] == "cancelled"
    assert statuses(events, "fake:a")[-1] == "cancelled"
    assert not [e for e in events if e["type"] == "judge_score" and e["data"]["score"] == 0]
    judge_kids = [c for c in snapshot["children"] if c["kind"] == "judge"]
    assert judge_kids and all(k["status"] == "cancelled" for k in judge_kids)


async def test_judge_progress_is_published_queued_then_scoring_with_position_and_total(tmp_path):
    """Story 9.3 : `queued` juste avant la place, `scoring` pendant la notation elle-même (le juge
    `fake:j` ne charge pas, pas de `loading` ici) ; `position`/`total` comptent les deux colonnes.
    """
    a, b = local("fake:a", say("Les ", "plantes")), local("fake:b", say("Elles mangent"))
    judge = local("fake:j", [verdict(72)[0], verdict(60)[0]])
    async with arena_app(tmp_path, a, b, judge) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    positions = set()
    for lane in ("fake:a", "fake:b"):
        phases = progress_events(events, lane)
        assert [p["phase"] for p in phases] == ["queued", "scoring"]
        # Rang d'arrivée chez le juge : stable pour une colonne, distinct d'une colonne à l'autre.
        assert len({p["position"] for p in phases}) == 1, phases
        positions.add(phases[0]["position"])
        assert all(p["total"] == 2 and p["judge"] == "fake:j" for p in phases), phases
        assert index(events, "lane_status", lane, "judging") < index(events, "judge_progress", lane)
        assert index(events, "judge_progress", lane) < index(events, "judge_score", lane)
    assert positions == {1, 2}


async def test_judge_progress_reports_loading_when_the_judge_warms_up(tmp_path):
    """Revue 9.3 : ordre réel queued -> loading -> scoring (aucun `scoring` avant le chargement)."""
    a = local("fake:a", say("A"))
    judge = local("fake:j", [LoadState("loading"), LoadState("loaded", 0.2), *verdict(80)])
    async with arena_app(tmp_path, a, local("fake:b", say("B")), judge) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    for lane in ("fake:a", "fake:b"):
        assert [p["phase"] for p in progress_events(events, lane)] == [
            "queued",
            "loading",
            "scoring",
        ]


async def test_a_warm_judge_that_reads_a_long_prompt_is_already_scoring(tmp_path):
    """Revue 9.3 : juge en mémoire (aucun chargement annoncé) qui tarde à son premier fragment :
    `scoring` part après le délai de grâce, avant la note."""
    judge = local("fake:j", [Sleep(0.6), *verdict(80)])
    async with arena_app(tmp_path, local("fake:a", say("A")), local("fake:b", say("B")), judge) as (
        _,
        client,
    ):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    assert [p["phase"] for p in progress_events(events, "fake:a")] == ["queued", "scoring"]


async def test_a_down_judge_publishes_only_queued(tmp_path):
    judge = local("fake:j", [ProviderError("ollama_down", "Ollama éteint")])
    async with arena_app(tmp_path, local("fake:a", say("A")), local("fake:b", say("B")), judge) as (
        _,
        client,
    ):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    assert [p["phase"] for p in progress_events(events, "fake:a")] == ["queued"]
    assert scores(events)["fake:a"]["reason"] == "non évalué : juge indisponible"


async def test_the_total_counts_only_columns_that_will_be_scored(tmp_path):
    """Revue 9.3 : une colonne en échec ou à réponse vide sort du `total` ; les colonnes encore
    chez le juge republient leur phase avec le total corrigé."""
    a = local("fake:a", say("A"))
    b = local("fake:b", [Sleep(0.5), ProviderError("ollama_error", "refus")])
    c = local("fake:c", [Sleep(0.5)])  # réponse vide
    # Juge cloud, sans place : il note pendant que b et c génèrent encore.
    judge = cloud("fake/j", [Sleep(1.5), *verdict(70)])
    async with arena_app(tmp_path, a, b, c, judge) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", "fake:c", judge="fake/j")).json()[
            "run_id"
        ]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    progress = progress_events(events, "fake:a")
    assert [(p["phase"], p["total"]) for p in progress] == [
        ("queued", 3),  # b et c génèrent encore
        ("scoring", 3),
        ("scoring", 2),  # b en échec
        ("scoring", 1),  # c sans réponse
    ]
    assert progress_events(events, "fake:b") == progress_events(events, "fake:c") == []


async def test_judge_progress_is_not_published_for_an_empty_answer_or_without_a_judge(tmp_path):
    a, b = local("fake:a", []), local("fake:b", say("B"))
    async with arena_app(tmp_path, a, b) as (_, client):  # pas de juge
        run_id = (await _post(client, "fake:a", "fake:b")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    assert progress_events(events) == []
    # Story 8.5 (vu en CI Windows, `assert 2 == 1`) : sans pause, le juge de `fake:b` pouvait
    # prendre la place locale avant que `fake:a` la demande ; `fake:b` était alors noté avec un total
    # de 2, juste à cet instant, et jamais republié. Une seconde de génération pour `fake:b` laisse
    # à `fake:a` le temps d'attendre la place avant le juge (file d'attente FIFO), quel que soit
    # l'ordre de départ des deux lanes.
    b = local("fake:b", [Sleep(1.0), *say("B")])
    judge = local("fake:j", verdict(50))
    async with arena_app(tmp_path, a, b, judge) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
    assert progress_events(events, "fake:a") == []  # réponse vide : le juge n'est pas dérangé
    b = progress_events(events, "fake:b")
    # La réponse vide de `fake:a` peut sortir du total pendant que `fake:b` attend : sa phase est
    # alors republiée avec le total corrigé (revue 9.3).
    phases = [p["phase"] for p in b]
    assert [x for i, x in enumerate(phases) if i == 0 or x != phases[i - 1]] == [
        "queued",
        "scoring",
    ]
    assert b[-1]["total"] == 1


async def test_without_a_scoring_service_a_named_judge_is_not_announced(tmp_path):
    """Revue : sans service de notation, l'événement `judge` n'annonce pas un juge qui ne notera
    pas, et `runs.params.judge` reste vide ; le juge nommé n'est jamais appelé."""
    a, b, j = local("fake:a", say("A")), local("fake:b", say("B")), local("fake:j", verdict(90))
    async with arena_app(tmp_path, a, b, j) as (app, client):
        app.state.arena._judge = None
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        await _ended(client, run_id)
        events = await _events(client, run_id)
        root = app.state.store.read("SELECT params FROM runs WHERE id = ?", (run_id,))[0]
    assert judge_event(events)["model"] is None and judge_event(events)["chosen"] == "none"
    assert json.loads(root["params"])["judge"] is None
    assert all(s["score"] is None and s["judge"] is None for s in scores(events).values())
    assert not j.requests
