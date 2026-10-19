"""Équipe d'agents : bibliothèque, validation et mission séquentielle (story 6.5).

L'app est la vraie (hub, registre, service, boucle, flux SSE) ; le modèle est le `fake` scriptable
(un script par appel de modèle, tous agents confondus, dans l'ordre), les outils des coroutines de
test. La bibliothèque lit un `config/agent_crews.json` écrit dans le dossier de test. Aucun réseau.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import httpx
import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.models.fake import FAKE_REF, Sleep
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from .test_agent_api import LEAF_CO2_METHODS, call, error_of, steps, tool, turns
from .test_rag_run_api import _ended, _events, _types

BASE = f"http://127.0.0.1:{TEST_PORT}"
TOPIC = "Étudier le marché des petits modèles"

CREWS = {
    "version": 1,
    "crews": {
        "duo": {
            "label": "Duo",
            "category": "Test",
            "description": "Deux agents.",
            "topic": "Un sujet",
            "agents": [
                {
                    "role": "Chercheur",
                    "goal": "Trouver",
                    "backstory": "Méticuleux",
                    "tools": ["add"],
                },
                {"role": "Rédacteur", "goal": "Rédiger", "tools": []},
            ],
        },
        "vide": {"label": "Vide", "agents": []},
        "mail": {
            "label": "Mail",
            "agents": [{"role": "Courrier", "goal": "Écrire", "tools": ["send"]}],
        },
    },
}


@contextlib.asynccontextmanager
async def crew_app(tmp_path, **settings):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "agent_crews.json").write_text(json.dumps(CREWS), encoding="utf-8")
    app = create_app(make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}, **settings))
    async with app.router.lifespan_context(app):
        app.state.agent_tools.register(tool())

        async def send(arguments):
            return "envoyé"

        app.state.agent_tools.register(tool("send", send, sensitive=True))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


@pytest.fixture
async def crewed(tmp_path):
    async with crew_app(tmp_path) as pair:
        yield pair


async def _start(client, crew="duo", **body):
    payload = {
        "mode": "crew",
        "crew": crew,
        "topic": TOPIC,
        "model": FAKE_REF.tag,
        "allow_cloud": False,
        **body,
    }
    return await client.post("/api/agents/runs", json=payload)


async def _mission(client, **body):
    started = await _start(client, **body)
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]
    return started.json(), await _ended(client, run_id), await _events(client, run_id)


def agent(**fields):
    return {"role": "A", "goal": "g", "tools": [], **fields}


async def _running(model, opened):
    async with asyncio.timeout(3):
        while model.opened < opened:
            await asyncio.sleep(0.01)


# --- bibliothèque ----------------------------------------------------------------------------


async def test_the_library_lists_agents_and_ordered_tasks(crewed):
    _, client = crewed
    body = (await client.get("/api/agents/crews")).json()
    assert body["max_agents"] == 5
    duo = next(c for c in body["crews"] if c["id"] == "duo")
    assert duo["label"] == "Duo" and duo["modified"] is False
    assert [a["role"] for a in duo["agents"]] == ["Chercheur", "Rédacteur"]
    first = duo["agents"][0]
    assert first["goal"] == "Trouver" and first["tools"] == ["add"] and first["model"] is None
    assert [t["agent"] for t in duo["tasks"]] == ["Chercheur", "Rédacteur"]
    assert "{topic}" in duo["tasks"][0]["description"]


async def test_validate_gives_one_message_per_field(crewed):
    _, client = crewed
    cases = [
        ({"agents": []}, ["agents"]),
        ({"agents": [agent(role=f"R{i}") for i in range(6)]}, ["agents"]),
        (
            {"agents": [agent(role="", goal="", tools=["nope"]), agent(role="B", model="x:1b")]},
            ["agents[0].role", "agents[0].goal", "agents[0].tools", "agents[1].model"],
        ),
        ({"agents": [agent(), agent(role="a")]}, ["agents[1].role"]),
    ]
    for body, fields in cases:
        got = await client.post("/api/agents/crews/validate", json=body)
        assert got.status_code == 200
        result = got.json()
        assert result["valid"] is False and [e["field"] for e in result["errors"]] == fields
        assert all(e["message"] for e in result["errors"])
    ok = await client.post(
        "/api/agents/crews/validate",
        json={"agents": [agent(tools=["add"], model=FAKE_REF.tag), agent(role="B")]},
    )
    assert ok.json() == {"valid": True, "errors": []}
    five = await client.post(
        "/api/agents/crews/validate", json={"agents": [agent(role=f"R{i}") for i in range(5)]}
    )
    assert five.json()["valid"] is True


async def test_a_modification_is_kept_in_preferences_and_reset_restores_the_origin(crewed):
    app, client = crewed
    mine = [agent(role="Seul", goal="Tout faire", tools=["add"])]
    saved = await client.put("/api/agents/crews/duo", json={"agents": mine})
    assert saved.status_code == 200 and saved.json()["modified"] is True
    assert [a["role"] for a in saved.json()["agents"]] == ["Seul"]
    assert app.state.preferences.get("agents.crews")["duo"][0]["role"] == "Seul"
    listed = next(
        c for c in (await client.get("/api/agents/crews")).json()["crews"] if c["id"] == "duo"
    )
    assert [a["role"] for a in listed["agents"]] == ["Seul"] and listed["modified"] is True

    reset = await client.delete("/api/agents/crews/duo")
    assert reset.status_code == 200 and reset.json()["modified"] is False
    assert [a["role"] for a in reset.json()["agents"]] == ["Chercheur", "Rédacteur"]
    assert "duo" not in (app.state.preferences.get("agents.crews") or {})
    assert (await client.delete("/api/agents/crews/duo")).status_code == 200  # idempotent


async def test_an_invalid_modification_or_unknown_crew_is_refused(crewed):
    _, client = crewed
    bad = await client.put("/api/agents/crews/duo", json={"agents": []})
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_request"
    assert "agents :" in bad.json()["detail"]["technical"]
    unknown = await client.put("/api/agents/crews/zzz", json={"agents": [agent()]})
    assert unknown.status_code == 404
    assert (await client.delete("/api/agents/crews/zzz")).status_code == 404


# --- mission ---------------------------------------------------------------------------------


async def test_a_mission_chains_the_agents_and_publishes_their_steps(crewed):
    app, client = crewed
    model = turns(app, ["Je cherche.", call(a=2, b=3)], ["Données : 5."], ["Rapport final : 5."])
    started, snapshot, events = await _mission(client)
    assert snapshot["status"] == "ok" and snapshot["kind"] == "agent"
    assert started["conversation_id"]
    assert snapshot["params"] == {
        "mode": "crew",
        "crew": "duo",
        "agents": [
            {"role": "Chercheur", "model": FAKE_REF.tag, "tools": ["add"]},
            {"role": "Rédacteur", "model": FAKE_REF.tag, "tools": []},
        ],
        "allow_cloud": False,
        "temperature": 0.2,
        "max_turns": 10,
    }
    assert TOPIC not in json.dumps(snapshot["params"])

    got = steps(events)
    assert [s["step_id"] for s in got] == list(range(1, len(got) + 1))
    assert [(s["agent"], s["kind"]) for s in got] == [
        ("Chercheur", "think"), ("Chercheur", "tool_call"), ("Chercheur", "tool_result"),
        ("Chercheur", "answer"), ("Rédacteur", "answer"),
    ]  # fmt: skip
    first_answer, last_answer = got[3], got[4]
    assert first_answer["agent_totals"]["tools"] == 1
    assert isinstance(first_answer["agent_totals"]["duration_s"], float)
    assert last_answer["agent_totals"]["tools"] == 0
    assert "agent_totals" not in got[0] and "agent_totals" not in got[2]

    # Seul le rapport du dernier agent est publié en `token`.
    assert [e["data"]["text"] for e in events if e["type"] == "token"] == ["Rapport final : 5."]

    # La sortie d'un agent est l'entrée du suivant ; chacun a sa consigne et ses outils.
    assert [r.tools for r in model.requests] == [[tool().spec()], [tool().spec()], []]
    system, user = model.requests[0].messages[:2]
    assert "Chercheur" in system.content and "Méticuleux" in system.content
    assert TOPIC in user.content and "agent précédent" not in user.content
    last_system, last_user = model.requests[2].messages[:2]
    assert TOPIC in last_user.content and "agent précédent (Chercheur)" in last_user.content
    assert "Données : 5." in last_user.content and "rapport final" in last_system.content

    # Feuilles : un appel de modèle = une feuille avec son `co2`.
    leaves = snapshot["children"]
    assert len(leaves) == 3 and all(
        c["status"] == "ok" and c["metrics"]["co2"]["method"] in LEAF_CO2_METHODS for c in leaves
    )

    # Rapport final gardé dans la conversation ; totaux de la mission dans l'instantané.
    conversation = (await client.get(f"/api/conversations/{started['conversation_id']}")).json()
    assert [(m["role"], m["content"]) for m in conversation["messages"]] == [
        ("user", TOPIC),
        ("assistant", "Rapport final : 5."),
    ]
    mission = snapshot["mission"]
    assert mission["agents_done"] == 2 and mission["duration_s"] > 0
    assert mission["peak_memory_gb"] is None or mission["peak_memory_gb"] > 0


async def test_an_agent_without_its_own_model_needs_the_mission_model(crewed):
    _, client = crewed
    response = await client.post(
        "/api/agents/runs", json={"mode": "crew", "crew": "duo", "topic": TOPIC}
    )
    assert response.status_code == 422
    assert "agents[0].model" in response.json()["detail"]["technical"]


async def test_an_agent_with_its_own_model_needs_no_mission_model(crewed):
    app, client = crewed
    mine = [agent(role="Seul", goal="Tout faire", model=FAKE_REF.tag)]
    assert (await client.put("/api/agents/crews/duo", json={"agents": mine})).status_code == 200
    turns(app, ["Fait."])
    response = await client.post(
        "/api/agents/runs", json={"mode": "crew", "crew": "duo", "topic": TOPIC}
    )
    assert response.status_code == 200
    assert (await _ended(client, response.json()["run_id"]))["status"] == "ok"


async def test_start_errors_run_nothing(crewed):
    app, client = crewed
    model = turns(app, ["x"])
    post = client.post
    cases = [
        (await _start(client, crew="zzz"), 404, "not_found"),
        (await _start(client, crew="vide"), 422, "invalid_request"),
        (await post("/api/agents/runs", json={"mode": "crew", "topic": TOPIC}), 422, None),
        (
            await post("/api/agents/runs", json={"mode": "crew", "crew": "duo", "topic": " "}),
            422,
            None,
        ),
        (await _start(client, tools=["add"]), 422, None),
        (await _start(client, model="inconnu:1b"), 404, "model_not_found"),
    ]
    for response, status, code in cases:
        assert response.status_code == status, response.text
        assert code is None or response.json()["code"] == code
    assert model.opened == 0 and app.state.hub.active_runs() == []


async def test_an_agent_that_fails_stops_the_mission_and_later_agents_publish_nothing(crewed):
    app, client = crewed
    model = turns(app, [ProviderError("ollama_error", "boum")])
    _, snapshot, events = await _mission(client)
    assert snapshot["status"] == "error" and error_of(events)["code"] == "ollama_error"
    assert steps(events) == [] and model.opened == 1
    assert snapshot["mission"]["agents_done"] == 0


async def test_a_sensitive_tool_is_refused_in_a_crew_until_approval_exists(crewed):
    app, client = crewed
    turns(app, [call(name="send")], ["Brouillon prêt."])
    _, snapshot, events = await _mission(client, crew="mail")
    assert snapshot["status"] == "ok"
    result = next(s for s in steps(events) if s["kind"] == "tool_result")
    assert result["agent"] == "Courrier" and result["failed"] is True
    assert "sensible" in result["summary"]


async def test_cancelling_keeps_the_partial_report_and_the_mission_totals(crewed):
    app, client = crewed
    model = turns(app, ["Étude du premier agent."], ["début", Sleep(60)])
    started = (await _start(client)).json()
    run_id = started["run_id"]
    await _running(model, 2)
    assert (await client.post(f"/api/runs/{run_id}/cancel")).status_code == 200
    snapshot = await _ended(client, run_id)
    assert snapshot["status"] == "cancelled" and model.opened == model.closed == 2
    events = await _events(client, run_id)
    assert [(s["agent"], s["kind"]) for s in steps(events)] == [("Chercheur", "answer")]
    tokens = [e["data"]["text"] for e in events if e["type"] == "token"]
    assert tokens == ["Étude du premier agent."]
    types = _types(events)
    assert types.index("mission_totals") < types.index("run_ended")
    conversation = (await client.get(f"/api/conversations/{started['conversation_id']}")).json()
    assert conversation["messages"][-1]["content"] == "Étude du premier agent."
    assert snapshot["mission"]["agents_done"] == 1 and snapshot["mission"]["duration_s"] > 0
    assert all(c["metrics"]["co2"]["method"] in LEAF_CO2_METHODS for c in snapshot["children"])


async def test_cancelling_the_first_agent_leaves_no_report(crewed):
    app, client = crewed
    model = turns(app, ["début", Sleep(60)])
    started = (await _start(client)).json()
    await _running(model, 1)
    await client.post(f"/api/runs/{started['run_id']}/cancel")
    snapshot = await _ended(client, started["run_id"])
    events = await _events(client, started["run_id"])
    assert snapshot["status"] == "cancelled" and not [e for e in events if e["type"] == "token"]
    assert snapshot["mission"]["agents_done"] == 0


async def test_a_second_mission_while_one_runs_is_run_busy(crewed):
    app, client = crewed
    model = turns(app, ["début", Sleep(60)])
    first = (await _start(client)).json()
    await _running(model, 1)
    second = await _start(client)
    assert second.status_code == 409 and second.json()["code"] == "run_busy"
    await client.post(f"/api/runs/{first['run_id']}/cancel")
    await _ended(client, first["run_id"])
