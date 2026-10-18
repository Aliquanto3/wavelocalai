"""Adaptateur Ollama du port `ChatModel` : flux, débit D3, chargement, annulation, pannes (AD-8).

Un faux serveur Ollama (transport httpx simulé) sous un vrai `ollama.AsyncClient` : aucun réseau.
"""

from __future__ import annotations

import asyncio

import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.models.ollama import OllamaChatModel
from wavelocalai.models.ollama_metrics import ollama_result
from wavelocalai.models.port import (
    ChatMessage,
    ChatModel,
    ChatRequest,
    Done,
    LoadState,
    ModelRef,
    TextDelta,
)

from ..fake_ollama import FakeOllama, Plan, final, part

REF = ModelRef("qwen2.5:1.5b", "ollama", "local", "chat")
REQUEST = ChatRequest([ChatMessage("user", "Bonjour")], temperature=0.3)


def _model(server: FakeOllama) -> OllamaChatModel:
    return OllamaChatModel(REF, server.client())


async def _collect(model, request=REQUEST):
    return [chunk async for chunk in model.stream(request)]


def test_the_adapter_respects_the_port():
    assert isinstance(_model(FakeOllama()), ChatModel)


async def test_nominal_stream_ends_with_one_done_carrying_d3_metrics():
    server = FakeOllama(
        loaded=["qwen2.5:1.5b"],
        plans=[
            Plan(
                [
                    part("", thinking="Je réfléchis"),
                    part("Bon"),
                    part("jour"),
                    final(eval_count=20, eval_s=0.5, load_s=0.2, prompt_eval_count=7, total_s=1.0),
                ]
            )
        ],
    )
    chunks = await _collect(_model(server))
    texts = [c for c in chunks if isinstance(c, TextDelta)]
    assert [(t.text, t.channel) for t in texts] == [
        ("Je réfléchis", "thought"),
        ("Bon", "answer"),
        ("jour", "answer"),
    ]
    assert [type(c) for c in chunks].count(Done) == 1 and isinstance(chunks[-1], Done)
    result = chunks[-1].result
    assert result.tps == 40.0 and result.tps_source == "ollama_eval"  # 20 / 0.5 s (D3)
    assert (result.load_s, result.eval_s, result.total_s) == (0.2, 0.5, 1.0)
    assert (result.input_tokens, result.output_tokens) == (7, 20)
    assert result.ttft_s is not None and result.ttft_s >= 0
    assert result.finish_reason == "stop"
    assert not [c for c in chunks if isinstance(c, LoadState)]  # déjà en mémoire


async def test_request_body_carries_model_history_and_temperature_without_think_by_default():
    server = FakeOllama(loaded=["qwen2.5:1.5b"], plans=[Plan([part("a"), final()])])
    request = ChatRequest(
        [
            ChatMessage("user", "Salut"),
            ChatMessage("assistant", "Oui ?"),
            ChatMessage("user", "Ok"),
        ],
        temperature=0.7,
        max_tokens=64,
    )
    await _collect(_model(server), request)
    body = server.chat_requests[0]
    assert body["model"] == "qwen2.5:1.5b" and body["stream"] is True
    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", "Salut"),
        ("assistant", "Oui ?"),
        ("user", "Ok"),
    ]
    assert body["options"] == {"temperature": 0.7, "num_predict": 64}
    assert "think" not in body  # comportement par défaut d'Ollama inchangé


async def test_loading_is_announced_when_the_model_is_not_in_memory_then_loaded_at_first_token():
    server = FakeOllama(loaded=[], plans=[Plan([part("Bon"), part("jour"), final()])])
    chunks = await _collect(_model(server))
    kinds = [c for c in chunks if isinstance(c, (LoadState, TextDelta))]
    assert kinds[0] == LoadState("loading")
    assert isinstance(kinds[1], LoadState) and kinds[1].phase == "loaded"
    assert kinds[1].duration_s is not None and kinds[1].duration_s >= 0
    assert isinstance(kinds[2], TextDelta)  # `loaded` précède le premier jeton


async def test_loading_is_closed_at_the_end_for_an_empty_answer():
    server = FakeOllama(loaded=[], plans=[Plan([final(load_s=1.5, eval_count=0)])])
    states = [c for c in await _collect(_model(server)) if isinstance(c, LoadState)]
    assert states == [LoadState("loading"), LoadState("loaded", 1.5)]


async def test_no_loading_state_when_ps_cannot_answer():
    server = FakeOllama(ps_fails="http", plans=[Plan([part("a"), final()])])
    chunks = await _collect(_model(server))
    assert not [c for c in chunks if isinstance(c, LoadState)]


