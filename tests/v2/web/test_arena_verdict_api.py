"""Verdict local/cloud (story 3.5) dans l'instantané `GET /api/runs/{id}`, de bout en bout.

L'app est la vraie (hub, registre, service de l'Arène, juge, sémaphore) ; les modèles et le juge
sont des `FakeChatModel`. Les prix de ces tests sont fictifs : ils servent à vérifier le calcul,
la vraie table de `wavelocalai.toml` est vide tant qu'aucun prix sourcé n'est relevé.
"""

from __future__ import annotations

import json

from wavelocalai.models.fake import FakeChatModel, Sleep
from wavelocalai.models.port import ModelRef

from .test_arena_api import _ended, _events, _post, arena_app, children, cloud, local, say

PRICES = {
    "prices": {
        "currency": "EUR",
        "retrieved_at": "2026-03-04",
        "source": "https://exemple.invalid/prix",
        "models": {"fake/c": {"input_per_mtok": 2.0, "output_per_mtok": 10.0}},
    }
}


class AnswerJudge(FakeChatModel):
    """Un juge qui note selon la réponse qu'il lit : `{mot de la réponse: note}`."""

    def __init__(self, tag: str, by_word: dict[str, int], origin: str = "local") -> None:
        super().__init__([], ModelRef(tag, "fake", origin, "chat"))
        self.by_word = by_word

    async def stream(self, request):
        prompt = request.messages[-1].content
        score = next(note for word, note in self.by_word.items() if word in prompt)
        self.script = say(json.dumps({"score": score, "reason": "Réponse claire."}))
        async for chunk in super().stream(request):
            yield chunk


async def _verdict(client, run_id):
    snapshot = await _ended(client, run_id)
    return snapshot, snapshot.get("verdict", "absent")


async def test_the_snapshot_of_an_arena_carries_the_verdict(tmp_path):
    a, b = local("fake:a", say("Alpha")), local("fake:b", say("Bravo"))
    c = cloud("fake/c", say("La ", "lumière"))
    judge = AnswerJudge("fake:j", {"Alpha": 60, "Bravo": 82, "lumière": 90})
    async with arena_app(tmp_path, a, b, c, judge, cloud=PRICES) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", "fake/c", judge="fake:j")).json()[
            "run_id"
        ]
        snapshot, verdict = await _verdict(client, run_id)
        events = await _events(client, run_id)

    assert snapshot["status"] == "ok"
    assert verdict["leader"] == "cloud" and verdict["score_gap"] == 8
    assert verdict["local"]["model"] == "fake:b" and verdict["local"]["score"] == 82
    assert verdict["cloud"]["model"] == "fake/c" and verdict["cloud"]["score"] == 90
    kids = children(snapshot)
    # Le CO2 de chacun est celui de sa feuille (AD-10), tel que l'instantané le porte.
    assert verdict["local"]["co2"] == kids["fake:b"]["metrics"]["co2"]
    assert verdict["cloud"]["co2"] == kids["fake/c"]["metrics"]["co2"]
    # 1 000 x (4 tokens x 2 + 2 tokens x 10) / 1 000 000 : le prix daté de la table.
    assert verdict["cloud"]["cost"] == {"amount": 0.028, "currency": "EUR", "reason": None}
    assert verdict["local"]["cost"]["amount"] == 0.0
    assert verdict["requests"] == 1000
    assert verdict["price_table"] == {
        "retrieved_at": "2026-03-04",
        "source": "https://exemple.invalid/prix",
        "currency": "EUR",
    }
    assert verdict["data_on_device"] == {
        "models": ["fake:a", "fake:b"],
        "count": 2,
        "judge_off_device": False,
    }
    # Aucun type d'événement de plus : le verdict n'existe que dans l'instantané.
    assert "verdict" not in {event["type"] for event in events}
    assert "verdict" not in json.dumps(events)


