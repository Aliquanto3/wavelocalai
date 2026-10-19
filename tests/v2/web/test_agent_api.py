"""`POST /api/agents/runs` : un agent appelle des outils et publie chaque étape (story 6.1).

L'app est la vraie (hub, registre, service d'agent, boucle, flux SSE). Le modèle est le `fake`
scriptable de `Settings.testing` (un script par tour, appels d'outils compris), puis, pour les
adaptateurs, un faux Ollama et un faux OpenAI sous leurs vrais SDK. Les outils sont des coroutines
de test inscrites au `ToolRegistry`. Aucun réseau.
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx
import pytest

from wavelocalai.agents.tools import AgentTool, ToolOutput
from wavelocalai.errors import ProviderError
from wavelocalai.models.fake import FAKE_REF, Sleep
from wavelocalai.models.port import TextDelta, ToolCall
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..fake_cloud import FakeCloud, Plan, chat_stream, chat_tool_stream
from ..fake_ollama import Plan as OllamaPlan
from ..fake_ollama import final, part
from .conftest import served  # noqa: F401 - fixture
from .test_chat_cloud_api import cloud_app
from .test_memory_guard_api import chat_app as ollama_app
from .test_memory_guard_api import ollama
from .test_rag_run_api import _ended, _events, _types

BASE = f"http://127.0.0.1:{TEST_PORT}"
LEAF_CO2_METHODS = ("codecarbon", "ecologits", "unmeasurable")


@contextlib.asynccontextmanager
async def agent_app(tmp_path, **settings):
    """(app, client) avec `WAVELOCALAI_TESTING=1` et des réglages d'agent à choisir."""
    app = create_app(make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}, **settings))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


def tool(tool_id="add", fn=None, **fields) -> AgentTool:
    async def add(arguments):
        return str(arguments["a"] + arguments["b"])

    return AgentTool(
        tool_id,
        fields.pop("description", "Additionne deux nombres."),
        fn or add,
        parameters={
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            "required": ["a", "b"],
        },
        **fields,
    )


def turns(app, *scripts):
    """Un script par appel du modèle : texte (`str`) ou appel d'outil (`ToolCall`), ou une erreur."""
    model = app.state.models[FAKE_REF.tag]
    model.scripts = [
        [TextDelta(s) if isinstance(s, str) else s for s in script] for script in scripts
    ]
    model.opened = model.closed = 0
    model.requests.clear()
    return model


def call(call_id="c1", name="add", **arguments) -> ToolCall:
    return ToolCall(call_id, name, arguments)


async def _post(client, prompt="Combien font 2 + 3 ?", tools=("add",), **body):
    payload = {
        "mode": "solo",
        "model": FAKE_REF.tag,
        "prompt": prompt,
        "tools": list(tools),
        "allow_cloud": False,
        **body,
    }
    return await client.post("/api/agents/runs", json=payload)


async def _run(client, **body):
    started = await _post(client, **body)
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]
    return started.json(), await _ended(client, run_id), await _events(client, run_id)


def steps(events):
    return [e["data"] for e in events if e["type"] == "step"]


def error_of(events):
    return next(e for e in events if e["type"] == "run_ended")["data"]["error"]


# --- boucle nominale -----------------------------------------------------------------------------


