"""Adaptateurs cloud (OpenAI, Groq, Anthropic, Mistral) sous les vrais SDK, faux transports (AD-8).

Aucun appel réseau : chaque SDK reçoit un client HTTP simulé (`tests/v2/fake_cloud.py`).
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from wavelocalai.errors import ProviderError, build_envelope
from wavelocalai.models.anthropic import AnthropicChatModel
from wavelocalai.models.mistral import MistralChatModel
from wavelocalai.models.openai_compat import OpenAICompatChatModel
from wavelocalai.models.port import ChatMessage, ChatRequest, Done, ModelRef, TextDelta

from ..fake_cloud import (
    FAKE_KEYS,
    MODELS,
    FakeCloud,
    Plan,
    anthropic_stream,
    chat_stream,
    mistral_stream,
    stream_for,
)

REQUEST = ChatRequest(
    [ChatMessage("system", "Sois bref."), ChatMessage("user", "Bonjour ?")], temperature=0.3
)
ADAPTERS = {
    "openai": OpenAICompatChatModel,
    "groq": OpenAICompatChatModel,
    "anthropic": AnthropicChatModel,
    "mistral": MistralChatModel,
}
NAMES = {"openai": "OpenAI", "groq": "Groq", "anthropic": "Anthropic", "mistral": "Mistral"}


def build(provider: str, tag: str, fake: FakeCloud, key: str | None = "default"):
    ref = ModelRef(tag, provider, "cloud", "chat")
    api_key = FAKE_KEYS[provider] if key == "default" else key
    return ADAPTERS[provider](ref, api_key, http_client=fake.client)


async def collect(model, request=REQUEST):
    return [chunk async for chunk in model.stream(request)]


@pytest.mark.parametrize(("provider", "tag", "model_id"), MODELS)
async def test_nominal_stream_is_text_deltas_then_one_wallclock_done(provider, tag, model_id):
    fake = FakeCloud(provider, [Plan(stream_for(provider, ["Bon", "jour"]))])
    chunks = await collect(build(provider, tag, fake))
    assert [c.text for c in chunks if isinstance(c, TextDelta)] == ["Bon", "jour"]
    assert all(c.channel == "answer" for c in chunks if isinstance(c, TextDelta))
    done = [c for c in chunks if isinstance(c, Done)]
    assert len(done) == 1 and chunks[-1] is done[0]  # un seul, en dernier
    result = done[0].result
    assert result.tps_source == "wallclock"
    assert result.input_tokens is not None and result.output_tokens is not None
    assert result.finish_reason == "stop"
    assert result.load_s is None and result.total_s is not None
    assert fake.bodies[0]["model"] == model_id  # sans le préfixe du fournisseur
    assert fake.bodies[0]["stream"] is True
    assert fake.clients[0].is_closed  # le client HTTP est fermé à la fin


async def test_openai_request_body_headers_and_usage():
    fake = FakeCloud("openai", [Plan(chat_stream(["a"], usage=(11, 5)))])
    chunks = await collect(build("openai", "openai/gpt-6-luna", fake))
    request, body = fake.requests[0], fake.bodies[0]
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {FAKE_KEYS['openai']}"
    assert body["messages"] == [
        {"role": "system", "content": "Sois bref."},
        {"role": "user", "content": "Bonjour ?"},
    ]
    assert body["stream_options"] == {"include_usage": True}
    assert "temperature" not in body  # gpt-6 : modèle de raisonnement, pas d'échantillonnage
    result = chunks[-1].result
    assert (result.input_tokens, result.output_tokens) == (11, 5)


async def test_openai_non_reasoning_model_gets_the_temperature():
    fake = FakeCloud("openai", [Plan(chat_stream(["a"]))])
    await collect(build("openai", "openai/gpt-4o-mini", fake))
    assert fake.bodies[0]["temperature"] == 0.3


async def test_groq_uses_its_base_url_and_reads_the_reasoning_channel():
    fake = FakeCloud("groq", [Plan(chat_stream(["Oui"], thinking="Je réfléchis"))])
    chunks = await collect(build("groq", "groq/openai/gpt-oss-20b", fake))
    request = fake.requests[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {FAKE_KEYS['groq']}"
    deltas = [(c.channel, c.text) for c in chunks if isinstance(c, TextDelta)]
    assert deltas == [("thought", "Je réfléchis"), ("answer", "Oui")]
    assert fake.bodies[0]["temperature"] == 0.3


async def test_anthropic_request_system_apart_no_sampling_and_usage():
    fake = FakeCloud("anthropic", [Plan(anthropic_stream(["Sa", "lut"], stop="max_tokens"))])
    chunks = await collect(build("anthropic", "anthropic/claude-haiku-5-5", fake))
    request, body = fake.requests[0], fake.bodies[0]
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == FAKE_KEYS["anthropic"]
    assert body["system"] == "Sois bref."
    assert body["messages"] == [{"role": "user", "content": "Bonjour ?"}]
    assert "temperature" not in body and body["max_tokens"] > 0
    result = chunks[-1].result
    assert (result.input_tokens, result.output_tokens) == (12, 7)
    assert result.finish_reason == "length"


async def test_mistral_reads_text_and_thinking_blocks_and_usage():
    blocks = [
        [{"type": "thinking", "thinking": [{"type": "text", "text": "Hmm"}]}],
        [{"type": "text", "text": "Voilà"}],
    ]
    fake = FakeCloud("mistral", [Plan(mistral_stream(blocks, usage=(9, 4)))])
    chunks = await collect(build("mistral", "mistral/mistral-small-latest", fake))
    request = fake.requests[0]
    assert str(request.url).startswith("https://api.mistral.ai/v1/chat/completions")
    assert request.headers["authorization"] == f"Bearer {FAKE_KEYS['mistral']}"
    deltas = [(c.channel, c.text) for c in chunks if isinstance(c, TextDelta)]
    assert deltas == [("thought", "Hmm"), ("answer", "Voilà")]
    assert (chunks[-1].result.input_tokens, chunks[-1].result.output_tokens) == (9, 4)
    assert fake.bodies[0]["temperature"] == 0.3


async def test_usage_missing_estimates_tokens_from_the_text():
    fake = FakeCloud("openai", [Plan(chat_stream(["x" * 40], usage=None))])
    chunks = await collect(build("openai", "openai/gpt-6-luna", fake))
    assert chunks[-1].result.output_tokens == 10 and chunks[-1].result.input_tokens is None


@pytest.mark.parametrize(("provider", "tag", "_"), MODELS)
async def test_missing_key_is_cloud_key_missing_without_any_call(provider, tag, _):
    fake = FakeCloud(provider, [Plan(b"")])
    with pytest.raises(ProviderError) as exc:
        await collect(build(provider, tag, fake, key=None))
    assert exc.value.code == "cloud_key_missing"
    envelope = build_envelope(exc.value.code, exc.value.technical, **exc.value.detail)
    assert fake.requests == []  # aucun appel
    assert NAMES[provider] in envelope["message"]
    assert f"{provider.upper()}_API_KEY" in envelope["action"] and ".env" in envelope["action"]


@pytest.mark.parametrize(("provider", "tag", "_"), MODELS)
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "cloud_key_refused"),
        (403, "cloud_key_refused"),
        (429, "cloud_rate_limited"),
        (400, "cloud_error"),
        (404, "cloud_error"),
        (500, "cloud_error"),
    ],
)
async def test_http_refusals_become_codes_that_name_the_provider(provider, tag, _, status, code):
    key = FAKE_KEYS[provider]
    fake = FakeCloud(provider, [Plan(status=status, message=f"Clé fautive : {key}")])
    with pytest.raises(ProviderError) as exc:
        await collect(build(provider, tag, fake))
    error = exc.value
    assert error.code == code and error.detail["http_status"] == status
    assert error.detail["provider"] == provider
    envelope = build_envelope(error.code, error.technical, [key], **error.detail)
    assert NAMES[provider] in envelope["message"]
    assert key not in repr(envelope)  # ni dans `detail`, ni dans le message, ni dans l'action
    assert len(fake.requests) == 1  # aucune nouvelle tentative du SDK


@pytest.mark.parametrize(("provider", "tag", "_"), MODELS)
async def test_unreachable_provider_is_named_and_offers_local(provider, tag, _):
    fake = FakeCloud(provider, [Plan(connect_error=True)])
    with pytest.raises(ProviderError) as exc:
        await collect(build(provider, tag, fake))
    assert exc.value.code == "cloud_unreachable"
    envelope = build_envelope(exc.value.code, exc.value.technical, **exc.value.detail)
    assert NAMES[provider] in envelope["message"]
    assert "Local" in envelope["action"]
    assert fake.clients[0].is_closed


async def test_a_stream_cut_after_text_is_generation_interrupted():
    first_frame = chat_stream(["début"]).split(b"\n\n")[1] + b"\n\n"
    fake = FakeCloud("openai", [Plan(cut_after=first_frame)])
    chunks = []
    with pytest.raises(ProviderError) as exc:
        async for chunk in build("openai", "openai/gpt-6-luna", fake).stream(REQUEST):
            chunks.append(chunk)
    assert exc.value.code == "generation_interrupted"
    assert [c.text for c in chunks if isinstance(c, TextDelta)] == ["début"]


@pytest.mark.parametrize(("provider", "tag", "_"), MODELS)
async def test_cancelling_the_task_closes_the_http_stream_and_client(provider, tag, _):
    release = asyncio.Event()
    fake = FakeCloud(provider, [Plan(stream_for(provider, ["début"]), hold=release)])
    model = build(provider, tag, fake)
    got = asyncio.Event()

    async def run():
        async for chunk in model.stream(REQUEST):
            if isinstance(chunk, TextDelta):
                got.set()

    task = asyncio.create_task(run())
    await asyncio.wait_for(got.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.clients[0].is_closed


@pytest.mark.parametrize(("provider", "tag", "_"), MODELS)
async def test_no_key_in_logs_when_the_provider_echoes_it(provider, tag, _, caplog):
    key = FAKE_KEYS[provider]
    fake = FakeCloud(provider, [Plan(status=401, message=f"Incorrect API key: {key}")])
    with caplog.at_level(logging.DEBUG), pytest.raises(ProviderError):
        await collect(build(provider, tag, fake))
    assert key not in caplog.text
    assert key not in str(fake.requests[0].url)
