"""Session carbone (AD-10) : somme des feuilles de l'`app_session` courante, rien que les feuilles."""

from __future__ import annotations

from pathlib import Path

import pytest

from wavelocalai.greenops.session import announce_carbon_updated, session_summary
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import Co2, LeafResult
from wavelocalai.runs.system_bus import SystemFeed
from wavelocalai.store.db import Store, db_path

from ..producers import LOCAL_CO2, produce_arena, produce_chat

CLOUD_CO2 = Co2(mg=4.0, method="ecologits", estimated=True)
UNMEASURED = Co2(mg=None, method="unmeasurable", reason="modèle absent de la table")


@pytest.fixture
async def store(tmp_path: Path):
    opened = Store.open(db_path(tmp_path / "data"))
    yield opened
    opened.close()


@pytest.fixture
async def hub(store: Store):
    started = RunHub(store, batch_interval_s=3600)
    await started.start()
    yield started
    await started.stop()


async def test_session_without_run_is_zero_and_nothing_unmeasurable(store, hub):
    summary = await session_summary(store, hub.app_session_id)
    assert summary["total_mg"] == 0.0 and summary["unmeasurable_runs"] == 0
    assert summary["measured_runs"] == 0 and summary["by_module"] == {}
    assert summary["by_origin"] == {
        "local": {"mg": 0.0, "runs": 0, "unmeasurable_runs": 0},
        "cloud": {"mg": 0.0, "runs": 0, "unmeasurable_runs": 0},
    }
    assert summary["app_session"]["id"] == hub.app_session_id
    assert summary["app_session"]["reason"] == "startup"


async def test_leaves_are_summed_by_module_and_by_origin(store, hub):
    await produce_chat(hub)  # local, 1,5 mg
    await produce_chat(hub)  # local, 1,5 mg
    rag = await hub.create_run("rag", models=["m:1b"], user_message="Q ?")
    await hub.finish_leaf(rag.run_id, LeafResult(origin="cloud"), CLOUD_CO2)
    summary = await session_summary(store, hub.app_session_id)
    assert summary["total_mg"] == pytest.approx(7.0)
    assert summary["by_origin"]["local"] == {
        "mg": pytest.approx(3.0),
        "runs": 2,
        "unmeasurable_runs": 0,
    }
    assert summary["by_origin"]["cloud"] == {
        "mg": pytest.approx(4.0),
        "runs": 1,
        "unmeasurable_runs": 0,
    }
    assert summary["by_module"]["chat"] == {
        "mg": pytest.approx(3.0),
        "runs": 2,
        "unmeasurable_runs": 0,
    }
    assert summary["by_module"]["rag"]["mg"] == pytest.approx(4.0)
    assert summary["measured_runs"] == 3 and summary["unmeasurable_runs"] == 0


async def test_unmeasurable_leaves_are_counted_apart_never_as_zero(store, hub):
    chat = await hub.create_run("chat", models=["m:1b"], user_message="Q ?")
    await hub.finish_leaf(chat.run_id, LeafResult(origin="cloud"), UNMEASURED)
    await produce_chat(hub)
    summary = await session_summary(store, hub.app_session_id)
    assert summary["total_mg"] == pytest.approx(1.5)
    assert summary["unmeasurable_runs"] == 1 and summary["measured_runs"] == 1
    assert summary["by_module"]["chat"]["unmeasurable_runs"] == 1
    assert summary["by_origin"]["cloud"] == {"mg": 0.0, "runs": 1, "unmeasurable_runs": 1}


async def test_a_composite_parent_is_never_counted_only_its_leaves(store, hub):
    parent, leaves = await produce_arena(hub, ("a:1b", "b:1b"))
    for leaf in leaves:
        await hub.finish_leaf(leaf.run_id, LeafResult(origin="local"), LOCAL_CO2)
    # Même si une ligne parent portait un `co2` (donnée corrompue), elle ne serait pas comptée.
    await store.awrite(
        lambda conn: conn.execute(
            "UPDATE runs SET co2_mg = 99, co2_method = 'codecarbon', co2_estimated = 0, origin = 'local' WHERE id = ?",
            (parent.run_id,),
        )
    )
    await hub.finish_run(parent.run_id)
    summary = await session_summary(store, hub.app_session_id)
    assert summary["total_mg"] == pytest.approx(3.0)  # 2 feuilles x 1,5 mg
    assert summary["by_module"] == {
        "arena": {"mg": pytest.approx(3.0), "runs": 2, "unmeasurable_runs": 0}
    }
    assert summary["measured_runs"] == 2


async def test_unfinished_leaves_are_not_counted_and_closed_leaves_without_co2_are_unmeasurable(
    store, hub
):
    running = await hub.create_run("chat", models=["m:1b"], user_message="Q ?")
    failed = await hub.create_run("agent", models=["m:1b"], user_message="Q ?")
    summary = await session_summary(store, hub.app_session_id)
    assert summary["measured_runs"] == 0 and summary["unmeasurable_runs"] == 0  # tous actifs
    # Une feuille en erreur ou annulée sans `co2` n'a pas de mesure : non-mesurable, jamais oubliée.
    await hub.finish_leaf(failed.run_id, LeafResult(status="error", origin="local"))
    await hub.cancel(running.run_id)
    summary = await session_summary(store, hub.app_session_id)
    assert summary["measured_runs"] == 0 and summary["unmeasurable_runs"] == 2
    assert summary["total_mg"] == 0.0
    assert summary["by_module"]["agent"] == {"mg": 0.0, "runs": 1, "unmeasurable_runs": 1}
    assert summary["by_origin"]["local"]["runs"] == 2


async def test_a_new_app_session_restarts_the_sum_and_keeps_the_history(store, hub):
    await produce_chat(hub)
    first = hub.app_session_id
    second = await hub.new_app_session("reset")
    assert (await session_summary(store, second))["total_mg"] == 0.0
    await produce_chat(hub)
    assert (await session_summary(store, second))["total_mg"] == pytest.approx(1.5)
    assert (await session_summary(store, first))["total_mg"] == pytest.approx(1.5)


async def test_announce_publishes_carbon_updated_on_the_system_bus(store, hub):
    await produce_chat(hub)
    feed = SystemFeed()
    with feed.subscribe() as queue:
        summary = await announce_carbon_updated(feed, store, hub.app_session_id)
        envelope = queue.get_nowait()
    assert envelope["type"] == "carbon_updated" and envelope["run_id"] is None
    assert envelope["data"] == summary and summary["total_mg"] == pytest.approx(1.5)
