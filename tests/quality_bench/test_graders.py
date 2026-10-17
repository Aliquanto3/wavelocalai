"""Correcteurs (AD-10) : un cas à verdict connu par correcteur, sur sorties synthétiques, et
ordre des statuts de ``grade_line``."""

from __future__ import annotations

import random

import pytest

from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.grading import registry
from scripts.quality_bench.grading.registry import GRADERS, grade_line
from scripts.quality_bench.questions.schema import GRADERS as GRADER_NAMES

from .factories import HASH_A
from .grading_factories import (
    CWE_WORDS,
    GOOD_STEPS,
    answer_output,
    assistant,
    generation_for,
    questions,
    run_conversation,
    tool_call,
)
from .set_factories import synthetic_question


@pytest.fixture(scope="module")
def q():
    return questions()


def _grade(question, output, verdicts=None, **generation):
    line = grade_line(question, generation_for(question, output, **generation), verdicts)
    record = {**line.record, "generation_manifest": HASH_A, "judgment_manifest": None}
    validate(record)  # chaque ligne valide qb.grading/1
    return record


def _outcome(record):
    return record["status"], record["score"], record["success"]


def test_registry_has_the_twelve_graders_at_version_one():
    assert set(GRADERS) == set(GRADER_NAMES)
    assert len(GRADERS) == 12
    assert all(
        registered.version == f"{name}@{2 if name == 'json_schema' else 1}"
        for name, registered in GRADERS.items()
    )


def test_langdetect_seed_fixed_by_registry():
    from langdetect import DetectorFactory

    assert DetectorFactory.seed == 0


# --- Raisonnement ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content, success",
    [
        ("Calcul…\nLa réponse est : **1 234**.", True),
        ("la réponse est: $\\boxed{1234}$", True),
        ("La Réponse Est :\n\n1234\nPuis du texte.", True),
        ("La réponse est : 12. Non : La réponse est : 1234", True),
        ("La réponse est : 1235", False),
        ("La réponse est : mille deux cent trente-quatre", False),
        ("1234", False),  # sans préfixe : échec
        ("La réponse est : " + "9" * 5000, False),  # entier illisible (plus de 4300 chiffres)
    ],
)
def test_exact_answer_integer_target(q, content, success):
    record = _grade(q["var_math"], answer_output(content))
    assert _outcome(record) == ("ok", 1.0 if success else 0.0, success)


@pytest.mark.parametrize(
    "content, success",
    [("Raisonnement. The answer is: (A)", True), ("The answer is: b", False)],
)
def test_exact_answer_string_target_uses_bbeh(q, content, success):
    assert _grade(q["bbeh"], answer_output(content))["success"] is success


# --- Consignes ---------------------------------------------------------------------------


def test_ifbench_all_followed(q, bench_nltk_data):
    record = _grade(q["ifbench"], answer_output("J'aime la banane. Rien d'autre"))
    assert _outcome(record) == ("ok", 1.0, True)
    assert record["metrics"]["instructions_followed"] == 1.0


def test_ifbench_partly_followed(q, bench_nltk_data):
    record = _grade(q["ifbench"], answer_output("La banane, la pomme"))
    assert _outcome(record) == ("ok", 0.0, False)
    assert record["metrics"]["instructions_followed"] == 0.5


def test_empty_answer_follows_nothing(q, bench_nltk_data):
    record = _grade(q["ifbench"], answer_output("   "))
    assert record["success"] is False
    assert record["metrics"]["instructions_followed"] == 0.0


def test_mifeval_fr_uses_french_punkt(q, bench_nltk_data):
    one = _grade(q["mifeval"], answer_output("Une seule phrase ici."))
    three = _grade(q["mifeval"], answer_output("Première phrase. Deuxième phrase. Troisième."))
    assert one["success"] is True
    assert three["success"] is False


