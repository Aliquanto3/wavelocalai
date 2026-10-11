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
