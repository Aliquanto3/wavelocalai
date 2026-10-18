"""Routes des conversations (story 2.6) : lecture, exports, effacement qui efface (AD-13).

Les conversations viennent des producteurs de test du hub (aucun adaptateur de modèle, aucun
réseau) ; l'app est la vraie, cycle de vie compris.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from wavelocalai.greenops.session import session_summary
from wavelocalai.inference.streaming import CANCELLED_CO2
from wavelocalai.runs.models import AssistantMessage, LeafResult
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..producers import LOCAL_CO2, produce_chat
from .conftest import served  # noqa: F401 - fixture

BASE = f"http://127.0.0.1:{TEST_PORT}"
FAKE_KEY = "gsk_FAKEKEYabcdefghijklmnop1234"
UNIQUE = "Zorglub-Quasimodo-7731"
ANSWER = "Reponse-Unique-Xylophone-9182"


async def two_exchanges(hub, first=UNIQUE, answer=ANSWER):
    one = await produce_chat(hub, first, tokens=(answer,))
    two = await produce_chat(
        hub, "Deuxième question", tokens=("Salut", " !"), conversation_id=one.conversation_id
    )
    return one.conversation_id, one.run_id, two.run_id


async def test_a_conversation_comes_back_as_displayed(served):  # noqa: F811
    app, client = served
    conv, first, second = await two_exchanges(app.state.hub)
    body = (await client.get(f"/api/conversations/{conv}")).json()
    assert body["id"] == conv and body["kind"] == "chat"
    assert body["model"] == "fake:1b" and body["temperature"] == 0.2
    assert body["active_run_id"] is None
    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", UNIQUE),
        ("assistant", ANSWER),
        ("user", "Deuxième question"),
        ("assistant", "Salut !"),
    ]
    reply = body["messages"][3]
    assert reply["run"]["run_id"] == second and reply["run"]["status"] == "ok"
    metrics = reply["run"]["metrics"]
    assert metrics["origin"] == "local" and metrics["tps"] == 42.0
    assert metrics["tps_source"] == "ollama_eval" and metrics["output_tokens"] == 2
    assert metrics["co2"] == LOCAL_CO2.as_dict()
    assert body["messages"][0]["run"]["run_id"] == first  # le message de la personne aussi


async def test_reasoning_and_the_partial_of_a_stopped_run_are_kept(served):  # noqa: F811
    app, client = served
    hub = app.state.hub
    handle = await hub.create_run("chat", models=["fake:1b"], user_message="Question")
    result = LeafResult(
        origin="local",
        assistant=AssistantMessage(content="Réponse", reasoning="Je réfléchis"),
    )
    await hub.finish_leaf(handle.run_id, result, LOCAL_CO2)
    stopped = await hub.create_run(
        "chat", models=["fake:1b"], user_message="Encore", conversation_id=handle.conversation_id
    )
    hub.publish_token(stopped.run_id, "fake:1b", "Début")
    await hub.cancel(stopped.run_id)
    url = f"/api/conversations/{handle.conversation_id}"
    messages = (await client.get(url)).json()["messages"]
    assert messages[1]["reasoning"] == "Je réfléchis"
    assert messages[3]["content"] == "Début" and messages[3]["run"]["status"] == "cancelled"


async def test_an_active_run_is_named_so_the_screen_can_follow_it(served):  # noqa: F811
    app, client = served
    handle = await produce_chat(app.state.hub, "En cours", finish=False)
    body = (await client.get(f"/api/conversations/{handle.conversation_id}")).json()
    assert body["active_run_id"] == handle.run_id
    assert [m["role"] for m in body["messages"]] == ["user"]  # la réponse arrivera par le flux


async def test_an_unknown_conversation_is_a_404_envelope(served):  # noqa: F811
    _, client = served
    for path in ("abc", "abc.json", "abc.md"):
        response = await client.get(f"/api/conversations/{path}")
        assert response.status_code == 404 and response.json()["code"] == "not_found"
    assert (await client.delete("/api/conversations/abc")).status_code == 404


async def test_the_list_gives_the_latest_conversation_first_and_filters_by_kind(
    served,
):  # noqa: F811
    app, client = served
    old = await produce_chat(app.state.hub, "Ancienne")
    new = await produce_chat(app.state.hub, "Récente")
    body = (await client.get("/api/conversations?kind=chat&limit=1")).json()
    assert [c["id"] for c in body["conversations"]] == [new.conversation_id]
    both = (await client.get("/api/conversations")).json()["conversations"]
    assert [c["id"] for c in both] == [new.conversation_id, old.conversation_id]
    assert both[0]["model"] == "fake:1b" and both[0]["message_count"] == 2
    assert (await client.get("/api/conversations?kind=rag")).json() == {"conversations": []}
    assert (await client.get("/api/conversations?kind=nope")).status_code == 422


async def test_json_export_has_messages_model_origin_rate_and_co2_with_method(served):  # noqa: F811
    app, client = served
    conv, _, _ = await two_exchanges(app.state.hub)
    response = await client.get(f"/api/conversations/{conv}.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"].startswith("attachment; filename=")
    assert response.headers["content-disposition"].endswith('.json"')
    document = json.loads(response.text)
    assert document["format"] == "wavelocalai.conversation/1"
    assert document["conversation"]["model"] == "fake:1b"
    assert "D3" in document["definitions"]["tps"]
    reply = document["messages"][3]
    assert reply["content"] == "Salut !" and reply["role"] == "assistant"
    assert reply["model"] == "fake:1b" and reply["origin"] == "local"
    assert reply["tps"] == 42.0 and reply["tps_source"] == "ollama_eval"
    assert reply["co2"]["method"] == "codecarbon" and reply["co2"]["mg"] == 1.5
    assert "origin" not in document["messages"][0]  # la question n'a ni mesure ni origine


async def test_markdown_export_reads_as_a_transcript(served):  # noqa: F811
    app, client = served
    conv, _, _ = await two_exchanges(app.state.hub)
    response = await client.get(f"/api/conversations/{conv}.md")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"].endswith('.md"')
    text = response.text
    assert text.startswith("# Conversation wavelocalai")
    assert f"## Vous\n\n{UNIQUE}" in text and f"## Modèle\n\n{ANSWER}" in text
    assert "fake:1b" in text and "origine : local" in text
    assert "débit : 42,0 tokens/s (mesuré par Ollama (D3))" in text
    assert "CO2 : 1,5 mg (codecarbon, mesuré)" in text


async def test_an_unmeasurable_co2_is_said_and_never_zero(served):  # noqa: F811
    app, client = served
    hub = app.state.hub
    handle = await hub.create_run("chat", models=["fake:1b"], user_message="Q")
    hub.declare_leaf(handle.run_id, CANCELLED_CO2)
    hub.publish_token(handle.run_id, "fake:1b", "Texte")
    await hub.cancel(handle.run_id)  # arrêtée : son co2 est « non mesurable »
    url = f"/api/conversations/{handle.conversation_id}"
    assert "non mesurable (réponse annulée avant la fin)" in (await client.get(url + ".md")).text
    document = (await client.get(url + ".json")).json()
    assert document["messages"][1]["co2"]["mg"] is None
    assert document["messages"][1]["status"] == "cancelled"


async def test_exports_never_contain_a_configured_api_key(tmp_path):
    settings = make_settings(
        tmp_path, environ={"WAVELOCALAI_TESTING": "1", "GROQ_API_KEY": FAKE_KEY}
    )
    assert FAKE_KEY in settings.secret_values()
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            # Une clé collée par erreur dans un message est masquée elle aussi.
            handle = await produce_chat(
                app.state.hub, f"Ma clé est {FAKE_KEY}", tokens=("Je ne la répète pas",)
            )
            conv = handle.conversation_id
            for extension in ("json", "md"):
                text = (await client.get(f"/api/conversations/{conv}.{extension}")).text
                assert FAKE_KEY not in text and "FAKEKEY" not in text
                assert "***" in text
                assert "api_key" not in text.lower()
                assert "Ma clé est" in text


async def test_delete_removes_the_text_from_the_database_and_the_journal(served):  # noqa: F811
    app, client = served
    hub, store = app.state.hub, app.state.store
    conv, first, second = await two_exchanges(hub)
    db = Path(store.path)
    wal = db.with_name(db.name + "-wal")

    def stored_bytes() -> bytes:
        return db.read_bytes() + (wal.read_bytes() if wal.exists() else b"")

    for needle in (UNIQUE, ANSWER):
        assert needle.encode() in stored_bytes()  # le test sait voir le texte avant l'effacement
    before = await session_summary(store, hub.app_session_id)

    response = await client.delete(f"/api/conversations/{conv}")
    assert response.status_code == 204

    for needle in (UNIQUE, ANSWER):
        assert needle.encode() not in db.read_bytes()
        assert needle.encode() not in wal.read_bytes()
    assert wal.stat().st_size == 0  # journal vidé : `wal_checkpoint(TRUNCATE)` en dernier
    assert (await client.get(f"/api/conversations/{conv}")).status_code == 404
    assert store.read("SELECT count(*) AS n FROM messages")[0]["n"] == 0
    assert store.read("SELECT count(*) AS n FROM run_events")[0]["n"] == 0
    assert store.read("SELECT count(*) AS n FROM conversations")[0]["n"] == 0
    runs = store.read("SELECT id, conversation_id, co2_mg FROM runs ORDER BY started_at")
    assert [r["id"] for r in runs] == [first, second]  # le registre carbone reste
    assert all(r["conversation_id"] is None and r["co2_mg"] == 1.5 for r in runs)
    # Le CO2 de session ne baisse pas.
    after = await session_summary(store, hub.app_session_id)
    assert after == before and after["total_mg"] == 3.0
    assert (await client.get("/api/carbon/session")).json()["total_mg"] == 3.0


async def test_delete_keeps_the_other_conversations(served):  # noqa: F811
    app, client = served
    keep = await produce_chat(app.state.hub, "Je reste", tokens=("Gardée",))
    gone = await produce_chat(app.state.hub, "Je pars", tokens=("Partie",))
    assert (await client.delete(f"/api/conversations/{gone.conversation_id}")).status_code == 204
    body = (await client.get(f"/api/conversations/{keep.conversation_id}")).json()
    assert [m["content"] for m in body["messages"]] == ["Je reste", "Gardée"]


async def test_delete_with_an_active_run_is_a_409_with_message_and_action(served):  # noqa: F811
    app, client = served
    hub = app.state.hub
    handle = await produce_chat(hub, "Question en cours", finish=False)
    response = await client.delete(f"/api/conversations/{handle.conversation_id}")
    assert response.status_code == 409
    envelope = response.json()
    assert envelope["code"] == "conversation_busy"
    assert envelope["message"] and envelope["action"]
    assert envelope["detail"]["run_id"] == handle.run_id
    # Rien n'a été effacé ; une fois le run fini, l'effacement passe.
    assert (await client.get(f"/api/conversations/{handle.conversation_id}")).status_code == 200
    await hub.cancel(handle.run_id)
    assert (await client.delete(f"/api/conversations/{handle.conversation_id}")).status_code == 204


async def test_a_message_sent_to_a_deleted_conversation_is_refused(served):  # noqa: F811
    app, client = served
    handle = await produce_chat(app.state.hub, "Q")
    await client.delete(f"/api/conversations/{handle.conversation_id}")
    response = await client.post(
        "/api/chat/runs",
        json={"conversation_id": handle.conversation_id, "model": "fake:1b", "message": "Suite"},
    )
    assert response.status_code == 404


async def test_routes_with_a_path_parameter_stay_under_the_read_budget(tmp_path):
    """`test_read_budget.py` ne couvre que les `GET` sans paramètre de chemin : ceux-ci se
    mesurent ici, Ollama injoignable (port fermé de `make_settings`), base de taille réelle."""
    app = create_app(make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            conv, _, _ = await two_exchanges(app.state.hub)
            paths = (
                f"/api/conversations/{conv}",
                f"/api/conversations/{conv}.json",
                f"/api/conversations/{conv}.md",
                "/api/conversations/inconnue",
            )
            for path in paths:
                started = time.perf_counter()
                response = await client.get(path)
                elapsed = time.perf_counter() - started
                assert response.status_code in (200, 404), path
                assert elapsed < 0.3, f"{path} : {elapsed * 1000:.0f} ms"


@pytest.mark.parametrize("extension", ["json", "md"])
async def test_exports_work_on_a_conversation_without_any_answer(served, extension):  # noqa: F811
    app, client = served
    handle = await app.state.hub.create_run("chat", models=["fake:1b"], user_message="Seule")
    await app.state.hub.cancel(handle.run_id)
    response = await client.get(f"/api/conversations/{handle.conversation_id}.{extension}")
    assert response.status_code == 200 and "Seule" in response.text
