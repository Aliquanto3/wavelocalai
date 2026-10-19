"""Les outils de la v1 dans l'app (story 6.2) : liste, fichiers produits, évasions, plafond d'appels.

L'app est la vraie (registre de production des outils, boucle, flux SSE) ; le modèle est le `fake`
scriptable. Aucun réseau, aucun envoi d'email.
"""

from __future__ import annotations

import contextlib
import json

import httpx

from wavelocalai.agents.tools import AgentTool
from wavelocalai.models.fake import FAKE_REF
from wavelocalai.web.app import create_app

from ..conftest import make_settings
from .test_agent_api import BASE, _post, _run, agent_app, call, steps, turns

CSV = "region,quantite\nNord,10\nSud,5\nNord,7\n"


@contextlib.asynccontextmanager
async def env_app(tmp_path, environ=None, **settings):
    app = create_app(
        make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1", **(environ or {})}, **settings)
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


def work_dir(app):
    return app.state.agent_workspace.root


# --- GET /api/agents/tools -----------------------------------------------------------------------


async def test_the_tools_are_listed_with_label_availability_and_sensitivity(tmp_path):
    async with agent_app(tmp_path) as (app, client):
        response = await client.get("/api/agents/tools")
    assert response.status_code == 200
    tools = {t["id"]: t for t in response.json()["tools"]}
    assert list(tools) == [
        "get_current_time", "calculator", "search_wavestone_internal", "send_email",
        "analyze_csv", "generate_document", "generate_chart", "generate_markdown_report",
        "system_monitor",
    ]  # fmt: skip
    assert all(
        set(t) == {"id", "label", "description", "available", "reason", "sensitive"}
        for t in tools.values()
    )
    assert tools["calculator"]["label"] == "Calculatrice" and tools["calculator"]["available"]
    email = tools["send_email"]
    assert email["label"] == "Envoi d'email" and email["sensitive"] is True
    assert email["available"] is False
    assert email["reason"].startswith("Configuration SMTP absente : renseignez SMTP_USER")
    assert "dans le fichier .env" in email["reason"]
    assert [i for i, t in tools.items() if t["sensitive"]] == ["send_email"]


async def test_the_email_is_listed_available_once_smtp_is_configured(tmp_path):
    env = {"SMTP_USER": "moi@example.org", "SMTP_PASSWORD": "pw-smtp-0123456789"}
    async with env_app(tmp_path, env) as (_, client):
        tools = {t["id"]: t for t in (await client.get("/api/agents/tools")).json()["tools"]}
    assert tools["send_email"]["available"] is True and tools["send_email"]["reason"] is None
    assert "pw-smtp-0123456789" not in json.dumps(tools)


async def test_an_unavailable_tool_is_refused_before_any_run(tmp_path):
    async with agent_app(tmp_path) as (_, client):
        response = await _post(client, tools=("send_email",))
    assert response.status_code == 422 and response.json()["code"] == "invalid_request"
    assert "Configuration SMTP absente" in response.json()["detail"]["technical"]


async def test_a_sensitive_tool_is_still_never_run_without_approval(tmp_path):
    env = {"SMTP_USER": "moi@example.org", "SMTP_PASSWORD": "pw-smtp-0123456789"}
    async with env_app(tmp_path, env) as (app, client):
        args = {"to": "a@example.org", "subject": "S", "body": "B"}
        turns(app, [call("c1", "send_email", **args)], ["Je n'ai pas pu l'envoyer."])
        _, snapshot, events = await _run(client, tools=("send_email",))
    assert snapshot["status"] == "ok"
    result = next(s for s in steps(events) if s["kind"] == "tool_result")
    assert result["failed"] is True and "sensible" in result["summary"]


# --- une tâche avec les outils de la v1 ----------------------------------------------------------


async def test_the_calculator_runs_in_an_agent_task(tmp_path):
    async with agent_app(tmp_path) as (app, client):
        model = turns(app, [call("c1", "calculator", expression="12 * (3 + 4)")], ["Cela fait 84."])
        _, snapshot, events = await _run(client, tools=("calculator",))
    assert snapshot["status"] == "ok"
    result = next(s for s in steps(events) if s["kind"] == "tool_result")
    assert result["summary"] == "84" and "failed" not in result
    assert model.requests[1].messages[-1].content == "84"


async def test_a_report_is_produced_then_downloaded_through_its_artifact_url(tmp_path):
    async with agent_app(tmp_path) as (app, client):
        report = call(
            "c1", "generate_markdown_report",
            title="Synthèse", sections='{"Résumé": "Tout va bien"}', filename="synthese",
        )  # fmt: skip
        turns(app, [report], ["Le rapport est prêt."])
        _, snapshot, events = await _run(client, tools=("generate_markdown_report",))
        assert snapshot["status"] == "ok"
        result = next(s for s in steps(events) if s["kind"] == "tool_result")
        assert result["artifact_url"] == "/api/outputs/synthese.md" and "failed" not in result
        assert result["summary"] == "Rapport Markdown créé : synthese.md"
        assert (work_dir(app) / "synthese.md").is_file()

        download = await client.get(result["artifact_url"])
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith("attachment;")
    assert 'filename="synthese.md"' in download.headers["content-disposition"]
    assert download.headers["content-type"].startswith("text/markdown")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert "## Résumé\n\nTout va bien" in download.text


async def test_a_csv_of_the_work_folder_is_analysed_and_a_chart_follows(tmp_path):
    async with agent_app(tmp_path) as (app, client):
        work_dir(app).mkdir(parents=True)
        (work_dir(app) / "ventes.csv").write_text(CSV, encoding="utf-8")
        chart = call(
            "c2", "generate_chart",
            data_json='{"labels": ["Nord", "Sud"], "values": [17, 5]}',
            chart_type="bar", title="Ventes", filename="ventes",
        )  # fmt: skip
        turns(
            app,
            [call("c1", "analyze_csv", filepath="ventes.csv", query="somme de quantite")],
            [chart],
            ["Voici le graphique."],
        )
        _, snapshot, events = await _run(client, tools=("analyze_csv", "generate_chart"))
        results = [s for s in steps(events) if s["kind"] == "tool_result"]
        assert snapshot["status"] == "ok" and "22.00" in results[0]["summary"]
        assert results[1]["artifact_url"] == "/api/outputs/ventes.png"
        png = await client.get("/api/outputs/ventes.png")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"


# --- aucun chemin libre --------------------------------------------------------------------------


async def test_an_agent_cannot_read_outside_the_work_folder(tmp_path):
    secret = tmp_path / "secret.csv"
    secret.write_text("cle\nvaleur-secrete\n", encoding="utf-8")
    async with agent_app(tmp_path) as (app, client):
        attempts = ["../../../secret.csv", str(secret), "C:\\Windows\\win.ini", "..\\secret.csv"]
        scripts = [
            [call(f"c{i}", "analyze_csv", filepath=p, query="aperçu")]
            for i, p in enumerate(attempts)
        ]
        model = turns(app, *scripts, ["Je n'y ai pas accès."])
        _, snapshot, events = await _run(client, tools=("analyze_csv",))
    assert snapshot["status"] == "ok"
    results = [s for s in steps(events) if s["kind"] == "tool_result"]
    assert len(results) == 4 and all(r["failed"] is True for r in results)
    assert all("refusé" in r["summary"] or "non trouvé" in r["summary"] for r in results)
    assert "valeur-secrete" not in json.dumps(events) + str(model.requests[-1].messages)


async def test_an_agent_cannot_write_outside_the_work_folder(tmp_path):
    async with agent_app(tmp_path) as (app, client):
        turns(
            app,
            [call("c1", "generate_document", title="T", content="x", filename="../../evasion")],
            ["Refusé."],
        )
        _, _, events = await _run(client, tools=("generate_document",))
    result = next(s for s in steps(events) if s["kind"] == "tool_result")
    assert result["failed"] is True and "refusé" in result["summary"]
    assert "artifact_url" not in result and not list(tmp_path.rglob("evasion*"))


async def test_the_outputs_route_serves_only_flat_produced_files(tmp_path):
    secret = tmp_path / "secret.md"
    secret.write_text("secret", encoding="utf-8")
    async with agent_app(tmp_path) as (app, client):
        assert (await client.get("/api/outputs/inconnu.md")).status_code == 404
        work_dir(app).mkdir(parents=True)
        (work_dir(app) / "ventes.csv").write_text(CSV, encoding="utf-8")
        (work_dir(app) / "note.txt").write_text("x", encoding="utf-8")
        (work_dir(app) / "rapport.md").write_text("# R", encoding="utf-8")
        assert (await client.get("/api/outputs/rapport.md")).status_code == 200
        # Un fichier du dossier de travail qui n'est pas un type produit n'est pas servi.
        for name in ("ventes.csv", "note.txt"):
            assert (await client.get(f"/api/outputs/{name}")).status_code == 404
        for url in (
            "/api/outputs/..",
            "/api/outputs/%2e%2e",
            "/api/outputs/..%2Fsecret.md",
            "/api/outputs/%2E%2E%5Csecret.md",
            "/api/outputs/C%3A%5Csecret.md",
            "/api/outputs/%2Fetc%2Fpasswd",
            "/api/outputs/.rapport.md",
        ):
            response = await client.get(url)
            assert response.status_code in (404, 422), url
            assert "secret" not in response.text.replace("secret.md", "")
        invalid = await client.get("/api/outputs/%2e%2e")
        assert invalid.status_code in (404, 422)
        bad = await client.get("/api/outputs/a:b.md")
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_request"


# --- secrets -------------------------------------------------------------------------------------


async def test_the_smtp_password_never_reaches_the_steps(tmp_path):
    password = "pw-smtp-0123456789abcdef"
    env = {"SMTP_USER": "moi@example.org", "SMTP_PASSWORD": password}
    async with env_app(tmp_path, env) as (app, client):

        async def leak(arguments):
            return f"le mot de passe est {password}"

        app.state.agent_tools.register(AgentTool("leak", "Fuit.", leak))
        model = turns(app, [call("c1", "leak", note=password)], ["Fini."])
        _, _, events = await _run(client, tools=("leak",))
    asked = next(s for s in steps(events) if s["kind"] == "tool_call")
    result = next(s for s in steps(events) if s["kind"] == "tool_result")
    assert password not in json.dumps(events) and "***" in result["summary"]
    assert "***" in asked["arguments"]["note"]
    assert password not in model.requests[1].messages[-1].content


# --- plafond d'appels d'outils par tour (report de la revue de la 6.1) ---------------------------


async def test_calls_beyond_the_per_turn_cap_are_refused_not_run(tmp_path):
    ran: list[str] = []

    async def count(arguments):
        ran.append(arguments["n"])
        return f"fait {arguments['n']}"

    async with agent_app(tmp_path, agents={"max_tool_calls_per_turn": 2}) as (app, client):
        app.state.agent_tools.register(AgentTool("count", "Compte.", count))
        model = turns(
            app,
            [call(f"c{i}", "count", n=str(i)) for i in range(1, 5)],
            ["Deux seulement ont été faits."],
        )
        _, snapshot, events = await _run(client, tools=("count",))
    assert snapshot["status"] == "ok" and ran == ["1", "2"]
    results = [s for s in steps(events) if s["kind"] == "tool_result"]
    assert [r.get("failed") for r in results] == [None, None, True, True]
    assert "au plus 2 appels d'outils par tour" in results[2]["summary"]
    assert [r["duration_s"] for r in results[2:]] == [0.0, 0.0]
    # Chaque appel du fournisseur reçoit un résultat (sans quoi il refuserait le tour suivant).
    answered = [m.tool_call_id for m in model.requests[1].messages if m.role == "tool"]
    assert answered == ["c1", "c2", "c3", "c4"]
    calls = [s for s in steps(events) if s["kind"] == "tool_call"]
    assert [c["call_id"] for c in calls] == ["c1", "c2", "c3", "c4"]


async def test_the_cap_applies_to_each_turn_separately(tmp_path):
    ran: list[str] = []

    async def count(arguments):
        ran.append(arguments["n"])
        return "ok"

    async with agent_app(tmp_path, agents={"max_tool_calls_per_turn": 1}) as (app, client):
        app.state.agent_tools.register(AgentTool("count", "Compte.", count))
        turns(
            app,
            [call("a1", "count", n="1"), call("a2", "count", n="2")],
            [call("b1", "count", n="3")],
            ["Fini."],
        )
        _, _, events = await _run(client, tools=("count",))
    assert ran == ["1", "3"]
    assert [s.get("failed") for s in steps(events) if s["kind"] == "tool_result"] == [
        None, True, None,
    ]  # fmt: skip


def test_the_default_cap_is_eight_calls_per_turn(tmp_path):
    assert make_settings(tmp_path).agents.max_tool_calls_per_turn == 8
