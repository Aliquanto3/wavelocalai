"""Stratégies HyDE et Self-RAG, nombre d'extraits et citations vérifiées de `POST /api/rag/runs`
(story 4.6), de bout en bout.

Comme `test_rag_run_api.py` : l'app est la vraie (hub, store, index, flux SSE), seuls l'embedding et
le modèle de réponse sont les `fake` de `Settings.testing`. Le `fake` rend ici un script **par
appel** (`FakeChatModel.scripts`) : réponse hypothétique, notation, reformulation, puis réponse.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.models.fake import FAKE_EMBED_REF, FAKE_REF, Sleep
from wavelocalai.models.port import TextDelta

from .conftest import served  # noqa: F401 - fixture
from .test_rag_run_api import (
    CARS,
    CATS,
    QUESTION,
    _ask,
    _ended,
    _events,
    _import,
    _types,
    rag_app,
)

HYPOTHESIS = "La voiture électrique recharge sa batterie sur une borne rapide."
REWRITTEN = "La voiture électrique recharge sa batterie sur une borne rapide"


def _calls(app, *scripts):
    """Un script par appel du modèle, dans l'ordre : du texte, ou une erreur à lever."""
    model = app.state.models[FAKE_REF.tag]
    model.scripts = [
        [TextDelta(s) if isinstance(s, str) else s for s in script] for script in scripts
    ]
    model.opened = 0
    return model


def _steps(events):
    return [e["data"] for e in events if e["type"] == "retrieval_step"]


def _sources(events):
    return next(e for e in events if e["type"] == "sources")["data"]


def _embedded(app):
    return app.state.embedders[FAKE_EMBED_REF.tag].texts


async def _run(client, **body):
    started = (await _ask(client, **body)).json()
    snapshot = await _ended(client, started["run_id"])
    return started, snapshot, await _events(client, started["run_id"])


# --- HyDE ------------------------------------------------------------------------------------


