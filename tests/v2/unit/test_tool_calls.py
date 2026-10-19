"""Appels d'outils par adaptateur (story 6.1, AD-8) : trois formats, quatre adaptateurs, faux clients.

Chaque adaptateur reçoit les outils au schéma neutre du port, les passe dans le format de son
fournisseur, rend des `ToolCall(id, name, arguments)` assemblés depuis le flux, puis accepte le
résultat de l'outil au tour suivant (message `assistant` avec ses appels, message `tool`). Aucun
réseau : les vrais SDK (`ollama`, `openai`, `anthropic`, `mistralai`) tournent sur des transports
HTTP simulés.
"""

from __future__ import annotations

import json

import pytest

from wavelocalai.models.anthropic import AnthropicChatModel
from wavelocalai.models.mistral import MistralChatModel
from wavelocalai.models.ollama import OllamaChatModel
from wavelocalai.models.openai_compat import OpenAICompatChatModel
from wavelocalai.models.port import (
    ChatMessage,
    ChatRequest,
    Done,
    ModelRef,
    TextDelta,
    ToolCall,
)
from wavelocalai.models.tool_format import ToolCallDeltas, parse_arguments

from ..fake_cloud import (
    FAKE_KEYS,
    FakeCloud,
    Plan,
    anthropic_tool_use_stream,
    chat_tool_stream,
    mistral_tool_stream,
)
from ..fake_ollama import FakeOllama
from ..fake_ollama import Plan as OllamaPlan
from ..fake_ollama import final, part

PARAMETERS = {
    "type": "object",
    "properties": {"ville": {"type": "string", "description": "Nom de la ville"}},
    "required": ["ville"],
}
TOOLS = [{"name": "meteo", "description": "Météo d'une ville", "parameters": PARAMETERS}]
ASK = ChatRequest(
    [ChatMessage("system", "Tu as des outils."), ChatMessage("user", "Quel temps à Lyon ?")],
    tools=TOOLS,
)
# Second tour : le modèle a appelé `meteo`, l'outil a répondu.
FOLLOW_UP = ChatRequest(
    [
        *ASK.messages,
        ChatMessage(
            "assistant",
            "Je regarde.",
            tool_calls=[{"id": "call_1", "name": "meteo", "arguments": {"ville": "Lyon"}}],
        ),
        ChatMessage("tool", "Lyon : 18 °C, ciel dégagé", tool_call_id="call_1"),
    ],
    tools=TOOLS,
)
FUNCTION_TOOL = {
    "type": "function",
    "function": {"name": "meteo", "description": "Météo d'une ville", "parameters": PARAMETERS},
}


async def collect(model, request):
    return [chunk async for chunk in model.stream(request)]


def calls_of(chunks) -> list[ToolCall]:
    return [c for c in chunks if isinstance(c, ToolCall)]


def build(adapter, provider, tag, fake):
    ref = ModelRef(tag, provider, "cloud", "chat")
    return adapter(ref, FAKE_KEYS[provider], http_client=fake.client)


# --- OpenAI et Groq : format `function`, arguments en chaîne JSON assemblée ----------------------


@pytest.mark.parametrize(
    ("provider", "tag"), [("openai", "openai/gpt-6-luna"), ("groq", "groq/openai/gpt-oss-20b")]
)
async def test_openai_compatible_sends_function_tools_and_assembles_streamed_calls(provider, tag):
    stream = chat_tool_stream(
        [
            ("call_a", "meteo", ['{"vil', 'le": "Ly', 'on"}']),
            ("call_b", "meteo", ['{"ville": "Paris"}']),
        ],
        text="Je regarde.",
    )
    fake = FakeCloud(provider, [Plan(stream)])
    chunks = await collect(build(OpenAICompatChatModel, provider, tag, fake), ASK)
    assert fake.bodies[0]["tools"] == [FUNCTION_TOOL]
    assert [(c.id, c.name, c.arguments, c.error) for c in calls_of(chunks)] == [
        ("call_a", "meteo", {"ville": "Lyon"}, None),
        ("call_b", "meteo", {"ville": "Paris"}, None),
    ]
    assert [c.text for c in chunks if isinstance(c, TextDelta)] == ["Je regarde."]
    assert chunks[-1].result.finish_reason == "tool_calls"
    # Les appels précèdent `Done`, émis une fois, en dernier.
    assert [i for i, c in enumerate(chunks) if isinstance(c, Done)] == [len(chunks) - 1]


