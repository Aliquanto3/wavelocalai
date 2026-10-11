"""Questions et sorties synthétiques pour les correcteurs (aucune question privée réelle)."""

from __future__ import annotations

from typing import Any

from scripts.quality_bench.envs.registry import make_env

from .factories import HASH_A, generation_record
from .set_factories import synthetic_question

MODEL = "m:1b"

WEATHER_FUNCTION = {
    "name": "weather.get",
    "description": "Météo synthétique.",
    "parameters": {
        "type": "dict",
        "properties": {
            "city": {"type": "string", "description": "Ville."},
            "unit": {"type": "string", "description": "Unité.", "enum": ["c", "f"]},
            "days": {"type": "float", "description": "Jours."},
        },
        "required": ["city"],
    },
}
WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "weather_get",
        "description": "Météo synthétique.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "unit": {"type": "string"},
                "days": {"type": "number"},
            },
            "required": ["city"],
        },
    },
}

FILE_SYSTEM_STATE = {
    "involved_classes": ["GorillaFileSystem", "MathAPI"],
    "initial_config": {
        "GorillaFileSystem": {
            "root": {
                "racine": {
                    "type": "directory",
                    "contents": {
                        "docs": {
                            "type": "directory",
                            "contents": {
                                "a.txt": {"type": "file", "content": "beta\nalpha\n"},
                            },
                        }
                    },
                }
            }
        }
    },
}
FS_TARGET = [
    ["cd(folder='docs')", "mkdir(dir_name='tmp')"],
    ["sort('a.txt')"],
]
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "nom": {"type": "string"},
        "age": {"type": "integer"},
        "actif": {"type": "boolean"},
    },
    "required": ["nom", "age"],
}
CWE_WORDS = sorted(f"mot{index}" for index in range(10))


def questions() -> dict[str, dict[str, Any]]:
    """Une question synthétique valide par cas, construite par ``build_question``."""
    multi_tools = [
        {
            "type": "function",
            "function": {"name": name, "description": "", "parameters": {"type": "object"}},
        }
        for name in ("cd", "mkdir", "sort", "ls")
    ]
    return {
        "bbeh": synthetic_question("bbeh-mini", 1, target="a"),
        "var_math": synthetic_question(
            "var-math-fr",
            1,
            grader_params={"answer_prefix": "La réponse est :"},
            target=1234,
        ),
        "ifbench": synthetic_question(
            "ifbench",
            1,
            grader_params={
                "key": "1",
                "instruction_id_list": ["keywords:existence", "punctuation:no_comma"],
                "kwargs": [{"keywords": ["banane"], "frequency": None}, {}],
            },
        ),
        "mifeval": synthetic_question(
            "mifeval-fr",
            1,
            grader_params={
                "key": "1",
                "instruction_id_list": ["fr:length_constraints:number_sentences"],
                "kwargs": [{"num_sentences": 2, "relation": "moins de"}],
            },
        ),
        "bfcl_ast": synthetic_question(
            "bfcl-live",
            1,
            tools=[WEATHER_TOOL],
            grader_params={
                "bfcl_id": "live_simple_0-0-0",
                "category": "live_simple",
                "functions": [WEATHER_FUNCTION],
                "underscore_to_dot": True,
            },
            target=[{"weather.get": {"city": ["Paris"], "unit": ["c", ""], "days": [2.5, ""]}}],
        ),
        "bfcl_multi": synthetic_question(
            "bfcl-multi",
            1,
            turns=[[{"role": "user", "content": "Tour synthétique 2"}]],
            tools=multi_tools,
            env={"name": "bfcl_multi_turn", "initial_state": FILE_SYSTEM_STATE},
            grader_params={
                "bfcl_id": "multi_turn_base_0",
                "category": "multi_turn_base",
                "excluded_function": [],
                "functions": [],
                "underscore_to_dot": True,
            },
            target=FS_TARGET,
        ),
        "irrelevance": synthetic_question(
            "bfcl-irrelevance",
            1,
            tools=[WEATHER_TOOL],
            grader_params={
                "bfcl_id": "live_irrelevance_0-0-0",
                "category": "live_irrelevance",
                "functions": [WEATHER_FUNCTION],
                "underscore_to_dot": True,
            },
        ),
        "jsonschema": synthetic_question(
            "jsonschemabench",
            1,
            grader_params={"schema": EXTRACTION_SCHEMA, "subset": "Github_easy"},
        ),
        "extraction": synthetic_question(
            "extraction-fr",
            1,
            grader_params={"schema": EXTRACTION_SCHEMA, "subset": "extraction-fr"},
            target={"nom": "Jeanne  Martin", "age": 40, "actif": True},
        ),
        "piaf": synthetic_question("piaf", 1, target=["la tour Eiffel", "Eiffel"]),
        "niah": synthetic_question(
            "oneruler-fr-niah",
            1,
            grader_params={"variant": "single", "none_answer": "aucun"},
            target=["1234567"],
        ),
        "none": synthetic_question(
            "oneruler-fr-none",
            1,
            grader_params={"variant": "none", "none_answer": "aucun"},
        ),
        "cwe": synthetic_question(
            "oneruler-fr-cwe",
            1,
            grader_params={"level": "easy", "common_repeats": 30, "uncommon_repeats": 3},
            target=CWE_WORDS,
        ),
        "abstention": synthetic_question(
            "abstention-fr", 1, grader_params={"marker": "JE NE SAIS PAS"}
        ),
        "writing": synthetic_question("writing-fr", 1),
    }