def test_unknown_instruction_id_is_a_bench_error(q, bench_nltk_data):
    question = {
        **q["mifeval"],
        "grader": {
            "name": "mifeval_fr",
            "params": {
                "key": "1",
                "instruction_id_list": ["fr:inconnu:consigne"],
                "kwargs": [{}],
            },
        },
    }
    record = _grade(question, answer_output("Réponse."))
    assert _outcome(record) == ("error", None, None)


def test_verifier_exception_is_a_bench_error(q, bench_nltk_data):
    question = {
        **q["mifeval"],
        "grader": {
            "name": "mifeval_fr",
            "params": {
                "key": "1",
                "instruction_id_list": ["fr:length_constraints:number_sentences"],
                "kwargs": [
                    {"num_sentences": 2, "relation": "environ"}
                ],  # relation refusée (ValueError)
            },
        },
    }
    assert _grade(question, answer_output("Réponse."))["status"] == "error"


def test_instruction_graders_restore_global_random(q, bench_nltk_data):
    random.seed(1234)
    expected = random.random()
    random.seed(1234)
    _grade(q["ifbench"], answer_output("banane"))
    assert random.random() == expected


def test_missing_nltk_resource_is_a_bench_error(q, bench_nltk_data, monkeypatch):
    """Une ressource NLTK absente lève ``LookupError`` dans le vérificateur : ``error``."""
    from scripts.quality_bench.grading.vendored.mifeval_fr.instruction_utils import (
        fr_instructions_util,
    )

    def missing(text):
        raise LookupError("ressource absente")

    monkeypatch.setattr(fr_instructions_util, "count_sentences", missing)
    record = _grade(q["mifeval"], answer_output("Une phrase."))
    assert _outcome(record) == ("error", None, None)


def test_nltk_data_read_from_bench_directory_only(tmp_path):
    """Sans fetch-nltk (racine des données vide), toutes les ressources manquent : NLTK ne
    cherche que sous $QUALITY_BENCH_DATA/nltk_data."""
    import nltk

    from scripts.quality_bench.common import paths
    from scripts.quality_bench.grading import nlp

    before = list(nltk.data.path)
    assert nlp.missing_resources() == list(nlp.RESOURCES)
    with nlp.bench_data() as directory:
        assert nltk.data.path == [str(paths.nltk_data_dir())] == [directory]
    assert nltk.data.path == before  # aucun état global durable


def test_instruction_graders_restore_nltk_path(q, bench_nltk_data):
    import nltk

    before = list(nltk.data.path)
    assert _grade(q["mifeval"], answer_output("Une phrase."))["status"] == "ok"
    assert nltk.data.path == before


# --- Outils ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arguments, success",
    [
        ({"city": "paris", "days": 2.5}, True),  # chaîne normalisée, flottant décodé
        ({"city": "Paris", "unit": "c", "days": 2.5}, True),
        ({"city": "Lyon", "days": 2.5}, False),
        ({"city": "Paris", "days": 3.0}, False),
        ({"city": "Paris", "days": 2.5, "autre": 1}, False),
    ],
)
def test_bfcl_ast(q, arguments, success):
    output = [assistant(tool_calls=[tool_call("weather_get", arguments)])]
    assert _grade(q["bfcl_ast"], output)["success"] is success


def test_bfcl_ast_wrong_count_and_no_call_fail(q):
    call = tool_call("weather_get", {"city": "Paris", "days": 2.5})
    assert _grade(q["bfcl_ast"], [assistant(tool_calls=[call, call])])["success"] is False
    assert _grade(q["bfcl_ast"], answer_output("Il fait beau."))["success"] is False


@pytest.mark.parametrize(
    "call",
    [
        {"function": {"name": "weather_get", "arguments": '{"city": "Paris"}'}},
        {"function": {"arguments": {"city": "Paris"}}},
    ],
)
def test_malformed_tool_call_is_non_compliant(q, call):
    record = _grade(q["bfcl_ast"], [assistant(tool_calls=[call])])
    assert _outcome(record) == ("non_compliant", 0.0, False)