async def test_a_task_runs_a_tool_then_answers_and_every_step_is_published(served):
    app, client = served
    app.state.agent_tools.register(tool())
    model = turns(app, ["Je calcule.", call(a=2, b=3)], ["Le résultat ", "est 5."])
    started, snapshot, events = await _run(client)
    assert started["conversation_id"]
    assert snapshot["status"] == "ok" and snapshot["kind"] == "agent"
    assert snapshot["params"] == {
        "mode": "solo",
        "tools": ["add"],
        "allow_cloud": False,
        "temperature": 0.2,
        "max_turns": 10,
    }

    # Ordre : `metrics` de chaque appel de modèle, puis ses étapes ; la réponse part après l'étape.
    assert _types(events) == [
        "run_started", "metrics", "step", "step", "step",
        "metrics", "step", "token", "run_ended",
    ]  # fmt: skip
    think, tool_call, tool_result, answer = steps(events)
    assert [s["kind"] for s in (think, tool_call, tool_result, answer)] == [
        "think", "tool_call", "tool_result", "answer",
    ]  # fmt: skip
    assert [s["step_id"] for s in steps(events)] == [1, 2, 3, 4]
    assert all(s["lane"] == FAKE_REF.tag and s["agent"] is None for s in steps(events))
    assert [s["turn"] for s in steps(events)] == [1, 1, 1, 2]
    assert think["summary"] == "Je calcule."
    assert tool_call["tool"] == "add" and tool_call["call_id"] == "c1"
    assert tool_call["arguments"] == {"a": 2, "b": 3} and tool_call["duration_s"] is None
    assert tool_result["tool"] == "add" and tool_result["call_id"] == "c1"
    assert tool_result["summary"] == "5" and isinstance(tool_result["duration_s"], float)
    assert "failed" not in tool_result and "artifact_url" not in tool_result
    assert answer["summary"] == "Le résultat est 5."
    tokens = [e["data"] for e in events if e["type"] == "token"]
    assert [(t["lane"], t["channel"], t["text"]) for t in tokens] == [
        (FAKE_REF.tag, "answer", "Le résultat est 5.")
    ]
    assert [e["data"]["turn"] for e in events if e["type"] == "metrics"] == [1, 2]

    # Le modèle a reçu l'outil (schéma neutre), puis l'appel et son résultat au tour suivant.
    first, second = model.requests
    assert first.tools == [tool().spec()] and first.messages[0].role == "system"
    assert first.messages[-1].content == "Combien font 2 + 3 ?"
    assistant, result = second.messages[-2:]
    assert assistant.role == "assistant" and assistant.content == "Je calcule."
    assert assistant.tool_calls == [{"id": "c1", "name": "add", "arguments": {"a": 2, "b": 3}}]
    assert (result.role, result.content, result.tool_call_id) == ("tool", "5", "c1")

    # Chaque appel de modèle est une feuille `generation` avec son `co2` ; le parent n'en a pas.
    leaves = snapshot["children"]
    assert [c["kind"] for c in leaves] == ["generation", "generation"]
    assert all(
        c["status"] == "ok" and c["metrics"]["co2"]["method"] in LEAF_CO2_METHODS for c in leaves
    )
    assert (await client.get("/api/carbon/session")).json()["by_module"]["agent"]["runs"] == 2

    # La conversation `agent` garde la tâche et la réponse finale.
    conversation = (await client.get(f"/api/conversations/{started['conversation_id']}")).json()
    assert [(m["role"], m["content"]) for m in conversation["messages"]] == [
        ("user", "Combien font 2 + 3 ?"),
        ("assistant", "Le résultat est 5."),
    ]


async def test_a_task_without_tools_answers_in_one_turn_and_a_conversation_continues(served):
    app, client = served
    model = turns(app, ["Bonjour !"], ["Je me souviens."])
    started, snapshot, events = await _run(client, prompt="Salut", tools=())
    assert snapshot["status"] == "ok" and model.requests[0].tools == []
    assert [s["kind"] for s in steps(events)] == ["answer"]
    follow = await _post(client, prompt="Tu te souviens ?", tools=(),
                         conversation_id=started["conversation_id"])  # fmt: skip
    assert (
        follow.status_code == 200 and follow.json()["conversation_id"] == started["conversation_id"]
    )
    await _ended(client, follow.json()["run_id"])
    roles = [(m.role, m.content) for m in model.requests[1].messages]
    assert roles[1:] == [
        ("user", "Salut"), ("assistant", "Bonjour !"), ("user", "Tu te souviens ?")
    ]  # fmt: skip


