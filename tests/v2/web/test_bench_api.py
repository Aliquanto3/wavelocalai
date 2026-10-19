"""Banc d'essai (story 7.4) : scénarios, run `bench`, verdict de format, résultat rouvert, liste.

L'app est la vraie (hub, registre, service, flux SSE) ; seul Ollama est simulé. Rien ne touche le
réseau.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import httpx
import pytest

from wavelocalai.models.ollama_api import OllamaHttpSource
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..fake_ollama import FakeOllama, Plan, final, part
from .conftest import parse_sse

BASE = f"http://127.0.0.1:{TEST_PORT}"
TAG = "qwen2.5:1.5b"
GOOD = '{"sentiment": "Neutre", "categorie": "formation"}'


@contextlib.asynccontextmanager
async def bench_app(tmp_path, server: FakeOllama, **settings):
    config = make_settings(tmp_path, **settings)
    registry = ModelRegistry(
        config, source=OllamaHttpSource(config.ollama.host, transport=server.transport)
    )
    app = create_app(config, registry=registry, ollama_client=server.client())
    async with app.router.lifespan_context(app):
        await registry.refresh()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


def _plan(*texts: str) -> Plan:
    return Plan([*(part(t) for t in texts), final()])


async def _post(client, **body):
    body = {"scenario": "classification", "model": TAG, "input": "Bien !", **body}
    return await client.post("/api/bench/runs", json=body)


async def _ended(client, run_id, timeout=3.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


async def test_scenarios_carry_instruction_and_schema_or_null(tmp_path):
    async with bench_app(tmp_path, FakeOllama()) as (_, client):
        body = (await client.get("/api/scenarios")).json()
    by_id = {s["id"]: s for s in body["scenarios"]}
    assert list(by_id) == [
        "classification",
        "traduction",
        "extraction",
        "code",
        "raisonnement",
        "resume",
    ]
    first = by_id["classification"]
    assert set(first) == {"id", "name", "instruction", "input", "schema"}
    assert first["name"] == "Classification (JSON)" and "sentiment" in first["instruction"]
    assert first["schema"]["required"] == ["sentiment", "categorie"]
    assert by_id["code"]["schema"] is None and by_id["resume"]["schema"] is None  # D-17


async def test_models_carry_structured_output(tmp_path):
    server = FakeOllama(tags=[TAG, "nomic-embed-text:latest"])
    async with bench_app(tmp_path, server) as (_, client):
        models = {m["tag"]: m for m in (await client.get("/api/models")).json()["models"]}
    assert models[TAG]["structured_output"] is True
    assert models["nomic-embed-text:latest"]["structured_output"] is False


async def test_run_streams_and_snapshot_reports_respected_format(tmp_path):
    server = FakeOllama(plans=[_plan(GOOD[:20], GOOD[20:])])
    async with bench_app(tmp_path, server) as (_, client):
        started = await _post(client, input="Le café était froid")
        assert started.status_code == 200 and set(started.json()) == {"run_id"}
        run_id = started.json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = [
            f["data"] for f in parse_sse((await client.get(f"/api/runs/{run_id}/events")).text)[0]
        ]
    assert snapshot["status"] == "ok" and snapshot["kind"] == "bench"
    verdict = snapshot["format_verdict"]
    assert verdict["ok"] is True and verdict["message"] == "Format respecté"
    assert json.loads(verdict["formatted"]) == json.loads(GOOD) and verdict["forced"] is False
    assert snapshot["bench"] == {
        "scenario": "classification", "force_format": False, "concise": False,
        "input": "Le café était froid", "output": GOOD,
    }  # fmt: skip
    metrics = snapshot["metrics"]
    assert metrics["tps"] == 40.0 and metrics["co2"] is not None and metrics["total_s"] == 1.0
    types = [e["type"] for e in events]
    assert types[:2] == ["run_started", "bench_input"] and types[-1] == "run_ended"
    assert types.index("metrics") < types.index("run_ended")
    assert "Le café" not in json.dumps(events[0])  # AD-7 : pas de texte saisi dans run_started
    # le système porte la consigne du scénario, l'entrée est le message utilisateur ; pas de format
    request = server.chat_requests[0]
    assert [m["role"] for m in request["messages"]] == ["system", "user"]
    assert "sentiment" in request["messages"][0]["content"]
    assert "format" not in request or request["format"] is None


async def test_violation_is_named_in_plain_french(tmp_path):
    bad = '{"sentiment": "Super", "categorie": "x"}'
    async with bench_app(tmp_path, FakeOllama(plans=[_plan(bad)])) as (_, client):
        snapshot = await _ended(client, (await _post(client)).json()["run_id"])
    verdict = snapshot["format_verdict"]
    assert snapshot["status"] == "ok" and verdict["ok"] is False
    assert verdict["message"] == "« sentiment » : valeur hors de la liste permise (Positif, Neutre, Négatif)"
    assert json.loads(verdict["formatted"])["sentiment"] == "Super"  # JSON lisible, mis en forme


async def test_unreadable_output_has_no_formatted_json(tmp_path):
    async with bench_app(tmp_path, FakeOllama(plans=[_plan("Voici : {oups")])) as (_, client):
        snapshot = await _ended(client, (await _post(client)).json()["run_id"])
    verdict = snapshot["format_verdict"]
    assert verdict["ok"] is False and verdict["formatted"] is None
    assert verdict["message"].startswith("La sortie n'est pas du JSON valide")


async def test_force_format_passes_schema_and_concise_adds_instruction(tmp_path):
    server = FakeOllama(plans=[_plan(GOOD)])
    async with bench_app(tmp_path, server) as (_, client):
        run_id = (await _post(client, force_format=True, concise=True)).json()["run_id"]
        snapshot = await _ended(client, run_id)
    request = server.chat_requests[0]
    assert request["format"]["required"] == ["sentiment", "categorie"]
    assert "concise" in request["messages"][0]["content"]
    assert snapshot["bench"]["force_format"] is True and snapshot["bench"]["concise"] is True
    assert snapshot["format_verdict"]["forced"] is True


async def test_scenario_without_format_has_no_verdict_and_refuses_force(tmp_path):
    server = FakeOllama(plans=[_plan("- retard", " de deux semaines")])
    async with bench_app(tmp_path, server) as (_, client):
        refused = await _post(client, scenario="resume", force_format=True)
        assert refused.status_code == 422 and refused.json()["code"] == "invalid_request"
        run_id = (await _post(client, scenario="resume")).json()["run_id"]
        snapshot = await _ended(client, run_id)
    assert snapshot["status"] == "ok" and "format_verdict" not in snapshot
    assert snapshot["bench"]["output"] == "- retard de deux semaines"


@pytest.mark.parametrize(
    ("body", "code", "status"),
    [
        ({"scenario": "inconnu"}, "invalid_request", 422),
        ({"input": "   "}, "invalid_request", 422),
        ({"model": "absent:1b"}, "model_not_found", None),
    ],
)
async def test_refusals(tmp_path, body, code, status):
    async with bench_app(tmp_path, FakeOllama()) as (_, client):
        response = await _post(client, **body)
    assert response.json()["code"] == code
    assert status is None or response.status_code == status


async def test_format_violation_raised_by_adapter_is_a_verdict_not_an_error(tmp_path):
    """`format` imposé et sortie quand même non conforme : l'adaptateur lève `invalid_output` ; le
    Banc le montre comme un format violé, le run finit `ok`."""
    server = FakeOllama(plans=[_plan('{"sentiment": "Super"}')])
    async with bench_app(tmp_path, server) as (_, client):
        run_id = (await _post(client, force_format=True)).json()["run_id"]
        snapshot = await _ended(client, run_id)
    assert snapshot["status"] == "ok" and snapshot["error"] is None
    assert snapshot["format_verdict"]["ok"] is False
    assert "sentiment" in snapshot["format_verdict"]["message"] or "categorie" in (
        snapshot["format_verdict"]["message"]
    )


async def test_timeout_names_the_real_delay(tmp_path):
    server = FakeOllama(plans=[Plan([part("{")], end="hang")])
    async with bench_app(tmp_path, server, delays={"lane_timeout_s": 0.3}) as (_, client):
        snapshot = await _ended(client, (await _post(client)).json()["run_id"])
    assert snapshot["status"] == "error" and snapshot["error"]["code"] == "timeout"
    assert snapshot["error"]["detail"]["timeout_s"] == 0.3
    assert "format_verdict" not in snapshot


async def test_list_reopen_and_unknown_run(tmp_path):
    server = FakeOllama(plans=[_plan(GOOD), _plan("{")])
    async with bench_app(tmp_path, server) as (app, client):
        first = (await _post(client, input="Premier")).json()["run_id"]
        await _ended(client, first)
        second = (await _post(client, input="Second", force_format=True)).json()["run_id"]
        await _ended(client, second)
        await app.state.hub.flush()
        runs = (await client.get("/api/bench/runs?limit=5")).json()["runs"]
        reopened = (await client.get(f"/api/runs/{first}")).json()
        unknown = await client.get("/api/runs/inconnu")
    assert [r["run_id"] for r in runs] == [second, first]  # les plus récents d'abord
    newest = runs[0]
    assert newest["scenario"] == "classification" and newest["model"] == TAG
    assert newest["force_format"] is True and newest["format_ok"] is False
    assert newest["input"] == "Second" and runs[1]["format_ok"] is True
    assert reopened["bench"]["output"] == GOOD and reopened["format_verdict"]["ok"] is True
    assert unknown.status_code == 404 and unknown.json()["code"] == "run_not_found"


async def test_a_second_bench_while_one_runs_is_busy(tmp_path):
    gate = asyncio.Event()
    server = FakeOllama(plans=[Plan([part("{"), final()], hold=gate)])
    async with bench_app(tmp_path, server) as (_, client):
        first = (await _post(client)).json()["run_id"]
        busy = await _post(client)
        gate.set()
        await _ended(client, first)
    assert busy.status_code == 409 and busy.json()["detail"]["run_id"] == first