async def test_a_refused_connection_on_the_probe_is_ollama_down_without_calling_chat():
    server = FakeOllama(ps_fails="connect", plans=[Plan([part("a"), final()])])
    with pytest.raises(ProviderError) as caught:
        await _collect(_model(server))
    assert caught.value.code == "ollama_down" and server.chat_requests == []


async def test_cancelling_the_task_closes_the_http_stream():
    release = asyncio.Event()
    server = FakeOllama(loaded=["qwen2.5:1.5b"], plans=[Plan([part("début")], end="hang")])
    model = _model(server)
    got: list = []

    async def consume():
        async for chunk in model.stream(REQUEST):
            got.append(chunk)
            release.set()

    task = asyncio.create_task(consume())
    await asyncio.wait_for(release.wait(), 2)
    assert server.opened == 1 and server.closed == 0
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert server.closed == 1  # flux HTTP fermé par le `finally`


async def test_closing_the_generator_early_closes_the_http_stream():
    server = FakeOllama(loaded=["qwen2.5:1.5b"], plans=[Plan([part("a"), part("b"), final()])])
    stream = _model(server).stream(REQUEST)
    first = await anext(stream)
    assert isinstance(first, TextDelta)
    await stream.aclose()
    assert server.closed == 1


@pytest.mark.parametrize(
    "plan",
    [
        Plan([part("Par")], end="cut"),  # flux clos sans `done`, en HTTP 200
        Plan([part("Par")], end="error"),  # connexion coupée en cours de route
    ],
)
async def test_a_stream_cut_before_done_is_generation_interrupted(plan):
    server = FakeOllama(loaded=["qwen2.5:1.5b"], plans=[plan])
    with pytest.raises(ProviderError) as caught:
        await _collect(_model(server))
    assert caught.value.code == "generation_interrupted"
    assert server.closed == 1


async def test_ollama_stopped_is_ollama_down():
    server = FakeOllama(plans=[Plan(end="refuse")])
    with pytest.raises(ProviderError) as caught:
        await _collect(_model(server))
    assert caught.value.code == "ollama_down"


async def test_ollama_refusals_become_provider_errors_with_a_closed_code():
    missing = FakeOllama(
        loaded=["qwen2.5:1.5b"],
        plans=[Plan(end="http_error", status=404, body='{"error":"model not found"}')],
    )
    with pytest.raises(ProviderError) as caught:
        await _collect(_model(missing))
    assert caught.value.code == "model_not_found" and caught.value.detail == {"tag": REF.tag}

    refused = FakeOllama(
        loaded=["qwen2.5:1.5b"],
        plans=[Plan(end="http_error", status=500, body='{"error":"more system memory needed"}')],
    )
    with pytest.raises(ProviderError) as caught:
        await _collect(_model(refused))
    assert caught.value.code == "ollama_error"
    assert "more system memory" in str(caught.value.technical)


async def test_tool_calls_are_mapped_to_the_port():
    call = part("")
    call["message"]["tool_calls"] = [
        {"function": {"name": "meteo", "arguments": {"ville": "Lyon"}}}
    ]
    server = FakeOllama(loaded=["qwen2.5:1.5b"], plans=[Plan([call, final()])])
    tools = [c for c in await _collect(_model(server)) if not isinstance(c, (TextDelta, Done))]
    assert [(t.name, t.arguments) for t in tools] == [("meteo", {"ville": "Lyon"})]


# --- métriques (copie adaptée de `ollama_metrics`, v1) -----------------------------------------


def test_tps_is_generation_only_and_ignores_prefill_and_load():
    chunk = final(eval_count=100, eval_s=2.0, load_s=5.0, prompt_eval_s=3.0, total_s=10.0)
    result = ollama_result(chunk, wall_s=10.5)
    assert result.tps == 50.0 and result.tps_source == "ollama_eval"
    assert result.total_s == 10.0 and result.load_s == 5.0


def test_missing_eval_duration_falls_back_to_wallclock_and_says_so():
    result = ollama_result(final(eval_count=30, eval_s=None, total_s=None), wall_s=3.0)
    assert result.tps == 10.0 and result.tps_source == "wallclock"
    assert result.eval_s is None and result.total_s == 3.0


def test_zero_eval_duration_never_divides_by_zero():
    chunk = final(eval_count=10, eval_s=0.0)
    assert ollama_result(chunk, wall_s=0.0).tps == 0.0
    assert ollama_result(chunk, wall_s=2.0).tps_source == "wallclock"


def test_a_real_eval_count_of_zero_wins_over_the_estimate_and_missing_counters_are_none():
    assert ollama_result(final(eval_count=0), 1.0, fallback_output_tokens=9).output_tokens == 0
    bare = ollama_result({"done": True}, 1.0, fallback_output_tokens=9)
    assert bare.output_tokens == 9 and bare.input_tokens is None and bare.load_s is None
