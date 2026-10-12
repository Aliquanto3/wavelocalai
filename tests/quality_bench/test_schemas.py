"""Schémas ``qb.generation/1``, ``qb.warmup/1``, ``qb.manifest/1``, ``qb.grading/1`` et
``qb.judgment/1`` (AD-7, AD-8, AD-10, AD-14, AD-16), et vérification des sorties JSON
(``conformity_error``)."""

import pytest

from scripts.quality_bench.common.schemas import (
    SchemaValidationError,
    UnknownSchemaError,
    check_schemas,
    validate,
)
from tests.quality_bench.factories import HASH_A, HASH_B, JUDGE, generation_record, manifest


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


def _grading(**overrides):
    record = {
        "schema": "qb.grading/1",
        "key": "c|m|think_off|tools/bfcl-live/0001|0",
        "generation_manifest": HASH_A,
        "judgment_manifest": None,
        "grader": "bfcl_ast@1",
        "status": "ok",
        "score": 1.0,
        "success": True,
        "metrics": {"inline_thinking": 0.0},
    }
    record.update(overrides)
    return record


def _judgment(**overrides):
    record = {
        "schema": "qb.judgment/1",
        "key": "c|m|think_off|writing/writing-fr/0001|0|c1",
        "generation_key": "c|m|think_off|writing/writing-fr/0001|0",
        "manifest": HASH_A,
        "criterion": "c1",
        "judge": "haiku",
        "verdict": True,
        "probability": 0.91,
        "tokens": {"input": 0, "output": 0},
        "cost_usd": 0.0,
        "attempts": 1,
        "error": None,
        "created_at": "2026-10-15T08:12:03Z",
    }
    record.update(overrides)
    return record


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"score": 0.0, "success": False},
        {"status": "truncated", "score": 0, "success": False, "metrics": {}},
        {"status": "non_compliant", "score": 0.0, "success": False},
        {"status": "error", "score": None, "success": None, "metrics": {}},
        {"status": "context_exceeded", "score": None, "success": None, "metrics": {}},
        {"grader": "judge_criteria@1", "score": 0.75, "success": None, "judgment_manifest": HASH_B},
        {"grader": "judge_criteria@1", "status": "truncated", "score": 0.0, "success": None},
        {
            "grader": "judge_criteria@1",
            "status": "awaiting_judgment",
            "score": None,
            "success": None,
        },
        {"metrics": {"f1": 0.5, "instructions_followed": 1, "inline_thinking": 1.0}},
    ],
)
def test_grading_lines_validate(overrides):
    assert validate(_grading(**overrides)) == "qb.grading/1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"score": 0.0},  # success vrai : score 1
        {"success": False},  # success faux : score 0
        {"success": None},  # hors rédaction, une ligne notée a un succès
        {"status": "truncated"},  # échec du modèle : score 0
        {"status": "error"},  # erreur du banc : ni score ni succès
        {"status": "awaiting_judgment", "score": None, "success": False},
        {"status": "ok", "score": None, "success": None},
        {"grader": "judge_criteria@1", "score": 1.0, "success": True},
        {"grader": "bfcl_ast"},
        {"grader": "bfcl_ast@0"},
        {"score": 1.5, "success": None, "grader": "judge_criteria@1"},
        {"metrics": {"f1": "0.5"}},
        {"metrics": {"flag": True}},
        {"status": "failed"},
        {"judgment_manifest": "x"},
        {"extra": 1},
    ],
)
def test_grading_cross_rules(overrides):
    with pytest.raises(SchemaValidationError):
        validate(_grading(**overrides))


def test_judgment_lines():
    assert validate(_judgment()) == "qb.judgment/1"
    assert validate(_judgment(verdict=None, probability=None, error="délai dépassé"))
    for overrides in (
        {"verdict": None},  # nul sans erreur
        {"error": "panne"},  # verdict avec erreur
        {"probability": 1.5},
        {"tokens": {"input": 0}},
        {"extra": 1},
    ):
        with pytest.raises(SchemaValidationError):
            validate(_judgment(**overrides))


