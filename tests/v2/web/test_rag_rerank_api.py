"""Reclassement des extraits par un reranker local, s'il est là (story 4.7), de bout en bout.

Comme `test_rag_strategies_api.py` : l'app est la vraie, seuls l'embedding, le modèle de réponse et
le reranker sont factices (`Settings.testing`, `POST /api/test/reranker`). Aucun modèle de reranker
n'est présent ni téléchargé : sans l'extra `rerank` (la CI) ou sans le cache, il est indisponible.
"""

from __future__ import annotations

import asyncio
import socket

from wavelocalai.models.fake import FAKE_REF
from wavelocalai.rag import rerank

from .conftest import served  # noqa: F401 - fixture
from .test_rag_run_api import (
    CARS,
    CATS,
    QUESTION,
    SOURCE_KEYS,
    _ask,
    _ended,
    _events,
    _import,
    _script,
    _types,
)
from .test_rag_strategies_api import HYPOTHESIS, _calls, _run, _sources, _steps

DOCS = {"chats.txt": CATS, "voitures.txt": CARS}


async def _rerank(client, mode="lexical", **extra):
    response = await client.post("/api/test/reranker", json={"mode": mode, **extra})
    assert response.status_code == 200, response.text
    return response.json()


async def test_without_a_reranker_nothing_changes_and_the_settings_say_why(served):
    app, client = served
    await _import(client, **DOCS)
    _, snapshot, events = await _run(client)
    assert snapshot["status"] == "ok"
    assert [s["step"] for s in _steps(events)] == ["embedding", "search"]
    assert all("reranking" not in s for s in _steps(events))
    sources = _sources(events)["sources"]
    assert all(set(s) == SOURCE_KEYS for s in sources)  # aucun `rerank_score`
    reranker = (await client.get("/api/rag/settings")).json()["reranker"]
    assert reranker["available"] is False and reranker["reason"]
    assert reranker["model"] == app.state.settings.rag.reranker_model


async def test_a_present_reranker_reclassifies_the_candidates_of_the_question(served):
    app, client = served
    await _import(client, **DOCS)
    await _rerank(client, "reverse")
    _script(app, "Réponse [1].")
    settings = (await client.get("/api/rag/settings")).json()["reranker"]
    assert settings["available"] is True and settings["reason"] is None

    _, snapshot, events = await _run(client, top_k=1)

    assert snapshot["status"] == "ok"
    steps = _steps(events)
    assert [s["step"] for s in steps] == ["embedding", "search", "rerank"]
    search, ranked = steps[1], steps[2]
    assert search["reranking"] is True  # le front sait qu'un reclassement suit
    assert ranked["candidates"] == 2 and ranked["kept"] == 1
    assert isinstance(ranked["duration_s"], float) and "fallback" not in ranked
    # sans reranker, la plus proche est `chats.txt` ; le reranker renverse l'ordre des vecteurs
    sources = _sources(events)["sources"]
    assert [s["document"] for s in sources] == ["voitures.txt"]
    assert sources[0]["rerank_score"] == 1.0 and sources[0]["rank"] == sources[0]["n"] == 1
    assert set(sources[0]) == SOURCE_KEYS | {"rerank_score"}
    # l'étape `rerank` précède `sources`, qui précède la réponse
    types = _types(events)
    assert types.index("sources") < types.index("token")
    assert types[1:5] == ["retrieval_step"] * 3 + ["sources"]


async def test_the_pool_is_wider_than_top_k_and_scored_against_the_question(served):
    app, client = served
    docs = {f"doc{i}.txt": f"Le chat numéro {i} dort sur le canapé du salon." for i in range(8)}
    await _import(client, **docs)
    await _rerank(client, "lexical")
    _, _, events = await _run(client, top_k=2)
    ranked = next(s for s in _steps(events) if s["step"] == "rerank")
    assert ranked["candidates"] == 6 and ranked["kept"] == 2  # 3 fois top_k candidats
    assert len(_sources(events)["sources"]) == 2
    calls = (await client.get("/api/test/reranker")).json()["calls"]
    assert calls == [{"question": QUESTION, "texts": 6}]


