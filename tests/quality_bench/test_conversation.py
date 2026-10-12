"""Conversation d'une question (AD-7, AD-11) : tours, outils, borne, troncature, contexte."""

from __future__ import annotations

import pytest

from scripts.quality_bench.envs.registry import make_env
from scripts.quality_bench.generation.conversation import ChatFailedError, run_conversation
from scripts.quality_bench.grading.registry import grade_line
from scripts.quality_bench.ollama.client import ChatResult, OllamaRequestError

from .grading_factories import GOOD_STEPS, generation_for, questions, tool_call


def result(content="", *, tool_calls=None, done_reason="stop", prompt=10, cached=0, thinking=""):
    return ChatResult(
        content=content,
        thinking=thinking,
        tool_calls=list(tool_calls or []),
        chunks={"content": 2 if content else 0, "thinking": 3 if thinking else 0, "tool_calls": 0},
        done_reason=done_reason,
        prompt_eval_count=prompt,
        prompt_eval_cached_count=cached,
        eval_count=5,
        durations_ns={"total": 100, "load": 10, "prompt_eval": 20, "eval": 30},
        wall_s=0.5,
    )


class ScriptedChat:
    """``chat(messages, tools)`` qui rend les résultats prévus et garde chaque requête."""

    def __init__(self, *results):
        self.results = list(results)
        self.requests = []

    def __call__(self, messages, tools):
        self.requests.append(([dict(m) for m in messages], tools))
        outcome = self.results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _run(question, chat, *, num_ctx=None, num_predict=2048, cap=8):
    return run_conversation(
        question,
        chat,
        num_ctx=num_ctx or question["num_ctx"],
        num_predict=num_predict,
        max_tool_calls_per_turn=cap,
    )


def test_single_answer_is_raw_and_counted():
    question = questions()["piaf"]
    chat = ScriptedChat(result("Eiffel", thinking="réflexion", cached=4))
    outcome = _run(question, chat)
    assert outcome.status == "ok" and not outcome.call_cap_reached
    assert outcome.output == [
        {
            "turn": 0,
            "role": "assistant",
            "content": "Eiffel",
            "thinking": "réflexion",
            "tool_calls": [],
        }
    ]
    assert outcome.calls == 1
    assert outcome.tokens == {
        "prompt": 10,
        "prompt_cached": 4,
        "completion": 5,
        "thinking_est": 3,
        "answer_est": 2,
    }
    assert outcome.durations_ns == {"total": 100, "load": 10, "prompt_eval": 20, "eval": 30}
    assert chat.requests[0] == (question["messages"], None)


def test_truncation_stops_the_question():
    question = questions()["bfcl_multi"]
    chat = ScriptedChat(result("début", done_reason="length"), result("jamais"))
    outcome = _run(question, chat)
    assert outcome.status == "truncated"
    assert outcome.calls == 1 and len(chat.results) == 1
    assert outcome.output[0]["content"] == "début"


@pytest.mark.parametrize("prompt, cached, status", [(100, 0, "ok"), (60, 40, "context_exceeded")])
def test_context_exceeded_counts_cached_prompt(prompt, cached, status):
    question = questions()["piaf"]
    # num_ctx − num_predict = 100 : prompt + cache ≥ 100 dépasse.
    chat = ScriptedChat(result("x", prompt=prompt - 1 if status == "ok" else prompt, cached=cached))
    outcome = _run(question, chat, num_ctx=150, num_predict=50)
    assert outcome.status == status


def test_context_exceeded_wins_over_truncation():
    question = questions()["piaf"]
    chat = ScriptedChat(result("x", done_reason="length", prompt=200))
    assert _run(question, chat, num_ctx=150, num_predict=50).status == "context_exceeded"


def test_single_turn_tools_stop_at_first_answer_without_tool_message():
    question = questions()["bfcl_ast"]
    first = [tool_call("weather_get", {"city": "Paris", "days": 2.5})]
    chat = ScriptedChat(result(tool_calls=first), result("jamais"))
    outcome = _run(question, chat)
    assert outcome.status == "ok" and outcome.calls == 1
    assert [m["role"] for m in outcome.output] == ["assistant"]
    assert outcome.output[0]["tool_calls"] == first
    assert chat.requests[0][1] == question["tools"]
    grade = grade_line(question, generation_for(question, outcome.output)).record
    assert (grade["status"], grade["success"]) == ("ok", True)


def _multi_turn_results(steps_by_turn):
    results = []
    for steps in steps_by_turn:
        for step in steps:
            results.append(result(tool_calls=[tool_call(n, a) for n, a in step]))
        results.append(result("Fait."))
    return results