async def test_the_reasoning_channel_becomes_a_think_step_before_the_answer(served):
    app, client = served
    turns(app, [TextDelta("Il faut additionner.", "thought"), "C'est fait."])
    _, snapshot, events = await _run(client, tools=())
    think, answer = steps(events)
    assert (think["kind"], think["summary"]) == ("think", "Il faut additionner.")
    assert (answer["kind"], answer["summary"]) == ("answer", "C'est fait.")
    assert [e["data"]["text"] for e in events if e["type"] == "token"] == ["C'est fait."]


async def test_parallel_calls_run_in_order_and_artifacts_are_referenced(served):
    app, client = served

    async def make_file(arguments):
        return ToolOutput("Fichier écrit.", artifact_url="/api/outputs/rapport.md")

    app.state.agent_tools.register(tool())
    app.state.agent_tools.register(tool("report", make_file, description="Écrit un rapport."))
    turns(app, [call("c1", a=1, b=1), call("c2", "report")], ["Terminé."])
    _, snapshot, events = await _run(client, tools=("add", "report"))
    assert snapshot["status"] == "ok"
    kinds = [(s["kind"], s.get("call_id")) for s in steps(events)]
    assert kinds == [
        ("tool_call", "c1"), ("tool_result", "c1"),
        ("tool_call", "c2"), ("tool_result", "c2"), ("answer", None),
    ]  # fmt: skip
    results = [s for s in steps(events) if s["kind"] == "tool_result"]
    assert "artifact_url" not in results[0]
    assert results[1]["artifact_url"] == "/api/outputs/rapport.md"


# --- erreurs d'outil -----------------------------------------------------------------------------


async def test_a_failing_tool_is_reported_to_the_agent_which_goes_on(served):
    app, client = served

    async def broken(arguments):
        raise ValueError("division par zéro")

    app.state.agent_tools.register(tool("div", broken))
    model = turns(app, [call("c1", "div")], ["Désolé, ça échoue."])
    _, snapshot, events = await _run(client, tools=("div",))
    assert snapshot["status"] == "ok"
    result = next(s for s in steps(events) if s["kind"] == "tool_result")
    assert result["failed"] is True and result["summary"] == "ValueError: division par zéro"
    assert model.requests[1].messages[-1].content == "ValueError: division par zéro"
    assert steps(events)[-1]["kind"] == "answer"


async def test_a_slow_tool_hits_its_timeout_and_the_agent_receives_it(tmp_path):
    async with agent_app(tmp_path, agents={"tool_timeout_s": 0.1}) as (app, client):

        async def slow(arguments):
            await asyncio.sleep(30)
            return "jamais"

        app.state.agent_tools.register(tool("slow", slow))
        model = turns(app, [call("c1", "slow")], ["Trop long."])
        _, snapshot, events = await _run(client, tools=("slow",))
        assert snapshot["status"] == "ok"
        result = next(s for s in steps(events) if s["kind"] == "tool_result")
        assert result["failed"] is True and result["summary"].startswith("Délai dépassé (0.1 s)")
        assert "Délai dépassé" in model.requests[1].messages[-1].content


async def test_unknown_unreadable_and_sensitive_calls_are_refused_without_running_a_tool(served):
    app, client = served
    ran: list[str] = []

    async def mail(arguments):
        ran.append("mail")
        return "envoyé"

    app.state.agent_tools.register(tool())
    app.state.agent_tools.register(tool("send_mail", mail, sensitive=True))
    turns(
        app,
        [
            call("c1", "teleport"),
            ToolCall("c2", "add", {}, error="Arguments illisibles (JSON invalide)"),
            call("c3", "send_mail"),
        ],
        ["Rien n'a marché."],
    )
    _, snapshot, events = await _run(client, tools=("add", "send_mail"))
    assert snapshot["status"] == "ok" and ran == []  # AD-9 : aucun outil sensible sans approbation
    results = [s for s in steps(events) if s["kind"] == "tool_result"]
    assert all(r["failed"] is True for r in results)
    assert "Outil inconnu : teleport" in results[0]["summary"] and "add" in results[0]["summary"]
    assert "Arguments illisibles" in results[1]["summary"]
    assert "sensible" in results[2]["summary"]


