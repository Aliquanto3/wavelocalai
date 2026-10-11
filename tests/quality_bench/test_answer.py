"""Extraction de la réponse (AD-10) : ``grading/answer.py`` seul lit ``output``."""

from __future__ import annotations

import pytest

from scripts.quality_bench.grading.answer import (
    JsonAnswerError,
    ToolCallError,
    after_prefix,
    decode_floats,
    decode_json,
    final_answer,
    tool_calls_by_turn,
    tool_steps,
)

from .grading_factories import assistant, tool_call


def _generation(output):
    return {"output": output}


def test_final_answer_takes_last_assistant_message():
    output = [
        assistant("premier"),
        {"turn": 0, "role": "tool", "content": "outil"},
        assistant("  dernier  "),
        {"turn": 1, "role": "user", "content": "question"},
    ]
    answer = final_answer(_generation(output))
    assert answer.text == "dernier"
    assert answer.inline_thinking == 0.0


def test_final_answer_without_assistant_is_empty():
    assert final_answer(_generation([])).text == ""


@pytest.mark.parametrize(
    "content, text",
    [
        ("<think>je réfléchis</think>\n\nRéponse.", "Réponse."),
        ("<think>a</think>b<think>c</think> fin", "fin"),
        ("Réponse partielle <think>réflexion sans fin", "Réponse partielle"),
    ],
)
def test_inline_thinking_is_removed_and_flagged(content, text):
    answer = final_answer(_generation([assistant(content)]))
    assert answer.text == text
    assert answer.inline_thinking == 1.0


@pytest.mark.parametrize(
    "text, value",
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": [1, 2]}\n```', {"a": [1, 2]}),
        ("```\n[true, null]\n```", [True, None]),
        ("  42  ", 42),
    ],
)
def test_decode_json(text, value):
    assert decode_json(text) == value


@pytest.mark.parametrize(
    "text",
    [
        "",
        'Voici : {"a": 1}',
        "{'a': 1}",
        '{"a": NaN}',
        '```json\n{"a":\n```',
        "1" * 5000,  # entier de plus de 4300 chiffres : ValueError de json.loads
    ],
)
def test_decode_json_refuses_unreadable(text):
    with pytest.raises(JsonAnswerError):
        decode_json(text)


def test_tool_steps_pair_calls_with_following_tool_messages():
    output = [
        assistant(tool_calls=[tool_call("cd", {"folder": "a"}), tool_call("ls", {})]),
        {"turn": 0, "role": "tool", "content": "r1"},
        {"turn": 0, "role": "tool", "content": "r2"},
        assistant("texte"),
        {"turn": 1, "role": "user", "content": "suite"},
        assistant(turn=1, tool_calls=[tool_call("pwd", {})]),
        {"turn": 1, "role": "tool", "content": "r3"},
    ]
    steps = tool_steps(_generation(output))
    assert [(s.turn, [c.name for c in s.calls], list(s.contents)) for s in steps] == [
        (0, ["cd", "ls"], ["r1", "r2"]),
        (1, ["pwd"], ["r3"]),
    ]
    by_turn = tool_calls_by_turn(_generation(output))
    assert [c.name for c in by_turn[0]] == ["cd", "ls"]
    assert [c.arguments for c in by_turn[1]] == [{}]


@pytest.mark.parametrize(
    "call",
    [
        {"function": {"arguments": {}}},
        {"function": {"name": "", "arguments": {}}},
        {"function": {"name": "cd", "arguments": '{"folder": "a"}'}},
        {"function": {"name": "cd", "arguments": None}},
        {"name": "cd"},
        "cd()",
    ],
)
def test_malformed_tool_call_raises(call):
    with pytest.raises(ToolCallError):
        tool_steps(_generation([assistant(tool_calls=[call])]))


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Calcul. La réponse est : 12", " 12"),
        ("la réponse est: 7\nfin", " 7\nfin"),
        ("LA  RÉPONSE   EST  :3", "3"),
        ("La réponse est : 1. Non, La réponse est : 2", " 2"),
    ],
)
def test_after_prefix_takes_last_occurrence(text, expected):
    assert after_prefix(text, "La réponse est :") == expected


def test_after_prefix_absent():
    assert after_prefix("Je pense que c'est 12", "La réponse est :") is None
    assert after_prefix("The answer is 4", "The answer is:") is None


def test_decode_floats_restores_encoded_floats():
    value = [{"f": {"x": [{"$float": "2.5"}, 3, "a"], "y": {"$float": "-0.1"}}}]
    assert decode_floats(value) == [{"f": {"x": [2.5, 3, "a"], "y": -0.1}}]
    assert decode_floats({"$float": "1.0", "autre": 1}) == {"$float": "1.0", "autre": 1}
