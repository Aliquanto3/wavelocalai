"""L'évaluation de la qualité contre le vrai Ollama du poste (story 7.1, marqueur `integration`).

La note de cadrage de l'atelier (`.docx`) est indexée par un modèle d'embedding **déjà installé**,
puis `qwen2.5:1.5b` répond à une question sur ses extraits et sert aussi de juge : le juge découpe la
réponse en affirmations, les vérifie, retrouve des questions et désigne les extraits utiles, par la
sortie structurée d'Ollama (`format`). CodeCarbon est le vrai (fixture `real_meter`), aucun cloud,
rien n'est téléchargé, la base est en dossier temporaire. Saut propre, avec sa raison, si Ollama ne
répond pas ou si l'un des modèles manque.

Un juge de 1,5 milliard de paramètres est peu fiable (l'événement `judge` le dit) : le test ne
vérifie pas la justesse des notes, seulement que chaque note est un entier de 0 à 100 ou un « non
évalué » avec sa raison (jamais 0 pour un inconnu), et qu'au moins une est notée.
"""

from __future__ import annotations

import httpx
import pytest

from wavelocalai.config import load_settings
from wavelocalai.runs.eval_snapshot import METRICS
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT
from ..web.conftest import parse_sse
from ..workshop_note import FILE_NAME, QUESTION, make_note
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


async def test_a_real_model_is_scored_on_faithfulness_relevance_and_precision(
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
            body = {"questions": [QUESTION], "models": [CHAT_MODEL], "judge": CHAT_MODEL}
            refused = await client.post("/api/rag/eval/runs", json=body)
            assert refused.status_code == 409 and refused.json()["code"] == "rag_base_empty"

            imported = await client.post(
                "/api/rag/documents",
                files=[("files", (FILE_NAME, make_note(), DOCX))],
                data={"embedding_model": embedding_model},
            )
            assert imported.status_code == 200, imported.text
            assert (await _until_done(client, imported.json()["run_id"]))["status"] == "ok"

            started = await client.post("/api/rag/eval/runs", json=body)
            assert started.status_code == 200, started.text
            run_id = started.json()["run_id"]
            snapshot = await _until_done(client, run_id, timeout=900)
            events = [
                f["data"]
                for f in parse_sse((await client.get(f"/api/runs/{run_id}/events")).text)[0]
            ]

    assert snapshot["status"] == "ok", events[-1]
    assert snapshot["partial"] is False
    info = next(e["data"] for e in events if e["type"] == "judge")
    assert info["model"] == CHAT_MODEL and info["unreliable"] is True  # 1,5 milliard : peu fiable
    types = [e["type"] for e in events]
    assert types.index("sources") < types.index("eval_answer") < types.index("eval_metric")
    answer = next(e["data"] for e in events if e["type"] == "eval_answer")
    assert answer["error"] is None and answer["text"].strip()
    metrics = {e["data"]["metric"]: e["data"] for e in events if e["type"] == "eval_metric"}
    assert set(metrics) == set(METRICS)
    for name, got in metrics.items():
        if got["score"] is None:
            assert got["reason"].startswith("non évalué"), (name, got)
        else:
            assert isinstance(got["score"], int) and 0 <= got["score"] <= 100, (name, got)
    assert any(got["score"] is not None for got in metrics.values()), metrics
    faith = metrics["faithfulness"]
    if faith["score"] is not None:
        assert faith["verdicts"] and all(
            v["verdict"] in ("appuyée", "non appuyée", "contredite") for v in faith["verdicts"]
        )
    leaf_kinds = [c["kind"] for c in snapshot["children"]]
    assert {"embedding", "generation", "judge"} <= set(leaf_kinds)