async def test_hyde_writes_a_hypothetical_answer_that_then_serves_the_search(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    model = _calls(app, [HYPOTHESIS], ["Réponse [1]."])
    _, snapshot, events = await _run(client, strategy="hyde")

    assert snapshot["status"] == "ok" and snapshot["params"]["strategy"] == "hyde"
    steps = _steps(events)
    assert [(s["strategy"], s["step"]) for s in steps] == [
        ("hyde", "hypothesis"), ("hyde", "embedding"), ("hyde", "search"),
    ]  # fmt: skip
    assert all(isinstance(s["duration_s"], float) and "fallback" not in s for s in steps)
    assert _embedded(app)[-1] == [HYPOTHESIS]  # l'hypothèse est vectorisée, pas la question
    sources = _sources(events)
    assert sources["strategy"] == "hyde"
    assert sources["sources"][0]["document"] == "voitures.txt"  # la question seule aurait dit chats
    assert sources["sources"][0]["passage"] is None or sources["sources"][0]["text"] == CARS

    # l'appel de l'hypothèse est silencieux : seule la réponse est dans le flux, sans `metrics` en plus
    types = _types(events)
    assert types[1:6] == ["retrieval_step"] * 3 + ["sources", "token"]
    assert "".join(e["data"]["text"] for e in events if e["type"] == "token") == "Réponse [1]."
    assert types.count("metrics") == 1
    hypothesis_request, answer_request = model.requests
    assert hypothesis_request.messages[1].content == f"Question : {QUESTION}"
    assert "Extraits :" in answer_request.messages[1].content
    assert answer_request.messages[1].content.endswith(
        f"Question : {QUESTION}"
    )  # la vraie question

    # la génération de l'hypothèse est une feuille, avec son `co2`
    leaves = snapshot["children"]
    assert sorted(c["kind"] for c in leaves) == ["embedding", "generation", "generation"]
    assert all(c["status"] == "ok" and c["metrics"]["co2"] is not None for c in leaves)
    carbon = (await client.get("/api/carbon/session")).json()
    assert carbon["by_module"]["rag"]["runs"] == 3


async def test_hyde_falls_back_to_the_question_when_the_hypothesis_fails_or_is_empty(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    _calls(app, [ProviderError("ollama_error")], ["Réponse."])
    _, snapshot, events = await _run(client, strategy="hyde")
    assert snapshot["status"] == "ok"
    hypothesis = _steps(events)[0]
    assert hypothesis["step"] == "hypothesis" and hypothesis["fallback"] == "question"
    assert _embedded(app)[-1] == [QUESTION]
    assert _sources(events)["sources"][0]["document"] == "chats.txt"
    statuses = sorted(c["status"] for c in snapshot["children"] if c["kind"] == "generation")
    assert statuses == ["error", "ok"]  # l'échec reste visible sur sa feuille

    _calls(app, ["   "], ["Réponse."])
    _, _, events = await _run(client, strategy="hyde")
    assert _steps(events)[0]["fallback"] == "question"
    assert _embedded(app)[-1] == [QUESTION]


# --- Self-RAG --------------------------------------------------------------------------------


async def test_self_rag_keeps_the_relevant_excerpts_and_answers_without_reformulating(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    model = _calls(app, ["1 : oui\n2 : non"], ["Il dort sur le canapé [1]."])
    _, snapshot, events = await _run(client, strategy="self_rag")

    assert snapshot["status"] == "ok" and snapshot["params"]["self_rag_max_iterations"] == 2
    steps = _steps(events)
    assert [s["step"] for s in steps] == ["embedding", "search", "grade"]
    assert all(s["strategy"] == "self_rag" and s["round"] == 0 for s in steps)
    grade = steps[2]
    assert (grade["checked"], grade["relevant"]) == (2, 1) and "fallback" not in grade
    sources = _sources(events)
    assert sources["strategy"] == "self_rag"
    assert [s["document"] for s in sources["sources"]] == ["chats.txt"]  # seul le pertinent reste
    assert [s["n"] for s in sources["sources"]] == [1]
    assert model.opened == 2  # la notation, puis la réponse : aucune reformulation
    grading = model.requests[0].messages[1].content
    assert "[1]\n" + CATS in grading and "[2]\n" + CARS in grading
    assert grading.endswith(f"Question : {QUESTION}")


async def test_self_rag_reformulates_the_question_while_no_excerpt_is_relevant(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    model = _calls(
        app,
        ["1 : non\n2 : non"],  # notation du premier tour : rien de pertinent
        [f"« {REWRITTEN} »\nExplication inutile."],  # reformulation
        ["1 : oui\n2 : non"],  # notation du second tour
        ["La borne rapide [1]."],
    )
    _, snapshot, events = await _run(client, strategy="self_rag")

    assert snapshot["status"] == "ok"
    steps = _steps(events)
    assert [(s["step"], s["round"]) for s in steps] == [
        ("embedding", 0), ("search", 0), ("grade", 0), ("rewrite", 0),
        ("embedding", 1), ("search", 1), ("grade", 1),
    ]  # fmt: skip
    assert steps[2]["relevant"] == 0 and "fallback" not in steps[3]
    assert _embedded(app)[-2:] == [[QUESTION], [REWRITTEN]]  # la reformulation est cherchée
    sources = _sources(events)["sources"]
    assert [s["document"] for s in sources] == ["voitures.txt"]
    assert sources[0]["passage"] is None or isinstance(sources[0]["passage"], dict)
    rewrite = model.requests[1].messages[1].content
    assert f"Question d'origine : {QUESTION}" in rewrite
    # la réponse part sur la question de l'utilisateur, pas sur la reformulation
    assert model.requests[3].messages[1].content.endswith(f"Question : {QUESTION}")
    # deux recherches : deux feuilles `embedding` ; quatre appels de modèle : quatre `generation`
    kinds = sorted(c["kind"] for c in snapshot["children"])
    assert kinds == ["embedding"] * 2 + ["generation"] * 4
    assert all(c["metrics"]["co2"] is not None for c in snapshot["children"])


async def test_self_rag_stops_at_the_bound_with_the_best_excerpts_found(tmp_path):
    async with rag_app(tmp_path, rag={"self_rag_max_iterations": 1}) as (app, client):
        await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
        model = _calls(
            app,
            ["1 : non\n2 : non"],
            ["autre formulation du chat"],
            ["1 : non\n2 : non"],
            ["Réponse."],
        )
        started, snapshot, events = await _run(client, strategy="self_rag")

        assert snapshot["status"] == "ok" and snapshot["params"]["self_rag_max_iterations"] == 1
        steps = _steps(events)
        assert [s["step"] for s in steps].count("rewrite") == 1  # jamais au-delà de la borne
        assert [s["step"] for s in steps].count("grade") == 2
        assert steps[-1]["step"] == "grade" and steps[-1]["relevant"] == 0
        sources = _sources(events)["sources"]
        # les meilleurs extraits vus, un par extrait malgré deux recherches, du plus proche
        assert sorted(s["document"] for s in sources) == ["chats.txt", "voitures.txt"]
        scores = [s["raw_score"] for s in sources]
        assert scores == sorted(scores, reverse=True)
        assert model.opened == 4
        assert "token" in _types(events) and events[-1]["data"]["status"] == "ok"


async def test_self_rag_keeps_every_excerpt_when_the_grade_is_unreadable_or_fails(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    model = _calls(app, ["Je ne sais pas."], ["Réponse."])
    _, snapshot, events = await _run(client, strategy="self_rag")
    grade = _steps(events)[2]
    assert grade["step"] == "grade" and grade["fallback"] == "all"
    assert (grade["checked"], grade["relevant"]) == (2, 2)
    assert len(_sources(events)["sources"]) == 2 and model.opened == 2

    model = _calls(app, [ProviderError("ollama_error")], ["Réponse."])
    _, snapshot, events = await _run(client, strategy="self_rag")
    assert snapshot["status"] == "ok" and _steps(events)[2]["fallback"] == "all"
    assert sorted(c["status"] for c in snapshot["children"] if c["kind"] == "generation") == [
        "error", "ok",
    ]  # fmt: skip


async def test_self_rag_stops_when_the_reformulation_is_empty_or_unchanged(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    model = _calls(app, ["1 : non\n2 : non"], ["   "], ["Réponse."])
    _, snapshot, events = await _run(client, strategy="self_rag")
    steps = _steps(events)
    assert snapshot["status"] == "ok" and steps[-1]["step"] == "rewrite"
    assert steps[-1]["fallback"] == "stop"
    assert model.opened == 3  # notation, reformulation vide, réponse : pas de second tour
    assert len(_sources(events)["sources"]) == 2  # les meilleurs extraits trouvés

    model = _calls(app, ["1 : non\n2 : non"], [QUESTION], ["Réponse."])
    _, _, events = await _run(client, strategy="self_rag")
    assert _steps(events)[-1]["fallback"] == "stop" and model.opened == 3


# --- Nombre d'extraits -----------------------------------------------------------------------


async def test_the_number_of_excerpts_acts_on_the_next_run(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    _, snapshot, events = await _run(client, top_k=1)
    assert snapshot["params"]["top_k"] == 1 and len(_sources(events)["sources"]) == 1
    _, snapshot, events = await _run(client, top_k=2)
    assert snapshot["params"]["top_k"] == 2 and len(_sources(events)["sources"]) == 2
    _, snapshot, _ = await _run(client)  # sans `top_k` : le défaut du serveur
    assert snapshot["params"]["top_k"] == app.state.settings.rag.top_k == 4


@pytest.mark.parametrize("top_k", [0, 21, -1])
async def test_a_number_of_excerpts_out_of_range_is_refused_before_any_run(served, top_k):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    before = app.state.store.read("SELECT count(*) AS n FROM runs WHERE kind = 'rag'")[0]["n"]
    response = await _ask(client, top_k=top_k)
    assert response.status_code == 422 and response.json()["code"] == "invalid_request"
    after = app.state.store.read("SELECT count(*) AS n FROM runs WHERE kind = 'rag'")[0]["n"]
    assert after == before


async def test_the_document_list_gives_the_search_defaults(served):
    _, client = served
    body = (await client.get("/api/rag/documents")).json()
    assert body["search"] == {"top_k": 4, "max_top_k": 20}


# --- Citations -------------------------------------------------------------------------------


async def test_the_server_verifies_the_markers_and_publishes_citations_after_the_metrics(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    _calls(app, ["Il dort sur le canapé [1] et ronronne [2]. Inventé [9] et [0]. Encore [1]."])
    started, _, events = await _run(client)
    types = _types(events)
    assert types[-3:] == ["metrics", "citations", "run_ended"]
    citations = next(e for e in events if e["type"] == "citations")["data"]
    assert citations == {"citations": [{"marker": 1, "n": 1}, {"marker": 2, "n": 2}]}
    # persistée comme les autres événements : un rejeu depuis la base la rend
    row = app.state.store.read(
        "SELECT data FROM run_events WHERE run_id = ? AND type = 'citations'", (started["run_id"],)
    )
    assert [json.loads(r["data"]) for r in row] == [citations]
    # la réponse reste telle que le modèle l'a écrite, marqueurs inventés compris
    answer = app.state.store.read(
        "SELECT content FROM messages WHERE conversation_id = ? AND role = 'assistant'",
        (started["conversation_id"],),
    )
    assert "[9]" in answer[0]["content"]


@pytest.mark.parametrize(
    "answer",
    [
        "Une réponse sans aucun marqueur.",
        "Un marqueur inventé [7], un autre [0], un dernier [12].",
        "Pas un marqueur : [a] et [1, 2] et (1).",
    ],
)
async def test_without_a_verified_marker_no_citations_event_is_published(served, answer):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    _calls(app, [answer])
    _, snapshot, events = await _run(client)
    assert snapshot["status"] == "ok" and "citations" not in _types(events)


async def test_the_markers_are_checked_against_the_sources_of_the_strategy(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    # Self-RAG ne garde qu'une source : [2] ne désigne plus rien, [1] oui
    _calls(app, ["1 : oui\n2 : non"], ["Sur le canapé [1] ; la voiture [2]."])
    _, _, events = await _run(client, strategy="self_rag")
    assert [e["data"] for e in events if e["type"] == "citations"] == [
        {"citations": [{"marker": 1, "n": 1}]}
    ]


async def test_a_cancelled_answer_publishes_no_citations(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    app.state.models[FAKE_REF.tag].script = [TextDelta("Il dort [1]"), Sleep(10)]
    started = (await _ask(client)).json()
    async with asyncio.timeout(3):
        while not any(
            e["type"] == "token" for e in await app.state.hub.events_after(started["run_id"])
        ):
            await asyncio.sleep(0.02)
    await client.post(f"/api/runs/{started['run_id']}/cancel")
    assert (await _ended(client, started["run_id"]))["status"] == "cancelled"
    assert "citations" not in _types(await _events(client, started["run_id"]))


# --- Annulation et erreurs -------------------------------------------------------------------


@pytest.mark.parametrize("strategy", ["hyde", "self_rag"])
async def test_cancelling_during_a_strategy_call_closes_every_leaf_with_a_co2(served, strategy):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    model = _calls(app, [TextDelta("Début"), Sleep(10)])
    started = (await _ask(client, strategy=strategy)).json()
    async with asyncio.timeout(3):
        while model.opened == 0:
            await asyncio.sleep(0.02)
    cancelled = await client.post(f"/api/runs/{started['run_id']}/cancel")
    assert cancelled.json()["cancelled"] is True
    snapshot = await _ended(client, started["run_id"])
    assert snapshot["status"] == "cancelled"
    types = _types(await _events(client, started["run_id"]))
    assert "sources" not in types and "token" not in types and "citations" not in types
    leaves = snapshot["children"]
    assert [c["status"] for c in leaves if c["kind"] == "generation"] == ["cancelled"] * 2
    # HyDE appelle le modèle avant toute recherche ; Self-RAG a déjà vectorisé la question
    embedding = next(c for c in leaves if c["kind"] == "embedding")
    assert embedding["status"] == ("cancelled" if strategy == "hyde" else "ok")
    assert all(c["metrics"]["co2"] is not None for c in snapshot["children"])
    async with asyncio.timeout(3):
        while model.closed < model.opened:  # le flux de l'adaptateur est fermé
            await asyncio.sleep(0.02)


async def test_an_embedding_failure_during_a_reformulation_ends_the_run_in_error(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS, "voitures.txt": CARS})
    embedder = app.state.embedders[FAKE_EMBED_REF.tag]
    embedder.script, embedder.calls = [None, ProviderError("ollama_down")], 0
    _calls(app, ["1 : non\n2 : non"], [REWRITTEN])
    embedder.calls = 0
    _, snapshot, events = await _run(client, strategy="self_rag")
    assert snapshot["status"] == "error" and snapshot["error"]["code"] == "ollama_down"
    types = _types(events)
    assert "sources" not in types and "token" not in types
    generation = [c for c in snapshot["children"] if c["kind"] == "generation"]
    assert generation and all(c["metrics"]["co2"] is not None for c in generation)
    # la réponse n'a jamais été lancée : sa feuille le dit
    assert any(c["metrics"]["co2"]["reason"].startswith("réponse non lancée") for c in generation)


async def test_an_unknown_strategy_is_still_refused(served):
    app, client = served
    await _import(client, **{"chats.txt": CATS})
    response = await _ask(client, strategy="inconnue")
    assert response.status_code == 422 and response.json()["code"] == "invalid_request"
