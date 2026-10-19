"""Supprimer un document et vider la base, avec un vrai modèle d'embedding (story 4.3, `integration`).

Un modèle d'embedding **déjà installé** (lu dans `GET /api/tags`) indexe deux petits documents ;
la suppression de l'un retire son texte des octets du `.db` et du `-wal`, et ses vecteurs réels (768
dimensions pour `nomic-embed-text`) de la table vec0 ; « Vider » recrée la table. Rien n'est
téléchargé ; saut propre, avec sa raison, si Ollama ne répond pas ou si aucun modèle ne convient.
"""

from __future__ import annotations

import asyncio
import struct
from pathlib import Path

import httpx
import pytest

from wavelocalai.config import load_settings
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, needs_vec
from .test_rag_ollama import _installed_embedding_model

pytestmark = pytest.mark.integration

SECRET = "Le dossier Zorglub-quarante-deux concerne la maintenance des licornes de Strasbourg."
OTHER = "La voiture électrique recharge sa batterie sur une borne rapide de l'autoroute."


@pytest.fixture
def real_settings(tmp_path):
    return load_settings(
        env_file=tmp_path / "absent.env",
        environ={},
        overrides={"data": {"dir": tmp_path / "data"}},
    )


async def _until_done(client, run_id, timeout=300):
    async with asyncio.timeout(timeout):
        while (await client.get(f"/api/runs/{run_id}")).json()["status"] == "running":
            await asyncio.sleep(0.3)


def _bytes(app) -> bytes:
    db = Path(app.state.store.path)
    wal = db.with_name(db.name + "-wal")
    return db.read_bytes() + (wal.read_bytes() if wal.exists() else b"")


@needs_vec
async def test_deleting_and_clearing_with_real_vectors_leave_nothing_behind(
    real_settings, real_meter
):
    model = _installed_embedding_model(real_settings.ollama.host)
    app = create_app(real_settings, meter=real_meter)
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url=f"http://127.0.0.1:{TEST_PORT}"
        ) as client:
            files = [
                ("files", ("secret.txt", SECRET.encode(), "text/plain")),
                ("files", ("autre.txt", OTHER.encode(), "text/plain")),
            ]
            started = await client.post(
                "/api/rag/documents", files=files, data={"embedding_model": model}
            )
            assert started.status_code == 200, started.text
            await _until_done(client, started.json()["run_id"])
            docs = {
                r["source"]: r["id"]
                for r in app.state.store.read("SELECT id, source FROM documents")
            }
            assert set(docs) == {"secret.txt", "autre.txt"}
            # Les vecteurs réels du premier document, lus dans la table avant l'effacement.
            table = next(
                row["name"]
                for row in app.state.store.read(
                    "SELECT name FROM sqlite_master WHERE name GLOB 'chunks_vec_[0-9]*'"
                )
                if row["name"].removeprefix("chunks_vec_").isdigit()  # sans les tables d'ombre
            )
            chunk = app.state.store.read(
                "SELECT id FROM chunks WHERE document_id = ?", (docs["secret.txt"],)
            )[0]["id"]
            vector = app.state.store.read(
                f"SELECT embedding FROM {table} WHERE rowid = ?",  # noqa: S608
                (chunk,),
                vec=True,
            )[0]["embedding"]
            assert SECRET.encode() in _bytes(app) and bytes(vector) in _bytes(app)

            assert (
                await client.delete(f"/api/rag/documents/{docs['secret.txt']}")
            ).status_code == 200
            after = _bytes(app)
            assert SECRET.encode() not in after
            assert bytes(vector) not in after and bytes(vector)[:16] not in after  # point différé
            assert struct.unpack("f", bytes(vector)[:4])  # (le vecteur était bien un `float[]`)

            total = (await client.get("/api/rag/documents")).json()["totals"]["chunks"]
            assert (
                await client.delete("/api/rag/base", params={"expected_count": total})
            ).status_code == 200
            assert app.state.store.read("SELECT count(*) AS n FROM chunks")[0]["n"] == 0
            assert OTHER.encode() not in _bytes(app)
