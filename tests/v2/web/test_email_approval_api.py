"""Aucun email ne part sans validation explicite (story 6.3, AD-9, D2).

L'app est la vraie (hub, boucle, flux SSE, route d'approbation, envoi SMTP) ; le modèle est le `fake`
scriptable ; le serveur SMTP est un faux **local** en processus (`tests/v2/fake_smtp.py`, port
éphémère sur `127.0.0.1`) : aucun vrai serveur n'est joint, et les `Settings` viennent de
`make_settings` (jamais du `.env` du poste).
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import httpx
import pytest

from wavelocalai.web.app import create_app

from ..conftest import closed_port, make_settings
from ..fake_smtp import FakeSmtp
from .test_agent_api import BASE, call, steps, turns

ARGS = {
    "to": "client@example.org",
    "subject": "Synthèse du mardi",
    "body": "Bonjour,\nVoici la synthèse.",
}
FINAL = ("ok", "error", "cancelled", "interrupted")
SENT = "Email envoyé à client@example.org"


@contextlib.asynccontextmanager
async def mail_app(tmp_path, server: FakeSmtp | None = None, **settings):
    """(app, client, smtp) : le SMTP de l'app vise le faux serveur local."""
    async with contextlib.AsyncExitStack() as stack:
        fake = server or await stack.enter_async_context(FakeSmtp())
        merged = {"smtp": fake.settings(), **settings}
        app = create_app(make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}, **merged))
        await stack.enter_async_context(app.router.lifespan_context(app))
        transport = httpx.ASGITransport(app=app)
        client = await stack.enter_async_context(
            httpx.AsyncClient(transport=transport, base_url=BASE)
        )
        yield app, client, fake


async def _start(client, prompt="Écris à mon client."):
    body = {
        "mode": "solo",
        "model": "fake:1b",
        "prompt": prompt,
        "tools": ["send_email"],
        "allow_cloud": False,
    }
    response = await client.post("/api/agents/runs", json=body)
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


async def _events(app, run_id):
    """Événements d'un run, actif ou fini, par le hub (le flux SSE d'un run actif ne se referme pas)."""
    return [
        {"type": e["type"], "data": e["data"]} for e in await app.state.hub.events_after(run_id)
    ]


async def _wait_for(app, run_id, event_type, timeout=5.0) -> dict:
    async with asyncio.timeout(timeout):
        while True:
            for event in await _events(app, run_id):
                if event["type"] == event_type:
                    return event
            await asyncio.sleep(0.02)


async def _finished(client, run_id, timeout=5.0) -> dict:
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] in FINAL:
                return snapshot
            await asyncio.sleep(0.02)


async def _answer(client, run_id, approval_id, decision, **kwargs):
    return await client.post(
        f"/api/runs/{run_id}/approvals/{approval_id}", json={"decision": decision}, **kwargs
    )


def _result(events) -> dict:
    return next(s for s in steps(events) if s["kind"] == "tool_result")


def _types(events):
    return [e["type"] for e in events]


async def _propose(app, client, args=ARGS, final="C'est fait."):
    """Lance un agent qui appelle `send_email` puis répond ; rend (run_id, approval_required)."""
    model = turns(app, [call("c1", "send_email", **args)], [final])
    run_id = await _start(client)
    return run_id, (await _wait_for(app, run_id, "approval_required"))["data"], model


# --- approuver ----------------------------------------------------------------------------------


async def test_the_email_is_sent_only_after_an_explicit_approval(tmp_path):
    async with mail_app(tmp_path) as (app, client, smtp):
        run_id, required, model = await _propose(app, client, final="L'email est parti.")
        # La demande montre tout ce qui partira ; rien n'est envoyé ni même tenté.
        assert required["kind"] == "email" and required["call_id"] == "c1"
        assert (required["destinataire"], required["objet"], required["corps"]) == (
            ARGS["to"], ARGS["subject"], ARGS["body"],
        )  # fmt: skip
        assert required["approval_id"] and required["expiry_s"] == 600.0
        snapshot = (await client.get(f"/api/runs/{run_id}")).json()
        assert snapshot["status"] == "awaiting_approval" and snapshot["kind"] == "agent"
        await asyncio.sleep(0.2)  # laisse à la boucle le temps de (mal) agir
        assert smtp.connections == 0 and smtp.messages == []
        assert "approval_resolved" not in _types(await _events(app, run_id))

        answered = await _answer(client, run_id, required["approval_id"], "approved")
        assert answered.status_code == 200
        assert answered.json() == {
            "run_id": run_id, "approval_id": required["approval_id"], "decision": "approved",
        }  # fmt: skip
        snapshot = await _finished(client, run_id)
        events = await _events(app, run_id)

    assert snapshot["status"] == "ok"
    (message,) = smtp.messages
    assert message.recipients == ["client@example.org"] and message.sender == "moi@example.org"
    assert message.subject == ARGS["subject"] and message.text == ARGS["body"]
    # Ordre : l'appel, la demande, la décision publiée, PUIS le résultat de l'envoi.
    kinds = [(e["type"], e["data"].get("kind")) for e in events if e["type"] != "metrics"]
    wanted = [("step", "tool_call"), ("approval_required", "email"), ("approval_resolved", None),
              ("step", "tool_result")]  # fmt: skip
    assert [k for k in kinds if k in wanted] == wanted
    resolved = next(e for e in events if e["type"] == "approval_resolved")["data"]
    assert resolved == {"approval_id": required["approval_id"], "decision": "approved"}
    result = _result(events)
    assert result["summary"].startswith(SENT) and "failed" not in result
    assert model.requests[1].messages[-1].content.startswith(SENT)


