"""CO2 mesuré de vraies réponses locales (story 2.3, marqueur `integration`, aucun cloud).

Deux petits modèles de chat **déjà installés** (lus dans `GET /api/tags`, rien n'est téléchargé) : leurs
`co2.mg` mesurés par CodeCarbon diffèrent, et aucun n'est la constante de la v1 (0,19 mg/token).
Saut propre si Ollama ne répond pas ou si moins de deux modèles de chat conviennent.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from wavelocalai.config import load_settings
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT

pytestmark = pytest.mark.integration

V1_MG_PER_TOKEN = 0.19  # la constante que la v2 remplace
NOT_TESTABLE_FAMILIES = {"dflash"}  # Bonsai 2 : ne répond pas sur cet Ollama
MIN_SIZE_RATIO = 1.5  # « tailles différentes » : le second pèse au moins 1,5 fois le premier


@pytest.fixture
def real_settings(tmp_path):
    return load_settings(
        env_file=tmp_path / "absent.env",
        environ={},
        overrides={"data": {"dir": tmp_path / "data"}},
    )


def _smallest_chat_pair(host: str) -> tuple[dict, dict]:
    """Le plus petit modèle de chat installé, puis le plus petit qui pèse au moins 1,5 fois plus."""
    try:
        tags = httpx.get(f"{host}/api/tags", timeout=2.0, trust_env=False).json()
    except Exception:  # noqa: BLE001 - tout échec = Ollama injoignable
        pytest.skip("Ollama ne répond pas")
    chat = sorted(
        (
            m
            for m in tags.get("models", [])
            if "completion" in m.get("capabilities", [])
            and "embedding" not in m.get("capabilities", [])
            and m.get("details", {}).get("family") not in NOT_TESTABLE_FAMILIES
        ),
        key=lambda m: m["size"],
    )
    if not chat:
        pytest.skip("aucun modèle de chat installé")
    first = chat[0]
    second = next((m for m in chat[1:] if m["size"] >= MIN_SIZE_RATIO * first["size"]), None)
    if second is None:
        pytest.skip("pas deux modèles de chat de tailles différentes installés")
    return first, second


async def _answer(client, tag: str) -> dict:
    body = {"model": tag, "message": "Réponds par un seul mot : bonjour.", "temperature": 0}
    response = await client.post("/api/chat/runs", json=body)
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    async with asyncio.timeout(240):
        while (snapshot := (await client.get(f"/api/runs/{run_id}")).json())["status"] == "running":
            await asyncio.sleep(0.3)
    assert snapshot["status"] == "ok", snapshot
    return snapshot


async def test_two_local_models_of_different_sizes_give_different_measured_co2(
    real_settings, real_meter
):
    small, large = _smallest_chat_pair(real_settings.ollama.host)
    app = create_app(real_settings, meter=real_meter)
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{TEST_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            runs = [await _answer(client, m["name"]) for m in (small, large)]

    for run in runs:
        metrics = run["metrics"]
        co2 = metrics["co2"]
        assert co2["method"] == "codecarbon" and co2["allocation"] == "direct"
        assert co2["mg"] is not None and co2["mg"] > 0 and co2["reason"] is None
        assert metrics["energy_wh"] is not None and metrics["energy_wh"] > 0
        tokens = metrics["output_tokens"]
        assert tokens and co2["mg"] != pytest.approx(V1_MG_PER_TOKEN * tokens, rel=1e-3)
        assert co2["mg"] / tokens != pytest.approx(V1_MG_PER_TOKEN, rel=1e-3)
    assert runs[0]["metrics"]["co2"]["mg"] != runs[1]["metrics"]["co2"]["mg"]
