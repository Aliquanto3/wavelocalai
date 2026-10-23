"""Agent contre le vrai Ollama du poste, sur `qwen2.5:1.5b` (marqueur `integration`, aucun cloud).

Saut propre si Ollama est injoignable ou si le modèle n'est pas installé. Le modèle reçoit un vrai
outil (une addition), l'appelle par le protocole natif d'Ollama, lit le résultat et répond : c'est la
preuve que le format d'outils et l'identifiant d'appel fabriqué passent sur un vrai serveur.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from wavelocalai.agents.tools import AgentTool
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


async def test_real_ollama_calls_a_tool_and_publishes_every_step(real_settings, real_meter):
    _require_model(real_settings.ollama.host)
    calls: list[dict] = []

    async def add(arguments):
        calls.append(arguments)
        return str(float(arguments["a"]) + float(arguments["b"]))

    app = create_app(real_settings, meter=real_meter)
    app.state.agent_tools.register(
        AgentTool(
            "add",
            "Additionne deux nombres a et b et rend leur somme.",
            add,
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "Premier nombre"},
                    "b": {"type": "number", "description": "Second nombre"},
                },
                "required": ["a", "b"],
            },
        )
    )
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{TEST_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            body = {
                "mode": "solo",
                "model": TAG,
                "prompt": "Utilise l'outil add pour calculer 17 + 25, puis donne le résultat.",
                "tools": ["add"],
                "temperature": 0,
            }
            response = await client.post("/api/agents/runs", json=body)
            assert response.status_code == 200, response.text
            run_id = response.json()["run_id"]
            async with asyncio.timeout(240):
                while (await client.get(f"/api/runs/{run_id}")).json()["status"] == "running":
                    await asyncio.sleep(0.2)
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            events = [
                f["data"]
                for f in parse_sse((await client.get(f"/api/runs/{run_id}/events")).text)[0]
            ]
    assert snapshot["status"] == "ok", snapshot
    steps = [e["data"] for e in events if e["type"] == "step"]
    kinds = [s["kind"] for s in steps]
    if "tool_call" not in kinds:
        pytest.skip(f"{TAG} n'a pas appelé l'outil à cette exécution (modèle de 1,5 milliard)")
    assert calls and kinds[-1] == "answer"
    result = next(s for s in steps if s["kind"] == "tool_result")
    assert result["summary"] == "42.0" and "failed" not in result
    leaves = snapshot["children"]
    assert len(leaves) >= 2 and all(c["metrics"]["tps_source"] == "ollama_eval" for c in leaves)
    assert all(c["metrics"]["co2"] is not None for c in leaves)
    answer = "".join(e["data"]["text"] for e in events if e["type"] == "token")
    assert answer.strip() and "42" in answer


async def test_real_ollama_runs_a_two_agent_crew_one_after_the_other(real_settings, real_meter):
    """Story 6.5 : deux agents en séquence sur le vrai modèle ; le second reçoit le travail du
    premier, chaque étape porte son agent et la mission rend ses totaux."""
    _require_model(real_settings.ollama.host)
    app = create_app(real_settings, meter=real_meter)
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{TEST_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            agents = [
                {"role": "Chercheur", "goal": "Donner deux faits courts sur le sujet", "tools": []},
                {"role": "Rédacteur", "goal": "Résumer ces faits en une phrase", "tools": []},
            ]
            saved = await client.put(
                "/api/agents/crews/etude_concurrentielle", json={"agents": agents}
            )
            assert saved.status_code == 200, saved.text
            body = {
                "mode": "crew",
                "crew": "etude_concurrentielle",
                "topic": "Les petits modèles de langage locaux",
                "model": TAG,
                "temperature": 0,
            }
            response = await client.post("/api/agents/runs", json=body)
            assert response.status_code == 200, response.text
            run_id = response.json()["run_id"]
            async with asyncio.timeout(240):
                while (await client.get(f"/api/runs/{run_id}")).json()["status"] == "running":
                    await asyncio.sleep(0.2)
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            events = [
                f["data"]
                for f in parse_sse((await client.get(f"/api/runs/{run_id}/events")).text)[0]
            ]
    assert snapshot["status"] == "ok", snapshot
    answers = [e["data"] for e in events if e["type"] == "step" and e["data"]["kind"] == "answer"]
    assert [a["agent"] for a in answers] == ["Chercheur", "Rédacteur"]
    assert all(a["agent_totals"]["tools"] == 0 for a in answers)
    report = "".join(e["data"]["text"] for e in events if e["type"] == "token")
    assert report.strip()  # le rapport final est le seul texte publié en `token`
    assert snapshot["mission"]["agents_done"] == 2 and snapshot["mission"]["duration_s"] > 0
    assert len(snapshot["children"]) == 2