async def test_the_approval_wait_is_not_cut_by_the_tool_timeout(tmp_path):
    async with mail_app(tmp_path, agents={"tool_timeout_s": 0.5}) as (app, client, smtp):
        run_id, required, _ = await _propose(app, client)
        await asyncio.sleep(0.8)  # plus long que le délai d'un outil
        assert (await client.get(f"/api/runs/{run_id}")).json()["status"] == "awaiting_approval"
        await _answer(client, run_id, required["approval_id"], "approved")
        assert (await _finished(client, run_id))["status"] == "ok"
    assert len(smtp.messages) == 1


async def test_a_slow_smtp_send_is_not_cut_by_the_tool_timeout(tmp_path):
    # Revue : l'envoi tourne dans un fil qu'on ne peut interrompre ; couper son attente au délai
    # d'un outil disait « pas abouti » d'un email parti quand même.
    async with (
        FakeSmtp(greeting_delay_s=0.6) as slow,
        mail_app(tmp_path, slow, agents={"tool_timeout_s": 0.2}) as (app, client, smtp),
    ):
        run_id, required, _ = await _propose(app, client)
        await _answer(client, run_id, required["approval_id"], "approved")
        assert (await _finished(client, run_id))["status"] == "ok"
        result = _result(await _events(app, run_id))
    assert result["summary"].startswith(SENT) and "failed" not in result
    assert len(smtp.messages) == 1


# --- refuser, expirer, annuler -------------------------------------------------------------------


async def test_a_refusal_sends_nothing_and_the_agent_can_announce_it(tmp_path):
    async with mail_app(tmp_path) as (app, client, smtp):
        run_id, required, model = await _propose(app, client, final="Vous avez refusé l'envoi.")
        assert (
            await _answer(client, run_id, required["approval_id"], "rejected")
        ).status_code == 200
        snapshot = await _finished(client, run_id)
        events = await _events(app, run_id)
    assert snapshot["status"] == "ok"
    assert smtp.connections == 0 and smtp.messages == []
    resolved = next(e for e in events if e["type"] == "approval_resolved")["data"]
    assert resolved["decision"] == "rejected"
    result = _result(events)
    assert result["failed"] is True and "refusé" in result["summary"]
    assert "refusé" in model.requests[1].messages[-1].content  # l'agent le lit et peut l'annoncer
    assert steps(events)[-1]["kind"] == "answer"


async def test_no_answer_in_time_expires_and_nothing_is_sent(tmp_path):
    async with mail_app(tmp_path, delays={"approval_expiry_s": 0.3}) as (app, client, smtp):
        run_id, required, model = await _propose(app, client)
        assert required["expiry_s"] == 0.3
        snapshot = await _finished(client, run_id)
        events = await _events(app, run_id)
        late = await _answer(client, run_id, required["approval_id"], "approved")
    assert snapshot["status"] == "ok"
    resolved = next(e for e in events if e["type"] == "approval_resolved")["data"]
    assert resolved == {"approval_id": required["approval_id"], "decision": "expired"}
    assert smtp.connections == 0 and smtp.messages == []
    assert _result(events)["failed"] is True and "pas répondu" in _result(events)["summary"]
    assert "pas répondu" in model.requests[1].messages[-1].content
    assert late.status_code == 409 and late.json()["code"] == "approval_not_pending"  # trop tard
    assert late.json()["detail"]["approval_id"] == required["approval_id"]


