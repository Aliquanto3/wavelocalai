"""Supprimer un document, vider la base, régler (story 4.3) : `DELETE /api/rag/documents/{id}`,
`DELETE /api/rag/base?expected_count=`, `GET` et `PUT /api/rag/settings`, de bout en bout.

L'app est la vraie (hub, store sqlite-vec, services, flux SSE) ; seuls l'embedding et le modèle de
réponse sont les `fake` de `Settings.testing`. Les tests d'octets lisent le `.db` et le `-wal` (AD-13).
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
from pathlib import Path

import httpx
import pytest

from wavelocalai.models.fake import FAKE_EMBED_REF, FAKE_REF, FakeEmbedder, Sleep, fake_vector
from wavelocalai.models.port import ModelRef, TextDelta
from wavelocalai.rag.index import NumpyIndex
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings, needs_vec
from .conftest import served  # noqa: F401 - fixture

BASE = f"http://127.0.0.1:{TEST_PORT}"
OTHER = ModelRef("fake-other:8", "fake", "local", "embedding")
SECRET = "Zorglub-quarante-deux-licornes"
SECOND = "Moustique-mauve-et-pelican-rieur"
CATS = "Le chat domestique dort sur le canapé du salon. Il ronronne quand on le caresse."
CARS = "La voiture électrique recharge sa batterie sur une borne rapide."


def _files(**named: str) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (name, text.encode(), "text/plain")) for name, text in named.items()]


async def _ended(client, run_id, timeout=5.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


async def _import(client, **docs: str) -> str:
    started = await client.post("/api/rag/documents", files=_files(**docs))
    assert started.status_code == 200, started.text
    assert (await _ended(client, started.json()["run_id"]))["status"] == "ok"
    return started.json()["run_id"]


def _documents(app) -> dict[str, dict]:
    rows = app.state.store.read("SELECT id, source, status, chunk_count FROM documents")
    return {r["source"]: dict(r) for r in rows}


def _count(app, table: str) -> int:
    return app.state.store.read(f"SELECT count(*) AS n FROM {table}")[0]["n"]  # noqa: S608


def _vec_rows(app) -> int:
    store = app.state.store
    if not store.vec_available:
        return app.state.rag._index.count(None)
    tables = store.read(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name GLOB 'chunks_vec_[0-9]*'"
    )
    return sum(
        store.read(f"SELECT count(*) AS n FROM {t['name']}", vec=True)[0]["n"]  # noqa: S608
        for t in tables
        if t["name"].removeprefix("chunks_vec_").isdigit()
    )


def _stored_bytes(app) -> bytes:
    db = Path(app.state.store.path)
    wal = db.with_name(db.name + "-wal")
    return db.read_bytes() + (wal.read_bytes() if wal.exists() else b"")


@contextlib.asynccontextmanager
async def rag_app(tmp_path, **settings):
    """App avec un second modèle d'embedding (`fake-other:8`) résolvable."""
    app = create_app(make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}, **settings))
    app.state.embedders[OTHER.tag] = FakeEmbedder(ref=OTHER, dim=8)
    app.state.registry._extra_refs[OTHER.tag] = OTHER
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


# --- Supprimer un document --------------------------------------------------------------------


async def test_deleting_a_document_removes_its_chunks_and_vectors_and_keeps_the_others(served):
    app, client = served
    await _import(client, **{"secret.txt": SECRET, "autre.txt": SECOND})
    docs = _documents(app)
    assert _count(app, "chunks") == 2 and _vec_rows(app) == 2
    response = await client.delete(f"/api/rag/documents/{docs['secret.txt']['id']}")
    assert response.status_code == 200
    assert response.json() == {
        "document_id": docs["secret.txt"]["id"],
        "source": "secret.txt",
        "status": "ready",
        "chunks_removed": 1,
    }
    assert set(_documents(app)) == {"autre.txt"}
    assert _count(app, "chunks") == 1 and _vec_rows(app) == 1  # `rowid` des vecteurs retirés aussi
    listed = (await client.get("/api/rag/documents")).json()
    assert [d["source"] for d in listed["documents"]] == ["autre.txt"]
    assert listed["totals"] == {"documents": 1, "chunks": 1}