async def test_a_cloud_model_absent_from_the_table_is_unknown_with_a_reason_never_zero(tmp_path):
    a, c = local("fake:a", say("Alpha")), cloud("fake/other", say("Lumière"))
    judge = AnswerJudge("fake:j", {"Alpha": 70, "Lumière": 65})
    async with arena_app(tmp_path, a, c, judge, cloud=PRICES) as (_, client):
        run_id = (await _post(client, "fake:a", "fake/other", judge="fake:j")).json()["run_id"]
        _, verdict = await _verdict(client, run_id)
    assert verdict["leader"] == "local" and verdict["score_gap"] == 5
    cost = verdict["cloud"]["cost"]
    assert cost["amount"] is None and "table de prix" in cost["reason"]
    assert verdict["price_table"]["retrieved_at"] == "2026-03-04"


async def test_the_shipped_empty_table_gives_an_unknown_cost(tmp_path):
    a, c = local("fake:a", say("Alpha")), cloud("fake/c", say("Lumière"))
    judge = AnswerJudge("fake:j", {"Alpha": 70, "Lumière": 65})
    async with arena_app(tmp_path, a, c, judge) as (_, client):  # table par défaut : vide
        run_id = (await _post(client, "fake:a", "fake/c", judge="fake:j")).json()["run_id"]
        _, verdict = await _verdict(client, run_id)
    assert verdict["cloud"]["cost"]["amount"] is None
    assert verdict["cloud"]["cost"]["reason"]
    assert verdict["price_table"]["retrieved_at"] is None


async def test_an_arena_without_cloud_or_without_scores_has_no_verdict(tmp_path):
    a, b = local("fake:a", say("Alpha")), local("fake:b", say("Bravo"))
    c = cloud("fake/c", say("Lumière"))
    judge = AnswerJudge("fake:j", {"Alpha": 70, "Bravo": 60})
    async with arena_app(tmp_path, a, b, c, judge, cloud=PRICES) as (_, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        snapshot, verdict = await _verdict(client, run_id)
        assert verdict is None  # pas de cloud : le classement suffit, la clé est là
        # Sans juge, aucune note : un cloud et un local non notés ne font pas de verdict.
        unscored = (await _post(client, "fake:a", "fake/c")).json()["run_id"]
        _, verdict = await _verdict(client, unscored)
    assert snapshot["kind"] == "arena" and verdict is None


async def test_a_cancelled_arena_has_no_verdict(tmp_path):
    a, c = local("fake:a", [Sleep(5.0), *say("Alpha")]), cloud("fake/c", say("Lumière"))
    judge = AnswerJudge("fake:j", {"Alpha": 70, "Lumière": 65})
    async with arena_app(tmp_path, a, c, judge, cloud=PRICES) as (_, client):
        run_id = (await _post(client, "fake:a", "fake/c", judge="fake:j")).json()["run_id"]
        await client.post(f"/api/runs/{run_id}/cancel")
        snapshot, verdict = await _verdict(client, run_id)
    assert snapshot["status"] == "cancelled" and verdict is None


async def test_a_cloud_judge_means_the_local_answers_left_the_device(tmp_path):
    a, c = local("fake:a", say("Alpha")), cloud("fake/c", say("Lumière"))
    judge = AnswerJudge("fake/judge", {"Alpha": 70, "Lumière": 65}, origin="cloud")
    async with arena_app(tmp_path, a, c, judge, cloud=PRICES) as (_, client):
        run_id = (await _post(client, "fake:a", "fake/c", judge="fake/judge")).json()["run_id"]
        _, verdict = await _verdict(client, run_id)
    assert verdict["data_on_device"]["judge_off_device"] is True
    assert verdict["data_on_device"]["models"] == ["fake:a"]


async def test_only_an_arena_has_a_verdict_field(served):
    _, client = served
    started = await client.post("/api/test/runs", json={"kind": "chat", "message": "Bonjour"})
    run_id = started.json()["run_id"]
    snapshot = await _ended(client, run_id)
    assert snapshot["kind"] == "chat" and "verdict" not in snapshot
