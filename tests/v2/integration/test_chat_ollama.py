"""Chat contre le vrai Ollama du poste, sur `qwen2.5:1.5b` (marqueur `integration`, aucun cloud).

Saut propre si Ollama est injoignable ou si le modèle n'est pas installé. Le débit attendu est celui
d'Ollama (`eval_count / eval_duration`, D3), donc `tps_source = "ollama_eval"`.
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

TAG = "qwen2.5:1.5b"


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
    if not any(m.get("model") == TAG for m in tags.get("models", [])):
        pytest.skip(f"{TAG} n'est pas installé")


async def test_real_ollama_streams_a_reply_with_ollama_eval_throughput(real_settings):
    _require_model(real_settings.ollama.host)
    app = create_app(real_settings)
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{TEST_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            body = {"model": TAG, "message": "Réponds par un seul mot : bonjour.", "temperature": 0}
            response = await client.post("/api/chat/runs", json=body)
            assert response.status_code == 200, response.text
            run_id = response.json()["run_id"]
            async with asyncio.timeout(180):
                while (await client.get(f"/api/runs/{run_id}")).json()["status"] == "running":
                    await asyncio.sleep(0.2)
            events = [
                f["data"]
                for f in parse_sse((await client.get(f"/api/runs/{run_id}/events")).text)[0]
            ]
    assert events[-1]["data"]["status"] == "ok", events[-1]
    tokens = [e["data"]["text"] for e in events if e["type"] == "token"]
    assert "".join(tokens).strip()
    metrics = next(e["data"] for e in events if e["type"] == "metrics")
    assert metrics["tps_source"] == "ollama_eval" and metrics["tps"] > 0
    assert metrics["eval_tokens"] > 0 and metrics["eval_s"] > 0 and metrics["total_s"] > 0
    assert metrics["ttft_s"] is not None and metrics["co2"]["method"] == "unmeasurable"
