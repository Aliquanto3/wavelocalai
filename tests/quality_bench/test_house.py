"""Questions maison ``qb.house/1`` : documents synthétiques, et ``writing-fr.yaml`` réel."""

from __future__ import annotations

import copy

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.canonical import pretty_bytes
from scripts.quality_bench.common.jsonl import rewrite_jsonl
from scripts.quality_bench.questions.house import build_house, house_path, load_house
from scripts.quality_bench.questions.schema import QuestionError, validate_question

from .set_factories import synthetic_question

SCHEMA = {
    "type": "object",
    "properties": {"nom": {"type": "string"}, "montant_centimes": {"type": "integer"}},
    "required": ["nom", "montant_centimes"],
    "additionalProperties": False,
}


def _doc(source, *questions):
    return {"schema": "qb.house/1", "source": source, "questions": list(questions)}


def _user(text):
    return [{"role": "user", "content": text}]


EXTRACTION = {
    "number": 1,
    "messages": _user(
        "Extrais.\n\nSchéma :\n" + pretty_bytes(SCHEMA).decode().rstrip("\n") + "\n\nDocument : X"
    ),
    "grader_params": {"schema": SCHEMA, "subset": "extraction-fr"},
    "target": {"nom": "Société fictive", "montant_centimes": 1250},
}
ABSTENTION = {
    "number": 1,
    "messages": _user("Document fictif. Réponds « INFO ABSENTE » si besoin. Question ?"),
    "grader_params": {"marker": "INFO ABSENTE"},
    "target": None,
}
INSTRUCTIONS = {
    "number": 3,
    "messages": _user("Écris un texte synthétique sans virgule."),
    "grader_params": {
        "instruction_id_list": ["fr:punctuation:no_comma", "fr:detectable_format:title"],
        "key": "3",
        "kwargs": [{}, {}],
    },
    "target": None,
}
WRITING = {
    "number": 1,
    "messages": _user("Rédige un courriel synthétique."),
    "grader_params": {},
    "target": None,
    "criteria": [
        {"id": f"c{i}", "question": f"Le courriel respecte-t-il la règle {i} ?"}
        for i in (1, 2, 3, 4)
    ],
}


@pytest.mark.parametrize(
    "source, item",
    [
        ("extraction-fr", EXTRACTION),
        ("abstention-fr", ABSTENTION),
        ("instructions-fr", INSTRUCTIONS),
        ("writing-fr", WRITING),
    ],
)
def test_valid_house_questions(source, item):
    (question,) = build_house(_doc(source, item), source)
    assert validate_question(question) == question
    assert question["source"] == source
    assert question["group"] == f"{source}/{item['number']:04d}"
    assert question["unit"] == question["id"]
    assert question["private"] == (source != "writing-fr")
    assert question["license"] == ("MIT" if source == "writing-fr" else "private")
    assert (question["criteria"] is not None) == (source == "writing-fr")


@pytest.mark.parametrize(
    "source, item, change, message",
    [
        ("writing-fr", WRITING, {"color": 1}, "clés inconnues"),
        ("writing-fr", WRITING, {"criteria": None}, "criteria"),
        ("writing-fr", WRITING, {"criteria": WRITING["criteria"][:3]}, "4 à 6"),
        ("writing-fr", WRITING, {"criteria": [{"id": "c2", "question": "A ?"}] * 4}, "critère"),
        (
            "writing-fr",
            WRITING,
            {"criteria": [{"id": f"c{i}", "question": "Affirmation."} for i in (1, 2, 3, 4)]},
            "critère",
        ),
        ("abstention-fr", ABSTENTION, {"criteria": WRITING["criteria"]}, "réservés"),
        ("abstention-fr", ABSTENTION, {"grader_params": {"marker": "AUTRE"}}, "marker"),
        ("abstention-fr", ABSTENTION, {"target": "x"}, "target"),
        ("abstention-fr", ABSTENTION, {"group": "abstention-fr/contenu-révélateur"}, "opaque"),
        (
            "abstention-fr",
            ABSTENTION,
            {"messages": [{"role": "assistant", "content": "x"}]},
            "messages",
        ),
        ("extraction-fr", EXTRACTION, {"messages": _user("Schéma absent")}, "schéma"),
        ("extraction-fr", EXTRACTION, {"target": None}, "target"),
        ("extraction-fr", EXTRACTION, {"target": {"nom": "x"}}, "non conforme"),
        (
            "extraction-fr",
            EXTRACTION,
            {"target": {"nom": "x", "montant_centimes": 1.5}},
            "flottant",
        ),
        ("instructions-fr", INSTRUCTIONS, {"grader_params": {"key": "3"}}, "grader_params"),
        ("instructions-fr", INSTRUCTIONS, {"derived_from": "tools/bfcl-live/0001"}, "réservé"),
    ],
)
def test_invalid_house_questions_refused(source, item, change, message):
    bad = {**copy.deepcopy(item), **change}
    with pytest.raises(QuestionError, match=message):
        build_house(_doc(source, bad), source)