async def test_hyde_and_self_rag_score_against_the_question_not_the_rewritten_text(served):
    app, client = served
    await _import(client, **DOCS)
    await _rerank(client, "lexical")

    _calls(app, [HYPOTHESIS], ["Réponse."])
    _, _, events = await _run(client, strategy="hyde")
    assert [s["step"] for s in _steps(events)] == ["hypothesis", "embedding", "search", "rerank"]
    calls = (await client.get("/api/test/reranker")).json()["calls"]
    assert calls[-1]["question"] == QUESTION  # pas l'hypothèse

    # Self-RAG : tout est jugé non pertinent au premier tour, la reformulation en refait un
    _calls(app, ["1 : non\n2 : non"], ["Où dort le chat"], ["1 : oui\n2 : non"], ["Réponse."])
    _, _, events = await _run(client, strategy="self_rag")
    names = [(s["step"], s.get("round")) for s in _steps(events)]
    assert names == [
        ("embedding", 0), ("search", 0), ("rerank", 0), ("grade", 0), ("rewrite", 0),
        ("embedding", 1), ("search", 1), ("rerank", 1), ("grade", 1),
    ]  # fmt: skip
    calls = (await client.get("/api/test/reranker")).json()["calls"]
    assert [c["question"] for c in calls[-2:]] == [QUESTION, QUESTION]  # jamais la reformulation
    sources = _sources(events)["sources"]
    assert all("rerank_score" in s for s in sources)


async def test_a_reranker_that_fails_while_scoring_keeps_the_vector_order(served):
    app, client = served
    await _import(client, **DOCS)

    class Boom:
        def score(self, query, texts):
            raise RuntimeError("onnx en panne")

    app.state.reranker.preset(Boom())
    _, snapshot, events = await _run(client, top_k=1)
    assert snapshot["status"] == "ok"
    ranked = next(s for s in _steps(events) if s["step"] == "rerank")
    assert ranked["fallback"] == "unavailable" and ranked["kept"] == 1
    sources = _sources(events)["sources"]
    assert [s["document"] for s in sources] == ["chats.txt"]  # l'ordre des vecteurs
    assert "rerank_score" not in sources[0]


async def test_a_model_that_cannot_be_loaded_is_remembered_and_never_downloaded(
    served, monkeypatch
):
    app, client = served
    await _import(client, **DOCS)
    service = app.state.reranker
    loads = []

    def loader(model, cache, env_file):
        loads.append((model, cache))
        raise rerank.RerankerUnavailableError(f"le modèle {model} n'a pas pu être chargé")

    monkeypatch.setattr(rerank, "_extra_installed", lambda: True)
    monkeypatch.setattr(rerank, "_model_in_cache", lambda model, cache: True)
    monkeypatch.setattr(service, "_loader", loader)
    assert service.status().available  # le dossier est là : le chargement tranche

    def no_network(*args, **kwargs):  # aucun téléchargement : la socket serait ouverte ici
        raise AssertionError("accès réseau pendant le reclassement")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    _, first, events = await _run(client, top_k=1)
    assert first["status"] == "ok"
    ranked = next(s for s in _steps(events) if s["step"] == "rerank")
    assert ranked["fallback"] == "unavailable"
    assert [s["document"] for s in _sources(events)["sources"]] == ["chats.txt"]

    reranker = (await client.get("/api/rag/settings")).json()["reranker"]
    assert reranker["available"] is False and "n'a pas pu être chargé" in reranker["reason"]

    _, _, events = await _run(client, top_k=1)  # pas de seconde tentative de chargement
    assert [s["step"] for s in _steps(events)] == ["embedding", "search"]
    assert len(loads) == 1 and loads[0][0] == app.state.settings.rag.reranker_model
    assert loads[0][1] == rerank.cache_dir(app.state.settings.data_dir)


async def test_cancelling_during_the_reranking_ends_the_run_without_sources(served):
    app, client = served
    await _import(client, **DOCS)
    await _rerank(client, "lexical", delay_s=1.0)
    _calls(app, ["Réponse."])
    started = (await _ask(client, top_k=1)).json()
    reranker = app.state.reranker.loaded
    async with asyncio.timeout(3):
        while not reranker.calls:  # le calcul a commencé
            await asyncio.sleep(0.02)
    cancelled = await client.post(f"/api/runs/{started['run_id']}/cancel")
    assert cancelled.json()["cancelled"] is True
    snapshot = await _ended(client, started["run_id"])
    assert snapshot["status"] == "cancelled"
    types = _types(await _events(client, started["run_id"]))
    assert "sources" not in types and "token" not in types
    assert all(c["metrics"]["co2"] is not None for c in snapshot["children"])
    assert app.state.models[FAKE_REF.tag].opened == 0  # la réponse n'a jamais été lancée


async def test_a_single_candidate_is_not_reranked(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    await _rerank(client, "reverse")
    _, _, events = await _run(client)
    assert [s["step"] for s in _steps(events)] == ["embedding", "search"]
    assert "reranking" not in _steps(events)[1]
    assert (await client.get("/api/test/reranker")).json()["calls"] == []


async def test_the_test_route_refuses_an_unknown_mode(served):
    _, client = served
    response = await client.post("/api/test/reranker", json={"mode": "magic"})
    assert response.status_code == 422
    done = await _rerank(client, "absent", reason="cache vide")
    assert done == {"available": False}
    reranker = (await client.get("/api/rag/settings")).json()["reranker"]
    assert reranker["reason"] == "cache vide"