async def test_the_deleted_text_is_in_neither_the_database_nor_the_journal(served):
    app, client = served
    await _import(client, **{"secret.txt": SECRET, "autre.txt": SECOND})
    for needle in (SECRET, SECOND):
        assert needle.encode() in _stored_bytes(
            app
        )  # le test sait voir le texte avant l'effacement
    doc_id = _documents(app)["secret.txt"]["id"]
    assert (await client.delete(f"/api/rag/documents/{doc_id}")).status_code == 200

    db = Path(app.state.store.path)
    wal = db.with_name(db.name + "-wal")
    assert SECRET.encode() not in db.read_bytes()
    assert SECRET.encode() not in wal.read_bytes()
    assert wal.stat().st_size == 0  # `wal_checkpoint(TRUNCATE)` en dernier
    assert SECOND.encode() in _stored_bytes(app)  # l'autre document est intact


@needs_vec
async def test_the_vector_residue_state_in_the_vec0_blob_after_a_delete_by_rowid(served):
    """Point différé de la spine : que reste-t-il du vecteur après `DELETE ... WHERE rowid` ?
    Constaté avec sqlite-vec 0.1.9 : rien. vec0 met à zéro les octets du vecteur supprimé dans son
    blob, et le `VACUUM` réécrit le fichier ; ni le vecteur entier ni un fragment de 16 octets ne
    se retrouvent dans le `.db` ou le `-wal`, alors que le vecteur du document voisin y est."""
    app, client = served
    await _import(client, **{"secret.txt": SECRET, "autre.txt": SECOND})

    def blob(text: str) -> bytes:
        vector = fake_vector(text)
        return struct.pack(f"{len(vector)}f", *vector)

    assert blob(SECRET) in _stored_bytes(app) and blob(SECOND) in _stored_bytes(app)
    doc_id = _documents(app)["secret.txt"]["id"]
    assert (await client.delete(f"/api/rag/documents/{doc_id}")).status_code == 200
    after = _stored_bytes(app)
    assert blob(SECRET) not in after and blob(SECRET)[:16] not in after
    assert blob(SECOND) in after


async def test_a_failed_document_is_deleted_with_no_chunk_to_remove(served):
    app, client = served
    started = await client.post("/api/rag/documents", files=_files(**{"vide.md": ""}))
    await _ended(client, started.json()["run_id"])
    doc = _documents(app)["vide.md"]
    assert doc["status"] == "failed"
    response = await client.delete(f"/api/rag/documents/{doc['id']}")
    assert response.status_code == 200
    assert response.json()["chunks_removed"] == 0 and response.json()["status"] == "failed"
    assert _documents(app) == {}


async def test_an_unknown_document_is_a_404(served):
    _, client = served
    response = await client.delete("/api/rag/documents/inconnu")
    assert response.status_code == 404 and response.json()["code"] == "not_found"


async def test_a_document_still_indexing_is_a_409_with_the_active_import(served):
    app, client = served
    app.state.embedders[FAKE_EMBED_REF.tag].script = [Sleep(0.6)]
    started = await client.post("/api/rag/documents", files=_files(**{"lent.txt": CATS}))
    run_id = started.json()["run_id"]
    while "lent.txt" not in _documents(app):
        await asyncio.sleep(0.02)
    doc = _documents(app)["lent.txt"]
    assert doc["status"] == "indexing"
    response = await client.delete(f"/api/rag/documents/{doc['id']}")
    assert response.status_code == 409
    envelope = response.json()
    assert envelope["code"] == "base_in_use" and envelope["message"] and envelope["action"]
    assert envelope["detail"]["run_id"] == run_id and envelope["detail"]["kind"] == "ingest"
    assert "lent.txt" in _documents(app)  # rien n'est supprimé
    await _ended(client, run_id)