def test_unreadable_bfcl_target_is_a_bench_error(q):
    question = {**q["bfcl_ast"], "target": "pas une liste"}
    output = [assistant(tool_calls=[tool_call("weather_get", {"city": "Paris"})])]
    assert _grade(question, output)["status"] == "error"


def test_bfcl_irrelevance(q):
    assert _grade(q["irrelevance"], answer_output("Je ne peux pas."))["success"] is True
    call = tool_call("weather_get", {"city": "Paris"})
    assert _grade(q["irrelevance"], [assistant(tool_calls=[call])])["success"] is False


def test_bfcl_state_replays_and_scores_the_final_state(q):
    record = _grade(q["bfcl_multi"], run_conversation(q["bfcl_multi"], GOOD_STEPS))
    assert _outcome(record) == ("ok", 1.0, True)


def test_bfcl_state_wrong_state_fails(q):
    steps = [[[("cd", {"folder": "docs"}), ("mkdir", {"dir_name": "autre"})]], GOOD_STEPS[1]]
    record = _grade(q["bfcl_multi"], run_conversation(q["bfcl_multi"], steps))
    assert _outcome(record) == ("ok", 0.0, False)


def test_bfcl_state_missing_calls_in_a_turn_fail(q):
    record = _grade(q["bfcl_multi"], run_conversation(q["bfcl_multi"], [GOOD_STEPS[0], []]))
    assert _outcome(record) == ("ok", 0.0, False)


def test_bfcl_state_modified_tool_content_is_a_bench_error(q):
    output = run_conversation(q["bfcl_multi"], GOOD_STEPS)
    index = next(i for i, m in enumerate(output) if m["role"] == "tool")
    output[index] = {**output[index], "content": output[index]["content"] + " "}
    assert _outcome(_grade(q["bfcl_multi"], output)) == ("error", None, None)


def test_bfcl_state_missing_turn_is_a_bench_error(q):
    output = [m for m in run_conversation(q["bfcl_multi"], GOOD_STEPS) if m["turn"] == 0]
    assert _grade(q["bfcl_multi"], output)["status"] == "error"


def test_bfcl_state_unreadable_target_call_is_a_bench_error(q):
    question = {**q["bfcl_multi"], "target": [["cd(folder=open('x'))"], ["ls()"]]}
    output = run_conversation(question, GOOD_STEPS)
    assert _grade(question, output)["status"] == "error"


# --- Extraction --------------------------------------------------------------------------


def test_json_schema_conforming_fenced_answer(q):
    record = _grade(q["jsonschema"], answer_output('```json\n{"nom": "x", "age": 3}\n```'))
    assert _outcome(record) == ("ok", 1.0, True)


@pytest.mark.parametrize(
    "content",
    ["pas du JSON", '{"nom": "x"}', '{"nom": "x", "age": "3"}', '{"nom": "x", "age": 3'],
)
def test_json_schema_unreadable_or_off_schema_is_non_compliant(q, content):
    record = _grade(q["jsonschema"], answer_output(content))
    assert _outcome(record) == ("non_compliant", 0.0, False)
    assert "f1" not in record["metrics"]
    extraction = _grade(q["extraction"], answer_output(content))
    assert extraction["status"] == "non_compliant"
    assert extraction["metrics"]["f1"] == 0.0


def test_json_schema_standard_integers(q):
    assert _grade(q["jsonschema"], answer_output('{"nom": "x", "age": 3.0}'))["success"] is True


def test_extraction_leaves(q):
    full = _grade(
        q["extraction"], answer_output('{"nom": "jeanne martin", "age": 40.0, "actif": true}')
    )
    assert _outcome(full) == ("ok", 1.0, True)
    assert full["metrics"]["f1"] == 1.0
    partial = _grade(q["extraction"], answer_output('{"nom": "Jeanne Martin", "age": 41}'))
    assert _outcome(partial) == ("ok", 0.0, False)
    assert partial["metrics"]["f1"] == pytest.approx(2 * 0.5 * (1 / 3) / (0.5 + 1 / 3))


