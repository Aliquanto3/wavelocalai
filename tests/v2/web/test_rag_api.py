"""`POST /api/rag/documents` : import multipart de bout en bout (app réelle, embedder `fake`).

L'app est la vraie (hub, store sqlite-vec, service d'ingestion, flux SSE) ; seul l'embedding est le
`fake` scriptable de `Settings.testing`. Rien ne touche le réseau.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from wavelocalai.models.fake import FAKE_EMBED_REF, Sleep
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..rag_files import make_docx, make_pdf
from .conftest import parse_sse, served  # noqa: F401 - fixture

BASE = f"http://127.0.0.1:{TEST_PORT}"
LONG = " ".join(f"phrase{i:03d}" for i in range(300))


def _staging_dirs() -> set[Path]:
    return set(Path(tempfile.gettempdir()).glob("wavelocalai-ingest-*"))


def _files(**named: bytes | str) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("files", (name, data if isinstance(data, bytes) else data.encode(), "application/octet"))
        for name, data in named.items()
    ]


async def _events(client, run_id):
    response = await client.get(f"/api/runs/{run_id}/events")
    return [f["data"] for f in parse_sse(response.text)[0]]


async def _ended(client, run_id, timeout=5.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


def _docs(app):
    rows = app.state.store.read("SELECT * FROM documents ORDER BY source")
    return {r["source"]: r for r in rows}


async def test_several_files_are_imported_and_followed_through_the_run_stream(served):
    app, client = served
    before = _staging_dirs()
    response = await client.post(
        "/api/rag/documents",
        files=_files(
            **{
                "notes.txt": LONG,
                "rapport.pdf": make_pdf(["Premiere page", "Seconde page"]),
                "memo.docx": make_docx(["Un memo.", "Deux phrases."]),
                "vide.md": "",
            }
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"run_id"}

    snapshot = await _ended(client, body["run_id"])
    assert snapshot["status"] == "ok"  # l'orchestration aboutit même si un fichier échoue
    events = await _events(client, body["run_id"])
    assert events[0]["type"] == "run_started" and events[0]["data"]["kind"] == "ingest"
    assert events[-1]["type"] == "run_ended" and events[-1]["data"]["status"] == "ok"
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    done = {e["data"]["file"]: e["data"] for e in events if e["type"] == "ingest_file_done"}
    assert {name: d["status"] for name, d in done.items()} == {
        "notes.txt": "ready",
        "rapport.pdf": "ready",
        "memo.docx": "ready",
        "vide.md": "failed",
    }
    assert done["vide.md"]["error"]["code"] == "ingest_failed"
    assert done["vide.md"]["error"]["detail"]["reason"] == "le fichier est vide"
    assert {e["data"]["phase"] for e in events if e["type"] == "ingest_progress"} == {
        "extract", "split", "embed",
    }  # fmt: skip

    docs = _docs(app)
    assert {n: d["status"] for n, d in docs.items()} == {
        "memo.docx": "ready", "notes.txt": "ready", "rapport.pdf": "ready", "vide.md": "failed",
    }  # fmt: skip
    assert {d["embedding_model"] for d in docs.values()} == {FAKE_EMBED_REF.tag}
    assert _staging_dirs() == before  # le dossier temporaire est supprimé à la fin du run


async def test_the_session_co2_counts_the_embedding_batches(served):
    app, client = served
    started = await client.post("/api/rag/documents", files=_files(**{"a.txt": LONG}))
    await _ended(client, started.json()["run_id"])
    carbon = (await client.get("/api/carbon/session")).json()
    assert carbon["by_module"]["ingest"]["runs"] >= 1
    assert carbon["by_origin"]["local"]["runs"] == carbon["by_module"]["ingest"]["runs"]


async def test_the_embedding_model_can_be_chosen_in_the_form(served):
    app, client = served
    started = await client.post(
        "/api/rag/documents",
        files=_files(**{"a.txt": "Un texte."}),
        data={"embedding_model": FAKE_EMBED_REF.tag},
    )
    await _ended(client, started.json()["run_id"])
    assert _docs(app)["a.txt"]["embedding_model"] == FAKE_EMBED_REF.tag


async def test_a_second_import_while_one_runs_is_a_409_with_the_active_run(served):
    app, client = served
    app.state.embedders[FAKE_EMBED_REF.tag].script = [Sleep(0.4)]
    first = await client.post("/api/rag/documents", files=_files(**{"a.txt": "Premier."}))
    before = _staging_dirs()
    second = await client.post("/api/rag/documents", files=_files(**{"b.txt": "Second."}))
    assert second.status_code == 409
    assert second.json()["code"] == "run_busy"
    assert second.json()["detail"]["run_id"] == first.json()["run_id"]
    assert _staging_dirs() == before  # le refus ne laisse pas de fichier reçu
    await _ended(client, first.json()["run_id"])


async def test_cancelling_the_run_keeps_ready_documents_and_drops_the_one_in_progress(served):
    app, client = served
    done = await client.post("/api/rag/documents", files=_files(**{"a.txt": "Document prêt."}))
    await _ended(client, done.json()["run_id"])
    embedder = app.state.embedders[FAKE_EMBED_REF.tag]
    embedder.script = [Sleep(10)]
    embedder.calls = 0
    started = await client.post("/api/rag/documents", files=_files(**{"b.txt": LONG}))
    run_id = started.json()["run_id"]
    async with asyncio.timeout(3):
        while embedder.calls < 1:
            await asyncio.sleep(0.01)

    cancelled = await client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.json()["cancelled"] is True
    assert (await _ended(client, run_id))["status"] == "cancelled"
    # `cancelled` est fixé par le hub avant que la tâche d'import ne retire le document en cours :
    # attendre la fin réelle de la tâche (course vue sur la CI macOS).
    if tasks := set(app.state.ingest._tasks):
        await asyncio.wait(tasks, timeout=5)
    assert set(_docs(app)) == {"a.txt"} and _docs(app)["a.txt"]["status"] == "ready"
    chunks = app.state.store.read("SELECT count(*) AS n FROM chunks")[0]["n"]
    assert chunks == 1


async def test_an_oversized_file_fails_with_its_reason(tmp_path):
    app = create_app(
        make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}, rag={"max_file_mb": 1})
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            big = await client.post(
                "/api/rag/documents", files=_files(**{"gros.txt": "x" * (1024 * 1024 + 10)})
            )
            await _ended(client, big.json()["run_id"])
            error = json.loads(_docs(app)["gros.txt"]["error"])
            assert error["detail"]["reason"] == "le fichier dépasse 1 Mo"


@pytest.mark.parametrize(
    ("kwargs", "status", "code"),
    [
        (
            {"data": {"embedding_model": FAKE_EMBED_REF.tag}},
            422,
            "invalid_request",
        ),  # aucun fichier
        (
            {"files": _files(a="x"), "data": {"embedding_model": "inconnu:1b"}},
            404,
            "model_not_found",
        ),
        (
            {"files": _files(a="x"), "data": {"embedding_model": "fake:1b"}},
            422,
            "model_not_embedding",
        ),
    ],
)
async def test_a_bad_request_gets_the_error_envelope_and_leaves_nothing_behind(
    served, kwargs, status, code
):
    app, client = served
    before = _staging_dirs()
    response = await client.post("/api/rag/documents", **kwargs)
    assert response.status_code == status
    envelope = response.json()
    assert envelope["code"] == code and envelope["message"] and envelope["action"]
    assert _staging_dirs() == before and _docs(app) == {}


async def test_a_foreign_origin_cannot_import_files(served):
    _, client = served
    response = await client.post(
        "/api/rag/documents",
        files=_files(a="x"),
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403 and response.json()["code"] == "forbidden_origin"


async def test_the_ingest_error_codes_are_in_the_closed_list():
    from wavelocalai.errors import ERRORS, build_envelope

    for code in ("ingest_failed", "no_embedding_model", "embedding_locked"):
        assert ERRORS[code].message and ERRORS[code].action
    envelope = build_envelope("ingest_failed", "x", file="a.pdf", reason="le PDF est vide")
    assert envelope["detail"] == {"technical": "x", "file": "a.pdf", "reason": "le PDF est vide"}
