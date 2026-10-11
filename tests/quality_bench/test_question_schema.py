"""Schéma de question ``qb.question/1``, liste fermée des sources et sources refusées (AD-5)."""

import copy

import pytest

from scripts.quality_bench.common.canonical import sha256_hex
from scripts.quality_bench.questions import schema
from scripts.quality_bench.questions.schema import (
    REFUSED_SOURCES,
    SOURCES,
    QuestionError,
    validate_question,
    with_hashes,
)

from .factories import question


def test_reference_question_validates():
    record = question()
    assert validate_question(record) == record


def test_hashes_follow_ad4():
    record = question()
    prompt_keys = ("messages", "turns", "tools", "format", "env", "num_ctx")
    assert record["prompt_hash"] == sha256_hex({k: record[k] for k in prompt_keys})
    assert record["target_hash"] == sha256_hex(
        {"target": record["target"], "criteria": record["criteria"]}
    )
    body = {k: v for k, v in record.items() if k not in schema.HASH_FIELDS}
    assert record["question_hash"] == sha256_hex(body)


def test_refused_sources_cover_every_exclusion():
    assert set(REFUSED_SOURCES) == {
        "ifeval",
        "ifeval-fr",
        "fquad",
        "gsm-symbolic",
        "math-500",
        "musr",
        "bfcl-non-live-ast",
        "bfcl-web-search",
    }
    assert not set(REFUSED_SOURCES) & set(SOURCES)


def test_every_source_is_coherent():
    for slug, spec in SOURCES.items():
        assert spec.slug == slug
        assert spec.usage in schema.USAGES
        assert spec.license in schema.LICENSES
        assert spec.grader in schema.GRADERS
        assert spec.private == (spec.license == "private")
        assert spec.producer.endswith(".py")


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"source": "ifeval", "id": "instructions/ifeval/0001"}, "refusée"),
        ({"source": "fquad", "id": "rag/fquad/0001"}, "refusée"),
        ({"source": "inconnue", "id": "reasoning/inconnue/0001"}, "liste fermée"),
        ({"license": "MIT"}, "licence"),
        ({"usage": "rag", "id": "rag/bbeh-mini/0001"}, "usage"),
        ({"private": True}, "privé"),
        ({"id": "reasoning/bbeh-mini/12"}, "identifiant"),
        ({"id": "reasoning/ifbench/0001"}, "identifiant"),
        ({"group": "a|b"}, "«"),
        ({"generator": "x@1"}, "generator"),
        ({"criteria": [{"id": "c1", "question": "Oui ?"}]}, "criteria"),
        ({"target": 1.5}, "flottant"),
        ({"target": "é"}, "NFC"),
        ({"grader": {"name": "ifbench", "params": {}}}, "correcteur"),
        ({"extra": 1}, "qb.question/1"),
    ],
)
def test_invalid_questions_refused(overrides, message):
    record = question(**overrides)
    with pytest.raises(QuestionError, match=message):
        validate_question(with_hashes(record))


def test_hash_mismatch_refused():
    record = question()
    record["messages"] = copy.deepcopy(record["messages"])
    record["messages"][0]["content"] = "autre"
    with pytest.raises(QuestionError, match="prompt_hash"):
        validate_question(record)


def test_missing_field_refused():
    record = question()
    del record["unit"]
    with pytest.raises(QuestionError, match="unit"):
        validate_question(record)


def test_integer_fields_refuse_floats_and_booleans():
    for value in (4096.0, True):
        with pytest.raises(QuestionError):
            validate_question(with_hashes(question(num_ctx=value)))


def test_question_schema_is_valid_json_schema():
    from scripts.quality_bench.common.schemas import check_schema

    check_schema(schema.QUESTION_V1)


def test_chat_messages_are_closed():
    record = question(messages=[{"role": "user", "content": "Q ?", "images": []}])
    with pytest.raises(QuestionError, match="qb.question/1"):
        validate_question(record)


STORY3_SOURCES = {
    # slug: (usage, licence, producteur, correcteur, privé)
    "var-math-fr": (
        "reasoning",
        "private",
        "questions/generators/var_math.py",
        "exact_answer",
        True,
    ),
    "oneruler-fr-niah": (
        "rag",
        "MIT",
        "questions/generators/oneruler_fr.py",
        "oneruler_niah",
        False,
    ),
    "oneruler-fr-cwe": ("rag", "MIT", "questions/generators/oneruler_fr.py", "oneruler_cwe", False),
    "oneruler-fr-none": (
        "abstention",
        "MIT",
        "questions/generators/oneruler_fr.py",
        "oneruler_niah",
        False,
    ),
    "instructions-fr": ("instructions", "private", "questions/house.py", "mifeval_fr", True),
    "tools-fr": ("tools", "private", "questions/house.py", "bfcl_ast", True),
    "extraction-fr": ("extraction", "private", "questions/house.py", "json_schema", True),
    "abstention-fr": ("abstention", "private", "questions/house.py", "abstention_marker", True),
    "writing-fr": ("writing", "MIT", "questions/house.py", "judge_criteria", False),
}


@pytest.mark.parametrize("slug", sorted(STORY3_SOURCES))
def test_story3_sources_declared(slug):
    usage, license_, producer, grader, private = STORY3_SOURCES[slug]
    spec = SOURCES[slug]
    assert (spec.usage, spec.license, spec.producer, spec.grader, spec.private) == (
        usage,
        license_,
        producer,
        grader,
        private,
    )
    assert spec.generated == producer.startswith("questions/generators/")


def test_story3_graders_registered():
    assert {"oneruler_niah", "oneruler_cwe", "abstention_marker", "judge_criteria"} <= set(
        schema.GRADERS
    )


def test_every_producer_module_exists():
    from scripts.quality_bench.common.paths import PACKAGE_DIR

    for spec in SOURCES.values():
        assert (PACKAGE_DIR / spec.producer).is_file(), spec.producer


def test_set_hash_is_order_independent():
    first = question()
    second = question(id="reasoning/bbeh-mini/0002", unit="reasoning/bbeh-mini/0002")
    tracks = {"think_off": [first["id"], second["id"]], "think_on": [first["id"]]}
    pairs = sorted([q["id"], q["question_hash"]] for q in (first, second))
    expected = sha256_hex({"questions": pairs, "tracks": tracks})
    assert schema.set_hash([first, second], tracks) == expected
    assert schema.set_hash([second, first], tracks) == expected
    assert schema.set_hash([first, second], {**tracks, "think_on": []}) != expected
