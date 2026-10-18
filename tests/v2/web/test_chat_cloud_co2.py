"""CO2 d'une réponse cloud (story 2.5) : estimé par ecologits ou « non mesurable », jamais 0.

L'app est la vraie ; le fournisseur est simulé sous son SDK (aucun réseau) et ecologits calcule sur
ses tables locales. Chaque réponse publie `carbon_updated` sur le flux système.
"""

from __future__ import annotations

import asyncio

import pytest

from ..fake_cloud import MODELS, SETTINGS_CLOUD, Plan, stream_for
from .test_chat_cloud_api import _ended, _events, _fake, _post, cloud_app

OPENAI_TAG = MODELS[0][1]
GROQ_TAG = MODELS[1][1]


async def _run_and_wait_update(app, client, tag):
    """Lance une réponse cloud et rend (run_id, `carbon_updated` reçu) une fois le run terminé."""
    with app.state.system_feed.subscribe() as queue:
        started = (await _post(client, tag, allow_cloud=True)).json()
        assert (await _ended(client, started["run_id"]))["status"] == "ok"
        while True:
            envelope = await asyncio.wait_for(queue.get(), 5)
            if envelope and envelope["type"] == "carbon_updated":
                return started["run_id"], envelope["data"]


async def _metrics_co2(client, run_id):
    events = await _events(client, run_id)
    return next(e["data"] for e in events if e["type"] == "metrics")["co2"]


async def test_estimated_cloud_response_is_stored_and_announced(tmp_path):
    fake = _fake("openai", Plan(stream_for("openai", ["Bonjour", " nuage"], usage=(11, 200))))
    async with cloud_app(tmp_path, [fake]) as (app, client):
        run_id, summary = await _run_and_wait_update(app, client, OPENAI_TAG)
        co2 = await _metrics_co2(client, run_id)
        assert co2["method"] == "ecologits" and co2["estimated"] is True and co2["mg"] > 0
        assert co2["allocation"] == "direct"
        assert co2["reason"] is None or "moins précise" in co2["reason"]  # réserve d'ecologits
        row = app.state.store.read("SELECT * FROM runs WHERE id = ?", (run_id,))[0]
        assert row["co2_method"] == "ecologits" and row["co2_estimated"] == 1
        assert row["co2_mg"] == pytest.approx(co2["mg"])
        assert row["co2_range_low_mg"] == pytest.approx(co2["range_mg"]["low"])
        assert row["co2_range_high_mg"] == pytest.approx(co2["range_mg"]["high"])
        assert row["co2_allocation"] == "direct"
        # carbon_updated : la somme de la session compte cette feuille cloud, aucune non mesurable
        assert summary["total_mg"] == pytest.approx(co2["mg"])
        assert summary["by_origin"]["cloud"]["runs"] == 1
        assert summary["by_origin"]["cloud"]["unmeasurable_runs"] == 0
        assert summary["unmeasurable_runs"] == 0 and summary["measured_runs"] == 1
        assert (await client.get("/api/carbon/session")).json() == summary


async def test_groq_model_without_a_table_entry_is_unmeasurable_and_counted_apart(tmp_path):
    fake = _fake("groq", Plan(stream_for("groq", ["Salut"])))
    cloud = {**SETTINGS_CLOUD, "groq_ecologits": {}}
    async with cloud_app(tmp_path, [fake], cloud=cloud) as (app, client):
        run_id, summary = await _run_and_wait_update(app, client, GROQ_TAG)
        co2 = await _metrics_co2(client, run_id)
        assert co2["method"] == "unmeasurable" and co2["mg"] is None and co2["range_mg"] is None
        assert "Groq" in co2["reason"] and co2["estimated"] is False
        row = app.state.store.read("SELECT * FROM runs WHERE id = ?", (run_id,))[0]
        assert row["co2_mg"] is None and row["co2_method"] == "unmeasurable" and row["co2_reason"]
        assert summary["total_mg"] == 0.0 and summary["measured_runs"] == 0
        assert summary["unmeasurable_runs"] == 1
        assert summary["by_origin"]["cloud"] == {"mg": 0.0, "runs": 1, "unmeasurable_runs": 1}


async def test_groq_model_with_a_table_entry_is_estimated_on_the_open_model(tmp_path, monkeypatch):
    from ecologits.tracers import utils

    calls = []
    real = utils.llm_impacts

    def spy(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(utils, "llm_impacts", spy)
    fake = _fake("groq", Plan(stream_for("groq", ["Salut"])))
    async with cloud_app(tmp_path, [fake]) as (app, client):
        run_id, _ = await _run_and_wait_update(app, client, GROQ_TAG)
        assert (await _metrics_co2(client, run_id))["method"] == "ecologits"
    assert [(c["provider"], c["model_name"]) for c in calls] == [
        ("huggingface_hub", "openai/gpt-oss-20b")
    ]


async def test_an_ecologits_exception_leaves_the_run_ok_and_unmeasurable(tmp_path, monkeypatch):
    from ecologits.tracers import utils

    def boom(**kwargs):
        raise RuntimeError("table illisible")

    monkeypatch.setattr(utils, "llm_impacts", boom)
    fake = _fake("openai", Plan(stream_for("openai", ["Bonjour"])))
    async with cloud_app(tmp_path, [fake]) as (app, client):
        run_id, summary = await _run_and_wait_update(app, client, OPENAI_TAG)
        co2 = await _metrics_co2(client, run_id)
        assert co2["method"] == "unmeasurable" and co2["mg"] is None and co2["reason"]
        snapshot = (await client.get(f"/api/runs/{run_id}")).json()
        assert snapshot["status"] == "ok" and snapshot["error"] is None
        assert summary["unmeasurable_runs"] == 1 and summary["total_mg"] == 0.0


async def test_estimated_and_unmeasurable_responses_add_up_separately(tmp_path):
    openai = _fake("openai", Plan(stream_for("openai", ["Un"], usage=(11, 100))))
    groq = _fake("groq", Plan(stream_for("groq", ["Deux"])))
    cloud = {**SETTINGS_CLOUD, "groq_ecologits": {}}
    async with cloud_app(tmp_path, [openai, groq], cloud=cloud) as (app, client):
        first, _ = await _run_and_wait_update(app, client, OPENAI_TAG)
        _, summary = await _run_and_wait_update(app, client, GROQ_TAG)
        mg = (await _metrics_co2(client, first))["mg"]
        assert mg > 0 and summary["total_mg"] == pytest.approx(mg)
        assert summary["measured_runs"] == 1 and summary["unmeasurable_runs"] == 1
        assert summary["by_origin"]["cloud"]["runs"] == 2
