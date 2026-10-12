"""Environnements d'outils (AD-11) : contrat de ``ToolEnv``, BFCL multi-tours rejouable et
déterministe, sur un état initial synthétique."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.quality_bench.common.manifest import HARNESS_DIRS
from scripts.quality_bench.envs.base import CallExpressionError, EnvError, parse_call
from scripts.quality_bench.envs.bfcl_multi_turn import render_result
from scripts.quality_bench.envs.registry import ENVS, make_env
from scripts.quality_bench.grading.answer import tool_steps
from scripts.quality_bench.grading.registry import grade_line

from .grading_factories import (
    FILE_SYSTEM_STATE,
    GOOD_STEPS,
    generation_for,
    questions,
    run_conversation,
)

SPEC = {"name": "bfcl_multi_turn", "initial_state": FILE_SYSTEM_STATE}
CALLS = [
    ("pwd", {}),
    ("ls", {}),
    ("cd", {"folder": "docs"}),
    ("cat", {"file_name": "a.txt"}),
    ("mkdir", {"dir_name": "tmp"}),
    ("sort", {"file_name": "a.txt"}),
    ("cd", {"folder": "inexistant"}),
    ("cd", {"dossier": "docs"}),
    ("mean", {"numbers": [1, 2, 4]}),
    ("square_root", {"number": 2, "precision": 30}),
    ("logarithm", {"value": 8, "base": 2, "precision": 20}),
]


def test_registry_versions():
    assert {name: env.version for name, env in ENVS.items()} == {
        "bfcl_multi_turn": "bfcl_multi_turn@1"
    }
    assert make_env(SPEC).version == "bfcl_multi_turn@1"


def test_envs_are_in_the_harness_hash():
    assert "envs" in HARNESS_DIRS


@pytest.mark.parametrize(
    "spec",
    [
        None,
        {"name": "inconnu", "initial_state": {}},
        {
            "name": "bfcl_multi_turn",
            "initial_state": {"involved_classes": ["Inconnue"], "initial_config": {}},
        },
        {
            "name": "bfcl_multi_turn",
            "initial_state": {"involved_classes": "GorillaFileSystem", "initial_config": {}},
        },
    ],
)
def test_unreadable_spec_raises_env_error(spec):
    with pytest.raises(EnvError):
        make_env(spec)


def test_two_fresh_environments_give_identical_results_and_state():
    first, second = make_env(SPEC), make_env(SPEC)
    results_first = [first.call(name, args) for name, args in CALLS]
    results_second = [second.call(name, args) for name, args in CALLS]
    assert results_first == results_second
    assert first.instances.keys() == second.instances.keys()
    for name, instance in first.instances.items():
        assert vars(instance).keys() == vars(second.instances[name]).keys()
        public = {k: v for k, v in vars(instance).items() if not k.startswith("_")}
        public_second = {
            k: v for k, v in vars(second.instances[name]).items() if not k.startswith("_")
        }
        assert public == public_second


def test_results_are_rendered_like_bfcl():
    env = make_env(SPEC)
    assert env.call("pwd", {}) == json.dumps({"current_working_directory": "/racine"})
    assert env.call("cd", {"folder": "docs"}) == '{"current_working_directory": "docs"}'
    assert env.call("sort", {"file_name": "a.txt"}) == json.dumps({"sorted_content": "alpha\nbeta"})
    assert render_result("texte") == "texte"
    assert render_result([1, 2]) == "[1, 2]"
    assert render_result({"r": {1, 2}}) == "{'r': {1, 2}}"  # non sérialisable : str()


def test_call_errors_are_rendered_never_raised():
    env = make_env(SPEC)
    assert env.call("inconnue", {}) == "Error during execution: name 'inconnue' is not defined"
    assert env.call("remove", {"x": 1}) == (
        "Error during execution: Function call remove is not allowed."
    )
    unexpected = env.call("cd", {"dossier": "docs"})
    assert unexpected.startswith("Error during execution: ")
    assert "unexpected keyword argument 'dossier'" in unexpected


TICKET_SCRIPT = """
import sys
from scripts.quality_bench.envs.registry import make_env
env = make_env({
    "name": "bfcl_multi_turn",
    "initial_state": {
        "involved_classes": ["TicketAPI"],
        "initial_config": {"TicketAPI": {
            "ticket_queue": [{"id": 1, "title": "t", "description": "", "status": "Open",
                              "priority": 1, "created_by": "u"}],
            "ticket_counter": 2,
            "current_user": "u",
        }},
    },
})
updates = {"owner": "a", "assignee": "b", "due_date": "c", "zone": "d"}
sys.stdout.write(env.call("edit_ticket", {"ticket_id": 1, "updates": updates}))
"""


def test_ticket_error_text_does_not_depend_on_the_hash_seed():
    """``edit_ticket`` joignait un ``set`` : l'ordre changeait avec ``PYTHONHASHSEED``, donc
    entre la génération et le rejeu de ``grade`` (rejeu divergent)."""
    root = Path(__file__).resolve().parents[2]
    outputs = set()
    for seed in ("1", "2", "3", "4", "5"):
        completed = subprocess.run(
            [sys.executable, "-c", TICKET_SCRIPT],
            cwd=root,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.add(completed.stdout)
    assert outputs == {
        '{"error": "Invalid fields for update: assignee, due_date, owner, zone"}'
    }


def test_unrenderable_result_is_rendered_as_an_error():
    """Un résultat que ``str`` ne sait pas rendre (entier de plus de 4300 chiffres) est une
    erreur rendue, jamais levée."""
    result = make_env(SPEC).call("power", {"base": 10, "exponent": 5000})
    assert result.startswith("Error during execution: ")


def test_call_never_shares_argument_objects_with_the_model_message():
    env = make_env(
        {
            "name": "bfcl_multi_turn",
            "initial_state": {
                "involved_classes": ["TwitterAPI"],
                "initial_config": {
                    "TwitterAPI": {
                        "username": "u",
                        "password": "p",
                        "authenticated": True,
                        "tweets": {},
                        "comments": {},
                        "retweets": {},
                        "following_list": [],
                        "tweet_counter": 0,
                    }
                },
            },
        }
    )
    arguments = {"content": "c", "tags": ["#a"], "mentions": ["@b"]}
    env.call("post_tweet", arguments)
    env.call("mention", {"tweet_id": 0, "mentioned_usernames": ["@c"]})
    assert arguments == {"content": "c", "tags": ["#a"], "mentions": ["@b"]}


def test_decimal_context_is_isolated():
    import decimal

    precision = decimal.getcontext().prec
    make_env(SPEC).call("square_root", {"number": 2, "precision": 5})
    assert decimal.getcontext().prec == precision


@pytest.mark.parametrize(
    "text, parsed",
    [
        ("cd(folder='document')", ("cd", (), {"folder": "document"})),
        ("sort('a.txt')", ("sort", ("a.txt",), {})),
        (
            "f(1, x=-2.5, y=[1, (2, 3)], z={'a': None})",
            ("f", (1,), {"x": -2.5, "y": [1, (2, 3)], "z": {"a": None}}),
        ),
        ("  ls()  ", ("ls", (), {})),
    ],
)
def test_parse_call(text, parsed):
    assert parse_call(text) == parsed


@pytest.mark.parametrize(
    "text",
    [
        "cd",
        "os.system('x')",
        "cd(folder=open('x'))",
        "cd(*args)",
        "cd(**kwargs)",
        "cd(folder=x)",
        "cd(folder='a'",
        "(lambda: 1)()",
        "cd(folder='a'); ls()",
    ],
)
def test_parse_call_refuses_anything_but_literal_calls(text):
    with pytest.raises(CallExpressionError):
        parse_call(text)


def test_call_expression_matches_model_call():
    target_env, model_env = make_env(SPEC), make_env(SPEC)
    assert target_env.call_expression("cd(folder='docs')") == model_env.call(
        "cd", {"folder": "docs"}
    )
    assert target_env.call_expression("sort('a.txt')") == model_env.call(
        "sort", {"file_name": "a.txt"}
    )


def test_grader_replays_a_conversation_produced_by_the_environment():
    """Critère : une conversation bfcl-multi synthétique produite par ``make_env(...).call`` est
    rejouée, chaque contenu ``tool`` retrouvé, l'état final noté comme BFCL ; un contenu
    modifié donne ``error``."""
    question = questions()["bfcl_multi"]
    output = run_conversation(question, GOOD_STEPS)
    generation = generation_for(question, output)
    replay = make_env(question["env"])
    for step in tool_steps(generation):
        for call, content in zip(step.calls, step.contents, strict=True):
            assert replay.call(call.name, call.arguments) == content
    assert grade_line(question, generation).record["success"] is True

    tampered = [dict(message) for message in output]
    last_tool = max(i for i, message in enumerate(tampered) if message["role"] == "tool")
    tampered[last_tool]["content"] = '{"sorted_content": "beta\\nalpha"}'
    record = grade_line(question, generation_for(question, tampered)).record
    assert (record["status"], record["score"], record["success"]) == ("error", None, None)
