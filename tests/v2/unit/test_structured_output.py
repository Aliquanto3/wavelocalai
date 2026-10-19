"""`ChatRequest.response_schema` (AD-8) : chaque adaptateur transmet le schéma et rend une sortie
structurée validée. Faux clients : Ollama et fournisseurs cloud simulés, aucun réseau."""

from __future__ import annotations

import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.models.anthropic import AnthropicChatModel
from wavelocalai.models.mistral import MistralChatModel
from wavelocalai.models.ollama import OllamaChatModel
from wavelocalai.models.openai_compat import OpenAICompatChatModel
from wavelocalai.models.port import ChatMessage, ChatRequest, Done, ModelRef, TextDelta
from wavelocalai.models.structured import parse_structured, schema_errors

from ..fake_cloud import (
    FAKE_KEYS,
    FakeCloud,
    Plan,
    anthropic_tool_stream,
    chat_stream,
    mistral_stream,
)
from ..fake_ollama import FakeOllama
from ..fake_ollama import Plan as OllamaPlan
from ..fake_ollama import final, part

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
    "additionalProperties": False,
}
GOOD = '{"score": 80, "reason": "clair"}'
REQUEST = ChatRequest(
    [ChatMessage("user", "Note cette réponse.")], response_schema=SCHEMA, temperature=0.0
)


async def collect(model):
    return [chunk async for chunk in model.stream(REQUEST)]


def answer(chunks) -> str:
    return "".join(c.text for c in chunks if isinstance(c, TextDelta) and c.channel == "answer")


def cloud_model(provider: str, tag: str, fake: FakeCloud):
    ref = ModelRef(tag, provider, "cloud", "chat")
    cls = {
        "openai": OpenAICompatChatModel,
        "groq": OpenAICompatChatModel,
        "anthropic": AnthropicChatModel,
        "mistral": MistralChatModel,
    }[provider]
    return cls(ref, FAKE_KEYS[provider], http_client=fake.client)


# --- le validateur ----------------------------------------------------------------------------


def test_parse_structured_accepts_valid_json_even_in_a_markdown_fence():
    assert parse_structured(GOOD, SCHEMA) == {"score": 80, "reason": "clair"}
    assert parse_structured(f"```json\n{GOOD}\n```", SCHEMA)["score"] == 80


@pytest.mark.parametrize(
    "text",
    [
        "pas du json",
        '{"score": 80}',  # champ requis absent
        '{"score": "80", "reason": "x"}',  # mauvais type
        '{"score": 101, "reason": "x"}',  # hors bornes
        '{"score": true, "reason": "x"}',  # un booléen n'est pas un entier
        '{"score": 5, "reason": "x", "extra": 1}',  # champ non prévu
        "[1, 2]",
    ],
)
def test_parse_structured_rejects_invalid_output(text):
    with pytest.raises(ProviderError) as exc:
        parse_structured(text, SCHEMA)
    assert exc.value.code == "invalid_output"


def test_schema_errors_covers_enum_and_items():
    schema = {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}}
    assert schema_errors(["a", "b"], schema) == []
    assert schema_errors(["a", "c"], schema)


# --- Ollama : `format` ---------------------------------------------------------------------------


def ollama_model(server: FakeOllama) -> OllamaChatModel:
    return OllamaChatModel(ModelRef("qwen2.5:1.5b", "ollama", "local", "chat"), server.client())


async def test_ollama_passes_the_schema_as_format_and_returns_the_validated_json():
    server = FakeOllama(
        loaded=["qwen2.5:1.5b"], plans=[OllamaPlan([part(GOOD[:12]), part(GOOD[12:]), final()])]
    )
    chunks = await collect(ollama_model(server))
    assert server.chat_requests[0]["format"] == SCHEMA
    assert answer(chunks) == GOOD and isinstance(chunks[-1], Done)


async def test_ollama_invalid_output_raises_before_done():
    server = FakeOllama(loaded=["qwen2.5:1.5b"], plans=[OllamaPlan([part("blabla"), final()])])
    seen = []
    with pytest.raises(ProviderError) as exc:
        async for chunk in ollama_model(server).stream(REQUEST):
            seen.append(chunk)
    assert exc.value.code == "invalid_output" and not any(isinstance(c, Done) for c in seen)


# --- OpenAI, Groq : `response_format` json_schema ----------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "tag", "strict"),
    [("openai", "openai/gpt-6-luna", True), ("groq", "groq/openai/gpt-oss-20b", False)],
)
async def test_openai_compatible_sends_json_schema_response_format(provider, tag, strict):
    fake = FakeCloud(provider, [Plan(chat_stream([GOOD[:10], GOOD[10:]]))])
    chunks = await collect(cloud_model(provider, tag, fake))
    assert fake.bodies[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": SCHEMA, "strict": strict},
    }
    assert answer(chunks) == GOOD and isinstance(chunks[-1], Done)


async def test_openai_invalid_output_raises():
    fake = FakeCloud("openai", [Plan(chat_stream(["{"]))])
    with pytest.raises(ProviderError) as exc:
        await collect(cloud_model("openai", "openai/gpt-6-luna", fake))
    assert exc.value.code == "invalid_output"


async def test_openai_without_schema_sends_no_response_format():
    fake = FakeCloud("openai", [Plan(chat_stream(["ok"]))])
    model = cloud_model("openai", "openai/gpt-6-luna", fake)
    _ = [c async for c in model.stream(ChatRequest([ChatMessage("user", "Salut")]))]
    assert "response_format" not in fake.bodies[0]


# --- Mistral : schéma JSON -------------------------------------------------------------------------


async def test_mistral_sends_json_schema_and_validates():
    fake = FakeCloud("mistral", [Plan(mistral_stream([GOOD[:9], GOOD[9:]]))])
    chunks = await collect(cloud_model("mistral", "mistral/mistral-small-latest", fake))
    response_format = fake.bodies[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["schema"] == SCHEMA
    assert response_format["json_schema"]["name"] == "response"
    assert answer(chunks) == GOOD and isinstance(chunks[-1], Done)


async def test_mistral_invalid_output_raises():
    fake = FakeCloud("mistral", [Plan(mistral_stream(['{"score": 1}']))])
    with pytest.raises(ProviderError) as exc:
        await collect(cloud_model("mistral", "mistral/mistral-small-latest", fake))
    assert exc.value.code == "invalid_output"


# --- Anthropic : tool_use forcé -------------------------------------------------------------------


async def test_anthropic_forces_a_tool_carrying_the_schema_and_returns_its_json():
    fake = FakeCloud("anthropic", [Plan(anthropic_tool_stream([GOOD[:8], GOOD[8:]]))])
    chunks = await collect(cloud_model("anthropic", "anthropic/claude-haiku-5-5", fake))
    body = fake.bodies[0]
    assert body["tools"][0]["name"] == "respond"
    assert body["tools"][0]["input_schema"] == SCHEMA
    assert body["tool_choice"] == {"type": "tool", "name": "respond"}
    assert answer(chunks) == GOOD
    assert chunks[-1].result.finish_reason == "stop"  # pas un appel d'outil pour l'appelant


async def test_anthropic_invalid_tool_input_raises():
    fake = FakeCloud("anthropic", [Plan(anthropic_tool_stream(['{"score": "x"}']))])
    with pytest.raises(ProviderError) as exc:
        await collect(cloud_model("anthropic", "anthropic/claude-haiku-5-5", fake))
    assert exc.value.code == "invalid_output"