@pytest.mark.parametrize(
    ("provider", "tag"), [("openai", "openai/gpt-6-luna"), ("groq", "groq/openai/gpt-oss-20b")]
)
async def test_openai_compatible_accepts_the_tool_result_on_the_next_turn(provider, tag):
    fake = FakeCloud(provider, [Plan(chat_tool_stream([("call_1", "meteo", ["{}"])]))])
    await collect(build(OpenAICompatChatModel, provider, tag, fake), FOLLOW_UP)
    messages = fake.bodies[0]["messages"]
    assert messages[2]["role"] == "assistant" and messages[2]["content"] == "Je regarde."
    (call,) = messages[2]["tool_calls"]
    assert (call["id"], call["type"], call["function"]["name"]) == ("call_1", "function", "meteo")
    assert json.loads(call["function"]["arguments"]) == {"ville": "Lyon"}  # chaîne JSON
    assert messages[3] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "Lyon : 18 °C, ciel dégagé",
    }


async def test_openai_unreadable_arguments_are_reported_not_guessed():
    stream = chat_tool_stream([("call_x", "meteo", ['{"ville": '])])  # JSON coupé
    fake = FakeCloud("openai", [Plan(stream)])
    chunks = await collect(build(OpenAICompatChatModel, "openai", "openai/gpt-6-luna", fake), ASK)
    (call,) = calls_of(chunks)
    assert call.arguments == {} and call.error and "JSON invalide" in call.error


async def test_a_request_without_tools_sends_none():
    fake = FakeCloud("openai", [Plan(chat_tool_stream([("c", "x", ["{}"])]))])
    request = ChatRequest([ChatMessage("user", "Bonjour")])
    await collect(build(OpenAICompatChatModel, "openai", "openai/gpt-6-luna", fake), request)
    assert "tools" not in fake.bodies[0]


# --- Anthropic : `tool_use` et `tool_result` ------------------------------------------------------


async def test_anthropic_sends_input_schema_and_reads_tool_use_blocks():
    stream = anthropic_tool_use_stream(
        [
            ("toolu_1", "meteo", ['{"vil', 'le": "Lyon"}']),
            ("toolu_2", "meteo", ['{"ville": "Nice"}']),
        ],
        text="Je regarde.",
    )
    fake = FakeCloud("anthropic", [Plan(stream)])
    model = build(AnthropicChatModel, "anthropic", "anthropic/claude-haiku-5-5", fake)
    chunks = await collect(model, ASK)
    assert fake.bodies[0]["tools"] == [
        {"name": "meteo", "description": "Météo d'une ville", "input_schema": PARAMETERS}
    ]
    assert "tool_choice" not in fake.bodies[0]  # l'outil n'est pas forcé
    assert [(c.id, c.name, c.arguments) for c in calls_of(chunks)] == [
        ("toolu_1", "meteo", {"ville": "Lyon"}),
        ("toolu_2", "meteo", {"ville": "Nice"}),
    ]
    assert [c.text for c in chunks if isinstance(c, TextDelta)] == ["Je regarde."]
    assert chunks[-1].result.finish_reason == "tool_calls"  # `tool_use` du fournisseur


