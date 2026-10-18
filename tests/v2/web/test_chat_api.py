"""`POST /api/chat/runs` : réponse en flux d'un modèle Ollama (faux serveur), de bout en bout.

L'app est la vraie (hub, registre, service de chat, flux SSE) ; seul Ollama est simulé, sous un vrai
`ollama.AsyncClient`. Rien ne touche le réseau.
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx

from wavelocalai.models.ollama_api import OllamaHttpSource
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..fake_ollama import FakeOllama, Plan, final, part
from .conftest import parse_sse, served  # noqa: F401 - fixture

BASE = f"http://127.0.0.1:{TEST_PORT}"
TAG = "qwen2.5:1.5b"


@contextlib.asynccontextmanager
async def chat_app(tmp_path, server: FakeOllama, *, real_client: bool = False, **settings):
    """(app, client). `real_client` : l'app crée son vrai client Ollama (port fermé)."""
    environ = settings.pop("environ", None)
    config = make_settings(tmp_path, environ=environ, **settings)
    registry = ModelRegistry(
        config, source=OllamaHttpSource(config.ollama.host, transport=server.transport)
    )
    app = create_app(
        config, registry=registry, ollama_client=None if real_client else server.client()
    )
    async with app.router.lifespan_context(app):
        await registry.refresh()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


async def _post(client, message="Bonjour", **body):
    body = {"model": TAG, "message": message, "temperature": 0.2, "allow_cloud": False, **body}
    return await client.post("/api/chat/runs", json=body)


async def _events(client, run_id):
    response = await client.get(f"/api/runs/{run_id}/events")
    return [f["data"] for f in parse_sse(response.text)[0]]


