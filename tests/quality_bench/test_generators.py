"""Générateurs à graine (VAR-MATH FR, OneRuler FR), sur des entrées synthétiques seulement."""

from __future__ import annotations

import json
import string
from collections import Counter

import pytest

from scripts.quality_bench.questions.build import CONTEXT_MARGIN, max_cap
from scripts.quality_bench.questions.generators import oneruler_fr, var_math
from scripts.quality_bench.questions.generators.var_math import GeneratorError
from scripts.quality_bench.questions.schema import validate_question

from .set_factories import synthetic_problems

# --- VAR-MATH --------------------------------------------------------------------------------


def _doc(**problem):
    base = {
        "number": 1,
        "text": "Synthétique : {a} et {b} ?",
        "params": {"a": {"min": 1, "max": 20}, "b": {"min": 1, "max": 20, "step": 2}},
        "constraints": ["a < b"],
        "answer": "a * b",
    }
    base.update(problem)
    return {"schema": "qb.var_math/1", "problems": [base]}


def test_var_math_variants_share_unit_and_group():
    questions = var_math.generate(synthetic_problems(4), seed=11, variants=3)
    assert len(questions) == 12
    for question in questions:
        assert validate_question(question) == question
        assert question["private"] and question["license"] == "private"
        assert question["generator"] == "var_math_fr@1" and question["generator_seed"] == 11
        assert question["grader"] == {
            "name": "exact_answer",
            "params": {"answer_prefix": "La réponse est :"},
        }
        assert isinstance(question["target"], int) and not isinstance(question["target"], bool)
        assert question["messages"][0]["content"].endswith("sans unité.")
        assert "« La réponse est : <entier> »" in question["messages"][0]["content"]
    units = Counter(q["unit"] for q in questions)
    assert set(units.values()) == {3}
    assert all(q["group"] == q["unit"] for q in questions)
    assert questions[0]["group"] == "reasoning/var-math-fr/p0001"
    texts = [q["messages"][0]["content"] for q in questions if q["unit"].endswith("p0001")]
    assert len(set(texts)) == 3


def test_var_math_is_deterministic_and_seed_dependent():
    problems = synthetic_problems(3)
    first = var_math.generate(problems, seed=5)
    assert first == var_math.generate(problems, seed=5)
    other = var_math.generate(problems, seed=6)
    assert [q["question_hash"] for q in first] != [q["question_hash"] for q in other]


def test_var_math_answer_matches_rendered_parameters():
    problems = var_math.parse_problems(_doc(derived={"c": "a * b - a"}, answer="c // 1 + 0"))
    for question in var_math.generate(problems, seed=3):
        text = question["messages"][0]["content"]
        a, b = (int(x) for x in text.split(":", 1)[1].split("?")[0].split(" et "))
        assert question["target"] == a * b - a and a < b


def test_var_math_derived_values_can_appear_in_text():
    problems = var_math.parse_problems(
        _doc(text="Synthétique : {a}, {b}, soit {s} ?", derived={"s": "a + b"})
    )
    content = var_math.generate(problems, seed=1)[0]["messages"][0]["content"]
    a, b, s = (
        int(x) for x in content.split(":", 1)[1].split("?")[0].replace("soit", "").split(",")
    )
    assert s == a + b


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "a.real",
        "open(a)",
        "print(a)",
        "min(a=1)",
        "a / b",
        "1.5 * a",
        "[a, b]",
        "a if b else 1",
        "lambda: 1",
        "'texte'",
        "True",
        "_secret",
    ],
)
def test_dangerous_or_forbidden_expressions_refused(expression):
    with pytest.raises(GeneratorError):
        var_math.parse_problems(_doc(answer=expression))


def test_allowed_operators_evaluate_on_integers():
    tree = var_math.parse_expression(
        "max(a, b) ** 2 // 3 % 7 - abs(-a) + min(a, b) * (a >= 1 and not b < 0 or 0)", "t"
    )
    a, b = 4, 9
    assert var_math.evaluate(tree, {"a": a, "b": b}) == (
        max(a, b) ** 2 // 3 % 7 - abs(-a) + min(a, b) * (a >= 1 and not b < 0 or 0)
    )