def test_conformity_error_follows_declared_draft_and_standard_integers():
    from scripts.quality_bench.common.schemas import conformity_error

    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    assert conformity_error(schema, {"n": 3}) is None
    assert conformity_error(schema, {"n": 3.0}) is None  # entier JSON standard
    assert conformity_error(schema, {"n": "3"}) == "n (type)"
    assert conformity_error(schema, {}) == "(racine) (required)"
    draft4 = {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "type": "number",
        "maximum": 5,
        "exclusiveMaximum": True,
    }
    assert conformity_error(draft4, 5) is not None  # sémantique draft-04 (booléen)
    assert conformity_error(draft4, 4) is None
    local_ref = {"$defs": {"x": {"type": "string"}}, "$ref": "#/$defs/x"}
    assert conformity_error(local_ref, "a") is None
    meta = {"$ref": "http://json-schema.org/draft-07/schema#"}
    assert conformity_error(meta, {"type": "string"}) is None  # métaschéma embarqué


def test_conformity_error_never_retrieves_remote_references(monkeypatch):
    import urllib.request

    from referencing.exceptions import NoSuchResource

    from scripts.quality_bench.common.schemas import conformity_error

    calls = []

    def no_network(*args, **kwargs):
        calls.append(args)
        raise AssertionError("accès réseau interdit")

    # Le registre par défaut de jsonschema passerait par urllib.request.urlopen.
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    with pytest.raises(Exception) as excinfo:  # noqa: B017 (chaîne d'exceptions vérifiée)
        conformity_error({"$ref": "https://example.invalid/schema.json"}, {})
    assert calls == []
    chain, error = [], excinfo.value
    while error is not None:
        chain.append(error)
        error = error.__cause__ or error.__context__
    assert any(isinstance(error, NoSuchResource) for error in chain)


def test_manifest_closed_sections():
    record = manifest()
    record["blocking"]["extra"] = 1
    with pytest.raises(SchemaValidationError):
        validate(record)
    record = manifest()
    record["informative"]["gpu"] = "RTX 3050"
    with pytest.raises(SchemaValidationError):
        validate(record)


def _warmup(**overrides):
    record = {
        "schema": "qb.warmup/1",
        "key": "pilot-20261015|qwen3.5:4b|8192|0",
        "manifest": HASH_A,
        "campaign": "pilot-20261015",
        "model": "qwen3.5:4b",
        "num_ctx": 8192,
        "prompt_tokens": 2000,
        "size": 4_000_000_000,
        "size_vram": 3_500_000_000,
        "prefill_tok_s": 812.5,
        "load_ns": 1_200_000_000,
        "created_at": "2026-10-15T08:00:00Z",
    }
    record.update(overrides)
    return record


def test_warmup_line_validates_with_unknown_values():
    assert validate(_warmup()) == "qb.warmup/1"
    validate(_warmup(size=None, size_vram=None, prefill_tok_s=None))


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"num_ctx": 0}, "num_ctx"),
        ({"prompt_tokens": -1}, "prompt_tokens"),
        ({"load_ns": None}, "load_ns"),
        ({"size": 1.5}, "size"),
        ({"prefill_tok_s": "rapide"}, "prefill_tok_s"),
        ({"manifest": "x"}, "manifest"),
        ({"extra": 1}, "(racine)"),
    ],
)
def test_warmup_line_is_closed_and_typed(overrides, field):
    with pytest.raises(SchemaValidationError) as excinfo:
        validate(_warmup(**overrides))
    assert excinfo.value.path == field


@pytest.mark.parametrize("name", [name for name in _warmup() if name != "schema"])
def test_warmup_requires_every_field(name):
    record = _warmup()
    del record[name]
    with pytest.raises(SchemaValidationError):
        validate(record)


# -- Exports d'une campagne (story 6) : qb.score/1, qb.report/1, qb.aa_reference/1 -----------


def _score(**overrides):
    record = {
        "schema": "qb.score/1",
        "question_hash": HASH_A,
        "model": "qwen3.5:4b",
        "digest": "sha256:" + "c" * 64,
        "track": "think_on",
        "seed": 0,
        "status": "ok",
        "score": 1.0,
        "success": True,
        "metrics": {"f1": 0.92, "inline_thinking": 0.0},
    }
    record.update(overrides)
    return record


