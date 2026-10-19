"""Flow 2 d'`EXPERIENCE.md` contre le vrai Ollama (story 4.9, marqueur `integration`).

La note de cadrage de l'atelier (`.docx`, 14 extraits) est indexée par un modèle d'embedding **déjà
installé**, puis `qwen2.5:1.5b` répond à une question de chaque stratégie à partir des extraits
trouvés : `naive`, puis `self_rag` (report de la revue de la 4.6 : la boucle de notation et de
reformulation n'avait jamais tourné sur un vrai modèle). CodeCarbon est le vrai (fixture
`real_meter`), aucun cloud, rien n'est téléchargé, la base est en dossier temporaire. Saut propre,
avec sa raison, si Ollama ne répond pas ou si l'un des deux modèles manque.
"""

from __future__ import annotations

import httpx
import pytest

from wavelocalai.config import load_settings
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT
from ..web.conftest import parse_sse
from ..workshop_note import ANSWER_PARAGRAPH, ANSWER_SENTENCE, FILE_NAME, QUESTION, make_note
from .test_rag_ollama import _installed_embedding_model
from .test_rag_question_ollama import CHAT_MODEL, _require_chat_model, _until_done

pytestmark = pytest.mark.integration

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def real_settings(tmp_path):
    return load_settings(
        env_file=tmp_path / "absent.env",
        environ={},
        overrides={"data": {"dir": tmp_path / "data"}},
    )


async def _ask(client, strategy: str) -> tuple[dict, list[dict]]:
    body = {"question": QUESTION, "model": CHAT_MODEL, "strategy": strategy}
    response = await client.post("/api/rag/runs", json=body)
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    snapshot = await _until_done(client, run_id)
    events = [
        frame["data"]
        for frame in parse_sse((await client.get(f"/api/runs/{run_id}/events")).text)[0]
    ]
    return snapshot, events


def _sources(events: list[dict]) -> list[dict]:
    return next(e for e in events if e["type"] == "sources")["data"]["sources"]


async def test_flow_2_on_a_real_model_naive_then_self_rag_then_the_mistaken_clear(
    real_settings, real_meter
):
    embedding_model = _installed_embedding_model(real_settings.ollama.host)
    _require_chat_model(real_settings.ollama.host)
    app = create_app(real_settings, meter=real_meter)
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url=f"http://127.0.0.1:{TEST_PORT}"
        ) as client:
            # Base vide : aucune question possible.
            refused = await client.post(
                "/api/rag/runs", json={"question": QUESTION, "model": CHAT_MODEL}
            )
            assert refused.status_code == 409
            assert refused.json()["code"] == "rag_base_empty"

            # L'import : « 14 extraits ajoutés depuis 1 document ».
            imported = await client.post(
                "/api/rag/documents",
                files=[("files", (FILE_NAME, make_note(), DOCX))],
                data={"embedding_model": embedding_model},
            )
            assert imported.status_code == 200, imported.text
            assert (await _until_done(client, imported.json()["run_id"]))["status"] == "ok"
            listed = (await client.get("/api/rag/documents")).json()
            assert listed["totals"] == {"documents": 1, "chunks": 14}

            # naive : les sources avant la réponse, le passage de la phrase qui répond (D-21).
            snapshot, events = await _ask(client, "naive")
            assert snapshot["status"] == "ok", snapshot
            types = [e["type"] for e in events]
            assert types.index("sources") < types.index("token")
            sources = _sources(events)
            assert all(source["document"] == FILE_NAME for source in sources)
            cited = next(s for s in sources if s["text"] == ANSWER_PARAGRAPH)
            passage = cited["passage"]
            assert passage is not None
            assert cited["text"][passage["start"] : passage["end"]] == ANSWER_SENTENCE
            assert "".join(e["data"]["text"] for e in events if e["type"] == "token").strip()

            # self_rag : la boucle de notation tourne sur un vrai modèle, et la réponse part.
            snapshot, events = await _ask(client, "self_rag")
            assert snapshot["status"] == "ok", snapshot
            types = [e["type"] for e in events]
            assert types.index("sources") < types.index("token")
            steps = [e["data"] for e in events if e["type"] == "retrieval_step"]
            assert [step["step"] for step in steps][:3] == ["embedding", "search", "grade"]
            assert all(step["strategy"] == "self_rag" for step in steps)
            assert _sources(events), "aucune source après la boucle Self-RAG"
            assert "".join(e["data"]["text"] for e in events if e["type"] == "token").strip()

            # « Vider » : le nombre d'extraits affiché est celui que le serveur vérifie.
            cleared = await client.delete("/api/rag/base", params={"expected_count": 14})
            assert cleared.status_code == 200, cleared.text
            assert cleared.json() == {"documents_removed": 1, "chunks_removed": 14}
            assert (await client.get("/api/rag/documents")).json()["totals"] == {
                "documents": 0,
                "chunks": 0,
            }
