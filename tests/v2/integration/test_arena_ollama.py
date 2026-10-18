"""Arène contre le vrai Ollama du poste, sur deux petits modèles déjà installés (marqueur
`integration`, aucun cloud, rien n'est téléchargé).

Saut propre si Ollama est injoignable ou si un des deux modèles manque.
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

TAGS = ("qwen2.5:1.5b", "granite4:350m")


@pytest.fixture
def real_settings(tmp_path):
    return load_settings(
        env_file=tmp_path / "absent.env",
        environ={},
        overrides={"data": {"dir": tmp_path / "data"}},
    )


def _require_models(host: str) -> None:
    try:
        tags = httpx.get(f"{host}/api/tags", timeout=2.0, trust_env=False).json()
    except Exception:  # noqa: BLE001 - tout échec = Ollama injoignable
        pytest.skip("Ollama ne répond pas")
    installed = {m.get("model") for m in tags.get("models", [])}
    for tag in TAGS:
        if tag not in installed:
            pytest.skip(f"{tag} n'est pas installé")


async def test_two_real_local_models_answer_one_after_the_other(real_settings, real_meter):
    _require_models(real_settings.ollama.host)
    app = create_app(real_settings, meter=real_meter)
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{TEST_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            body = {"models": list(TAGS), "prompt": "Réponds par un seul mot : bonjour."}
            response = await client.post("/api/arena/runs", json=body)
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
    assert events[-1]["data"]["status"] == "ok"
    for tag in TAGS:
        lane = [e for e in events if e["data"].get("lane") == tag]
        statuses = [e["data"]["status"] for e in lane if e["type"] == "lane_status"]
        assert statuses[0] == "waiting" and statuses[-1] == "done", (tag, statuses)
        assert "".join(e["data"]["text"] for e in lane if e["type"] == "token").strip()
        metrics = next(e["data"] for e in lane if e["type"] == "metrics")
        assert metrics["tps_source"] == "ollama_eval" and metrics["origin"] == "local"
        # Vraie mesure CodeCarbon, un tracker par lane locale (AD-10, AD-11).
        assert metrics["co2"]["method"] == "codecarbon" and metrics["co2"]["mg"] is not None
        assert metrics["co2"]["mg"] > 0 and metrics["energy_wh"] is not None
    # Un seul modèle à la fois en mémoire : le second ne produit rien avant la fin du premier.
    first, second = TAGS
    last_first = max(
        i for i, e in enumerate(events) if e["data"].get("lane") == first and e["type"] == "token"
    )
    first_second = min(
        i for i, e in enumerate(events) if e["data"].get("lane") == second and e["type"] == "token"
    )
    assert last_first < first_second