def test_multi_turn_tools_execute_env_and_inject_turns():
    question = questions()["bfcl_multi"]
    chat = ScriptedChat(*_multi_turn_results(GOOD_STEPS))
    outcome = _run(question, chat)
    assert outcome.status == "ok" and not outcome.call_cap_reached
    assert outcome.calls == 5
    env = make_env(question["env"])
    expected_tools = [
        env.call(name, arguments)
        for steps in GOOD_STEPS
        for step in steps
        for name, arguments in step
    ]
    assert [m["content"] for m in outcome.output if m["role"] == "tool"] == expected_tools
    users = [m for m in outcome.output if m["role"] == "user"]
    assert users == [{"turn": 1, "role": "user", "content": question["turns"][0][0]["content"]}]
    assert [m["turn"] for m in outcome.output if m["role"] == "assistant"] == [0, 0, 0, 1, 1]
    # Le message tool renvoyé au modèle porte le nom de l'outil ; la sortie, non.
    second_request = chat.requests[1][0]
    assert second_request[-1] == {"role": "tool", "content": expected_tools[0], "tool_name": "cd"}
    assert second_request[-2]["tool_calls"] == [tool_call("cd", {"folder": "docs"})]
    grade = grade_line(question, generation_for(question, outcome.output)).record
    assert (grade["status"], grade["success"]) == ("ok", True)


def test_counters_are_summed_and_thinking_is_sent_back():
    """Tokens, durées et temps sont les sommes des appels de l'essai (AD-7) ; la réflexion d'un
    appel d'outil est renvoyée au modèle, et absente quand elle est vide."""
    question = questions()["bfcl_multi"]
    first = result(
        tool_calls=[tool_call("cd", {"folder": "docs"})], prompt=11, cached=3, thinking="je cherche"
    )
    second = result("Fait.", prompt=17, cached=5)
    rest = _multi_turn_results(GOOD_STEPS[1:])
    chat = ScriptedChat(first, second, *rest)
    outcome = _run(question, chat)
    assert outcome.status == "ok"
    calls = 2 + len(rest)
    assert outcome.calls == calls
    assert outcome.tokens == {
        "prompt": 11 + 17 + 10 * len(rest),
        "prompt_cached": 3 + 5,
        "completion": 5 * calls,
        "thinking_est": 3,
        "answer_est": 2 * sum(1 for r in [second, *rest] if r.content),
    }
    assert outcome.durations_ns == {
        "total": 100 * calls,
        "load": 10 * calls,
        "prompt_eval": 20 * calls,
        "eval": 30 * calls,
    }
    assert outcome.wall_s == pytest.approx(0.5 * calls)
    sent_back = chat.requests[1][0][-2]
    assert sent_back["role"] == "assistant" and sent_back["thinking"] == "je cherche"
    later = [m for m in chat.requests[2][0] if m["role"] == "assistant"]
    assert "thinking" not in later[-1]


def test_call_cap_is_not_executed_and_stops():
    question = questions()["bfcl_multi"]
    calls = [tool_call("cd", {"folder": "docs"}), tool_call("ls", {})]
    chat = ScriptedChat(result(tool_calls=calls[:1]), result(tool_calls=calls), result("jamais"))
    outcome = _run(question, chat, cap=2)
    assert outcome.call_cap_reached
    assert outcome.calls == 2 and len(chat.results) == 1
    assert [m["role"] for m in outcome.output] == ["assistant", "tool", "assistant"]
    grade = grade_line(question, generation_for(question, outcome.output, call_cap_reached=True))
    assert grade.record["status"] == "non_compliant"


def test_call_cap_counts_per_turn():
    question = questions()["bfcl_multi"]
    one = [tool_call("cd", {"folder": "docs"})]
    chat = ScriptedChat(
        result(tool_calls=one),
        result("Fait."),
        result(tool_calls=[tool_call("ls", {})]),
        result("Fait."),
    )
    outcome = _run(question, chat, cap=1)
    assert not outcome.call_cap_reached and outcome.calls == 4


@pytest.mark.parametrize(
    "bad",
    [
        {"function": {"name": "", "arguments": {}}},
        {"function": {"name": "cd", "arguments": "folder=docs"}},
        {"name": "cd"},
    ],
)
def test_malformed_call_stops_and_keeps_output(bad):
    question = questions()["bfcl_multi"]
    chat = ScriptedChat(result(tool_calls=[bad]), result("jamais"))
    outcome = _run(question, chat)
    assert outcome.status == "ok" and outcome.calls == 1
    assert outcome.output[0]["tool_calls"] == [bad]
    assert not any(m["role"] == "tool" for m in outcome.output)
    grade = grade_line(question, generation_for(question, outcome.output)).record
    assert grade["status"] == "non_compliant"


def test_chat_failure_carries_partial_output():
    question = questions()["bfcl_multi"]
    error = OllamaRequestError("/api/chat : statut 400 (refus)", 400)
    chat = ScriptedChat(result(tool_calls=[tool_call("cd", {"folder": "docs"})]), error)
    with pytest.raises(ChatFailedError) as excinfo:
        _run(question, chat)
    assert excinfo.value.cause is error
    assert excinfo.value.partial.calls == 1
    assert [m["role"] for m in excinfo.value.partial.output] == ["assistant", "tool"]


def test_env_is_fresh_for_each_run():
    question = questions()["bfcl_multi"]
    first = _run(question, ScriptedChat(*_multi_turn_results(GOOD_STEPS)))
    second = _run(question, ScriptedChat(*_multi_turn_results(GOOD_STEPS)))
    assert first.output == second.output
