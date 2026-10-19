"""La validation d'un email contre le vrai Ollama du poste, sur `qwen2.5:1.5b` (marqueur `integration`).

Le modèle est réel ; le serveur SMTP est le faux **local** de `tests/v2/fake_smtp.py` (`127.0.0.1`,
port éphémère) : aucun email réel, aucun cloud, aucun téléchargement, et jamais le `.env` du poste
(`env_file` absent, environnement vide). Saut propre si Ollama est injoignable, si le modèle manque
ou s'il n'appelle pas l'outil (modèle de 1,5 milliard de paramètres).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from wavelocalai.config import load_settings
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT
from ..fake_smtp import FakeSmtp
from .test_agent_ollama import TAG, _require_model

pytestmark = pytest.mark.integration


async def _wait(app, run_id, done, timeout):
    async with asyncio.timeout(timeout):
        while not (found := done(await app.state.hub.events_after(run_id))):
            await asyncio.sleep(0.2)
    return found


async def test_real_ollama_prepares_an_email_that_is_sent_only_once_approved(tmp_path, real_meter):
    async with FakeSmtp() as smtp:
        settings = load_settings(
            env_file=tmp_path / "absent.env",
            environ={},
            overrides={"data": {"dir": tmp_path / "data"}, "smtp": smtp.settings()},
        )
        _require_model(settings.ollama.host)
        app = create_app(settings, meter=real_meter)
        async with app.router.lifespan_context(app):
            await app.state.registry.refresh()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url=f"http://127.0.0.1:{TEST_PORT}"
            ) as client:
                prompt = (
                    "Utilise l'outil send_email pour écrire à client@example.org, avec l'objet "
                    "« Point du mardi » et le corps « Bonjour, la réunion est à 14 h. »."
                )
                body = {"mode": "solo", "model": TAG, "prompt": prompt, "tools": ["send_email"]}
                response = await client.post("/api/agents/runs", json=body)
                assert response.status_code == 200, response.text
                run_id = response.json()["run_id"]

                def ask(events):
                    ended = any(e["type"] == "run_ended" for e in events)
                    required = [e for e in events if e["type"] == "approval_required"]
                    return required or ended or None

                found = await _wait(app, run_id, ask, timeout=240)
                if found is True:
                    pytest.skip(f"{TAG} n'a pas appelé l'outil d'email à cette exécution")
                assert smtp.connections == 0  # la demande est posée : rien n'est parti
                required = found[0]["data"]
                assert (
                    required["kind"] == "email" and required["destinataire"] == "client@example.org"
                )
                snapshot = (await client.get(f"/api/runs/{run_id}")).json()
                assert snapshot["status"] == "awaiting_approval"

                answered = await client.post(
                    f"/api/runs/{run_id}/approvals/{required['approval_id']}",
                    json={"decision": "approved"},
                )
                assert answered.status_code == 200
                await _wait(
                    app, run_id, lambda ev: any(e["type"] == "run_ended" for e in ev) or None, 240
                )
        assert [m.recipients for m in smtp.messages] == [["client@example.org"]]
        assert smtp.messages[0].subject == required["objet"]
        assert smtp.messages[0].text == required["corps"]
