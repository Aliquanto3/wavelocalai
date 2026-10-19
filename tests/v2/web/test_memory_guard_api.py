"""Garde-fou mémoire de bout en bout (story 4.8) : chat, Arène, question RAG et déchargement.

L'app est la vraie (hub, registre avec son conseiller mémoire, services, flux SSE) ; la mémoire du
poste est simulée et Ollama est un faux (`FakeOllama`, `/api/ps` et `keep_alive: 0` compris).
Aucun vrai déchargement, aucun réseau.
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx

from wavelocalai.hardware.memory import MemoryAdvisor, MemoryReading
from wavelocalai.inference.memory_guard import MemoryGuard
from wavelocalai.models.fake import FakeChatModel, fake_embedders, fake_models
from wavelocalai.models.ollama_api import OllamaHttpSource
from wavelocalai.models.ollama_ps import LoadedModel
from wavelocalai.models.port import ModelRef, TextDelta
from wavelocalai.models.registry import ModelNeed, ModelRegistry
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..fake_ollama import FakeOllama, Plan, final, part
from .conftest import parse_sse, served  # noqa: F401 - fixture
from .test_rag_run_api import CATS, QUESTION, _ask, _ended, _events, _import, _script

BASE = f"http://127.0.0.1:{TEST_PORT}"
GB = 1024**3
# Besoin chiffré (taille × 1,25), puis mémoire requise (× 1,1 + 0,5 de réserve) :
#   big:7b    5,0 Go → 6,25 Go → 7,375 Go requis      mid:2b   1,6 Go → 2,0 Go → 2,7 Go requis
#   tiny:0.5b 0,4 Go → 0,5 Go  → 1,05 Go requis
SIZES = {"big:7b": int(5.0 * GB), "mid:2b": int(1.6 * GB), "tiny:0.5b": int(0.4 * GB)}
FREE_GB = 4.0


def reading(available_gb: float):
    return lambda: MemoryReading(total_gb=16.0, available_gb=available_gb)


@contextlib.asynccontextmanager
async def chat_app(tmp_path, server: FakeOllama, available_gb: float = FREE_GB):
    config = make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"})
    memory = reading(available_gb)
    registry = ModelRegistry(
        config,
        source=OllamaHttpSource(config.ollama.host, transport=server.transport),
        advisor=MemoryAdvisor(memory),
    )
    app = create_app(
        config,
        registry=registry,
        ollama_client=server.client(),
        ollama_transport=server.transport,
        memory_reader=memory,
    )
    async with app.router.lifespan_context(app):
        await registry.refresh()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


def ollama(**fields) -> FakeOllama:
    return FakeOllama(tags=list(SIZES), sizes=dict(SIZES), **fields)


async def _chat(client, model: str, message: str = "Bonjour, une question."):
    return await client.post(
        "/api/chat/runs",
        json={"model": model, "message": message, "temperature": 0.2, "allow_cloud": False},
    )


async def _events_of(client, run_id):
    response = await client.get(f"/api/runs/{run_id}/events")
    return [f["data"] for f in parse_sse(response.text)[0]]


async def _wait_ended(client, run_id, timeout=3.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


# --- Chat ---------------------------------------------------------------------------------------


async def test_a_chat_that_does_not_fit_ends_in_ram_guard_and_keeps_the_question(tmp_path):
    server = ollama(plans=[Plan([part("jamais"), final()])])
    async with chat_app(tmp_path, server) as (app, client):
        response = await _chat(client, "big:7b", "Ma question importante")
        assert response.status_code == 200  # le run existe : la question est dans l'historique
        started = response.json()
        assert (await _wait_ended(client, started["run_id"]))["status"] == "error"

        events = await _events_of(client, started["run_id"])
        assert [e["type"] for e in events if e["type"] in ("token", "model_loading")] == []
        ended = events[-1]["data"]
        error = ended["error"]
        assert ended["status"] == "error" and error["code"] == "ram_guard"
        assert error["message"] == "Mémoire insuffisante : 7,4 Go nécessaires, 4,0 Go libres."
        assert error["detail"]["needed_gb"] == 7.4 and error["detail"]["free_gb"] == 4.0
        assert error["detail"]["suggested_model"] == "mid:2b"  # le plus gros qui tient
        assert set(error["detail"]) == {"technical", "needed_gb", "free_gb", "suggested_model"}
        assert server.chat_requests == []  # le modèle n'a jamais été appelé

        conversation = (await client.get(f"/api/conversations/{started['conversation_id']}")).json()
        assert [m["content"] for m in conversation["messages"] if m["role"] == "user"] == [
            "Ma question importante"
        ]


async def test_a_refused_chat_leaves_a_leaf_without_a_measure_and_says_why(tmp_path):
    server = ollama()
    async with chat_app(tmp_path, server) as (app, client):
        run_id = (await _chat(client, "big:7b")).json()["run_id"]
        await _wait_ended(client, run_id)
        rows = app.state.store.read(
            "SELECT co2_method, co2_reason FROM runs WHERE id = ?", (run_id,)
        )
        assert rows and rows[0]["co2_method"] == "unmeasurable"
        assert "mémoire insuffisante" in rows[0]["co2_reason"]


async def test_a_chat_that_fits_runs_normally_without_reading_ps(tmp_path):
    server = ollama(plans=[Plan([part("Bonjour"), final()])])
    async with chat_app(tmp_path, server) as (app, client):
        run_id = (await _chat(client, "mid:2b")).json()["run_id"]
        assert (await _wait_ended(client, run_id))["status"] == "ok"
        assert len(server.chat_requests) == 1


async def test_a_model_already_loaded_in_ollama_is_not_blocked(tmp_path):
    """`/api/ps` simulé : `big:7b` est chargé, sa place est déjà prise (AC 1)."""
    server = ollama(loaded=["big:7b"], plans=[Plan([part("Déjà là"), final()])])
    async with chat_app(tmp_path, server, available_gb=0.6) as (app, client):
        run_id = (await _chat(client, "big:7b")).json()["run_id"]
        snapshot = await _wait_ended(client, run_id)
        assert snapshot["status"] == "ok"
        assert len(server.chat_requests) == 1


async def test_the_same_model_unloaded_is_blocked_with_the_same_memory(tmp_path):
    server = ollama(loaded=[])
    async with chat_app(tmp_path, server, available_gb=0.6) as (app, client):
        run_id = (await _chat(client, "big:7b")).json()["run_id"]
        await _wait_ended(client, run_id)
        events = await _events_of(client, run_id)
        assert events[-1]["data"]["error"]["code"] == "ram_guard"
        assert events[-1]["data"]["error"]["detail"]["suggested_model"] is None  # rien ne tient


# --- Arène --------------------------------------------------------------------------------------


def _fake(tag: str, *words: str) -> FakeChatModel:
    return FakeChatModel([TextDelta(w) for w in words], ModelRef(tag, "fake", "local", "chat"))


@contextlib.asynccontextmanager
async def guarded_app(tmp_path, guard_needs, available_gb, *fakes: FakeChatModel):
    config = make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"})
    refs = [*fake_models(config).values(), *fake_embedders(config).values(), *fakes]
    registry = ModelRegistry(config, extra_refs={m.ref.tag: m.ref for m in refs})
    app = create_app(config, registry=registry)
    app.state.models.update({m.ref.tag: m for m in fakes})
    ps: list[LoadedModel] = []

    async def loaded():
        return list(ps)

    class Needs:
        def memory_needs(self):
            return list(guard_needs)

    app.state.memory_guard = MemoryGuard(
        Needs(), config.ollama.host, reader=reading(available_gb), loaded=loaded
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


async def test_an_arena_lane_that_does_not_fit_fails_alone_with_its_envelope(tmp_path):
    big, small = _fake("big:7b", "jamais"), _fake("small:1b", "Salut", " toi")
    needs = [ModelNeed("big:7b", "chat", 6.0), ModelNeed("small:1b", "chat", 1.0)]
    async with guarded_app(tmp_path, needs, 3.0, big, small) as (app, client):
        response = await client.post(
            "/api/arena/runs",
            json={
                "models": ["big:7b", "small:1b"],
                "prompt": "Une question.",
                "allow_cloud": False,
            },
        )
        assert response.status_code == 200, response.text
        run_id = response.json()["run_id"]
        assert (await _wait_ended(client, run_id, timeout=5.0))["status"] == "ok"
        events = await _events_of(client, run_id)
        lanes = {
            e["data"]["lane"]: e["data"]
            for e in events
            if e["type"] == "lane_status" and e["data"]["status"] in ("failed", "done")
        }
        assert lanes["small:1b"]["status"] == "done"
        failed = lanes["big:7b"]
        assert failed["status"] == "failed" and failed["error"]["code"] == "ram_guard"
        assert failed["error"]["detail"]["suggested_model"] == "small:1b"
        assert failed["error"]["detail"]["needed_gb"] == 7.1  # 6,0 × 1,1 + 0,5
        tokens = [e["data"]["lane"] for e in events if e["type"] == "token"]
        assert tokens and set(tokens) == {"small:1b"}  # la lane refusée n'a rien généré


async def test_a_local_judge_that_does_not_fit_leaves_the_score_not_evaluated(tmp_path):
    a, b = _fake("small:1b", "Salut"), _fake("mid:2b", "Bonjour")
    judge = _fake("big:7b", "jamais")
    needs = [
        ModelNeed("big:7b", "chat", 6.0),
        ModelNeed("small:1b", "chat", 1.0),
        ModelNeed("mid:2b", "chat", 1.5),
    ]
    async with guarded_app(tmp_path, needs, 3.0, a, b, judge) as (app, client):
        response = await client.post(
            "/api/arena/runs",
            json={
                "models": ["small:1b", "mid:2b"],
                "prompt": "Une question.",
                "allow_cloud": False,
                "judge": "big:7b",
            },
        )
        assert response.status_code == 200, response.text
        run_id = response.json()["run_id"]
        snapshot = await _wait_ended(client, run_id, timeout=5.0)
        events = await _events_of(client, run_id)
    assert snapshot["status"] == "ok"
    assert judge.requests == []  # le juge refusé n'est jamais appelé
    got = {e["data"]["lane"]: e["data"] for e in events if e["type"] == "judge_score"}
    assert set(got) == {"small:1b", "mid:2b"}
    assert all(
        g["score"] is None and g["reason"] == "non évalué : juge indisponible" for g in got.values()
    )
    done = {
        e["data"]["lane"]
        for e in events
        if e["type"] == "lane_status" and e["data"]["status"] == "done"
    }
    assert done == {"small:1b", "mid:2b"}  # la notation refusée ne fait pas échouer les lanes
    kids = [c for c in snapshot["children"] if c["kind"] == "judge"]
    assert kids and all(k["status"] == "error" for k in kids)
    assert all(k["error"]["code"] == "ram_guard" for k in kids if k.get("error"))


# --- Question RAG -------------------------------------------------------------------------------


async def test_a_rag_question_that_does_not_fit_keeps_its_sources_and_ends_in_ram_guard(tmp_path):
    needs = [ModelNeed("fake:1b", "chat", 6.0), ModelNeed("petit:1b", "chat", 0.5)]
    async with guarded_app(tmp_path, needs, 2.5) as (app, client):
        await _import(client, **{"chats.txt": CATS})
        _script(app, "jamais")
        started = (await _ask(client, QUESTION)).json()
        assert (await _ended(client, started["run_id"]))["status"] == "error"
        events = await _events(client, started["run_id"])
        types = [e["type"] for e in events]
        assert "sources" in types and "token" not in types
        error = events[-1]["data"]["error"]
        assert error["code"] == "ram_guard" and error["detail"]["suggested_model"] == "petit:1b"
        conversation = (await client.get(f"/api/conversations/{started['conversation_id']}")).json()
        assert [m["content"] for m in conversation["messages"] if m["role"] == "user"] == [QUESTION]


# --- Déchargement -------------------------------------------------------------------------------


async def test_unload_leaves_the_model_of_a_running_chat_and_frees_the_others(tmp_path):
    hold = asyncio.Event()
    server = ollama(
        loaded=["mid:2b", "tiny:0.5b"],
        plans=[Plan([part("En cours"), final()], hold=hold)],
    )
    async with chat_app(tmp_path, server, available_gb=9.0) as (app, client):
        run_id = (await _chat(client, "mid:2b")).json()["run_id"]
        async with asyncio.timeout(3):
            while "mid:2b" not in app.state.hub.active_models():
                await asyncio.sleep(0.01)

        feed = app.state.system_feed
        with feed.subscribe() as queue:
            response = await client.post("/api/models/unload")
            assert response.status_code == 200, response.text
            report = response.json()
            assert report["unloaded"] == ["tiny:0.5b"]
            assert report["kept"] == [{"tag": "mid:2b", "run_id": run_id}]
            assert report["failed"] == [] and report["free_gb"] == 9.0
            assert server.unloaded == ["tiny:0.5b"] and server.loaded == ["mid:2b"]
            # La mémoire libre se met à jour sur le flux système, sans attendre le tick de 2 s.
            envelope = await asyncio.wait_for(queue.get(), 2)
            assert envelope["type"] == "system_state" and envelope["run_id"] is None
            assert envelope["data"]["memory"]["available_gb"] > 0
        hold.set()
        await _wait_ended(client, run_id)


async def test_unload_with_nothing_loaded_is_a_calm_no_op(tmp_path):
    server = ollama(loaded=[])
    async with chat_app(tmp_path, server) as (app, client):
        response = await client.post("/api/models/unload")
        assert response.json() == {"unloaded": [], "kept": [], "failed": [], "free_gb": 4.0}
        assert server.unloaded == []


async def test_unload_reports_a_model_ollama_refuses_to_release(tmp_path):
    server = ollama(loaded=["tiny:0.5b"], unload_fails=True)
    async with chat_app(tmp_path, server) as (app, client):
        report = (await client.post("/api/models/unload")).json()
        assert report["unloaded"] == [] and report["failed"] == ["tiny:0.5b"]


async def test_unload_says_ollama_is_down_with_the_standard_envelope(served):
    app, client = served  # Ollama pointe sur un port fermé
    response = await client.post("/api/models/unload")
    assert response.status_code == 503
    assert response.json()["code"] == "ollama_down"


# --- Revue : lane précédente encore chargée, question renvoyée ----------------------------------


class _Loading(FakeChatModel):
    """Modèle simulé qui reste chargé après sa réponse (keep_alive d'Ollama) : il entre dans
    `/api/ps` et la mémoire libre du poste baisse d'autant."""

    def __init__(self, tag: str, size_gb: float, ps: list[LoadedModel], *words: str) -> None:
        super().__init__([TextDelta(w) for w in words], ModelRef(tag, "fake", "local", "chat"))
        self._size, self._ps = size_gb, ps

    async def stream(self, request):
        self._ps.append(LoadedModel(self.ref.tag, size_gb=self._size, vram_gb=0.0))
        async for chunk in super().stream(request):
            yield chunk


async def test_an_arena_lane_after_a_big_lane_is_not_refused_while_ollama_can_evict_it(tmp_path):
    """Poste de 7,5 Go libres : la lane `big:7b` (7,1 Go requis) passe et reste chargée (5,0 Go) ;
    la lane suivante `mid:4b` (4,9 Go requis) ne voit que 2,5 Go libres, mais Ollama évincera
    `big:7b`, inactif : elle passe aussi."""
    config = make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"})
    ps: list[LoadedModel] = []
    big = _Loading("big:7b", 5.0, ps, "Grande")
    mid = _Loading("mid:4b", 3.6, ps, "Moyenne")
    refs = [*fake_models(config).values(), *fake_embedders(config).values(), big, mid]
    registry = ModelRegistry(config, extra_refs={m.ref.tag: m.ref for m in refs})
    app = create_app(config, registry=registry)
    app.state.models.update({m.ref.tag: m for m in (big, mid)})
    needs = [ModelNeed("big:7b", "chat", 6.0), ModelNeed("mid:4b", "chat", 4.0)]

    class Needs:
        def memory_needs(self):
            return list(needs)

    async def loaded():
        return list(ps)

    def memory():
        return MemoryReading(total_gb=16.0, available_gb=7.5 - sum(m.size_gb for m in ps))

    app.state.memory_guard = MemoryGuard(Needs(), config.ollama.host, reader=memory, loaded=loaded)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            response = await client.post(
                "/api/arena/runs",
                json={"models": ["big:7b", "mid:4b"], "prompt": "Q ?", "allow_cloud": False},
            )
            assert response.status_code == 200, response.text
            run_id = response.json()["run_id"]
            await _wait_ended(client, run_id, timeout=5.0)
            events = await _events_of(client, run_id)
    ends = {
        e["data"]["lane"]: e["data"]["status"]
        for e in events
        if e["type"] == "lane_status" and e["data"]["status"] in ("failed", "done")
    }
    assert ends == {"big:7b": "done", "mid:4b": "done"}, events


async def test_a_question_resent_after_a_refusal_is_read_once_by_the_model(tmp_path):
    """Refus `ram_guard`, puis la personne prend le modèle proposé et renvoie sa question : le
    modèle ne la lit qu'une fois (l'historique, lui, garde les deux envois)."""
    server = ollama(plans=[Plan([part("Réponse"), final()])])
    async with chat_app(tmp_path, server) as (app, client):
        first = (await _chat(client, "big:7b", "Ma question")).json()
        await _wait_ended(client, first["run_id"])
        again = await client.post(
            "/api/chat/runs",
            json={
                "model": "mid:2b",
                "message": "Ma question",
                "temperature": 0.2,
                "allow_cloud": False,
                "conversation_id": first["conversation_id"],
            },
        )
        assert again.status_code == 200, again.text
        assert (await _wait_ended(client, again.json()["run_id"]))["status"] == "ok"
        sent = server.chat_requests[-1]["messages"]
        assert [(m["role"], m["content"]) for m in sent] == [("user", "Ma question")]
        conversation = (await client.get(f"/api/conversations/{first['conversation_id']}")).json()
        users = [m["content"] for m in conversation["messages"] if m["role"] == "user"]
        assert users == ["Ma question", "Ma question"]