async def test_cancelling_the_run_is_a_refusal_and_nothing_is_sent(tmp_path):
    async with mail_app(tmp_path) as (app, client, smtp):
        run_id, required, _ = await _propose(app, client)
        cancelled = await client.post(f"/api/runs/{run_id}/cancel")
        assert cancelled.json()["cancelled"] is True and cancelled.json()["status"] == "cancelled"
        events = await _events(app, run_id)
        late = await _answer(client, run_id, required["approval_id"], "approved")
        await asyncio.sleep(0.2)
    kinds = _types(events)
    assert kinds[-3:] == ["approval_required", "approval_resolved", "run_ended"]
    assert events[-2]["data"]["decision"] == "rejected"
    assert smtp.connections == 0 and smtp.messages == []
    assert late.status_code == 409 and late.json()["code"] == "approval_not_pending"


async def test_a_second_answer_is_refused_and_one_approval_sends_one_email(tmp_path):
    async with mail_app(tmp_path) as (app, client, smtp):
        run_id, required, _ = await _propose(app, client)
        approval_id = required["approval_id"]
        first, second = await asyncio.gather(
            _answer(client, run_id, approval_id, "approved"),
            _answer(client, run_id, approval_id, "approved"),
        )
        assert sorted([first.status_code, second.status_code]) == [200, 409]
        refused = await _answer(
            client, run_id, approval_id, "rejected"
        )  # ne retourne pas la décision
        assert refused.status_code == 409
        await _finished(client, run_id)
    assert len(smtp.messages) == 1


# --- la route d'approbation ----------------------------------------------------------------------


async def test_the_approval_route_refuses_unknown_runs_requests_and_decisions(tmp_path):
    async with mail_app(tmp_path) as (app, client, smtp):
        unknown = await _answer(client, "0" * 32, "x" * 32, "approved")
        assert unknown.status_code == 404 and unknown.json()["code"] == "run_not_found"
        run_id, required, _ = await _propose(app, client)
        other = await _answer(client, run_id, "autre", "approved")
        assert other.status_code == 409 and other.json()["code"] == "approval_not_pending"
        for body in ({"decision": "expired"}, {"decision": "oui"}, {}):
            bad = await client.post(
                f"/api/runs/{run_id}/approvals/{required['approval_id']}", json=body
            )
            assert bad.status_code == 422 and bad.json()["code"] == "invalid_request"
        # Aucune de ces réponses n'a décidé : la demande attend toujours.
        assert (await client.get(f"/api/runs/{run_id}")).json()["status"] == "awaiting_approval"
        await client.post(f"/api/runs/{run_id}/cancel")
    assert smtp.messages == []


async def test_a_foreign_origin_cannot_approve(tmp_path):
    async with mail_app(tmp_path) as (app, client, smtp):
        run_id, required, _ = await _propose(app, client)
        evil = await _answer(
            client, run_id, required["approval_id"], "approved",
            headers={"Origin": "http://evil.example"},
        )  # fmt: skip
        assert evil.status_code == 403 and evil.json()["code"] == "forbidden_origin"
        await asyncio.sleep(0.2)
        assert (await client.get(f"/api/runs/{run_id}")).json()["status"] == "awaiting_approval"
        assert smtp.connections == 0 and smtp.messages == []
        own = await _answer(
            client, run_id, required["approval_id"], "approved", headers={"Origin": BASE}
        )
        assert own.status_code == 200
        await _finished(client, run_id)
    assert len(smtp.messages) == 1


# --- brouillons invalides : aucune demande -------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        {**ARGS, "to": "pas-une-adresse"},
        {**ARGS, "to": "a@example.org, b@example.org"},  # un seul destinataire
        {**ARGS, "to": "a@example.org\r\nBcc: x@example.org"},  # injection d'en-tête
        {**ARGS, "subject": "Objet\r\nBcc: x@example.org"},
        {**ARGS, "subject": "x" * 201},
        {**ARGS, "body": ""},
    ],
)
async def test_an_invalid_draft_is_refused_without_asking_the_user(tmp_path, args):
    async with mail_app(tmp_path) as (app, client, smtp):
        model = turns(app, [call("c1", "send_email", **args)], ["Je corrige."])
        run_id = await _start(client)
        snapshot = await _finished(client, run_id)
        events = await _events(app, run_id)
    assert snapshot["status"] == "ok"
    assert "approval_required" not in _types(events)
    assert _result(events)["failed"] is True
    assert not model.requests[1].messages[-1].content.startswith(SENT)
    assert smtp.connections == 0 and smtp.messages == []


# --- le mot de passe SMTP ne se voit nulle part ----------------------------------------------------