async def test_a_long_result_is_cut_for_the_model_and_clipped_in_the_step(tmp_path):
    async with agent_app(tmp_path, agents={"result_chars": 200, "summary_chars": 60}) as (
        app,
        client,
    ):

        async def long_text(arguments):
            return "x" * 500

        app.state.agent_tools.register(tool("long", long_text))
        model = turns(app, [call("c1", "long")], ["Lu."])
        _, _, events = await _run(client, tools=("long",))
        shown = model.requests[1].messages[-1].content
        assert shown.startswith("x" * 200) and "tronqué : 200 caractères sur 500" in shown
        result = next(s for s in steps(events) if s["kind"] == "tool_result")
        assert len(result["summary"]) == 60 and result["summary"].endswith("…")


# --- borne de tours ------------------------------------------------------------------------------


async def test_the_turn_limit_ends_cleanly_with_the_reason(tmp_path):
    async with agent_app(tmp_path, agents={"max_turns": 2}) as (app, client):
        app.state.agent_tools.register(tool())
        model = turns(app, [call("c1", a=1, b=2)])  # le même appel, à chaque tour
        _, snapshot, events = await _run(client)
        assert snapshot["status"] == "ok" and model.opened == 2
        assert len(snapshot["children"]) == 2
        last = steps(events)[-1]
        assert last["kind"] == "answer" and last["stopped"] == "max_turns"
        assert "limite de 2 appels de modèle" in last["summary"]
        text = "".join(e["data"]["text"] for e in events if e["type"] == "token")
        assert "limite de 2 appels de modèle" in text


# --- annulation ----------------------------------------------------------------------------------


async def test_cancelling_during_a_tool_cuts_the_tool_and_leaves_no_new_model_call(served):
    app, client = served
    started_tool, tool_cancelled = asyncio.Event(), asyncio.Event()

    async def hang(arguments):
        started_tool.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            tool_cancelled.set()
            raise

    app.state.agent_tools.register(tool("hang", hang))
    model = turns(app, [call("c1", "hang")], ["jamais"])
    run_id = (await _post(client, tools=("hang",))).json()["run_id"]
    async with asyncio.timeout(3):
        await started_tool.wait()
    assert (await client.post(f"/api/runs/{run_id}/cancel")).status_code == 200
    snapshot = await _ended(client, run_id)
    assert snapshot["status"] == "cancelled"
    async with asyncio.timeout(3):
        await tool_cancelled.wait()  # l'outil en cours est coupé
    assert model.opened == model.closed == 1  # le flux du premier appel est fermé, pas de second
    assert [c["status"] for c in snapshot["children"]] == ["ok"]
    types = _types(await _events(client, run_id))
    assert types[-1] == "run_ended" and "token" not in types


async def test_cancelling_during_a_model_call_closes_its_stream(served):
    app, client = served
    model = turns(app, ["début", Sleep(60)])
    run_id = (await _post(client, tools=())).json()["run_id"]
    async with asyncio.timeout(3):
        while model.opened == 0:
            await asyncio.sleep(0.01)
    await client.post(f"/api/runs/{run_id}/cancel")
    snapshot = await _ended(client, run_id)
    assert snapshot["status"] == "cancelled"
    assert model.opened == model.closed == 1
    (leaf,) = snapshot["children"]
    assert leaf["status"] == "cancelled" and leaf["metrics"]["co2"]["method"] in LEAF_CO2_METHODS


# --- erreurs de modèle et de requête -------------------------------------------------------------


async def test_a_model_failure_ends_the_run_in_error_with_its_envelope(served):
    app, client = served
    turns(app, [ProviderError("ollama_error", "boum")])
    _, snapshot, events = await _run(client, tools=())
    assert snapshot["status"] == "error"
    assert error_of(events)["code"] == "ollama_error"
    assert steps(events) == []
    assert snapshot["children"][0]["status"] == "error"


async def test_a_failure_in_the_second_turn_keeps_the_steps_already_published(served):
    app, client = served
    app.state.agent_tools.register(tool())
    turns(app, [call(a=1, b=1)], [ProviderError("generation_interrupted")])
    _, snapshot, events = await _run(client)
    assert snapshot["status"] == "error" and error_of(events)["code"] == "generation_interrupted"
    assert [s["kind"] for s in steps(events)] == ["tool_call", "tool_result"]


