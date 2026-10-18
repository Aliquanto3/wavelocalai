"""`POST /api/rag/runs` et `GET /api/rag/chunks/{id}` : une question, ses sources, puis la réponse
(story 4.4), de bout en bout.

L'app est la vraie (hub, store, index vectoriel, services d'ingestion et de question, flux SSE) ;
seuls l'embedding et le modèle de réponse sont les `fake` scriptables de `Settings.testing`. Rien ne
touche le réseau.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime

import httpx
import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.models.fake import FAKE_EMBED_REF, FAKE_REF, Sleep, fake_vector
from wavelocalai.models.ollama_api import OllamaHttpSource
from wavelocalai.models.port import TextDelta
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.rag import repo
from wavelocalai.rag.split import ChunkDraft
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..fake_cloud import MODELS, SETTINGS_CLOUD, Plan, factories, stream_for
from ..fake_ollama import FakeOllama
from .conftest import parse_sse, served  # noqa: F401 - fixture
from .test_chat_cloud_api import _fake

BASE = f"http://127.0.0.1:{TEST_PORT}"
CATS = (
    "Le chat domestique dort sur le canapé du salon. Il ronronne quand on le caresse. "
    "La nuit, il chasse les souris dans le jardin."
)
CARS = (
    "La voiture électrique recharge sa batterie sur une borne rapide. "
    "L'autonomie dépend de la vitesse et de la température."
)
QUESTION = "Où dort le chat domestique ?"
LABELS = {"très proche", "proche", "éloignée"}
SOURCE_KEYS = {
    "n", "doc_id", "document", "page", "chunk_id", "text", "rank", "relevance_label",
    "raw_score", "passage",
}  # fmt: skip


def _files(**named: str) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (name, text.encode(), "text/plain")) for name, text in named.items()]


async def _ended(client, run_id, timeout=5.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


async def _events(client, run_id, after=0):
    response = await client.get(f"/api/runs/{run_id}/events", params={"after": after})
    return [f["data"] for f in parse_sse(response.text)[0]]


async def _import(client, **docs: str):
    started = await client.post("/api/rag/documents", files=_files(**docs))
    assert started.status_code == 200, started.text
    assert (await _ended(client, started.json()["run_id"]))["status"] == "ok"


async def _ask(client, question=QUESTION, **body):
    payload = {"question": question, "model": FAKE_REF.tag, "strategy": "naive", **body}
    return await client.post("/api/rag/runs", json=payload)


def _types(events):
    return [e["type"] for e in events]


def _script(app, *deltas: str):
    app.state.models[FAKE_REF.tag].script = [TextDelta(d) for d in deltas]


@contextlib.asynccontextmanager
async def rag_app(tmp_path, **settings):
    app = create_app(make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}, **settings))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


async def test_the_sources_come_before_the_first_token_then_the_answer_and_its_metrics(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    _script(app, "Le chat dort", " sur le canapé [1].")

    response = await _ask(client)
    assert response.status_code == 200
    started = response.json()
    assert set(started) == {"run_id", "conversation_id"} and started["conversation_id"]
    snapshot = await _ended(client, started["run_id"])
    assert snapshot["status"] == "ok" and snapshot["kind"] == "rag"

    events = await _events(client, started["run_id"])
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    types = _types(events)
    assert types[0] == "run_started" and types[-1] == "run_ended"
    assert types.index("sources") < types.index("token")
    assert types[1:4] == ["retrieval_step", "retrieval_step", "sources"]
    steps = [e["data"] for e in events if e["type"] == "retrieval_step"]
    assert [(s["strategy"], s["step"]) for s in steps] == [
        ("naive", "embedding"),
        ("naive", "search"),
    ]
    assert all(isinstance(s["duration_s"], float) and s["duration_s"] >= 0 for s in steps)

    sources = next(e for e in events if e["type"] == "sources")["data"]["sources"]
    assert sources and all(set(s) == SOURCE_KEYS for s in sources)
    assert (
        [s["n"] for s in sources]
        == [s["rank"] for s in sources]
        == list(range(1, len(sources) + 1))
    )
    first = sources[0]
    assert first["document"] == "chats.txt" and first["page"] is None
    assert first["text"] == CATS  # l'extrait entier
    assert first["relevance_label"] in LABELS and isinstance(first["raw_score"], float)
    passage = first["passage"]
    assert (
        CATS[passage["start"] : passage["end"]] == "Le chat domestique dort sur le canapé du salon."
    )
    assert all(s["raw_score"] <= first["raw_score"] for s in sources)

    tokens = "".join(e["data"]["text"] for e in events if e["type"] == "token")
    assert tokens == "Le chat dort sur le canapé [1]."
    assert {e["data"]["lane"] for e in events if e["type"] == "token"} == {FAKE_REF.tag}
    metrics = next(e for e in events if e["type"] == "metrics")["data"]
    assert metrics["lane"] == FAKE_REF.tag and metrics["tps"] and metrics["tps_source"]
    assert metrics["retrieval_s"] >= sum(s["duration_s"] for s in steps) - 1e-3
    assert metrics["co2"]["method"] in {"codecarbon", "unmeasurable"}
    assert types.index("metrics") > types.index("token")

    # la conversation `rag` : la question et la réponse sont dans `messages`, jamais dans `params`
    messages = app.state.store.read(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY rowid",
        (started["conversation_id"],),
    )
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", QUESTION),
        ("assistant", "Le chat dort sur le canapé [1]."),
    ]
    kind = app.state.store.read(
        "SELECT kind FROM conversations WHERE id = ?", (started["conversation_id"],)
    )[0]["kind"]
    assert kind == "rag"
    assert QUESTION not in json.dumps(snapshot["params"]) and "text" not in snapshot["params"]


async def test_the_prompt_holds_the_numbered_sources_then_the_question(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    started = (await _ask(client)).json()
    await _ended(client, started["run_id"])
    request = app.state.models[FAKE_REF.tag].requests[-1]
    assert [m.role for m in request.messages] == ["system", "user"]
    user = request.messages[1].content
    assert "[1] (chats.txt)\n" + CATS in user and "[2] (voitures.txt)" in user
    assert user.endswith(f"Question : {QUESTION}")
    assert "[1]" in request.messages[0].content  # la consigne demande les numéros d'extrait


async def test_the_question_and_the_generation_are_two_leaves_each_with_its_co2(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    started = (await _ask(client)).json()
    snapshot = await _ended(client, started["run_id"])
    leaves = {c["kind"]: c for c in snapshot["children"]}
    assert set(leaves) == {"embedding", "generation"}
    assert leaves["embedding"]["model"] == FAKE_EMBED_REF.tag
    assert leaves["generation"]["model"] == FAKE_REF.tag
    for leaf in leaves.values():
        assert leaf["status"] == "ok" and leaf["metrics"]["co2"]["method"] in {
            "codecarbon", "unmeasurable",
        }  # fmt: skip
    assert snapshot["metrics"] is None  # le parent ne porte pas de métriques (AD-5)
    carbon = (await client.get("/api/carbon/session")).json()
    assert carbon["by_module"]["rag"]["runs"] == 2


async def test_a_local_question_takes_the_local_slot_for_the_embedding_and_the_answer(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    before = app.state.local_slot.acquired
    await _ended(client, (await _ask(client)).json()["run_id"])
    assert app.state.local_slot.acquired - before == 2  # une place par appel (AD-14)


async def test_an_empty_base_leads_to_the_document_base_and_creates_nothing(served):
    app, client = served
    response = await _ask(client)
    assert response.status_code == 409
    envelope = response.json()
    assert envelope["code"] == "rag_base_empty"
    assert "#/documents/base" in envelope["action"]
    assert app.state.store.read("SELECT count(*) AS n FROM runs")[0]["n"] == 0
    assert app.state.store.read("SELECT count(*) AS n FROM conversations")[0]["n"] == 0


async def test_a_document_not_ready_does_not_make_the_base_queryable(served):
    app, client = served
    _plant(app, "d-encours", "encours.txt", "indexing", QUESTION)
    assert (await _ask(client)).json()["code"] == "rag_base_empty"
    _plant(app, "d-echec", "echec.txt", "failed", QUESTION)
    assert (await _ask(client)).json()["code"] == "rag_base_empty"


def _plant(app, doc_id, source, status, text, *, vector=True):
    """Un document inséré à la main (état intermédiaire que l'import ne laisse pas voir)."""
    now = datetime.now(UTC).isoformat()

    def tx(conn):
        repo.insert_document(
            conn, doc_id=doc_id, source=source, fingerprint=doc_id.ljust(64, "0"), size_bytes=1,
            embedding_model=FAKE_EMBED_REF.tag, run_id=None, now=now,
        )  # fmt: skip
        ids = repo.insert_chunks(conn, doc_id, [ChunkDraft(0, None, text)])
        if vector:
            app.state.rag._index.add(conn, ids, [fake_vector(text)])
        if status == "ready":
            repo.mark_ready(conn, doc_id, dim=16, chunk_count=1, page_count=None, now=now)
        elif status == "failed":
            conn.execute("UPDATE documents SET status='failed', error='{}' WHERE id = ?", (doc_id,))
        return ids[0]

    return app.state.store.write(tx).result()


async def test_only_ready_documents_are_queried_even_when_a_pending_one_matches_best(tmp_path):
    async with rag_app(tmp_path, rag={"top_k": 1}) as (app, client):
        await _import(client, **{"voitures.txt": CARS})
        _plant(
            app, "d-encours", "encours.txt", "indexing", QUESTION
        )  # la plus proche de la question
        started = (await _ask(client)).json()
        await _ended(client, started["run_id"])
        events = await _events(client, started["run_id"])
        sources = next(e for e in events if e["type"] == "sources")["data"]["sources"]
        assert [s["document"] for s in sources] == ["voitures.txt"]  # un `ready`, au lieu de rien


async def test_a_cloud_model_needs_allow_cloud(tmp_path):
    fake = _fake("openai", Plan(stream_for("openai", ["Réponse", " cloud"], usage=(11, 200))))
    environ = {"WAVELOCALAI_TESTING": "1", "OPENAI_API_KEY": "sk-test-0123456789abcdef"}
    config = make_settings(tmp_path, environ=environ, cloud=SETTINGS_CLOUD)
    server = FakeOllama()
    registry = ModelRegistry(
        config,
        source=OllamaHttpSource(config.ollama.host, transport=server.transport),
        extra_refs={FAKE_REF.tag: FAKE_REF, FAKE_EMBED_REF.tag: FAKE_EMBED_REF},
    )
    app = create_app(
        config, registry=registry, ollama_client=server.client(), cloud_http=factories(fake)
    )
    async with app.router.lifespan_context(app):
        await registry.refresh()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            await _import(client, **{"chats.txt": CATS})
            tag = MODELS[0][1]
            refused = await _ask(client, model=tag)
            assert refused.status_code == 403 and refused.json()["code"] == "cloud_not_allowed"
            assert (
                app.state.store.read("SELECT count(*) AS n FROM runs WHERE kind='rag'")[0]["n"] == 0
            )

            started = (await _ask(client, model=tag, allow_cloud=True)).json()
            snapshot = await _ended(client, started["run_id"])
            assert snapshot["status"] == "ok" and snapshot["params"]["allow_cloud"] is True
            leaves = {c["kind"]: c for c in snapshot["children"]}
            # la génération cloud est estimée comme celle du chat ; l'embedding reste local
            assert leaves["generation"]["metrics"]["co2"]["method"] == "ecologits"
            assert leaves["generation"]["metrics"]["origin"] == "cloud"
            assert leaves["embedding"]["metrics"]["origin"] == "local"
            events = await _events(client, started["run_id"])
            metrics = next(e for e in events if e["type"] == "metrics")["data"]
            assert metrics["co2"]["method"] == "ecologits" and metrics["retrieval_s"] >= 0


async def test_a_second_question_while_one_runs_is_a_409_with_the_active_run(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    app.state.models[FAKE_REF.tag].script = [TextDelta("Début"), Sleep(0.5)]
    first = (await _ask(client)).json()
    second = await _ask(client, "Une autre question ?")
    assert second.status_code == 409
    assert second.json()["code"] == "run_busy"
    assert second.json()["detail"]["run_id"] == first["run_id"]
    await _ended(client, first["run_id"])


async def test_a_conversation_goes_on_and_a_chat_conversation_is_refused(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    _script(app, "Sur le canapé.")
    first = (await _ask(client)).json()
    await _ended(client, first["run_id"])
    second = await _ask(client, "Que fait-il la nuit ?", conversation_id=first["conversation_id"])
    assert second.json()["conversation_id"] == first["conversation_id"]
    await _ended(client, second.json()["run_id"])
    view = (await client.get(f"/api/conversations/{first['conversation_id']}")).json()
    assert view["kind"] == "rag" and [m["role"] for m in view["messages"]] == [
        "user", "assistant", "user", "assistant",
    ]  # fmt: skip
    chat = (
        await client.post("/api/chat/runs", json={"model": FAKE_REF.tag, "message": "Salut"})
    ).json()
    await _ended(client, chat["run_id"])
    refused = await _ask(client, conversation_id=chat["conversation_id"])
    assert refused.status_code == 422 and refused.json()["code"] == "invalid_request"
    unknown = await _ask(client, conversation_id="inconnue")
    assert unknown.status_code == 404


async def test_a_replayed_run_gets_its_source_text_back_and_null_once_the_document_is_deleted(
    served,
):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    started = (await _ask(client)).json()
    await _ended(client, started["run_id"])
    live = next(e for e in await _events(client, started["run_id"]) if e["type"] == "sources")

    # persisté sans `text`, avec les positions du passage (AD-7, D-21)
    row = app.state.store.read(
        "SELECT data FROM run_events WHERE run_id = ? AND type = 'sources'", (started["run_id"],)
    )[0]
    stored = json.loads(row["data"])["sources"]
    assert stored and all("text" not in s and "passage" in s for s in stored)
    assert [s["passage"] for s in stored] == [s["passage"] for s in live["data"]["sources"]]
    assert stored[0]["passage"] is not None
    assert CATS not in row["data"]  # aucun morceau du document dans le journal des événements

    # rejeu depuis la base : le texte revient des `chunks`
    assert [s["text"] for s in live["data"]["sources"]] == [CATS, CARS]

    # document supprimé : `text` nul, le reste de la source (nom, positions) est gardé
    doc_id = live["data"]["sources"][0]["doc_id"]
    await app.state.store.awrite(
        lambda conn: repo.delete_document(conn, app.state.rag._index, doc_id)
    )
    replay = next(e for e in await _events(client, started["run_id"]) if e["type"] == "sources")
    texts = {s["document"]: s["text"] for s in replay["data"]["sources"]}
    assert texts == {"chats.txt": None, "voitures.txt": CARS}
    gone = next(s for s in replay["data"]["sources"] if s["document"] == "chats.txt")
    assert gone["passage"] == live["data"]["sources"][0]["passage"]  # positions persistées


async def test_a_chunk_is_read_whole_and_a_vanished_one_is_a_clear_error(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    started = (await _ask(client)).json()
    await _ended(client, started["run_id"])
    source = next(e for e in await _events(client, started["run_id"]) if e["type"] == "sources")[
        "data"
    ]["sources"][0]
    chunk = await client.get(f"/api/rag/chunks/{source['chunk_id']}")
    assert chunk.status_code == 200
    assert chunk.json() == {
        "chunk_id": source["chunk_id"], "doc_id": source["doc_id"], "document": "chats.txt",
        "page": None, "position": 0, "text": CATS,
    }  # fmt: skip
    await app.state.store.awrite(
        lambda conn: repo.delete_document(conn, app.state.rag._index, source["doc_id"])
    )
    gone = await client.get(f"/api/rag/chunks/{source['chunk_id']}")
    assert gone.status_code == 404 and gone.json()["code"] == "chunk_not_found"
    assert gone.json()["detail"]["chunk_id"] == source["chunk_id"] and gone.json()["action"]
    assert (await client.get("/api/rag/chunks/999999")).json()["code"] == "chunk_not_found"
    assert (await client.get("/api/rag/chunks/abc")).status_code == 422


async def test_a_chunk_of_a_document_not_ready_is_not_readable(served):
    app, client = served
    chunk_id = _plant(app, "d-encours", "encours.txt", "indexing", "Texte en cours.")
    assert (await client.get(f"/api/rag/chunks/{chunk_id}")).json()["code"] == "chunk_not_found"


async def test_an_embedding_failure_ends_the_run_in_error_before_any_source(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    embedder = app.state.embedders[FAKE_EMBED_REF.tag]
    embedder.script, embedder.calls = [ProviderError("ollama_down")], 0
    started = (await _ask(client)).json()
    snapshot = await _ended(client, started["run_id"])
    assert snapshot["status"] == "error" and snapshot["error"]["code"] == "ollama_down"
    types = _types(await _events(client, started["run_id"]))
    assert "sources" not in types and "token" not in types and types[-1] == "run_ended"
    leaves = {c["kind"]: c for c in snapshot["children"]}
    assert leaves["embedding"]["status"] == "error"
    assert leaves["embedding"]["metrics"]["co2"]["mg"] is None  # jamais 0 pour un inconnu
    assert leaves["generation"]["status"] == "cancelled"
    assert leaves["generation"]["metrics"]["co2"]["reason"]  # `co2` présent partout (AD-10)
    assert app.state.models[FAKE_REF.tag].requests == []  # le modèle n'a jamais été appelé


async def test_a_generation_failure_keeps_the_sources_and_ends_the_run_in_error(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    app.state.models[FAKE_REF.tag].script = [TextDelta("Début"), ProviderError("ollama_error")]
    started = (await _ask(client)).json()
    snapshot = await _ended(client, started["run_id"])
    assert snapshot["status"] == "error" and snapshot["error"]["code"] == "ollama_error"
    events = await _events(client, started["run_id"])
    assert "sources" in _types(events)
    ended = events[-1]["data"]
    assert ended["status"] == "error" and ended["error"]["code"] == "ollama_error"


async def test_cancelling_during_the_answer_keeps_the_sources_and_the_partial_answer(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    app.state.models[FAKE_REF.tag].script = [TextDelta("Début de réponse"), Sleep(10)]
    started = (await _ask(client)).json()
    async with asyncio.timeout(3):
        while not any(
            e["type"] == "token" for e in await app.state.hub.events_after(started["run_id"])
        ):
            await asyncio.sleep(0.02)
    cancelled = await client.post(f"/api/runs/{started['run_id']}/cancel")
    assert cancelled.json()["cancelled"] is True
    snapshot = await _ended(client, started["run_id"])
    assert snapshot["status"] == "cancelled"
    assert "sources" in _types(await _events(client, started["run_id"]))
    answer = app.state.store.read(
        "SELECT content FROM messages WHERE conversation_id = ? AND role = 'assistant'",
        (started["conversation_id"],),
    )
    assert [r["content"] for r in answer] == ["Début de réponse"]
    assert all(c["metrics"]["co2"] is not None for c in snapshot["children"])


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"question": "   "}, 422, "invalid_request"),
        ({"question": ""}, 422, "invalid_request"),
        ({"strategy": "hyde"}, 422, "invalid_request"),
        ({"model": "inconnu:1b"}, 404, "model_not_found"),
        ({"model": FAKE_EMBED_REF.tag}, 422, "model_not_chat"),
    ],
)
async def test_a_bad_question_gets_the_error_envelope_and_creates_nothing(
    served, body, status, code
):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    runs = app.state.store.read("SELECT count(*) AS n FROM runs WHERE kind = 'rag'")[0]["n"]
    response = await _ask(client, **body)
    assert response.status_code == status and response.json()["code"] == code
    after = app.state.store.read("SELECT count(*) AS n FROM runs WHERE kind = 'rag'")[0]["n"]
    assert after == runs


async def test_a_missing_question_or_model_is_a_422(served):
    _, client = served
    response = await client.post("/api/rag/runs", json={"model": FAKE_REF.tag})
    assert response.status_code == 422 and response.json()["code"] == "invalid_request"
    response = await client.post("/api/rag/runs", json={"question": "Q ?"})
    assert response.status_code == 422


async def test_a_foreign_origin_cannot_ask_a_question(served):
    _, client = served
    response = await client.post(
        "/api/rag/runs",
        json={"question": "Q ?", "model": FAKE_REF.tag},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403 and response.json()["code"] == "forbidden_origin"


async def test_the_whole_path_works_with_the_numpy_fallback_index(tmp_path, monkeypatch):
    """Sans sqlite-vec (CPython sans chargement d'extensions, CI macOS) : `NumpyIndex`, partagé par
    l'import et la question, et une lecture sans extension."""
    from wavelocalai.rag.index import NumpyIndex

    monkeypatch.setattr("wavelocalai.web.app.select_index", lambda available: NumpyIndex())
    async with rag_app(tmp_path, rag={"top_k": 1}) as (app, client):
        await _import(client, **{"voitures.txt": CARS, "chats.txt": CATS})
        _plant(app, "d-encours", "encours.txt", "indexing", QUESTION)  # non prêt : écarté
        assert isinstance(app.state.rag._index, NumpyIndex)
        started = (await _ask(client)).json()
        assert (await _ended(client, started["run_id"]))["status"] == "ok"
        events = await _events(client, started["run_id"])
        sources = next(e for e in events if e["type"] == "sources")["data"]["sources"]
        assert [s["document"] for s in sources] == ["chats.txt"]
        assert sources[0]["passage"] is not None
