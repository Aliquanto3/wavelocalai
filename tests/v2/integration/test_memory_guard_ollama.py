"""Garde-fou mémoire contre le vrai Ollama du poste, sur `qwen2.5:1.5b` (marqueur `integration`).

Saut propre si Ollama est injoignable ou si le modèle n'est pas installé. La mémoire du poste est
simulée (le test ne sature rien) ; `/api/ps`, `/api/tags` et le déchargement sont réels. Rien n'est
téléchargé. **Le test ne décharge que `qwen2.5:1.5b` qu'il a chargé lui-même** : si un autre
processus l'avait déjà chargé, la partie « déchargement » est sautée ; si d'autres modèles sont
chargés, elle passe par `unload_model` sur ce seul modèle, jamais par la route (qui libère tout ce
qui est inactif).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from wavelocalai.config import load_settings
from wavelocalai.hardware.memory import MemoryReading
from wavelocalai.models.ollama_ps import loaded_models, unload_model
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT
from ..web.conftest import parse_sse

pytestmark = pytest.mark.integration

TAG = "qwen2.5:1.5b"
RUN_TIMEOUT_S = 180


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


async def _ended_events(client, message: str):
    response = await client.post(
        "/api/chat/runs", json={"model": TAG, "message": message, "temperature": 0}
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    async with asyncio.timeout(RUN_TIMEOUT_S):
        while (await client.get(f"/api/runs/{run_id}")).json()["status"] == "running":
            await asyncio.sleep(0.2)
    return [f["data"] for f in parse_sse((await client.get(f"/api/runs/{run_id}/events")).text)[0]]


async def _tags_in_memory(host: str) -> set[str]:
    loaded = await loaded_models(host, timeout_s=3.0)
    assert loaded is not None, "`/api/ps` ne répond pas"
    return {model.tag for model in loaded}


async def _wait_unloaded(host: str) -> None:
    async with asyncio.timeout(30):
        while TAG in await _tags_in_memory(host):
            await asyncio.sleep(0.5)


async def test_real_ps_a_loaded_model_is_never_blocked_and_an_unloaded_one_is(
    real_settings, real_meter
):
    host = real_settings.ollama.host
    _require_model(host)
    mine_was_loaded = TAG in await _tags_in_memory(host)
    free = {"gb": 64.0}
    app = create_app(
        real_settings,
        meter=real_meter,
        memory_reader=lambda: MemoryReading(total_gb=64.0, available_gb=free["gb"]),
    )
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{TEST_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            # 1. Mémoire large : la réponse passe, et le modèle est chargé (`/api/ps` réel).
            events = await _ended_events(client, "Réponds par un seul mot : bonjour.")
            assert events[-1]["data"]["status"] == "ok", events[-1]
            assert TAG in await _tags_in_memory(host)

            # 2. Mémoire quasi nulle, modèle chargé : son besoin est nul, aucun blocage à tort.
            free["gb"] = 0.1
            events = await _ended_events(client, "Réponds par un seul mot : merci.")
            assert events[-1]["data"]["status"] == "ok", events[-1]

            if mine_was_loaded:
                pytest.skip(
                    "`qwen2.5:1.5b` était déjà chargé par un autre processus : on n'y touche pas"
                )

            # 3. Déchargé (par ce test seulement), la même mémoire le refuse, besoin chiffré.
            only_mine = await _tags_in_memory(host) == {TAG}
            if only_mine:  # rien d'autre n'est chargé : la vraie route peut libérer
                response = await client.post("/api/models/unload")
                assert response.status_code == 200, response.text
                assert response.json()["unloaded"] == [TAG]
            else:  # d'autres modèles servent peut-être : on ne décharge que le nôtre
                assert await unload_model(host, TAG)
            await _wait_unloaded(host)
            events = await _ended_events(client, "Réponds par un seul mot : salut.")
            ended = events[-1]["data"]
            assert ended["status"] == "error", ended
            error = ended["error"]
            assert error["code"] == "ram_guard"
            assert error["detail"]["free_gb"] == 0.1
            assert error["detail"]["needed_gb"] > 0.1
            assert error["message"].startswith("Mémoire insuffisante : ")
            assert error["detail"]["suggested_model"] != TAG
            assert not [e for e in events if e["type"] == "token"]  # le modèle n'a pas été appelé
            assert TAG not in await _tags_in_memory(host)  # et il n'a pas été rechargé