async def _ended(client, run_id, timeout=3.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


def _types(events):
    return [e["type"] for e in events]


def _messages(app, conversation_id):
    rows = app.state.store.read(
        "SELECT role, content, reasoning FROM messages WHERE conversation_id = ? ORDER BY rowid",
        (conversation_id,),
    )
    return [(r["role"], r["content"], r["reasoning"]) for r in rows]


async def test_nominal_chat_streams_tokens_then_metrics_and_stores_both_messages(tmp_path):
    server = FakeOllama(
        loaded=[],  # modèle à charger : model_loading / model_loaded
        plans=[Plan([part("", thinking="Hmm"), part("Bonjour"), part(" le monde"), final()])],
    )
    async with chat_app(tmp_path, server) as (app, client):
        response = await _post(client, "Salut modèle")
        assert response.status_code == 200
        started = response.json()
        assert set(started) == {"run_id", "conversation_id"} and started["conversation_id"]
        run_id = started["run_id"]
        assert (await _ended(client, run_id))["status"] == "ok"
        events = await _events(client, run_id)
        types = _types(events)
        assert types[0] == "run_started" and types[-1] == "run_ended"
        assert types.index("model_loading") < types.index("model_loaded") < types.index("token")
        tokens = [e["data"] for e in events if e["type"] == "token"]
        assert {t["lane"] for t in tokens} == {TAG}
        assert "".join(t["text"] for t in tokens if t["channel"] == "answer") == "Bonjour le monde"
        assert "".join(t["text"] for t in tokens if t["channel"] == "thought") == "Hmm"
        metrics = next(e["data"] for e in events if e["type"] == "metrics")
        assert metrics["lane"] == TAG and metrics["origin"] == "local"
        assert metrics["tps"] == 40.0 and metrics["tps_source"] == "ollama_eval"
        assert (metrics["load_s"], metrics["eval_s"], metrics["total_s"]) == (0.2, 0.5, 1.0)
        assert metrics["eval_tokens"] == 20 and metrics["ttft_s"] is not None
        assert (metrics["prefill_s"], metrics["prefill_tps"]) == (0.1, 70.0)  # 7 jetons en 0,1 s
        co2 = metrics["co2"]  # présent partout (AD-10), ici non mesurable avec sa raison
        assert co2["method"] == "unmeasurable" and co2["mg"] is None and co2["reason"]
        assert events[-1]["data"] == {"status": "ok", "error": None}
        assert _messages(app, started["conversation_id"]) == [
            ("user", "Salut modèle", None),
            ("assistant", "Bonjour le monde", "Hmm"),
        ]
        # AD-7 : aucun texte saisi dans `runs.params` ni dans `run_started`
        sql = "SELECT params, model, tps_source FROM runs WHERE id = ?"
        row = app.state.store.read(sql, (run_id,))[0]
        assert "Salut" not in row["params"] and row["model"] == TAG
        assert row["tps_source"] == "ollama_eval"
        assert "Salut" not in str(events[0])


async def test_second_message_resumes_the_conversation_with_its_whole_history(tmp_path):
    server = FakeOllama(
        loaded=[TAG], plans=[Plan([part("Une"), final()]), Plan([part("Deux"), final()])]
    )
    async with chat_app(tmp_path, server) as (_, client):
        first = (await _post(client, "Premier ?")).json()
        await _ended(client, first["run_id"])
        again = await _post(client, "Et ensuite ?", conversation_id=first["conversation_id"])
        second = again.json()
        assert second["conversation_id"] == first["conversation_id"]
        await _ended(client, second["run_id"])
        sent = [(m["role"], m["content"]) for m in server.chat_requests[1]["messages"]]
        assert sent == [("user", "Premier ?"), ("assistant", "Une"), ("user", "Et ensuite ?")]
        assert server.chat_requests[1]["options"] == {"temperature": 0.2}
        unknown = await _post(client, "x", conversation_id="inconnue")
        assert unknown.status_code == 404 and unknown.json()["code"] == "not_found"


async def test_unknown_model_cloud_without_agreement_and_blank_message_are_refused(tmp_path):
    server = FakeOllama()
    async with chat_app(
        tmp_path,
        server,
        environ={"OPENAI_API_KEY": "sk-test-0123456789"},
        cloud={"models": {"openai": ["gpt-x"]}},
    ) as (app, client):
        unknown = await _post(client, model="absent:1b")
        assert unknown.status_code == 404 and unknown.json()["code"] == "model_not_found"
        refused = await _post(client, model="openai/gpt-x")
        assert refused.status_code == 403 and refused.json()["code"] == "cloud_not_allowed"
        blank = await _post(client, "   ")
        assert blank.status_code == 422 and blank.json()["code"] == "invalid_request"
        assert (await _post(client, temperature=5)).status_code == 422
        assert server.chat_requests == []  # rien n'est parti vers Ollama
        assert app.state.hub.active_runs() == []  # et aucun run n'a été créé


async def test_a_second_chat_while_one_runs_is_run_busy_with_the_active_run_id(tmp_path):
    release = asyncio.Event()
    server = FakeOllama(loaded=[TAG], plans=[Plan([part("Lent"), final()], hold=release)])
    async with chat_app(tmp_path, server) as (_, client):
        first = (await _post(client)).json()
        busy = await _post(client, "Autre ?")
        assert busy.status_code == 409
        body = busy.json()
        assert body["code"] == "run_busy" and body["detail"]["run_id"] == first["run_id"]
        release.set()
        assert (await _ended(client, first["run_id"]))["status"] == "ok"
        assert (await _post(client, "Maintenant ?")).status_code == 200  # la place est rendue


async def test_cancelling_closes_the_http_stream_and_keeps_the_partial_answer(tmp_path):
    server = FakeOllama(loaded=[TAG], plans=[Plan([part("Début")], end="hang")])
    async with chat_app(tmp_path, server) as (app, client):
        started = (await _post(client)).json()
        for _ in range(100):
            if server.opened:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.15)  # le premier fragment est publié
        cancelled = (await client.post(f"/api/runs/{started['run_id']}/cancel")).json()
        assert cancelled["cancelled"] is True and cancelled["status"] == "cancelled"
        await asyncio.sleep(0.05)
        assert server.closed == 1  # flux HTTP fermé
        assert not app.state.local_slot.busy
        assert _messages(app, started["conversation_id"])[-1] == ("assistant", "Début", None)
        events = await _events(client, started["run_id"])
        assert events[-1]["data"]["status"] == "cancelled"
        # AD-10 : la feuille annulée garde un `co2`, non mesurable et avec sa raison
        co2 = (await client.get(f"/api/runs/{started['run_id']}")).json()["metrics"]["co2"]
        assert co2["method"] == "unmeasurable" and co2["mg"] is None and co2["reason"]