def test_leaf_comparison_rules():
    from scripts.quality_bench.grading.extraction import leaf_scores

    assert leaf_scores({"a": True}, {"a": 1}) == (False, 0.0)  # booléen distinct d'un nombre
    assert leaf_scores({"a": 2}, {"a": 2.0}) == (True, 1.0)  # nombres par valeur
    assert leaf_scores({"a": ["X  y"]}, {"a": ["x y"], "b": 1})[0] is True
    assert leaf_scores({"a": {"b": "c"}}, {"a": {}}) == (False, 0.0)
    # Chemins en segments : une clé pointée ne se confond pas avec un objet imbriqué.
    assert leaf_scores({"a.b": 1}, {"a": {"b": 1}}) == (False, 0.0)
    assert leaf_scores({"a": {"0": 1}}, {"a": [1]}) == (False, 0.0)
    assert leaf_scores({"a": [1, 2]}, {"a": [2, 1]}) == (False, 0.0)  # listes par position


def test_extraction_float_target_is_decoded(q):
    question = synthetic_question(
        "extraction-fr",
        2,
        grader_params={
            "schema": {"type": "object", "properties": {"montant": {"type": "number"}}},
            "subset": "extraction-fr",
        },
        target={"montant": 12.5},
    )
    assert question["target"] == {"montant": {"$float": "12.5"}}
    record = _grade(question, answer_output('{"montant": 12.5}'))
    assert _outcome(record) == ("ok", 1.0, True)
    assert record["metrics"]["f1"] == 1.0


def test_unverifiable_schema_is_a_bench_error(q):
    question = {
        **q["jsonschema"],
        "grader": {
            "name": "json_schema",
            "params": {"schema": {"$ref": "https://example.invalid/schema.json"}, "subset": "x"},
        },
    }
    assert _grade(question, answer_output("{}"))["status"] == "error"


# --- RAG ---------------------------------------------------------------------------------


def test_squad_f1(q):
    exact = _grade(q["piaf"], answer_output("Tour Eiffel."))
    assert _outcome(exact) == ("ok", 1.0, True)
    assert exact["metrics"]["f1"] == 1.0
    apostrophe = _grade(q["piaf"], answer_output("L'Eiffel"))
    assert apostrophe["success"] is True
    partial = _grade(q["piaf"], answer_output("la grande tour"))
    assert partial["success"] is False
    assert partial["metrics"]["f1"] == pytest.approx(0.5)


def test_squad_f1_ignores_answers_empty_after_normalization():
    question = synthetic_question("piaf", 2, target=["l'", "Eiffel"])
    assert _grade(question, answer_output(""))["success"] is False
    assert _grade(question, answer_output("Eiffel"))["success"] is True
    only_empty = synthetic_question("piaf", 3, target=["la", "« »"])
    assert _outcome(_grade(only_empty, answer_output(""))) == ("error", None, None)


def test_oneruler_niah(q):
    assert _grade(q["niah"], answer_output("Le nombre est 1234567."))["success"] is True
    assert _grade(q["niah"], answer_output("1234568"))["success"] is False
    assert _grade(q["niah"], answer_output("aucun"))["success"] is False
    assert _grade(q["none"], answer_output("Aucun."))["success"] is True
    assert _grade(q["none"], answer_output("1234567"))["success"] is False


def test_oneruler_cwe(q):
    assert _grade(q["cwe"], answer_output(", ".join(reversed(CWE_WORDS))))["success"] is True
    assert _grade(q["cwe"], answer_output(", ".join(CWE_WORDS[:9])))["success"] is False


# --- Abstention --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content, success",
    [
        ("JE NE SAIS PAS", True),
        ("« Je ne sais pas. »", True),
        ("**je ne sais pas**", True),
        ("`Je ne sais pas`.", True),
        ("Je ne sais pas, désolé.", False),
        ("Paris", False),
    ],
)
def test_abstention_marker(q, content, success):
    assert _grade(q["abstention"], answer_output(content))["success"] is success


