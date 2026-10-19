"""Les outils de la v1 contre le vrai Ollama du poste, sur `qwen2.5:1.5b` (marqueur `integration`).

Le modèle reçoit la vraie calculatrice et le vrai rapport Markdown du registre de production, les
appelle par le protocole natif d'Ollama, et le fichier produit se télécharge par son `artifact_url`.
Saut propre si Ollama est injoignable, si le modèle manque ou s'il n'appelle pas l'outil (modèle de
1,5 milliard de paramètres). Aucun cloud, aucun téléchargement, aucun envoi d'email.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT
from ..web.conftest import parse_sse
from .test_agent_ollama import TAG, _require_model, real_settings  # noqa: F401 - fixture

pytestmark = pytest.mark.integration


async def _task(client, prompt, tools):
    body = {"mode": "solo", "model": TAG, "prompt": prompt, "tools": tools, "temperature": 0}
    response = await client.post("/api/agents/runs", json=body)
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    async with asyncio.timeout(240):
        while (await client.get(f"/api/runs/{run_id}")).json()["status"] == "running":
            await asyncio.sleep(0.2)
    status = (await client.get(f"/api/runs/{run_id}")).json()["status"]
    events = [
        f["data"] for f in parse_sse((await client.get(f"/api/runs/{run_id}/events")).text)[0]
    ]
    return status, [e["data"] for e in events if e["type"] == "step"]


async def test_real_ollama_uses_the_calculator_and_the_markdown_report(real_settings, real_meter):
    _require_model(real_settings.ollama.host)
    app = create_app(real_settings, meter=real_meter)
    async with app.router.lifespan_context(app):
        await app.state.registry.refresh()
        transport = httpx.ASGITransport(app=app)
        base = f"http://127.0.0.1:{TEST_PORT}"
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            listed = (await client.get("/api/agents/tools")).json()["tools"]
            assert any(t["id"] == "calculator" and t["available"] for t in listed)

            status, steps = await _task(
                client, "Utilise l'outil calculator pour calculer 17 * 23.", ["calculator"]
            )
            assert status == "ok"
            results = [s for s in steps if s["kind"] == "tool_result"]
            if not results:
                pytest.skip(f"{TAG} n'a pas appelé la calculatrice à cette exécution")
            assert results[0]["summary"] == "391" and "failed" not in results[0]

            status, steps = await _task(
                client,
                "Utilise l'outil generate_markdown_report avec le titre « Essai », les sections "
                '{"Résumé": "Tout va bien"} et le nom de fichier « essai ».',
                ["generate_markdown_report"],
            )
            assert status == "ok"
            produced = [s for s in steps if s["kind"] == "tool_result" and "artifact_url" in s]
            if not produced:
                pytest.skip(f"{TAG} n'a pas produit le rapport à cette exécution")
            download = await client.get(produced[0]["artifact_url"])
    assert download.status_code == 200 and download.text.startswith("# Essai")
