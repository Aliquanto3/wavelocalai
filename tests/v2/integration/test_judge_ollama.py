"""Le juge de l'Arène contre le vrai Ollama du poste, avec `qwen2.5:1.5b` (marqueur `integration`,
aucun cloud, rien n'est téléchargé). Saut propre si Ollama est injoignable ou le modèle absent.

`format` d'Ollama contraint la sortie au schéma : la note revient en entier de 0 à 100.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from wavelocalai.config import load_settings
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT
from ..web.conftest import parse_sse

pytestmark = pytest.mark.integration

JUDGE = "qwen2.5:1.5b"


@pytest.fixture
def real_settings(tmp_path):
    return load_settings(
        env_file=tmp_path / "absent.env",
        environ={},
        overrides={"data": {"dir": tmp_path / "data"}},
    )


def _require_model(host: str) -> None:
    try:
        tags = httpx.get(f"{host}/api/tags", timeout=2.0, trust_env=False).json()
    except Exception:  # noqa: BLE001 - tout échec = Ollama injoignable
        pytest.skip("Ollama ne répond pas")
    if JUDGE not in {m.get("model") for m in tags.get("models", [])}:
        pytest.skip(f"{JUDGE} n'est pas installé")


async def test_the_real_judge_scores_each_answer_out_of_100(real_settings, real_meter):
    _require_model(real_settings.ollama.host)
    app = create_app(real_settings, meter=real_meter)
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{TEST_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            body = {
                "models": [JUDGE, "granite4:350m"],
                "prompt": "Quelle est la capitale de la France ? Réponds en une phrase.",
                "judge": JUDGE,
                "criteria": ["exactitude", "concision"],
            }
            response = await client.post("/api/arena/runs", json=body)
            if response.status_code == 404:  # granite4:350m absent : se contenter de deux tags
                pytest.skip("granite4:350m n'est pas installé")
            assert response.status_code == 200, response.text
            run_id = response.json()["run_id"]
            async with asyncio.timeout(300):
                while (await client.get(f"/api/runs/{run_id}")).json()["status"] == "running":
                    await asyncio.sleep(0.2)
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            events = [
                f["data"]
                for f in parse_sse((await client.get(f"/api/runs/{run_id}/events")).text)[0]
            ]
    assert snapshot["status"] == "ok", events[-1]
    info = next(e["data"] for e in events if e["type"] == "judge")
    assert info["model"] == JUDGE and info["unreliable"] is True  # 1,5 milliard : note peu fiable
    scores = {e["data"]["lane"]: e["data"] for e in events if e["type"] == "judge_score"}
    assert set(scores) == {JUDGE, "granite4:350m"}
    for lane, got in scores.items():
        assert isinstance(got["score"], int) and 0 <= got["score"] <= 100, (lane, got)
        assert got["reason"].strip()
        statuses = [
            e["data"]["status"]
            for e in events
            if e["type"] == "lane_status" and e["data"]["lane"] == lane
        ]
        assert statuses[-2:] == ["judging", "done"], statuses
    judged = [c for c in snapshot["children"] if c["kind"] == "judge"]
    assert len(judged) == 2 and all(c["status"] == "ok" for c in judged)
    assert all(c["metrics"]["co2"]["method"] == "codecarbon" for c in judged)
