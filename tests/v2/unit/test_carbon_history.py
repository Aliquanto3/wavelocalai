"""Historique carbone (story 5.2, AD-10, AD-13, D-37) : une ligne par session close, calculée depuis
les feuilles de `runs` ; la remise à zéro n'efface rien et un run actif reste dans sa session."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from wavelocalai.greenops.history import carbon_history
from wavelocalai.greenops.session import session_summary
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import Co2, LeafResult
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


async def history(store, hub, window="all", now=None):
    return (await carbon_history(store, hub.app_session_id, window, now))["sessions"]


async def test_the_session_in_progress_is_not_in_the_history_until_it_is_closed(store, hub):
    await produce_chat(hub)
    assert await history(store, hub) == []  # D-37 : la session en cours n'y figure pas
    first = hub.app_session_id
    await hub.new_app_session("reset")
    rows = await history(store, hub)
    assert [row["id"] for row in rows] == [first]
    assert rows[0]["total_mg"] == pytest.approx(1.5) and rows[0]["measured_runs"] == 1


async def test_a_closed_row_gives_start_end_total_local_cloud_and_unmeasurable(store, hub):
    await produce_chat(hub)  # local 1,5 mg
    rag = await hub.create_run("rag", models=["m:1b"], user_message="Q ?")
    await hub.finish_leaf(rag.run_id, LeafResult(origin="cloud"), CLOUD_CO2)  # cloud 4 mg
    agent = await hub.create_run("agent", models=["m:1b"], user_message="Q ?")
    await hub.finish_leaf(agent.run_id, LeafResult(origin="local"), UNMEASURED)
    session = hub.app_session_id
    await hub.new_app_session("reset")
    (row,) = await history(store, hub)
    assert row["id"] == session
    assert row["total_mg"] == pytest.approx(5.5)
    assert row["local_mg"] == pytest.approx(1.5) and row["cloud_mg"] == pytest.approx(4.0)
    assert row["measured_runs"] == 2 and row["unmeasurable_runs"] == 1
    assert row["started_at"] <= row["ended_at"]
    # Les mêmes chiffres que ceux de la session quand elle était en cours.
    summary = await session_summary(store, session)
    assert summary["total_mg"] == pytest.approx(row["total_mg"])


async def test_a_session_with_nothing_measured_keeps_its_place_with_a_null_total(store, hub):
    agent = await hub.create_run("agent", models=["m:1b"], user_message="Q ?")
    await hub.finish_leaf(agent.run_id, LeafResult(origin="local"), UNMEASURED)
    await hub.new_app_session("reset")
    (row,) = await history(store, hub)
    # Jamais 0 pour un inconnu (AD-10) : le total et le local (des réponses sans mesure) sont nuls ;
    # le cloud, sans aucune réponse, vaut exactement 0.
    assert row["total_mg"] is None and row["local_mg"] is None and row["cloud_mg"] == 0.0
    assert row["measured_runs"] == 0 and row["unmeasurable_runs"] == 1


async def test_an_origin_without_any_answer_is_exactly_zero_not_unknown(store, hub):
    rag = await hub.create_run("rag", models=["m:1b"], user_message="Q ?")
    await hub.finish_leaf(rag.run_id, LeafResult(origin="cloud"), CLOUD_CO2)
    await hub.new_app_session("reset")
    (row,) = await history(store, hub)
    assert row["local_mg"] == 0.0 and row["cloud_mg"] == pytest.approx(4.0)


async def test_an_origin_whose_answers_are_all_unmeasurable_is_unknown(store, hub):
    chat = await hub.create_run("chat", models=["m:1b"], user_message="Q ?")
    await hub.finish_leaf(chat.run_id, LeafResult(origin="local"), LOCAL_CO2)
    rag = await hub.create_run("rag", models=["m:1b"], user_message="Q ?")
    await hub.finish_leaf(rag.run_id, LeafResult(origin="cloud"), UNMEASURED)
    await hub.new_app_session("reset")
    (row,) = await history(store, hub)
    assert row["cloud_mg"] is None and row["local_mg"] == pytest.approx(1.5)
    assert row["total_mg"] == pytest.approx(1.5)


async def test_a_session_without_any_counted_run_is_not_listed(store, hub):
    await hub.new_app_session("reset")  # un démarrage sans réponse
    await produce_chat(hub)
    await hub.new_app_session("reset")
    assert len(await history(store, hub)) == 1


async def test_only_leaves_are_counted_arena_parent_and_ingest_never(store, hub):
    parent, leaves = await produce_arena(hub)
    for leaf in leaves:
        await hub.finish_leaf(leaf.run_id, LeafResult(origin="local"), LOCAL_CO2)
    await hub.finish_run(parent.run_id)
    await hub.new_app_session("reset")
    (row,) = await history(store, hub)
    assert row["measured_runs"] == 2 and row["total_mg"] == pytest.approx(3.0)


async def test_erasing_a_conversation_does_not_lower_the_history(store, hub):
    """AD-13 : `runs` survit à l'effacement, le registre carbone ne baisse pas."""
    handle = await produce_chat(hub)
    await hub.new_app_session("reset")
    before = (await history(store, hub))[0]["total_mg"]
    await hub.erase_conversation(handle.conversation_id)
    assert (await history(store, hub))[0]["total_mg"] == pytest.approx(before)