async def test_a_cut_generation_is_retried_once_then_succeeds(tmp_path):
    server = FakeOllama(
        loaded=[TAG], plans=[Plan([part("Par")], end="cut"), Plan([part("Bonjour"), final()])]
    )
    async with chat_app(tmp_path, server) as (app, client):
        started = (await _post(client)).json()
        assert (await _ended(client, started["run_id"]))["status"] == "ok"
        events = await _events(client, started["run_id"])
        retries = [e for e in events if e["type"] == "retry"]
        assert len(retries) == 1 and retries[0]["data"]["lane"] == TAG
        assert retries[0]["data"]["reason"]
        assert len(server.chat_requests) == 2 and server.closed == 2
        assert _messages(app, started["conversation_id"])[-1][1] == "Bonjour"


async def test_a_generation_cut_twice_ends_in_error_interrupted_after_one_retry(tmp_path):
    server = FakeOllama(
        loaded=[TAG], plans=[Plan([part("A")], end="cut"), Plan([part("B")], end="error")]
    )
    async with chat_app(tmp_path, server) as (_, client):
        started = (await _post(client)).json()
        assert (await _ended(client, started["run_id"]))["status"] == "error"
        events = await _events(client, started["run_id"])
        assert _types(events).count("retry") == 1
        error = events[-1]["data"]["error"]
        assert error["code"] == "generation_interrupted"
        assert set(error) == {"code", "message", "action", "detail"}
        assert len(server.chat_requests) == 2


async def test_ollama_stopped_ends_in_ollama_down(tmp_path):
    # Le registre connaît le modèle (liste en cache) ; le client de l'app vise un port fermé.
    async with chat_app(tmp_path, FakeOllama(), real_client=True) as (_, client):
        started = (await _post(client)).json()
        # Sous Windows, une connexion refusée met jusqu'à ~2 s à échouer (sonde `ps` comprise).
        assert (await _ended(client, started["run_id"], timeout=10))["status"] == "error"
        events = await _events(client, started["run_id"])
        assert events[-1]["data"]["error"]["code"] == "ollama_down"
        assert "retry" not in _types(events)


async def test_a_delay_exceeded_ends_in_timeout_with_the_settings_delay(tmp_path):
    server = FakeOllama(loaded=[TAG], plans=[Plan([part("Lent")], end="hang")])
    async with chat_app(tmp_path, server, delays={"lane_timeout_s": 0.3}) as (app, client):
        started = (await _post(client)).json()
        assert (await _ended(client, started["run_id"]))["status"] == "error"
        error = (await _events(client, started["run_id"]))[-1]["data"]["error"]
        assert error["code"] == "timeout" and error["detail"]["timeout_s"] == 0.3
        assert server.closed == 1 and not app.state.local_slot.busy


async def test_ollama_refusal_is_a_closed_code_in_run_ended(tmp_path):
    server = FakeOllama(
        loaded=[TAG], plans=[Plan(end="http_error", status=500, body='{"error":"out of memory"}')]
    )
    async with chat_app(tmp_path, server) as (_, client):
        started = (await _post(client)).json()
        await _ended(client, started["run_id"])
        error = (await _events(client, started["run_id"]))[-1]["data"]["error"]
        assert error["code"] == "ollama_error" and "out of memory" in error["detail"]["technical"]


async def test_the_chat_route_is_a_write_and_obeys_the_local_origin_rule(tmp_path):
    async with chat_app(tmp_path, FakeOllama()) as (_, client):
        response = await client.post(
            "/api/chat/runs",
            json={"model": TAG, "message": "x"},
            headers={"Origin": "http://evil.example"},
        )
        assert response.status_code == 403 and response.json()["code"] == "forbidden_origin"


async def test_the_fake_model_chats_through_the_same_route_in_testing_mode(served):
    _, client = served  # `WAVELOCALAI_TESTING=1` : le `fake` est résoluble par le registre
    started = (await _post(client, "Bonjour fake", model="fake:1b")).json()
    assert (await _ended(client, started["run_id"]))["status"] == "ok"
    events = await _events(client, started["run_id"])
    assert _types(events)[0] == "run_started" and _types(events)[-1] == "run_ended"
    metrics = next(e["data"] for e in events if e["type"] == "metrics")
    assert metrics["lane"] == "fake:1b" and metrics["tps_source"] == "wallclock"