async def test_a_document_cannot_be_deleted_while_a_question_runs(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    app.state.models[FAKE_REF.tag].script = [TextDelta("Début"), Sleep(0.6)]
    asked = await client.post(
        "/api/rag/runs", json={"question": "Où dort le chat ?", "model": FAKE_REF.tag}
    )
    run_id = asked.json()["run_id"]
    doc_id = _documents(app)["chats.txt"]["id"]
    response = await client.delete(f"/api/rag/documents/{doc_id}")
    assert response.status_code == 409 and response.json()["code"] == "base_in_use"
    assert response.json()["detail"] == {"technical": response.json()["detail"]["technical"],
                                         "run_id": run_id, "kind": "rag"}  # fmt: skip
    await _ended(client, run_id)
    assert (await client.delete(f"/api/rag/documents/{doc_id}")).status_code == 200


# --- Vider la base ----------------------------------------------------------------------------


async def test_clearing_deletes_everything_and_recreates_the_vector_table(served):
    app, client = served
    await _import(client, **{"secret.txt": SECRET, "autre.txt": SECOND})
    started = await client.post("/api/rag/documents", files=_files(**{"vide.md": ""}))
    await _ended(client, started.json()["run_id"])  # un document en échec, vidé aussi
    assert _count(app, "documents") == 3

    response = await client.delete("/api/rag/base", params={"expected_count": 2})
    assert response.status_code == 200
    assert response.json() == {"documents_removed": 3, "chunks_removed": 2}
    assert _count(app, "documents") == 0 and _count(app, "chunks") == 0
    assert _vec_rows(app) == 0
    if app.state.store.vec_available:  # la table est recréée, pas seulement vidée
        tables = app.state.store.read("SELECT name FROM sqlite_master WHERE name = 'chunks_vec_16'")
        assert len(tables) == 1
    for needle in (SECRET, SECOND):
        assert needle.encode() not in _stored_bytes(app)
    # La base repart : un import et une question marchent.
    await _import(client, **{"chats.txt": CATS})
    assert _count(app, "chunks") == 1 and _vec_rows(app) == 1


@needs_vec
async def test_clearing_leaves_no_vector_in_the_file(served):
    app, client = served
    await _import(client, **{"secret.txt": SECRET})
    vector = fake_vector(SECRET)
    blob = struct.pack(f"{len(vector)}f", *vector)
    assert blob in _stored_bytes(app)
    assert (await client.delete("/api/rag/base", params={"expected_count": 1})).status_code == 200
    assert blob not in _stored_bytes(app)
    db = Path(app.state.store.path)
    assert db.with_name(db.name + "-wal").stat().st_size == 0


async def test_a_stale_expected_count_deletes_nothing(served):
    app, client = served
    await _import(client, **{"secret.txt": SECRET, "autre.txt": SECOND})
    response = await client.delete("/api/rag/base", params={"expected_count": 5})
    assert response.status_code == 409
    envelope = response.json()
    assert envelope["code"] == "base_count_stale" and envelope["message"] and envelope["action"]
    assert envelope["detail"]["expected"] == 5 and envelope["detail"]["actual"] == 2
    assert _count(app, "documents") == 2 and _count(app, "chunks") == 2 and _vec_rows(app) == 2
    assert SECRET.encode() in _stored_bytes(app)
    # Le bon nombre passe.
    assert (await client.delete("/api/rag/base", params={"expected_count": 2})).status_code == 200


async def test_the_expected_count_is_required_and_a_number(served):
    _, client = served
    for params in ({}, {"expected_count": "beaucoup"}, {"expected_count": -1}):
        response = await client.delete("/api/rag/base", params=params)
        assert response.status_code == 422 and response.json()["code"] == "invalid_request"


async def test_an_empty_base_clears_to_zero(served):
    _, client = served
    response = await client.delete("/api/rag/base", params={"expected_count": 0})
    assert response.status_code == 200
    assert response.json() == {"documents_removed": 0, "chunks_removed": 0}


async def test_clearing_is_a_409_while_an_import_runs_and_nothing_is_deleted(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    app.state.embedders[FAKE_EMBED_REF.tag].script = [Sleep(0.6)]
    started = await client.post("/api/rag/documents", files=_files(**{"lent.txt": CARS}))
    run_id = started.json()["run_id"]
    response = await client.delete("/api/rag/base", params={"expected_count": 1})
    assert response.status_code == 409 and response.json()["code"] == "base_in_use"
    assert response.json()["detail"]["run_id"] == run_id
    assert "chats.txt" in _documents(app)
    await _ended(client, run_id)


async def test_clearing_is_a_409_while_a_question_runs(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    app.state.models[FAKE_REF.tag].script = [TextDelta("Début"), Sleep(0.6)]
    asked = await client.post(
        "/api/rag/runs", json={"question": "Où dort le chat ?", "model": FAKE_REF.tag}
    )
    response = await client.delete("/api/rag/base", params={"expected_count": 1})
    assert response.status_code == 409 and response.json()["code"] == "base_in_use"
    assert response.json()["detail"]["kind"] == "rag"
    await _ended(client, asked.json()["run_id"])
    assert (await client.delete("/api/rag/base", params={"expected_count": 1})).status_code == 200


async def test_replayed_sources_of_a_deleted_document_have_no_text(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    app.state.models[FAKE_REF.tag].script = [TextDelta("Sur le canapé.")]
    asked = (
        await client.post(
            "/api/rag/runs", json={"question": "Où dort le chat ?", "model": FAKE_REF.tag}
        )
    ).json()
    await _ended(client, asked["run_id"])
    assert (await client.delete("/api/rag/base", params={"expected_count": 1})).status_code == 200
    text = (await client.get(f"/api/runs/{asked['run_id']}/events")).text
    assert "Le chat domestique dort" not in text  # le texte de l'extrait a disparu du rejeu


# --- Réglages ---------------------------------------------------------------------------------


async def test_the_settings_start_from_the_toml_defaults(served):
    app, client = served
    body = (await client.get("/api/rag/settings")).json()
    assert body["chunk_size"] == 800 and body["chunk_overlap"] == 100
    assert body["top_k"] == 4 and body["strategy"] == "naive"
    assert body["embedding_model"] is None
    assert body["base"] == {"embedding_model": None, "documents": 0, "chunks": 0}
    assert body["strategies"] == ["naive", "hyde", "self_rag"]
    assert (
        body["verify_min_params_b"] == 3.0
    )  # seuil de l'avertissement « vérification peu fiable »
    assert body["limits"]["chunk_size"] == {"min": 100, "max": 8000}
    assert body["limits"]["top_k"] == {"min": 1, "max": 20}
    # sqlite-vec chargé : index persistant ; sans l'extension (CI macOS), repli en mémoire.
    assert body["index"] == {"persistent": app.state.store.vec_available}
    assert body["embedding_models"] == []  # Ollama injoignable : aucun modèle installé listé


async def test_a_put_keeps_the_other_fields_and_applies_to_the_next_import_and_question(served):
    app, client = served
    body = (await client.put("/api/rag/settings", json={"chunk_size": 200, "top_k": 2})).json()
    assert (body["chunk_size"], body["chunk_overlap"], body["top_k"]) == (200, 100, 2)
    again = (await client.put("/api/rag/settings", json={"strategy": "naive"})).json()
    assert (again["chunk_size"], again["top_k"]) == (200, 2)  # les champs absents restent
    assert (await client.get("/api/rag/settings")).json()["chunk_size"] == 200
    stored = app.state.preferences.get("rag.settings")
    assert stored == {"chunk_size": 200, "top_k": 2, "strategy": "naive"}

    run_id = await _import(client, **{"long.txt": " ".join(f"mot{i:03d}" for i in range(300))})
    params = (await client.get(f"/api/runs/{run_id}")).json()["params"]
    assert params["chunk_size"] == 200
    assert _documents(app)["long.txt"]["chunk_count"] > 4  # découpé à 200 caractères, pas 800
    app.state.models[FAKE_REF.tag].script = [TextDelta("Réponse.")]
    asked = (
        await client.post("/api/rag/runs", json={"question": "mot001 ?", "model": FAKE_REF.tag})
    ).json()
    snapshot = await _ended(client, asked["run_id"])
    assert snapshot["params"]["top_k"] == 2


async def test_a_null_gives_the_choice_back_to_the_toml(served):
    _, client = served
    await client.put("/api/rag/settings", json={"top_k": 9})
    body = (await client.put("/api/rag/settings", json={"top_k": None})).json()
    assert body["top_k"] == 4


@pytest.mark.parametrize(
    "payload",
    [
        {"chunk_size": 10},
        {"chunk_size": 99999},
        {"top_k": 0},
        {"top_k": 21},
        {"strategy": "agentic"},
        {"chunk_size": 200, "chunk_overlap": 200},
        {"inconnu": 1},
        {"embedding_model": ""},
    ],
)
async def test_a_bad_setting_is_a_422_and_nothing_is_stored(served, payload):
    app, client = served
    response = await client.put("/api/rag/settings", json=payload)
    assert response.status_code == 422 and response.json()["code"] == "invalid_request"
    assert app.state.preferences.get("rag.settings") is None


async def test_changing_the_embedding_of_a_non_empty_base_must_clear_first(tmp_path):
    async with rag_app(tmp_path) as (app, client):
        await _import(client, **{"chats.txt": CATS})
        response = await client.put("/api/rag/settings", json={"embedding_model": OTHER.tag})
        assert response.status_code == 409
        envelope = response.json()
        assert envelope["code"] == "embedding_change_needs_clear"
        assert envelope["message"] and envelope["action"]
        assert envelope["detail"]["current"] == FAKE_EMBED_REF.tag
        assert envelope["detail"]["requested"] == OTHER.tag
        assert app.state.preferences.get("rag.settings") is None  # rien n'est écrit
        # Le même modèle passe ; une autre valeur passe une fois la base vidée.
        same = await client.put("/api/rag/settings", json={"embedding_model": FAKE_EMBED_REF.tag})
        assert same.status_code == 200
        await client.delete("/api/rag/base", params={"expected_count": 1})
        changed = await client.put("/api/rag/settings", json={"embedding_model": OTHER.tag})
        assert changed.status_code == 200 and changed.json()["embedding_model"] == OTHER.tag
        await _import(client, **{"voitures.txt": CARS})  # le nouveau modèle sert à l'import
        assert {d["embedding_model"] for d in (await client.get("/api/rag/documents")).json()[
            "documents"]} == {OTHER.tag}  # fmt: skip


async def test_changing_the_embedding_is_a_409_while_an_import_runs(tmp_path):
    async with rag_app(tmp_path) as (app, client):
        app.state.embedders[FAKE_EMBED_REF.tag].script = [Sleep(0.6)]
        started = await client.post("/api/rag/documents", files=_files(**{"lent.txt": CATS}))
        response = await client.put("/api/rag/settings", json={"embedding_model": OTHER.tag})
        assert response.status_code == 409 and response.json()["code"] == "base_in_use"
        assert app.state.preferences.get("rag.settings") is None
        await _ended(client, started.json()["run_id"])


async def test_an_unknown_or_chat_model_cannot_be_the_embedding(served):
    _, client = served
    unknown = await client.put("/api/rag/settings", json={"embedding_model": "nulle-part:1"})
    assert unknown.status_code == 404 and unknown.json()["code"] == "model_not_found"
    chat = await client.put("/api/rag/settings", json={"embedding_model": FAKE_REF.tag})
    assert chat.status_code == 422 and chat.json()["code"] == "model_not_embedding"


async def test_the_app_never_writes_the_toml_file(served, tmp_path):
    toml = Path(__file__).resolve().parents[3] / "wavelocalai.toml"
    before = toml.read_bytes() if toml.exists() else None
    _, client = served
    await client.put("/api/rag/settings", json={"chunk_size": 300, "top_k": 3})
    assert (toml.read_bytes() if toml.exists() else None) == before
    assert list(tmp_path.rglob("*.toml")) == []


async def test_a_foreign_origin_cannot_delete_or_change_settings(served):
    _, client = served
    headers = {"Origin": "http://evil.example"}
    for call in (
        client.delete("/api/rag/documents/x", headers=headers),
        client.delete("/api/rag/base", params={"expected_count": 0}, headers=headers),
        client.put("/api/rag/settings", json={"top_k": 3}, headers=headers),
    ):
        response = await call
        assert response.status_code == 403 and response.json()["code"] == "forbidden_origin"


# --- Sans sqlite-vec : refus explicite --------------------------------------------------------


async def test_a_base_whose_vectors_were_lost_is_refused_with_its_own_message(
    tmp_path, monkeypatch
):
    """Repli numpy : les vecteurs vivent en mémoire. Après un redémarrage, une base « prête » n'a
    plus de vecteurs ; la question le dit (`vector_index_lost`), au lieu de « aucun document »."""
    monkeypatch.setattr("wavelocalai.web.app.select_index", lambda available: NumpyIndex())
    async with rag_app(tmp_path) as (app, client):
        await _import(client, **{"chats.txt": CATS})
        assert (await client.get("/api/rag/settings")).json()["index"] == {"persistent": False}
        app.state.rag._index.clear(None)  # le serveur a redémarré : l'index en mémoire est vide
        response = await client.post(
            "/api/rag/runs", json={"question": "Où dort le chat ?", "model": FAKE_REF.tag}
        )
        assert response.status_code == 409
        envelope = response.json()
        assert (
            envelope["code"] == "vector_index_lost" and envelope["message"] and envelope["action"]
        )
        rag_runs = app.state.store.read("SELECT count(*) AS n FROM runs WHERE kind = 'rag'")
        assert rag_runs[0]["n"] == 0  # aucun run `rag` n'a été créé
        # Vider puis réimporter répare.
        assert (
            await client.delete("/api/rag/base", params={"expected_count": 1})
        ).status_code == 200
        await _import(client, **{"chats.txt": CATS})
        app.state.models[FAKE_REF.tag].script = [TextDelta("Sur le canapé.")]
        ok = await client.post(
            "/api/rag/runs", json={"question": "Où dort le chat ?", "model": FAKE_REF.tag}
        )
        assert ok.status_code == 200
        await _ended(client, ok.json()["run_id"])


# --- Revue : `null` sur la découpe, retour au `.toml`, vecteurs vec0 laissés au repli -----------


async def test_a_null_chunk_size_or_overlap_gives_the_choice_back_to_the_toml(served):
    app, client = served
    await client.put("/api/rag/settings", json={"chunk_size": 300, "chunk_overlap": 50})
    response = await client.put("/api/rag/settings", json={"chunk_size": None})
    assert response.status_code == 200, response.text
    assert (response.json()["chunk_size"], response.json()["chunk_overlap"]) == (800, 50)
    response = await client.put("/api/rag/settings", json={"chunk_overlap": None})
    assert response.status_code == 200, response.text
    assert response.json()["chunk_overlap"] == 100
    stored = app.state.preferences.get("rag.settings")
    assert "chunk_size" not in stored and "chunk_overlap" not in stored


async def test_going_back_to_another_toml_embedding_on_a_non_empty_base_must_clear_first(tmp_path):
    """`null` rend le choix au `.toml` : s'il nomme un autre modèle que celui de la base, c'est un
    changement de modèle comme un autre (AD-16)."""
    async with rag_app(tmp_path, rag={"embedding_model": OTHER.tag}) as (app, client):
        chosen = await client.put("/api/rag/settings", json={"embedding_model": FAKE_EMBED_REF.tag})
        assert chosen.status_code == 200  # base vide : libre
        await _import(client, **{"chats.txt": CATS})  # indexé avec le modèle choisi
        response = await client.put("/api/rag/settings", json={"embedding_model": None})
        assert response.status_code == 409, response.text
        envelope = response.json()
        assert envelope["code"] == "embedding_change_needs_clear"
        assert envelope["detail"] == {
            **envelope["detail"],
            "current": FAKE_EMBED_REF.tag,
            "requested": OTHER.tag,
        }
        stored = app.state.preferences.get("rag.settings")
        assert stored["embedding_model"] == FAKE_EMBED_REF.tag  # rien n'a changé


async def test_without_a_toml_embedding_a_null_is_accepted_on_a_non_empty_base(served):
    _, client = served
    await _import(client, **{"chats.txt": CATS})
    response = await client.put("/api/rag/settings", json={"embedding_model": None})
    assert response.status_code == 200, response.text


def _stray_vec_table(app, chunk_ids: list[int]) -> None:
    """Une table vec0 écrite un jour avec sqlite-vec, que l'index de repli ignore."""
    from wavelocalai.rag.index import SqliteVecIndex

    app.state.store.write(
        lambda conn: SqliteVecIndex().add(conn, chunk_ids, [fake_vector("x", 8)] * len(chunk_ids))
    ).result()


@needs_vec
async def test_the_fallback_index_still_erases_vectors_left_in_vec0_tables(tmp_path, monkeypatch):
    monkeypatch.setattr("wavelocalai.web.app.select_index", lambda available: NumpyIndex())
    async with rag_app(tmp_path) as (app, client):
        await _import(client, **{"secret.txt": SECRET, "autre.txt": SECOND})
        ids = [r["id"] for r in app.state.store.read("SELECT id FROM chunks ORDER BY id")]
        _stray_vec_table(app, ids)
        assert _vec_rows_in_files(app) == 2
        doc = _documents(app)["secret.txt"]["id"]
        assert (await client.delete(f"/api/rag/documents/{doc}")).status_code == 200
        assert _vec_rows_in_files(app) == 1  # la ligne du document supprimé est partie
        cleared = await client.delete("/api/rag/base", params={"expected_count": 1})
        assert cleared.status_code == 200, cleared.text
        assert _vec_rows_in_files(app) == 0


def _vec_rows_in_files(app) -> int:
    store = app.state.store
    names = store.read(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name GLOB 'chunks_vec_[0-9]*'"
    )
    return sum(
        store.read(f"SELECT count(*) AS n FROM {n['name']}", vec=True)[0]["n"]  # noqa: S608
        for n in names
        if n["name"].removeprefix("chunks_vec_").isdigit()
    )


@needs_vec
def test_vectors_that_cannot_be_erased_without_sqlite_vec_refuse_the_deletion(tmp_path):
    """Sans le module vec0, une table vec0 ne se vide ni ne se supprime : refus, rien n'est perdu
    en mémoire ni dans le fichier."""
    import sqlite3

    from wavelocalai.errors import AppError
    from wavelocalai.rag.index import SqliteVecIndex
    from wavelocalai.rag.manage import _erase_stray_vectors
    from wavelocalai.store.vec import load_vec

    path = tmp_path / "base.db"
    with contextlib.closing(sqlite3.connect(path)) as conn:
        assert load_vec(conn)
        SqliteVecIndex().add(conn, [1, 2], [fake_vector("a", 8), fake_vector("b", 8)])
        conn.commit()
    index = NumpyIndex()
    index.add(None, [1], [fake_vector("a", 8)])
    with contextlib.closing(sqlite3.connect(path)) as conn:  # sans l'extension
        for ids in ([1], None):
            with pytest.raises(AppError) as refused:
                _erase_stray_vectors(conn, index, ids)
            assert refused.value.code == "vector_tables_unreachable"
        _erase_stray_vectors(conn, index, [])  # aucun extrait : rien à effacer, pas de refus
    assert index.count(None) == 1