def test_score_line_validates():
    assert validate(_score()) == "qb.score/1"
    validate(_score(status="error", score=None, success=None, metrics={}))


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"question_id": "tools/bfcl-multi/0042"}, "(racine)"),
        ({"key": "x"}, "(racine)"),
        ({"metrics": {"f1": "0,9"}}, "metrics.f1"),
        ({"score": 1.5}, "score"),
        ({"question_hash": "x"}, "question_hash"),
        ({"status": "failed"}, "status"),
    ],
)
def test_score_line_is_closed(overrides, field):
    with pytest.raises(SchemaValidationError) as excinfo:
        validate(_score(**overrides))
    assert excinfo.value.path == field


def _aa(**overrides):
    record = {
        "schema": "qb.aa_reference/1",
        "date": "2026-10-01",
        "source": "Artificial Analysis",
        "entries": [
            {"tag": "qwen3.5:4b", "index": 21.5, "status": "measured", "variant": "reasoning"}
        ],
    }
    record.update(overrides)
    return record


def test_aa_reference_validates():
    assert validate(_aa()) == "qb.aa_reference/1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"date": "01/10/2026"},
        {"entries": [{"tag": "m", "index": 1, "status": "guessed", "variant": "reasoning"}]},
        {"entries": [{"tag": "m", "index": 1, "status": "measured", "variant": "thinking"}]},
        {"entries": [{"tag": "m", "index": None, "status": "measured", "variant": "reasoning"}]},
        {"url": "https://artificialanalysis.ai"},
    ],
)
def test_aa_reference_is_closed(overrides):
    with pytest.raises(SchemaValidationError):
        validate(_aa(**overrides))


def _report():
    return {
        "schema": "qb.report/1",
        "campaign": "pilot-20261015",
        "partial": False,
        "set": {"id": "set-v1", "hash": HASH_A},
        "generation_manifest": HASH_A,
        "judgment_manifest": None,
        "k": 1,
        "method": {"alpha": 0.05, "bootstrap_resamples": 2000, "bootstrap_seed": 1},
        "completeness": {
            "expected": 10,
            "retained": 10,
            "generation_missing": 0,
            "generation_discordant": 0,
            "grading_missing": 0,
            "grading_discordant": 0,
            "awaiting_judgment": 0,
            "config_discordant": False,
        },
        "models": [
            {"tag": "m:1b", "digest": "sha256:x", "family": "qwen", "tracks": ["think_off"]}
        ],
        "tracks": [
            {
                "track": "think_off",
                "scopes": [
                    {
                        "usage": None,
                        "method": "mcnemar",
                        "units": 10,
                        "leader": "m:1b",
                        "models": [
                            {
                                "model": "m:1b",
                                "mean": 0.5,
                                "n": 10,
                                "excluded": 0,
                                "se": 0.1,
                                "ci_low": 0.3,
                                "ci_high": 0.7,
                                "sim_ci_low": 0.3,
                                "sim_ci_high": 0.7,
                                "rank": 1,
                                "group": 1,
                                "graded": 10,
                                "truncated": 0,
                                "truncation_rate": 0.0,
                            }
                        ],
                        "comparisons": [],
                        "matrix": [],
                        "continuous": None,
                    }
                ],
                "k_bonferroni": {
                    "leader": "m:1b",
                    "usages": 0,
                    "alpha_per_test": None,
                    "models": [],
                },
                "spearman": {
                    "status": "absent",
                    "variant": "non_reasoning",
                    "n": 0,
                    "models": [],
                    "rho": None,
                    "p": None,
                    "ci_low": None,
                    "ci_high": None,
                    "conclusion": None,
                },
            }
        ],
        "aa_reference": None,
    }


def test_report_validates():
    assert validate(_report()) == "qb.report/1"


def test_report_is_closed_at_every_level():
    record = _report()
    record["questions"] = []
    with pytest.raises(SchemaValidationError):
        validate(record)
    record = _report()
    record["tracks"][0]["scopes"][0]["models"][0]["question_id"] = "x"
    with pytest.raises(SchemaValidationError):
        validate(record)
    record = _report()
    record["tracks"][0]["scopes"][0]["method"] = "friedman"
    with pytest.raises(SchemaValidationError):
        validate(record)