def test_zero_denominator_draws_are_rejected_not_fatal():
    problems = var_math.parse_problems(
        _doc(
            params={"a": {"min": 1, "max": 6}, "b": {"min": 1, "max": 6}},
            constraints=[],
            answer="a // (b - a) + a % (b - a)",
        )
    )
    for seed in range(20):
        for question in var_math.generate(problems, seed=seed):
            text = question["messages"][0]["content"]
            a, b = (int(x) for x in text.split(":", 1)[1].split("?")[0].split(" et "))
            assert a != b and question["target"] == a // (b - a) + a % (b - a)


def test_unbounded_exponent_is_rejected_as_a_draw():
    problems = var_math.parse_problems(_doc(answer="a ** b", constraints=["a < b", "b > 10"]))
    with pytest.raises(GeneratorError, match="variantes distinctes"):
        var_math.generate(problems, seed=1)


@pytest.mark.parametrize(
    "problem, message",
    [
        ({"constraints": ["a > 100"]}, "problème 1"),  # jamais satisfaites
        ({"params": {"a": {"min": 1, "max": 1}, "b": {"min": 2, "max": 2}}}, "distinctes"),
        ({"answer": "a < b"}, "non entière"),
        ({"text": "Sans paramètre {a} ?"}, "chaque paramètre"),
        ({"text": "{a} {b} {z} ?"}, "inconnus"),
        ({"answer": "a + z"}, "inconnus"),
        ({"color": 1}, "clés inconnues"),
        ({"params": {"a": {"min": 1.5, "max": 3}, "b": {"min": 1, "max": 3}}}, "entier"),
        ({"params": {"min": {"min": 1, "max": 3}}}, "invalide"),
    ],
)
def test_non_instantiable_problems_refused(problem, message):
    with pytest.raises(GeneratorError, match=message):
        var_math.generate(var_math.parse_problems(_doc(**problem)), seed=1)


def test_var_math_file_level_errors():
    with pytest.raises(GeneratorError):
        var_math.parse_problems({"schema": "qb.var_math/2", "problems": []})
    doc = _doc()
    doc["problems"].append(dict(doc["problems"][0]))
    with pytest.raises(GeneratorError, match="double"):
        var_math.parse_problems(doc)


# --- OneRuler FR -----------------------------------------------------------------------------


def _word(index: int) -> str:
    letters = string.ascii_lowercase
    word = ""
    index += 26**3
    while index:
        index, rest = divmod(index, 26)
        word = letters[rest] + word
    return word + "x"


SYNTHETIC_NIAH = {
    "task": "Lis le texte.\n\n<Texte>\n{context}\n</Texte>\n\n",
    "needle_numbers": 'Le nombre spécial pour "{key}" est : {value}',
    "question_single_numbers": '<Question> Quels nombres pour "{query1}" ?',
    "please_list": "Liste-les tous.",
    "if_no_numbers": 'Sinon, réponds "aucun".</Question>\n\n',
    "answer_prefix": "Format :\n",
    "answer_numbers": "<Réponse> nombres </Réponse>",
    "none": "aucun",
}


@pytest.fixture(scope="module")
def texts():
    """Livre synthétique : 6 000 mots inventés, en phrases de 10 mots."""
    words = [_word(i) for i in range(6000)]
    sentences = [" ".join(words[i : i + 10]).capitalize() + "." for i in range(0, 6000, 10)]
    return oneruler_fr.parse_texts(
        "\n".join(sentences),
        json.dumps(SYNTHETIC_NIAH, ensure_ascii=False),
        "Liste : <Liste> {context} </Liste> Quels sont les 10 mots les plus courants ?",
    )


def _limit(tier, usage="rag"):
    return (tier - max_cap(usage)) / CONTEXT_MARGIN


