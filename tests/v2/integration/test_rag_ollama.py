"""Indexation de vrais documents par le vrai Ollama (story 4.1, marqueur `integration`, aucun cloud).

Un modèle d'embedding **déjà installé** (lu dans `GET /api/tags`, rien n'est téléchargé) vectorise
deux petits textes importés par `POST /api/rag/documents` ; CodeCarbon est le vrai (fixture
`real_meter`). Saut propre, avec sa raison, si Ollama ne répond pas ou si aucun modèle d'embedding
n'est installé.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from wavelocalai.config import load_settings
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT

pytestmark = pytest.mark.integration

CATS = "Le chat domestique dort sur le canapé et ronronne quand on le caresse. " * 3
CARS = "La voiture électrique recharge sa batterie sur une borne rapide de l'autoroute. " * 3


@pytest.fixture
def real_settings(tmp_path):
    return load_settings(
        env_file=tmp_path / "absent.env",
        environ={},
        overrides={"data": {"dir": tmp_path / "data"}, "rag": {"embed_batch_size": 4}},
    )


def _installed_embedding_model(host: str) -> str:
    try:
        tags = httpx.get(f"{host}/api/tags", timeout=2.0, trust_env=False).json()
    except Exception:  # noqa: BLE001 - tout échec = Ollama injoignable
        pytest.skip("Ollama ne répond pas")
    for model in tags.get("models", []):
        name = model.get("model") or model.get("name") or ""
        if "embed" in name.lower():
            return name
    pytest.skip("aucun modèle d'embedding installé dans Ollama (rien n'est téléchargé par le test)")


async def test_two_documents_are_indexed_with_a_real_embedding_model(real_settings, real_meter):
    tag = _installed_embedding_model(real_settings.ollama.host)
    app = create_app(real_settings, meter=real_meter)
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{TEST_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            response = await client.post(
                "/api/rag/documents",
                files=[
                    ("files", ("chats.txt", CATS.encode(), "text/plain")),
                    ("files", ("voitures.md", CARS.encode(), "text/markdown")),
                ],
                data={"embedding_model": tag},
            )
            assert response.status_code == 200, response.text
            run_id = response.json()["run_id"]
            async with asyncio.timeout(300):
                while (snap := (await client.get(f"/api/runs/{run_id}")).json())[
                    "status"
                ] == "running":
                    await asyncio.sleep(0.3)
            carbon = (await client.get("/api/carbon/session")).json()
        assert snap["status"] == "ok", snap

        store = app.state.store
        docs = {r["source"]: r for r in store.read("SELECT * FROM documents")}
        assert {n: d["status"] for n, d in docs.items()} == {
            "chats.txt": "ready",
            "voitures.md": "ready",
        }
        dims = {d["embedding_dim"] for d in docs.values()}
        assert len(dims) == 1 and dims.pop() > 100  # la dimension réelle du modèle
        assert {d["embedding_model"] for d in docs.values()} == {tag}

        # chaque lot est une feuille mesurée par le vrai CodeCarbon, comptée dans la session
        leaves = store.read("SELECT * FROM runs WHERE parent_run_id = ?", (run_id,))
        assert leaves and {leaf["kind"] for leaf in leaves} == {"embedding"}
        for leaf in leaves:
            assert leaf["status"] == "ok" and leaf["co2_method"] == "codecarbon"
            assert leaf["co2_mg"] > 0 and leaf["energy_wh"] > 0
        assert carbon["by_module"]["ingest"]["mg"] > 0  # comptés dans le CO2 de session
        assert carbon["by_module"]["ingest"]["runs"] == len(leaves)

        # les vecteurs sont dans sqlite-vec : l'extrait le plus proche d'un texte est le sien
        ref = app.state.registry.resolve_embedder(tag)
        embedder = app.state.ingest._factory.embedder(ref)
        (query,) = await embedder.embed(["Mon chat ronronne sur le canapé."])
        index = app.state.ingest._index
        owner = {
            r["id"]: r["document_id"] for r in store.read("SELECT id, document_id FROM chunks")
        }
        found = await asyncio.to_thread(_search, store, index, query, 1)
        assert owner[found[0][0]] == docs["chats.txt"]["id"], json.dumps(found)


def _search(store, index, vector, k):
    import sqlite3

    from wavelocalai.store.vec import load_vec

    conn = sqlite3.connect(store.path)
    try:
        load_vec(conn)
        return index.search(conn, vector, k)
    finally:
        conn.close()
