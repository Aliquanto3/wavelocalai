"""`GET /api/rag/documents` (liste, totaux, plafonds), plafonds d'un import et route de test
`POST /api/test/embedder` (story 4.2). App réelle, embedder `fake`, aucun réseau."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from wavelocalai.models.fake import FAKE_EMBED_REF
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..rag_files import make_blank_pdf
from .conftest import served  # noqa: F401 - fixture

BASE = f"http://127.0.0.1:{TEST_PORT}"
LONG = " ".join(f"phrase{i:03d}" for i in range(300))


def _files(**named: bytes | str) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("files", (name, data if isinstance(data, bytes) else data.encode(), "application/octet"))
        for name, data in named.items()
    ]


async def _ended(client, run_id, timeout=5.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


async def test_an_empty_base_lists_nothing_and_states_the_limits(served):
    _, client = served
    body = (await client.get("/api/rag/documents")).json()
    assert body == {
        "documents": [],
        "totals": {"documents": 0, "chunks": 0},
        "limits": {"max_file_mb": 50, "max_files": 50, "max_import_mb": 500},
        "search": {"top_k": 4, "max_top_k": 20},
    }


async def test_the_list_gives_every_status_newest_first_and_totals_count_ready_only(served):
    app, client = served
    first = await client.post("/api/rag/documents", files=_files(**{"notes.txt": LONG}))
    await _ended(client, first.json()["run_id"])
    second = await client.post(
        "/api/rag/documents",
        files=_files(**{"vide.md": "", "protege.pdf": make_blank_pdf("secret")}),
    )
    await _ended(client, second.json()["run_id"])

    body = (await client.get("/api/rag/documents")).json()
    by_name = {d["source"]: d for d in body["documents"]}
    assert set(by_name) == {"notes.txt", "vide.md", "protege.pdf"}
    ready = by_name["notes.txt"]
    assert ready["status"] == "ready" and ready["chunks"] >= 1 and ready["error"] is None
    assert ready["embedding_model"] == FAKE_EMBED_REF.tag
    assert ready["run_id"] == first.json()["run_id"] and ready["ready_at"]
    failed = by_name["vide.md"]
    assert failed["status"] == "failed" and failed["chunks"] == 0 and failed["ready_at"] is None
    assert failed["error"]["code"] == "ingest_failed"
    assert failed["error"]["detail"]["reason"] == "le fichier est vide"
    assert body["totals"] == {"documents": 1, "chunks": ready["chunks"]}
    created = [d["created_at"] for d in body["documents"]]
    assert created == sorted(created, reverse=True)
    assert body["documents"][-1]["source"] == "notes.txt"  # le plus ancien en dernier


async def test_a_base_with_only_a_failed_document_lists_it_with_its_reason_and_counts_none(served):
    _, client = served
    started = await client.post("/api/rag/documents", files=_files(**{"vide.md": ""}))
    await _ended(client, started.json()["run_id"])
    for _ in range(2):  # la liste se relit à l'identique : le document n'est pas retiré
        body = (await client.get("/api/rag/documents")).json()
        assert body["totals"] == {"documents": 0, "chunks": 0}
        [doc] = body["documents"]
        assert (doc["source"], doc["status"], doc["chunks"]) == ("vide.md", "failed", 0)
        assert doc["error"]["code"] == "ingest_failed"
        assert doc["error"]["detail"]["reason"] == "le fichier est vide"
        assert doc["error"]["message"]  # le front compose la phrase avec le message de l'enveloppe


async def test_a_document_being_indexed_is_listed_as_indexing_and_not_counted(served):
    from wavelocalai.models.fake import Sleep

    app, client = served
    embedder = app.state.embedders[FAKE_EMBED_REF.tag]
    embedder.script = [Sleep(0.6)]
    started = await client.post("/api/rag/documents", files=_files(**{"lent.txt": LONG}))
    async with asyncio.timeout(3):
        while embedder.calls < 1:
            await asyncio.sleep(0.01)
    during = (await client.get("/api/rag/documents")).json()
    assert [(d["source"], d["status"], d["chunks"]) for d in during["documents"]] == [
        ("lent.txt", "indexing", 0)
    ]
    assert during["totals"] == {"documents": 0, "chunks": 0}
    assert during["documents"][0]["run_id"] == started.json()["run_id"]
    await _ended(client, started.json()["run_id"])
    after = (await client.get("/api/rag/documents")).json()
    assert after["documents"][0]["status"] == "ready" and after["totals"]["documents"] == 1


async def test_an_import_over_the_file_count_or_total_size_cap_is_refused(tmp_path):
    settings = make_settings(
        tmp_path,
        environ={"WAVELOCALAI_TESTING": "1"},
        rag={"max_files": 2, "max_import_mb": 1},
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            many = await client.post(
                "/api/rag/documents", files=_files(a="un", b="deux", c="trois")
            )
            assert many.status_code == 422 and many.json()["code"] == "invalid_request"
            assert "2 au plus" in many.json()["detail"]["technical"]
            heavy = await client.post(
                "/api/rag/documents",
                files=_files(a="x" * 700_000, b="y" * 700_000),
            )
            assert heavy.status_code == 422 and heavy.json()["code"] == "invalid_request"
            assert "1 Mo au plus" in heavy.json()["detail"]["technical"]
            assert (await client.get("/api/rag/documents")).json()["documents"] == []


@pytest.mark.parametrize("script", [[{"text": "non"}], [{"done": {}}], [{"load": "loading"}]])
async def test_the_embedder_test_route_refuses_chat_steps(served, script):
    _, client = served
    response = await client.post("/api/test/embedder", json={"script": script})
    assert response.status_code == 422


async def test_the_embedder_test_route_scripts_the_fake_embedder(served):
    app, client = served
    embedder = app.state.embedders[FAKE_EMBED_REF.tag]
    embedder.calls = 7
    response = await client.post(
        "/api/test/embedder", json={"script": [{"sleep_s": 0.01}, {"fail": "ollama_down"}]}
    )
    assert response.json() == {"steps": 2} and embedder.calls == 0 and len(embedder.script) == 2
    await client.post("/api/test/embedder", json={"script": [{"fail": "ollama_down"}]})
    started = await client.post("/api/rag/documents", files=_files(**{"a.txt": LONG}))
    await _ended(client, started.json()["run_id"])
    failed = (await client.get("/api/rag/documents")).json()["documents"][0]
    assert failed["status"] == "failed" and failed["error"]["code"] == "ingest_failed"
    await client.post("/api/test/embedder", json={"script": []})  # instantané de nouveau
    assert embedder.script == [] and embedder.calls == 0