async def test_anthropic_accepts_the_tool_result_as_a_user_block():
    fake = FakeCloud("anthropic", [Plan(anthropic_tool_use_stream([("t", "meteo", ["{}"])]))])
    model = build(AnthropicChatModel, "anthropic", "anthropic/claude-haiku-5-5", fake)
    request = ChatRequest(
        [
            *FOLLOW_UP.messages,
            # Un second appel du même tour : ses résultats forment un seul message `user`.
            ChatMessage("tool", "second résultat", tool_call_id="call_2"),
        ],
        tools=TOOLS,
    )
    await collect(model, request)
    body = fake.bodies[0]
    assert body["system"] == "Tu as des outils."
    assert body["messages"][1] == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Je regarde."},
            {"type": "tool_use", "id": "call_1", "name": "meteo", "input": {"ville": "Lyon"}},
        ],
    }
    assert body["messages"][2] == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "call_1",
                "content": "Lyon : 18 °C, ciel dégagé",
            },
            {"type": "tool_result", "tool_use_id": "call_2", "content": "second résultat"},
        ],
    }


async def test_anthropic_keeps_the_forced_structured_tool_apart_from_real_tools():
    # `response_schema` et outils ensemble : l'outil forcé reste une réponse, pas un appel d'outil.
    from ..fake_cloud import anthropic_tool_stream

    fake = FakeCloud("anthropic", [Plan(anthropic_tool_stream(['{"a": 1}']))])
    model = build(AnthropicChatModel, "anthropic", "anthropic/claude-haiku-5-5", fake)
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
    request = ChatRequest([ChatMessage("user", "x")], tools=TOOLS, response_schema=schema)
    chunks = await collect(model, request)
    names = [t["name"] for t in fake.bodies[0]["tools"]]
    assert names == ["meteo", "respond"]
    assert fake.bodies[0]["tool_choice"] == {"type": "tool", "name": "respond"}
    assert not calls_of(chunks)
    assert chunks[-1].result.finish_reason == "stop"


# --- Mistral : format `function`, `name` sur le résultat -----------------------------------------


async def test_mistral_sends_function_tools_and_reads_whole_calls_even_without_id():
    stream = mistral_tool_stream(
        [("AbCd12345", "meteo", '{"ville": "Lyon"}'), (None, "meteo", {"ville": "Paris"})]
    )
    fake = FakeCloud("mistral", [Plan(stream)])
    model = build(MistralChatModel, "mistral", "mistral/mistral-small-latest", fake)
    chunks = await collect(model, ASK)
    assert fake.bodies[0]["tools"] == [FUNCTION_TOOL]
    first, second = calls_of(chunks)
    assert (first.id, first.name, first.arguments) == ("AbCd12345", "meteo", {"ville": "Lyon"})
    assert second.arguments == {"ville": "Paris"}
    assert len(second.id) == 9 and second.id.isalnum()  # id fabriqué, format Mistral
    assert second.id != first.id and chunks[-1].result.finish_reason == "tool_calls"


async def test_mistral_accepts_the_tool_result_with_its_tool_name():
    fake = FakeCloud("mistral", [Plan(mistral_tool_stream([("AbCd12345", "meteo", "{}")]))])
    model = build(MistralChatModel, "mistral", "mistral/mistral-small-latest", fake)
    await collect(model, FOLLOW_UP)
    messages = fake.bodies[0]["messages"]
    assert messages[2]["role"] == "assistant"
    (call,) = messages[2]["tool_calls"]
    assert call["id"] == "call_1" and call["function"]["name"] == "meteo"
    assert json.loads(call["function"]["arguments"]) == {"ville": "Lyon"}
    assert messages[3]["role"] == "tool" and messages[3]["tool_call_id"] == "call_1"
    assert messages[3]["name"] == "meteo" and messages[3]["content"] == "Lyon : 18 °C, ciel dégagé"


# --- Ollama : format `function`, `tool_name` sur le résultat -------------------------------------

TAG = "qwen2.5:1.5b"
OLLAMA_REF = ModelRef(TAG, "ollama", "local", "chat")


def _ollama_call(*calls: tuple[str, dict]):
    chunk = part("")
    chunk["message"]["tool_calls"] = [
        {"function": {"name": name, "arguments": arguments}} for name, arguments in calls
    ]
    return chunk