def assistant(content: str = "", turn: int = 0, tool_calls=None, thinking=None) -> dict:
    return {
        "turn": turn,
        "role": "assistant",
        "content": content,
        "thinking": thinking,
        "tool_calls": tool_calls or [],
    }


def tool_call(name: str, arguments: Any) -> dict:
    return {"function": {"name": name, "arguments": arguments}}


def answer_output(content: str) -> list[dict]:
    return [assistant(content)]


def generation_for(
    question: dict[str, Any],
    output: list[dict],
    *,
    campaign: str = "grade-test",
    status: str = "ok",
    call_cap_reached: bool = False,
    manifest: str = HASH_A,
    seed: int = 0,
) -> dict[str, Any]:
    """Ligne ``qb.generation/1`` valide pour ``question``."""
    return generation_record(
        key=f"{campaign}|{MODEL}|think_off|{question['id']}|{seed}",
        manifest=manifest,
        campaign=campaign,
        model=MODEL,
        track="think_off",
        question_id=question["id"],
        usage=question["usage"],
        group=question["group"],
        unit=question["unit"],
        prompt_hash=question["prompt_hash"],
        seed=seed,
        think=False,
        num_ctx=question["num_ctx"],
        status=status,
        output=output,
        call_cap_reached=call_cap_reached,
    )


def run_conversation(question: dict[str, Any], steps_by_turn: list[list[list[tuple]]]) -> list:
    """Simule le runner (contrat d'outils de la story 5) : ``make_env``, puis ``env.call`` par
    appel, contenus ``tool`` dans l'ordre ; une réponse texte clôt chaque tour."""
    env = make_env(question["env"])
    output: list[dict] = []
    for turn, steps in enumerate(steps_by_turn):
        if turn > 0:
            output.append({"turn": turn, "role": "user", "content": f"Tour {turn + 1}"})
        for step in steps:
            calls = [tool_call(name, arguments) for name, arguments in step]
            output.append(assistant(turn=turn, tool_calls=calls))
            for name, arguments in step:
                output.append({"turn": turn, "role": "tool", "content": env.call(name, arguments)})
        output.append(assistant("Fait.", turn=turn))
    return output


GOOD_STEPS = [
    [[("cd", {"folder": "docs"})], [("mkdir", {"dir_name": "tmp"})]],
    [[("sort", {"file_name": "a.txt"})]],
]