def _check_filled(question, tier, usage="rag"):
    assert validate_question(question) == question
    assert question["num_ctx"] == tier
    assert question["est_prompt_tokens"] <= _limit(tier, usage)
    previous = oneruler_fr.TIERS.index(tier) - 1
    floor = _limit(oneruler_fr.TIERS[previous], usage) if previous >= 0 else 0
    assert question["est_prompt_tokens"] > max(floor, _limit(tier, usage) - 100)
    assert question["generator"] == "oneruler_fr@1" and question["license"] == "MIT"
    assert not question["private"]
    assert question["group"] == f"{question['source']}/{question['id'][-4:]}"


def test_parse_texts_vocabulary(texts):
    assert texts.vocabulary == tuple(sorted(set(texts.vocabulary)))
    assert all(len(w) >= 4 and w.isalpha() and w == w.lower() for w in texts.vocabulary)


def test_niah_variants_tiers_and_needles(texts):
    questions = oneruler_fr.generate_niah(texts, seed=3, count=9)
    variants = Counter((q["num_ctx"], q["grader"]["params"]["variant"]) for q in questions)
    assert set(variants.values()) == {1} and len(variants) == 9
    for question in questions:
        _check_filled(question, question["num_ctx"])
        content = question["messages"][0]["content"]
        variant = question["grader"]["params"]["variant"]
        assert question["grader"]["params"]["none_answer"] == "aucun"
        expected = 4 if variant == "multivalue" else 1
        assert len(question["target"]) == expected
        for value in question["target"]:
            assert len(value) == 7 and value.isdigit() and value in content
        needles = content.count("Le nombre spécial pour")
        assert needles == (4 if variant in ("multikey", "multivalue") else 1)
        query = content.split('<Question> Quels nombres pour "')[1].split('"')[0]
        for value in question["target"]:  # chaque valeur est dans l'aiguille de la clé demandée
            assert f'Le nombre spécial pour "{query}" est : {value}.' in content


def test_none_variant_queries_an_absent_key(texts):
    for question in oneruler_fr.generate_none(texts, seed=4, count=3):
        _check_filled(question, question["num_ctx"], usage="abstention")
        assert question["target"] is None and question["usage"] == "abstention"
        content = question["messages"][0]["content"]
        query = content.split('<Question> Quels nombres pour "')[1].split('"')[0]
        assert f'pour "{query}" est' not in content
        assert content.count("Le nombre spécial pour") == 4


def test_cwe_levels_and_common_words(texts):
    questions = oneruler_fr.generate_cwe(texts, seed=5, count=6)
    levels = Counter((q["num_ctx"], q["grader"]["params"]["level"]) for q in questions)
    assert len(levels) == 6
    for question in questions:
        _check_filled(question, question["num_ctx"])
        params = question["grader"]["params"]
        listed = question["messages"][0]["content"].split("<Liste> ")[1].split(" </Liste>")[0]
        words = Counter(item.split(". ", 1)[1] for item in _entries(listed))
        assert len(question["target"]) == 10 and question["target"] == sorted(question["target"])
        assert all(words[word] == params["common_repeats"] for word in question["target"])
        others = {w: n for w, n in words.items() if w not in question["target"]}
        assert set(others.values()) == {params["uncommon_repeats"]}


def _entries(listed):
    import re

    return re.findall(r"\d+\. [a-z]+", listed)


def test_oneruler_is_deterministic(texts):
    first = oneruler_fr.generate_niah(texts, seed=9, count=3)
    assert first == oneruler_fr.generate_niah(texts, seed=9, count=3)
    other = oneruler_fr.generate_niah(texts, seed=10, count=3)
    assert [q["question_hash"] for q in first] != [q["question_hash"] for q in other]


def test_parse_texts_refuses_incomplete_templates():
    with pytest.raises(GeneratorError):
        oneruler_fr.parse_texts("Phrase.", json.dumps({"task": "{context}"}), "{context}")


def test_raw_files_are_pinned_and_exclude_vocab():
    paths = [remote.path for remote in oneruler_fr.RAW_FILES]
    assert not any("vocab" in path for path in paths)
    assert all(len(remote.sha256) == 64 for remote in oneruler_fr.RAW_FILES)
    assert {remote.revision for remote in oneruler_fr.RAW_FILES} == {
        "a3fe6af862dc4b30794afc0a8f3d4f60758cecfa"
    }