async def test_a_request_with_an_unknown_or_unavailable_tool_is_refused_before_any_run(served):
    app, client = served
    app.state.agent_tools.register(tool("off", available=False, reason="SMTP absent"))
    turns(app, ["jamais"])
    unknown = await _post(client, tools=("teleport",))
    assert unknown.status_code == 422 and unknown.json()["code"] == "invalid_request"
    assert "teleport" in unknown.json()["detail"]["technical"]
    off = await _post(client, tools=("off",))
    assert off.status_code == 422 and "SMTP absent" in off.json()["detail"]["technical"]
    repeated = await _post(client, tools=("off", "off"))
    assert repeated.status_code == 422
    assert app.state.models[FAKE_REF.tag].opened == 0
    assert app.state.hub.active_runs() == []


async def test_invalid_bodies_are_422_and_crew_mode_is_not_taken_here(served):
    _, client = served
    for body in (
        {"mode": "crew", "model": FAKE_REF.tag, "prompt": "x", "tools": []},
        {"mode": "solo", "model": FAKE_REF.tag, "prompt": "   ", "tools": []},
        {"mode": "solo", "model": "", "prompt": "x"},
        {"model": FAKE_REF.tag, "prompt": "x"},
    ):
        response = await client.post("/api/agents/runs", json=body)
        assert response.status_code == 422 and response.json()["code"] == "invalid_request"
    unknown = await client.post(
        "/api/agents/runs", json={"mode": "solo", "model": "inconnu:1b", "prompt": "x"}
    )
    assert unknown.status_code == 404 and unknown.json()["code"] == "model_not_found"


async def test_a_second_agent_run_while_one_is_active_is_run_busy(served):
    app, client = served
    gate = asyncio.Event()

    async def wait(arguments):
        await gate.wait()
        return "ok"

    app.state.agent_tools.register(tool("wait", wait))
    turns(app, [call("c1", "wait")], ["Fini."])
    first = (await _post(client, tools=("wait",))).json()["run_id"]
    busy = await _post(client, tools=("wait",))
    assert busy.status_code == 409 and busy.json()["code"] == "run_busy"
    assert busy.json()["detail"]["run_id"] == first
    gate.set()
    assert (await _ended(client, first))["status"] == "ok"


