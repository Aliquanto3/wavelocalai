"""Question posée à de vrais documents par le vrai Ollama (story 4.4, marqueur `integration`).

Un modèle d'embedding **déjà installé** (lu dans `GET /api/tags`) indexe trois petits documents, puis
`qwen2.5:1.5b` répond à une question à partir des extraits trouvés ; CodeCarbon est le vrai (fixture
`real_meter`), aucun cloud, rien n'est téléchargé. Saut propre, avec sa raison, si Ollama ne répond
pas ou si l'un des deux modèles manque.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from wavelocalai.config import load_settings
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT
from ..web.conftest import parse_sse
from .test_rag_ollama import _installed_embedding_model

pytestmark = pytest.mark.integration

CHAT_MODEL = "qwen2.5:1.5b"
CATS = (
    "Le chat domestique dort sur le canapé du salon. Il ronronne quand on le caresse. "
    "La nuit, il chasse les souris dans le jardin."
)
CARS = (
    "La voiture électrique recharge sa batterie sur une borne rapide de l'autoroute en trente "
    "minutes. L'autonomie dépend de la vitesse et de la température extérieure."
)
CONTRACT = (
    "Le contrat de maintenance prévoit une intervention sous quatre heures ouvrées en cas "
    "d'incident majeur. Les pénalités de retard sont plafonnées à dix pour cent du montant annuel."
)
QUESTION = "Où dort le chat domestique ?"


@pytest.fixture
def real_settings(tmp_path):
    return load_settings(
        env_file=tmp_path / "absent.env",
        environ={},
        overrides={"data": {"dir": tmp_path / "data"}},
    )


def _require_chat_model(host: str) -> None:
    try:
        tags = httpx.get(f"{host}/api/tags", timeout=2.0, trust_env=False).json()
    except Exception:  # noqa: BLE001 - tout échec = Ollama injoignable
        pytest.skip("Ollama ne répond pas")
    if not any(m.get("model") == CHAT_MODEL for m in tags.get("models", [])):
        pytest.skip(f"{CHAT_MODEL} n'est pas installé (rien n'est téléchargé par le test)")


async def _until_done(client, run_id, timeout=300):
    async with asyncio.timeout(timeout):
        while (snapshot := (await client.get(f"/api/runs/{run_id}")).json())["status"] == "running":
            await asyncio.sleep(0.3)
    return snapshot


async def test_a_real_question_gets_its_sources_first_then_a_measured_answer(
    real_settings, real_meter
):
    embedding_model = _installed_embedding_model(real_settings.ollama.host)
    _require_chat_model(real_settings.ollama.host)
    app = create_app(real_settings, meter=real_meter)
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{TEST_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            files = [
                ("files", ("chats.txt", CATS.encode(), "text/plain")),
                ("files", ("voitures.md", CARS.encode(), "text/markdown")),
                ("files", ("contrat.txt", CONTRACT.encode(), "text/plain")),
            ]
            imported = await client.post(
                "/api/rag/documents", files=files, data={"embedding_model": embedding_model}
            )
            assert imported.status_code == 200, imported.text
            assert (await _until_done(client, imported.json()["run_id"]))["status"] == "ok"

            body = {"question": QUESTION, "model": CHAT_MODEL, "strategy": "naive"}
            response = await client.post("/api/rag/runs", json=body)
            assert response.status_code == 200, response.text
            started = response.json()
            snapshot = await _until_done(client, started["run_id"])
            events = [
                f["data"]
                for f in parse_sse(
                    (await client.get(f"/api/runs/{started['run_id']}/events")).text
                )[0]
            ]
            carbon = (await client.get("/api/carbon/session")).json()
            first = next(e for e in events if e["type"] == "sources")["data"]["sources"][0]
            chunk = await client.get(f"/api/rag/chunks/{first['chunk_id']}")
    assert snapshot["status"] == "ok", snapshot

    types = [e["type"] for e in events]
    assert types.index("sources") < types.index("token")  # les sources avant le premier jeton
    sources = next(e for e in events if e["type"] == "sources")["data"]["sources"]
    assert sources[0]["document"] == "chats.txt" and sources[0]["text"] == CATS
    assert sources[0]["relevance_label"] in {"très proche", "proche"}  # un vrai embedding
    assert sources[0]["raw_score"] > 0.6 and sources[0]["rank"] == 1
    passage = sources[0]["passage"]
    assert passage is not None
    assert (
        CATS[passage["start"] : passage["end"]] == "Le chat domestique dort sur le canapé du salon."
    )
    assert chunk.status_code == 200 and chunk.json()["text"] == CATS

    answer = "".join(e["data"]["text"] for e in events if e["type"] == "token")
    assert answer.strip()
    metrics = next(e for e in events if e["type"] == "metrics")["data"]
    assert metrics["tps_source"] == "ollama_eval" and metrics["tps"] > 0  # débit D3
    assert 0 < metrics["retrieval_s"] < metrics["total_s"] + 30
    assert metrics["co2"]["method"] == "codecarbon" and metrics["co2"]["mg"] > 0

    # deux feuilles mesurées par le vrai CodeCarbon, comptées dans la session (module `rag`)
    leaves = {c["kind"]: c for c in snapshot["children"]}
    assert set(leaves) == {"embedding", "generation"}
    for leaf in leaves.values():
        assert leaf["status"] == "ok" and leaf["metrics"]["co2"]["method"] == "codecarbon"
        assert leaf["metrics"]["co2"]["mg"] > 0
    assert carbon["by_module"]["rag"]["runs"] == 2 and carbon["by_module"]["rag"]["mg"] > 0
