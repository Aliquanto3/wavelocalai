"""Schémas ``qb.generation/1`` et ``qb.manifest/1`` (AD-7, AD-8)."""

import pytest

from scripts.quality_bench.common.schemas import (
    SchemaValidationError,
    UnknownSchemaError,
    check_schemas,
    validate,
)
from tests.quality_bench.factories import HASH_A, JUDGE, generation_record, manifest


def test_declared_schemas_are_valid_json_schemas():
    check_schemas()


def test_reference_records_validate():
    assert validate(generation_record()) == "qb.generation/1"
    assert validate(manifest()) == "qb.manifest/1"


@pytest.mark.parametrize("schema", ["qb.generation/2", "qb.manifest/0", "qb.unknown/1", "x", None])
def test_unknown_schema_refused(schema):
    with pytest.raises(UnknownSchemaError):
        validate(generation_record(schema=schema))


def test_missing_schema_refused():
    record = generation_record()
    del record["schema"]
    with pytest.raises(UnknownSchemaError):
        validate(record)


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"extra": 1}, "(racine)"),
        ({"status": "failed"}, "status"),
        ({"track": "think_maybe"}, "track"),
        ({"usage": "chat"}, "usage"),
        ({"seed": 1.0}, "seed"),
        ({"seed": True}, "seed"),
        ({"manifest": "ABC"}, "manifest"),
        ({"created_at": "2026-10-15 08:12:03"}, "created_at"),
        ({"backend": "vllm"}, "backend"),
    ],
)
def test_generation_field_errors_name_the_field(overrides, field):
    with pytest.raises(SchemaValidationError) as excinfo:
        validate(generation_record(**overrides))
    assert excinfo.value.path == field


def test_generation_closed_nested_objects():
    record = generation_record()
    record["tokens"]["reasoning"] = 3
    with pytest.raises(SchemaValidationError, match="tokens"):
        validate(record)
    record = generation_record()
    record["output"][1]["thinking"] = "x"  # message d'outil : pas de réflexion
    with pytest.raises(SchemaValidationError):
        validate(record)


def test_generation_required_fields():
    record = generation_record()
    del record["call_cap_reached"]
    with pytest.raises(SchemaValidationError):
        validate(record)


def test_manifest_phase_judgment_requires_judge_and_generation_manifest():
    judgment = manifest(phase="judgment")
    with pytest.raises(SchemaValidationError):
        validate(judgment)
    judgment["blocking"]["judge"] = dict(JUDGE)
    judgment["blocking"]["generation_manifest"] = HASH_A
    assert validate(judgment) == "qb.manifest/1"


def test_manifest_phase_generation_forbids_judge():
    record = manifest()
    record["blocking"]["judge"] = dict(JUDGE)
    with pytest.raises(SchemaValidationError):
        validate(record)


def test_manifest_closed_sections():
    record = manifest()
    record["blocking"]["extra"] = 1
    with pytest.raises(SchemaValidationError):
        validate(record)
    record = manifest()
    record["informative"]["gpu"] = "RTX 3050"
    with pytest.raises(SchemaValidationError):
        validate(record)