def test_abstention_marker_is_stripped_like_the_answer():
    question = synthetic_question(
        "abstention-fr", 2, grader_params={"marker": "« Je ne sais pas. »"}
    )
    assert _grade(question, answer_output("je ne sais pas"))["success"] is True


# --- Rédaction ---------------------------------------------------------------------------


def _verdicts(*values):
    return {
        f"c{index}": {"verdict": value, "error": None if value is not None else "panne"}
        for index, value in enumerate(values, start=1)
    }


def test_judge_criteria_scores_share_of_true_verdicts(q):
    record = _grade(q["writing"], answer_output("Texte."), _verdicts(True, True, False, True))
    assert _outcome(record) == ("ok", 0.75, None)


def test_judge_criteria_missing_verdict_awaits(q):
    verdicts = _verdicts(True, True, True)
    assert _grade(q["writing"], answer_output("Texte."), verdicts)["status"] == (
        "awaiting_judgment"
    )
    assert _grade(q["writing"], answer_output("Texte."), None)["status"] == "awaiting_judgment"
    assert _grade(q["writing"], answer_output("Texte."), {})["status"] == "awaiting_judgment"


def test_judge_criteria_verdict_in_error(q):
    record = _grade(q["writing"], answer_output("Texte."), _verdicts(True, None))
    assert _outcome(record) == ("error", None, None)


# --- Ordre des statuts (grade_line) ------------------------------------------------------


@pytest.mark.parametrize(
    "status, expected",
    [
        ("truncated", ("truncated", 0.0, False)),
        ("context_exceeded", ("context_exceeded", None, None)),
        ("error", ("error", None, None)),
    ],
)
def test_generation_status_comes_first(q, status, expected):
    record = _grade(q["var_math"], answer_output("La réponse est : 1234"), status=status)
    assert _outcome(record) == expected
    assert record["metrics"] == {}


def test_truncated_writing_has_no_success(q):
    record = _grade(q["writing"], answer_output("Texte."), status="truncated")
    assert _outcome(record) == ("truncated", 0.0, None)


def test_call_cap_reached_is_non_compliant(q):
    output = run_conversation(q["bfcl_multi"], GOOD_STEPS)
    record = _grade(q["bfcl_multi"], output, call_cap_reached=True)
    assert _outcome(record) == ("non_compliant", 0.0, False)
    assert record["metrics"] == {"inline_thinking": 0.0}


def test_inline_thinking_metric_on_every_ok_line(q):
    record = _grade(q["var_math"], answer_output("<think>1233 ?</think>La réponse est : 1234"))
    assert _outcome(record) == ("ok", 1.0, True)
    assert record["metrics"] == {"inline_thinking": 1.0}
    assert _grade(q["piaf"], answer_output("Eiffel"))["metrics"]["inline_thinking"] == 0.0


def test_unexpected_grader_exception_is_a_bench_error(q, monkeypatch):
    def boom(question, generation, verdicts=None):
        raise RuntimeError("panne")

    monkeypatch.setitem(GRADERS, "squad_f1", registry.Registered("squad_f1@1", boom))
    assert _outcome(_grade(q["piaf"], answer_output("x"))) == ("error", None, None)


def test_graders_never_mutate_their_inputs(q, bench_nltk_data):
    import copy

    for name in ("bfcl_ast", "bfcl_multi", "ifbench", "extraction"):
        question = q[name]
        if name == "bfcl_multi":
            output = run_conversation(question, GOOD_STEPS)
        elif name == "bfcl_ast":
            output = [assistant(tool_calls=[tool_call("weather_get", {"city": "Paris"})])]
        else:
            output = answer_output('{"nom": "x", "age": 1}')
        generation = generation_for(question, output)
        before = copy.deepcopy((question, generation))
        grade_line(question, generation)
        assert (question, generation) == before