def test_document_level_errors():
    with pytest.raises(QuestionError):
        build_house({**_doc("writing-fr", WRITING), "extra": 1}, "writing-fr")
    with pytest.raises(QuestionError):
        build_house(_doc("abstention-fr", WRITING), "writing-fr")  # source différente
    with pytest.raises(QuestionError, match="double"):
        build_house(_doc("writing-fr", WRITING, WRITING), "writing-fr")
    with pytest.raises(QuestionError, match="inconnue"):
        build_house(_doc("bbeh-mini", WRITING), "bbeh-mini")


def _origin():
    tools = [{"type": "function", "function": {"name": "f", "description": "", "parameters": {}}}]
    return synthetic_question(
        "bfcl-live",
        42,
        group="bfcl-live/0042",
        tools=tools,
        grader_params={"bfcl_id": "live_simple_1", "category": "live_simple", "functions": []},
        target=[{"f": {"x": [1]}}],
    )


def test_derived_from_copies_everything_but_messages():
    origin = _origin()
    item = {"number": 1, "derived_from": origin["id"], "messages": _user("Traduction fictive")}
    (question,) = build_house(_doc("tools-fr", item), "tools-fr", {origin["id"]: origin})
    for field in ("group", "tools", "format", "env", "target", "turns"):
        assert question[field] == origin[field]
    assert question["grader"]["params"] == origin["grader"]["params"]
    assert question["messages"] == item["messages"] and question["private"]


@pytest.mark.parametrize(
    "item, message",
    [
        (
            {"number": 1, "derived_from": "tools/bfcl-live/9999", "messages": _user("x")},
            "introuvable",
        ),
        (
            {
                "number": 1,
                "derived_from": "tools/bfcl-live/0042",
                "messages": _user("x"),
                "target": [],
            },
            "clés exactes",
        ),
        (
            {
                "number": 1,
                "derived_from": "tools/bfcl-live/0042",
                "messages": [{"role": "system", "content": "s"}, *_user("x")],
            },
            "rôles",
        ),
    ],
)
def test_derived_from_errors(item, message):
    origin = _origin()
    with pytest.raises(QuestionError, match=message):
        build_house(_doc("tools-fr", item), "tools-fr", {origin["id"]: origin})


def test_load_house_reads_origins_from_candidates(tmp_path):
    origin = _origin()
    rewrite_jsonl(paths.candidates_path("bfcl-live"), [origin])
    path = tmp_path / "tools-fr.yaml"
    path.write_text(
        "schema: qb.house/1\nsource: tools-fr\nquestions:\n"
        f"  - {{number: 1, derived_from: {origin['id']}, messages: [{{role: user, content: Traduction}}]}}\n",
        encoding="utf-8",
    )
    (question,) = load_house(path, "tools-fr")
    assert question["group"] == "bfcl-live/0042"


def test_load_house_without_origin_candidates_names_fetch(tmp_path):
    path = tmp_path / "tools-fr.yaml"
    path.write_text(
        "schema: qb.house/1\nsource: tools-fr\nquestions:\n"
        "  - {number: 1, derived_from: tools/bfcl-live/0001, messages: [{role: user, content: T}]}\n",
        encoding="utf-8",
    )
    with pytest.raises(QuestionError, match="fetch --source bfcl-live"):
        load_house(path, "tools-fr")


def test_house_paths(_isolated_data_root):
    assert house_path("abstention-fr") == _isolated_data_root / "private" / "abstention-fr.yaml"
    assert house_path("writing-fr") == (
        paths.PACKAGE_DIR / "questions" / "writing" / "writing-fr.yaml"
    )


def test_real_writing_file_has_80_valid_questions():
    questions = load_house(house_path("writing-fr"), "writing-fr")
    assert len(questions) == 80
    assert len({q["group"] for q in questions}) == 80
    for question in questions:
        assert validate_question(question) == question
        assert 4 <= len(question["criteria"]) <= 6
        assert all(c["question"].endswith("?") for c in question["criteria"])
        assert not question["private"] and question["license"] == "MIT"