async def test_the_smtp_password_is_never_shown_nor_sent_by_the_agent(tmp_path):
    password = "pw-smtp-0123456789"
    async with mail_app(tmp_path) as (app, client, smtp):
        # Un agent qui glisserait le mot de passe dans son message : refusé avant toute demande.
        leaky = {**ARGS, "body": f"Mon mot de passe est {password}"}
        model = turns(app, [call("c1", "send_email", **leaky)], ["Compris."])
        run_id = await _start(client)
        snapshot = await _finished(client, run_id)
        events = await _events(app, run_id)
        assert "approval_required" not in _types(events)
        assert "secrète" in _result(events)["summary"]
        assert smtp.connections == 0 and smtp.messages == []
        everything = json.dumps([events, snapshot, [m.content for m in model.requests[1].messages]])
        assert password not in everything

        # Un envoi normal : ni les événements, ni l'instantané, ni les réponses ne le portent.
        run_id, required, _ = await _propose(app, client)
        answer = await _answer(client, run_id, required["approval_id"], "approved")
        snapshot = await _finished(client, run_id)
        events = await _events(app, run_id)
        listed = (await client.get("/api/agents/tools")).text
    assert password not in json.dumps([events, snapshot]) + answer.text + listed
    assert smtp.auth_attempts and smtp.auth_attempts[-1] == (
        smtp.user,
        password,
    )  # il sert à l'envoi


async def test_a_wrong_smtp_password_is_a_failed_result_without_revealing_it(tmp_path):
    async with FakeSmtp() as smtp:
        wrong = smtp.settings(password="pw-faux-9876543210")
        async with mail_app(tmp_path, smtp, smtp=wrong) as (app, client, _):
            run_id, required, model = await _propose(app, client, final="L'envoi a échoué.")
            await _answer(client, run_id, required["approval_id"], "approved")
            snapshot = await _finished(client, run_id)
            events = await _events(app, run_id)
    assert snapshot["status"] == "ok" and smtp.messages == []
    result = _result(events)
    assert result["failed"] is True and "authentification SMTP" in result["summary"]
    assert "pw-faux-9876543210" not in json.dumps(events) + json.dumps(snapshot)
    assert "authentification" in model.requests[1].messages[-1].content


async def test_a_refused_recipient_and_an_unreachable_server_are_failed_results(tmp_path):
    refuse = FakeSmtp(refuse_recipients=("client@example.org",))
    async with refuse as smtp, mail_app(tmp_path, smtp) as (app, client, _):
        run_id, required, _ = await _propose(app, client)
        await _answer(client, run_id, required["approval_id"], "approved")
        await _finished(client, run_id)
        events = await _events(app, run_id)
    assert "refusé le destinataire" in _result(events)["summary"] and smtp.messages == []

    async with FakeSmtp() as smtp:
        down = smtp.settings(port=closed_port())  # rien n'écoute : injoignable
        async with mail_app(tmp_path / "down", smtp, smtp=down) as (app, client, _):
            run_id, required, _ = await _propose(app, client)
            await _answer(client, run_id, required["approval_id"], "approved")
            assert (await _finished(client, run_id))["status"] == "ok"
            events = await _events(app, run_id)
    assert "injoignable" in _result(events)["summary"] and smtp.connections == 0


async def test_a_crew_agent_asks_for_the_same_approval_as_a_single_agent(tmp_path):
    """Point d'intégration 6.3 / 6.5 : la boucle d'un agent d'équipe porte les actions sensibles."""
    crews = {
        "version": 1,
        "crews": {
            "courrier": {
                "label": "Courrier",
                "agents": [{"role": "Courrier", "goal": "Écrire", "tools": ["send_email"]}],
            }
        },
    }
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "agent_crews.json").write_text(json.dumps(crews), encoding="utf-8")
    async with mail_app(tmp_path) as (app, client, smtp):
        model = turns(app, [call("c1", "send_email", **ARGS)], ["Rapport : email parti."])
        body = {"mode": "crew", "crew": "courrier", "topic": "Sujet", "model": "fake:1b"}
        started = await client.post("/api/agents/runs", json={**body, "allow_cloud": False})
        assert started.status_code == 200, started.text
        run_id = started.json()["run_id"]
        required = (await _wait_for(app, run_id, "approval_required"))["data"]
        assert required["destinataire"] == ARGS["to"] and smtp.messages == []
        snapshot = (await client.get(f"/api/runs/{run_id}")).json()
        assert snapshot["status"] == "awaiting_approval"
        answered = await _answer(client, run_id, required["approval_id"], "approved")
        assert answered.status_code == 200
        snapshot = await _finished(client, run_id)
        events = await _events(app, run_id)

    assert snapshot["status"] == "ok" and len(smtp.messages) == 1
    assert any(
        e["type"] == "step"
        and e["data"].get("agent") == "Courrier"
        and e["data"]["kind"] == "tool_result"
        for e in events
    )
    assert model.requests