async def test_sessions_are_listed_from_the_oldest_to_the_most_recent(store, hub):
    ids = []
    for _ in range(3):
        await produce_chat(hub)
        ids.append(hub.app_session_id)
        await hub.new_app_session("reset")
    assert [row["id"] for row in await history(store, hub)] == ids


async def test_windows_keep_the_sessions_whose_last_answer_falls_inside(store, hub):
    await produce_chat(hub)
    await hub.new_app_session("reset")
    soon = datetime.now(UTC)
    assert len(await history(store, hub, "7d", soon)) == 1
    assert len(await history(store, hub, "7d", soon + timedelta(days=8))) == 0
    assert len(await history(store, hub, "30d", soon + timedelta(days=8))) == 1
    assert len(await history(store, hub, "30d", soon + timedelta(days=31))) == 0
    assert len(await history(store, hub, "all", soon + timedelta(days=3650))) == 1


async def test_an_unknown_window_is_refused(store, hub):
    with pytest.raises(ValueError):
        await carbon_history(store, hub.app_session_id, "1y")


# --- Remise à zéro et run actif ---------------------------------------------------------------


async def test_an_active_run_keeps_counting_in_the_session_where_it_started(store, hub):
    """Une feuille créée après la remise à zéro par un run racine ouvert avant elle reste dans la
    session de son parent : le run est compté là où il a commencé (story 5.2)."""
    await produce_chat(hub)  # la session a une réponse comptée : le compteur n'est pas vide
    first = hub.app_session_id
    parent = await hub.create_run("arena", models=["a:1b", "b:1b"], params={"judge": "j:1b"})
    early = await hub.create_run("generation", models=["a:1b"], parent_run_id=parent.run_id)

    second = await hub.new_app_session("reset")  # remise à zéro pendant l'Arène

    late = await hub.create_run("generation", models=["b:1b"], parent_run_id=parent.run_id)
    for leaf in (early, late):
        await hub.finish_leaf(leaf.run_id, LeafResult(origin="local"), LOCAL_CO2)
    await hub.finish_run(parent.run_id)

    assert (await session_summary(store, second))["total_mg"] == 0.0  # rien dans la nouvelle
    assert (await session_summary(store, second))["measured_runs"] == 0
    closed = (await history(store, hub))[0]
    assert closed["id"] == first
    assert closed["measured_runs"] == 3  # le chat, puis les deux voies de l'Arène
    assert closed["total_mg"] == pytest.approx(4.5)


async def test_a_run_started_after_the_reset_counts_in_the_new_session(store, hub):
    await produce_chat(hub)
    second = await hub.new_app_session("reset")
    await produce_chat(hub)
    assert (await session_summary(store, second))["total_mg"] == pytest.approx(1.5)