async def test_ollama_sends_function_tools_and_mints_unique_call_ids():
    server = FakeOllama(
        loaded=[TAG],
        plans=[
            OllamaPlan([_ollama_call(("meteo", {"ville": "Lyon"})), final()]),
            OllamaPlan([_ollama_call(("meteo", {"ville": "Lyon"})), final()]),
        ],
    )
    model = OllamaChatModel(OLLAMA_REF, server.client())
    first = calls_of(await collect(model, ASK))
    second = calls_of(await collect(model, ASK))
    (tool,) = server.chat_requests[0]["tools"]
    assert tool["type"] == "function" and tool["function"]["name"] == "meteo"
    assert tool["function"]["description"] == "Météo d'une ville"
    assert tool["function"]["parameters"]["required"] == ["ville"]
    assert tool["function"]["parameters"]["properties"]["ville"]["type"] == "string"
    assert [(c.name, c.arguments) for c in first] == [("meteo", {"ville": "Lyon"})]
    assert first[0].id and first[0].id != second[0].id  # Ollama n'a pas d'id : unique par appel


async def test_ollama_accepts_the_tool_result_with_tool_name():
    server = FakeOllama(loaded=[TAG], plans=[OllamaPlan([part("Il fait 18 °C."), final()])])
    await collect(OllamaChatModel(OLLAMA_REF, server.client()), FOLLOW_UP)
    messages = server.chat_requests[0]["messages"]
    assert messages[2]["role"] == "assistant"
    assert messages[2]["tool_calls"] == [
        {"function": {"name": "meteo", "arguments": {"ville": "Lyon"}}}
    ]
    assert messages[3] == {
        "role": "tool",
        "content": "Lyon : 18 °C, ciel dégagé",
        "tool_name": "meteo",
    }


# --- assemblage et lecture des arguments ---------------------------------------------------------


def test_parse_arguments_accepts_objects_and_json_and_rejects_the_rest():
    assert parse_arguments({"a": 1}) == ({"a": 1}, None)
    assert parse_arguments('{"a": 1}') == ({"a": 1}, None)
    assert parse_arguments("") == ({}, None) and parse_arguments(None) == ({}, None)
    assert parse_arguments("[1]")[1] and parse_arguments("{")[1]


def test_parallel_deltas_are_assembled_by_index_and_new_ids_split_calls():
    deltas = ToolCallDeltas()
    deltas.add(0, "a", "outil_un", '{"x"')
    deltas.add(1, "b", "outil_deux", "")
    deltas.add(0, None, None, ": 1}")
    deltas.add(1, None, None, '{"y": 2}')
    deltas.add(1, "c", "outil_trois", "{}")  # un autre id sur l'indice 1 : un nouvel appel
    assert [(c.id, c.name, c.arguments) for c in deltas.calls()] == [
        ("a", "outil_un", {"x": 1}),
        ("b", "outil_deux", {"y": 2}),
        ("c", "outil_trois", {}),
    ]


def test_whole_calls_on_one_index_without_id_are_not_merged():
    """Mistral : deux appels entiers sur l'indice 0, `id = "null"` : deux appels, pas un mélange."""
    deltas = ToolCallDeltas()
    deltas.add(0, "null", "meteo", '{"ville": "Lyon"}')
    deltas.add(0, "null", "heure", {"fuseau": "UTC"})
    deltas.add(0, "null", "meteo", '{"ville": "Paris"}')
    calls = deltas.calls()
    assert [(c.name, c.arguments, c.error) for c in calls] == [
        ("meteo", {"ville": "Lyon"}, None),
        ("heure", {"fuseau": "UTC"}, None),
        ("meteo", {"ville": "Paris"}, None),
    ]
    assert len({c.id for c in calls}) == 3


def test_a_repeated_name_with_the_same_id_stays_one_call():
    deltas = ToolCallDeltas()
    deltas.add(0, "a", "meteo", '{"ville"')
    deltas.add(0, "a", "meteo", ': "Lyon"}')
    assert [(c.id, c.arguments) for c in deltas.calls()] == [("a", {"ville": "Lyon"})]