def test_house_path_chooses_a_versioned_file():
    chosen = house_path("writing-fr", "writing-fr-v2.yaml")
    assert chosen == paths.PACKAGE_DIR / "questions" / "writing" / "writing-fr-v2.yaml"
    with pytest.raises(QuestionError, match="source privée"):
        house_path("abstention-fr", "x.yaml")


def test_writing_v2_keeps_the_v1_questions_and_adds_checks_only():
    v1 = load_house(house_path("writing-fr"), "writing-fr")
    v2 = load_house(house_path("writing-fr", "writing-fr-v2.yaml"), "writing-fr")
    assert [q["id"] for q in v2] == [q["id"] for q in v1] and len(v2) == 80
    checked = 0
    for old, new in zip(v1, v2, strict=True):
        assert validate_question(new) == new
        assert new["messages"] == old["messages"] and new["group"] == old["group"]
        assert new["prompt_hash"] == old["prompt_hash"]  # le prompt est celui de set-v1
        assert [(c["id"], c["question"]) for c in new["criteria"]] == [
            (c["id"], c["question"]) for c in old["criteria"]
        ]
        checked += sum(1 for c in new["criteria"] if "check" in c)
    assert checked == 69
    assert sum(len(q["criteria"]) for q in v2) == 418
    assert sum(1 for q in v2 for c in q["criteria"] if "check" not in c) == 418 - 69


def test_check_with_a_bad_form_is_refused_by_the_house_loader():
    question = {
        "number": 1,
        "messages": _user("Rédige."),
        "grader_params": {},
        "target": None,
        "criteria": [
            {"id": f"c{i}", "question": f"Critère {i} ?"}
            | ({"check": {"count": "words"}} if i == 1 else {})
            for i in range(1, 5)
        ],
    }
    with pytest.raises(QuestionError, match="critère 1"):
        build_house(_doc("writing-fr", question), "writing-fr")
    question["criteria"][0] = {"id": "c1", "question": "Critère 1 ?", "juge": True}
    with pytest.raises(QuestionError, match="critère 1"):
        build_house(_doc("writing-fr", question), "writing-fr")


SECRET = "VALEUR-SECRETE-4242"


def test_private_errors_never_quote_values():
    """Cible hors schéma d'une question privée : le message nomme le champ, pas la valeur."""
    bad = {**copy.deepcopy(EXTRACTION), "target": {"nom": "x", "montant_centimes": SECRET}}
    with pytest.raises(QuestionError) as caught:
        build_house(_doc("extraction-fr", bad), "extraction-fr")
    assert "montant_centimes" in str(caught.value) and SECRET not in str(caught.value)


def test_private_schema_errors_do_not_dump_the_schema():
    schema = {"type": "object", "properties": {"nom": {"type": SECRET}}}
    item = {**copy.deepcopy(EXTRACTION), "grader_params": {"schema": schema, "subset": "x"}}
    with pytest.raises(QuestionError, match="schéma JSON invalide") as caught:
        build_house(_doc("extraction-fr", item), "extraction-fr")
    assert SECRET not in str(caught.value)


def test_private_question_schema_errors_are_redacted():
    """Défaut de ``qb.question/1`` levé par ``build_question`` : chemin et nature seulement."""
    item = {**copy.deepcopy(ABSTENTION), "tools": SECRET}
    with pytest.raises(QuestionError, match="tools") as caught:
        build_house(_doc("abstention-fr", item), "abstention-fr")
    assert SECRET not in str(caught.value)


def _other_origin(source, **extra):
    return synthetic_question(source, 7, group=f"{source}/0007", **extra)


@pytest.mark.parametrize(
    "origin_factory, message",
    [
        (lambda: _other_origin("bbeh-mini"), "origine publique"),  # autre usage
        (lambda: _other_origin("tools-fr"), "origine publique"),  # origine privée
        (lambda: _other_origin("bfcl-multi"), "correcteur"),  # autre correcteur
    ],
)
def test_derived_from_refuses_incompatible_origins(origin_factory, message):
    origin = origin_factory()
    item = {"number": 1, "derived_from": origin["id"], "messages": _user("Traduction fictive")}
    with pytest.raises(QuestionError, match=message):
        build_house(_doc("tools-fr", item), "tools-fr", {origin["id"]: origin})


@pytest.mark.parametrize("messages", ["texte", 3, None, [{"role": "user"}]])
def test_derived_messages_are_validated_first(messages):
    origin = _origin()
    item = {"number": 1, "derived_from": origin["id"], "messages": messages}
    with pytest.raises(QuestionError, match="messages"):
        build_house(_doc("tools-fr", item), "tools-fr", {origin["id"]: origin})