async def test_agent_secrets_never_reach_the_steps(tmp_path):
    key = "sk-test-OPENAI0123456789abcdef"
    app = create_app(
        make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1", "OPENAI_API_KEY": key})
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:

            async def leak(arguments):
                return f"clé : {key}"

            app.state.agent_tools.register(tool("leak", leak))
            model = turns(app, [call("c1", "leak")], ["Fini."])
            _, _, events = await _run(client, tools=("leak",))
            result = next(s for s in steps(events) if s["kind"] == "tool_result")
            assert key not in result["summary"] and "***" in result["summary"]
            assert key not in model.requests[1].messages[-1].content


# --- adaptateurs réels sous la boucle ------------------------------------------------------------


def _ollama_tool_call(name, arguments):
    chunk = part("")
    chunk["message"]["tool_calls"] = [{"function": {"name": name, "arguments": arguments}}]
    return chunk


async def test_an_ollama_model_calls_a_tool_through_the_real_adapter(tmp_path):
    server = ollama(
        loaded=["mid:2b"],
        plans=[
            OllamaPlan([_ollama_tool_call("add", {"a": 4, "b": 5}), final()]),
            OllamaPlan([part("Cela fait 9."), final()]),
        ],
    )
    async with ollama_app(tmp_path, server) as (app, client):
        app.state.agent_tools.register(tool())
        started = await client.post(
            "/api/agents/runs",
            json={"mode": "solo", "model": "mid:2b", "prompt": "4 + 5 ?", "tools": ["add"]},
        )
        assert started.status_code == 200, started.text
        snapshot = await _ended(client, started.json()["run_id"])
        events = await _events(client, started.json()["run_id"])
    assert snapshot["status"] == "ok"
    assert [s["kind"] for s in steps(events)] == ["tool_call", "tool_result", "answer"]
    assert next(s for s in steps(events) if s["kind"] == "tool_result")["summary"] == "9"
    first, second = server.chat_requests
    assert first["tools"][0]["function"]["name"] == "add"
    assert second["messages"][-1]["role"] == "tool" and second["messages"][-1]["tool_name"] == "add"
    assert second["messages"][-2]["tool_calls"][0]["function"]["arguments"] == {"a": 4, "b": 5}
    assert [c["metrics"]["tps_source"] for c in snapshot["children"]] == ["ollama_eval"] * 2


async def test_a_local_model_that_does_not_fit_ends_in_ram_guard(tmp_path):
    server = ollama(plans=[OllamaPlan([part("jamais"), final()])])
    async with ollama_app(tmp_path, server) as (app, client):
        app.state.agent_tools.register(tool())
        started = await client.post(
            "/api/agents/runs",
            json={"mode": "solo", "model": "big:7b", "prompt": "4 + 5 ?", "tools": ["add"]},
        )
        assert started.status_code == 200  # le garde-fou parle dans le run, comme pour le chat
        run_id = started.json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)
    assert snapshot["status"] == "error"
    error = error_of(events)
    assert (
        error["code"] == "ram_guard" and error["detail"]["needed_gb"] > error["detail"]["free_gb"]
    )
    assert snapshot["children"][0]["metrics"]["co2"]["reason"].startswith("modèle non chargé")
    assert server.chat_requests == []  # Ollama n'a jamais été appelé


async def test_a_cloud_model_needs_allow_cloud_then_calls_a_tool_through_the_openai_adapter(
    tmp_path,
):
    fake = FakeCloud(
        "openai",
        [
            Plan(chat_tool_stream([("call_9", "add", ['{"a": 6, ', '"b": 1}'])])),
            Plan(chat_stream(["Sept."])),
        ],
    )
    async with cloud_app(tmp_path, [fake]) as (app, client):
        app.state.agent_tools.register(tool())
        body = {"mode": "solo", "model": "openai/gpt-6-luna", "prompt": "6 + 1 ?", "tools": ["add"]}
        refused = await client.post("/api/agents/runs", json=body)
        assert refused.status_code == 403 and refused.json()["code"] == "cloud_not_allowed"
        assert fake.requests == []  # le fournisseur n'a jamais été appelé
        started = await client.post("/api/agents/runs", json={**body, "allow_cloud": True})
        assert started.status_code == 200, started.text
        run_id = started.json()["run_id"]
        snapshot = await _ended(client, run_id)
        events = await _events(client, run_id)
    assert snapshot["status"] == "ok"
    assert [s["kind"] for s in steps(events)] == ["tool_call", "tool_result", "answer"]
    assert fake.bodies[0]["tools"][0]["function"]["name"] == "add"
    tool_message = fake.bodies[1]["messages"][-1]
    assert tool_message == {"role": "tool", "tool_call_id": "call_9", "content": "7"}
    leaves = snapshot["children"]
    assert len(leaves) == 2 and all(c["metrics"]["tps_source"] == "wallclock" for c in leaves)
    assert all(c["metrics"]["co2"]["method"] in LEAF_CO2_METHODS for c in leaves)


async def test_an_interrupted_model_call_is_retried_once_without_leaking_partial_text(served):
    app, client = served
    model = turns(
        app,
        ["Rép", ProviderError("generation_interrupted")],  # flux coupé après un fragment
        ["Réponse complète."],
    )
    _, snapshot, events = await _run(client, tools=())
    assert snapshot["status"] == "ok" and model.opened == 2
    assert "retry" not in _types(events)  # aucun texte n'était parti pendant le tour
    tokens = "".join(e["data"]["text"] for e in events if e["type"] == "token")
    assert tokens == "Réponse complète." and len(snapshot["children"]) == 1
