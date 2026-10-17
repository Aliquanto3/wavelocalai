"""Conversion des jeux publics en questions candidates, sur des échantillons synthétiques
au format des fichiers sources (aucun réseau, aucun item réel recopié)."""

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.quality_bench.common.canonical import canonical_bytes
from scripts.quality_bench.questions.importers import (
    base,
    bbeh,
    bfcl,
    ifbench,
    jsonschemabench,
    mifeval,
    piaf,
)
from scripts.quality_bench.questions.schema import validate_question


def _write_jsonl(path, rows, final_newline=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(text + ("\n" if final_newline else ""), encoding="utf-8")
    return path


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


def _check(questions, source, usage):
    for question in questions:
        assert validate_question(question) == question
        assert question["source"] == source and question["usage"] == usage
        assert question["id"].startswith(f"{usage}/{source}/")
    assert len({q["id"] for q in questions}) == len(questions)


def test_bbeh(tmp_path):
    path = _write_json(
        tmp_path / "data.json",
        {"examples": [{"input": "Q1 ?", "target": "pen"}, {"input": "Q2", "target": "(b)"}]},
    )
    questions = bbeh.convert({bbeh.DATA.path: path})
    _check(questions, "bbeh-mini", "reasoning")
    assert [q["id"] for q in questions] == ["reasoning/bbeh-mini/0001", "reasoning/bbeh-mini/0002"]
    assert questions[0]["target"] == "pen" and questions[0]["license"] == "CC-BY-4.0"
    assert questions[0]["messages"][0]["content"].startswith("Q1 ?\n\nThink step by step")
    assert '"The answer is:"' in questions[0]["messages"][0]["content"]


@pytest.mark.parametrize("module, slug", [(ifbench, "ifbench"), (mifeval, "mifeval-fr")])
def test_instruction_sources(tmp_path, module, slug):
    rows = [
        {
            "key": 0,
            "prompt": "Rédigez un texte de 3 phrases.",
            "instruction_id_list": ["fr:length_constraints:number_sentences"],
            "kwargs": [{"num_sentences": 3, "relation": "exactement", "unused": None}],
        }
    ]
    # Dernière ligne sans fin de ligne : un fichier tiers complet, pas un fragment.
    path = _write_jsonl(tmp_path / "data.jsonl", rows, final_newline=False)
    questions = module.convert({module.DATA.path: path})
    _check(questions, slug, "instructions")
    assert len(questions) == 1
    params = questions[0]["grader"]["params"]
    assert params["instruction_id_list"] == rows[0]["instruction_id_list"]
    assert params["kwargs"] == rows[0]["kwargs"] and params["key"] == "0"
    assert questions[0]["target"] is None


def test_piaf_groups_questions_by_paragraph(tmp_path):
    data = {
        "version": "1.0",
        "data": [
            {
                "title": "Titre",
                "paragraphs": [
                    {
                        "context": "Le ministère emploie 100 personnes.",
                        "qas": [
                            {"id": "a", "question": "Combien ?", "answers": [{"text": "100"}]},
                            {"id": "b", "question": "Qui ?", "answers": [{"text": "Le ministère"}]},
                        ],
                    },
                    {
                        "context": "Autre.",
                        "qas": [{"id": "c", "question": "Quoi ?", "answers": []}],
                    },
                ],
            }
        ],
    }
    questions = piaf.convert({piaf.DATA.path: _write_json(tmp_path / "piaf.json", data)})
    _check(questions, "piaf", "rag")
    assert [q["group"] for q in questions] == ["piaf/001-001", "piaf/001-001", "piaf/001-002"]
    assert questions[0]["target"] == ["100"]
    assert "Le ministère emploie 100 personnes." in questions[0]["messages"][0]["content"]


def test_jsonschemabench_reads_parquet_and_skips_oversized(tmp_path, caplog):
    small = {"type": "object", "properties": {"n": {"type": "number", "maximum": 1.5}}}
    huge = {"type": "object", "description": "x" * 200_000}
    rows = [
        {"json_schema": json.dumps(small), "unique_id": "o1"},
        {"json_schema": json.dumps(huge), "unique_id": "o2"},
        {"json_schema": json.dumps(small), "unique_id": "o3"},
    ]
    local = {}
    for subset, remote in jsonschemabench.FILES.items():
        path = tmp_path / subset / "test.parquet"
        path.parent.mkdir(parents=True)
        schema = pa.schema([("json_schema", pa.string()), ("unique_id", pa.string())])
        table = pa.Table.from_pylist(rows if subset == "Glaiveai2K" else [], schema=schema)
        pq.write_table(table, path)
        local[remote.path] = path
    questions = jsonschemabench.convert(local)
    _check(questions, "jsonschemabench", "extraction")
    assert [q["id"] for q in questions] == [
        "extraction/jsonschemabench/0001",
        "extraction/jsonschemabench/0003",
    ]
    assert questions[0]["format"] is None
    assert questions[0]["grader"]["params"] == {"schema": small, "subset": "Glaiveai2K"}
    assert questions[0]["group"] == "jsonschemabench/Glaiveai2K/o1"
    assert "1 questions écartées" in caplog.text


def _function(name="api.get", ptype="dict"):
    return {
        "name": name,
        "description": "Obtenir.",
        "parameters": {
            "type": ptype,
            "required": ["x"],
            "properties": {"x": {"type": "float"}, "t": {"type": "tuple"}},
        },
    }


def _bfcl_local(tmp_path, names_rows):
    local = {}
    for name, rows in names_rows.items():
        local[bfcl._DATA + name] = _write_jsonl(tmp_path / name, rows)
    return local


def test_bfcl_live_converts_tools_and_encodes_float_targets(tmp_path):
    question_row = {
        "id": "live_simple_0-0-0",
        "question": [[{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]],
        "function": [_function()],
    }
    answer = {"id": "live_simple_0-0-0", "ground_truth": [{"api.get": {"x": [1.5, 2]}}]}
    local = _bfcl_local(
        tmp_path,
        {
            "BFCL_v4_live_simple.json": [question_row],
            "possible_answer/BFCL_v4_live_simple.json": [answer],
            "BFCL_v4_live_multiple.json": [],
            "possible_answer/BFCL_v4_live_multiple.json": [],
        },
    )
    questions = bfcl.convert_live(local)
    _check(questions, "bfcl-live", "tools")
    tool = questions[0]["tools"][0]["function"]
    assert tool["name"] == "api_get"
    assert tool["parameters"]["type"] == "object"
    assert tool["parameters"]["properties"]["x"]["type"] == "number"
    assert tool["parameters"]["properties"]["t"]["type"] == "array"
    assert questions[0]["messages"] == question_row["question"][0]
    assert questions[0]["target"] == [{"api.get": {"x": [{"$float": "1.5"}, 2]}}]
    params = questions[0]["grader"]["params"]
    assert params["functions"] == [_function()] and params["category"] == "live_simple"


def test_bfcl_live_requires_an_answer(tmp_path):
    row = {"id": "q", "question": [[{"role": "user", "content": "U"}]], "function": [_function()]}
    local = _bfcl_local(
        tmp_path,
        {
            "BFCL_v4_live_simple.json": [row],
            "possible_answer/BFCL_v4_live_simple.json": [],
            "BFCL_v4_live_multiple.json": [],
            "possible_answer/BFCL_v4_live_multiple.json": [],
        },
    )
    with pytest.raises(ValueError, match="réponse attendue absente"):
        bfcl.convert_live(local)


def test_bfcl_irrelevance_without_functions_has_no_tools(tmp_path):
    rows = [
        {"id": "i0", "question": [[{"role": "user", "content": "Bonjour"}]], "function": []},
        {
            "id": "i1",
            "question": [[{"role": "user", "content": "Météo ?"}]],
            "function": [_function()],
        },
    ]
    local = _bfcl_local(tmp_path, {"BFCL_v4_live_irrelevance.json": rows})
    questions = bfcl.convert_irrelevance(local)
    _check(questions, "bfcl-irrelevance", "abstention")
    assert questions[0]["tools"] is None and questions[1]["tools"]
    assert all(q["target"] is None for q in questions)


def test_bfcl_multi_turn(tmp_path):
    docs = {
        doc: [
            {"name": f"{doc}_f", "description": "d", "parameters": {"type": "dict"}, "response": {}}
        ]
        for doc in bfcl.CLASS_DOCS.values()
    }
    docs["math_api"].append({"name": "cp", "description": "d", "parameters": {"type": "dict"}})
    row = {
        "id": "multi_turn_base_0",
        "question": [[{"role": "user", "content": "T1"}], [{"role": "user", "content": "T2"}]],
        "initial_config": {"MathAPI": {}},
        "path": [],
        "involved_classes": ["MathAPI", "TwitterAPI"],
        "excluded_function": ["cp"],
    }
    names_rows = {f"multi_turn_func_doc/{doc}.json": rows for doc, rows in docs.items()}
    names_rows[bfcl.MULTI] = [row]
    names_rows[f"possible_answer/{bfcl.MULTI}"] = [
        {"id": "multi_turn_base_0", "ground_truth": [["f(a=1)"], ["g()"]]}
    ]
    questions = bfcl.convert_multi(_bfcl_local(tmp_path, names_rows))
    _check(questions, "bfcl-multi", "tools")
    question = questions[0]
    assert question["messages"] == [{"role": "user", "content": "T1"}]
    assert question["turns"] == [[{"role": "user", "content": "T2"}]]
    assert [t["function"]["name"] for t in question["tools"]] == ["math_api_f", "posting_api_f"]
    assert question["env"] == {
        "name": "bfcl_multi_turn",
        "initial_state": {
            "involved_classes": ["MathAPI", "TwitterAPI"],
            "initial_config": {"MathAPI": {}},
        },
    }
    assert question["target"] == [["f(a=1)"], ["g()"]]
    params = question["grader"]["params"]
    assert [f["name"] for f in params["functions"]] == ["math_api_f", "posting_api_f"]
    assert params["functions"][0]["response"] == {}  # déclaration d'origine conservée
    assert params["underscore_to_dot"] is True and params["excluded_function"] == ["cp"]


def _tool_messages(history):
    return [message for message in history if message["role"] == "tool"]


def test_gold_history_replays_the_target_turn_by_turn():
    from .grading_factories import FILE_SYSTEM_STATE

    env = {"name": "bfcl_multi_turn", "initial_state": FILE_SYSTEM_STATE}
    history = bfcl.gold_history(env, [["ls()", "cd(folder='docs')"], ["cat(file_name='a.txt')"]])
    # Par tour : appels, un résultat par appel, puis la réponse de fin de tour.
    assert [message["role"] for message in history] == [
        "assistant", "tool", "tool", "assistant", "assistant", "tool", "assistant",
    ]  # fmt: skip
    first = history[0]["tool_calls"]
    assert [call["function"]["name"] for call in first] == ["ls", "cd"]
    assert first[1]["function"]["arguments"] == {"folder": "docs"}
    assert "docs" in _tool_messages(history)[0]["content"]
    assert "beta" in _tool_messages(history)[2]["content"]  # cat voit le répertoire courant
    reply = history[3]["content"]
    assert len(reply) == bfcl.REPLY_ALLOWANCE_TOKENS * base.CHARS_PER_TOKEN


def test_gold_history_tolerates_an_unreadable_target_call():
    from .grading_factories import FILE_SYSTEM_STATE

    env = {"name": "bfcl_multi_turn", "initial_state": FILE_SYSTEM_STATE}
    history = bfcl.gold_history(env, [["pas un appel valide ("]])
    assert [message["role"] for message in history] == ["assistant", "tool", "assistant"]
    assert _tool_messages(history)[0]["content"] == ""


def test_multi_turn_history_raises_the_estimate_and_the_tier():
    prompt = {"messages": [{"role": "user", "content": "T1"}], "turns": None, "tools": None}
    without = base.estimate_prompt_tokens(prompt)
    history = [{"role": "tool", "content": "r" * 6000, "tool_name": "ls"}] * 2
    with_history = base.estimate_prompt_tokens(prompt, history)
    assert with_history >= without + 2 * 6000 // base.CHARS_PER_TOKEN
    # 3000 tokens de contexte seul : palier 8192 pour 2048 tokens de plafond ; avec l'historique
    # (+ 4000 tokens), l'AD-5 exige 8192 puis 16384.
    assert base.choose_num_ctx(without + 2000, "tools") == 8192
    assert base.choose_num_ctx(with_history + 2000, "tools") == 16384


def test_bfcl_multi_turn_counts_the_accumulated_history(tmp_path):
    from .grading_factories import FILE_SYSTEM_STATE

    docs = {
        doc: [
            {"name": f"{doc}_f", "description": "d", "parameters": {"type": "dict"}, "response": {}}
        ]
        for doc in bfcl.CLASS_DOCS.values()
    }
    names_rows = {f"multi_turn_func_doc/{doc}.json": rows for doc, rows in docs.items()}
    turns = [[{"role": "user", "content": f"T{n}"}] for n in range(1, 8)]
    row = {
        "id": "multi_turn_base_0",
        "question": turns,
        "initial_config": FILE_SYSTEM_STATE["initial_config"],
        "path": [],
        "involved_classes": FILE_SYSTEM_STATE["involved_classes"],
        "excluded_function": [],
    }
    names_rows[bfcl.MULTI] = [row]
    names_rows[f"possible_answer/{bfcl.MULTI}"] = [
        {"id": "multi_turn_base_0", "ground_truth": [["cat(file_name='a.txt')"]] * 7}
    ]
    question = bfcl.convert_multi(_bfcl_local(tmp_path, names_rows))[0]
    short = dict(row, question=turns[:1])
    names_rows[bfcl.MULTI] = [short]
    names_rows[f"possible_answer/{bfcl.MULTI}"] = [
        {"id": "multi_turn_base_0", "ground_truth": [["cat(file_name='a.txt')"]]}
    ]
    one_turn = bfcl.convert_multi(_bfcl_local(tmp_path / "short", names_rows))[0]
    # Sept tours : sept fois la réponse et les messages d'appel, pas seulement les tours.
    assert question["est_prompt_tokens"] > one_turn["est_prompt_tokens"] + 6 * 100
    assert question["turns"] and len(question["turns"]) == 6
    assert "history" not in question  # estimation seulement : rien n'est ajouté à la question


def test_conversion_is_deterministic(tmp_path):
    path = _write_json(tmp_path / "data.json", {"examples": [{"input": "Q", "target": "1"}]})
    first = canonical_bytes(bbeh.convert({bbeh.DATA.path: path}))
    assert canonical_bytes(bbeh.convert({bbeh.DATA.path: path})) == first


def test_strings_are_normalized_to_nfc(tmp_path):
    path = _write_json(tmp_path / "data.json", {"examples": [{"input": "Québec ?", "target": "é"}]})
    question = bbeh.convert({bbeh.DATA.path: path})[0]
    assert question["messages"][0]["content"].startswith("Québec ?")
    assert question["target"] == "é"


@pytest.mark.parametrize(
    "usage, est, expected", [("rag", 1000, 4096), ("reasoning", 1000, 8192), ("rag", 4000, 8192)]
)
def test_choose_num_ctx_respects_ad5(usage, est, expected):
    assert base.choose_num_ctx(est, usage) == expected


def test_choose_num_ctx_refuses_oversized_prompts():
    with pytest.raises(base.PromptTooLongError):
        base.choose_num_ctx(30_000, "rag")


def test_build_questions_skips_oversized_prompts_without_shifting_ids(caplog):
    items = [
        {
            "number": number,
            "group": f"piaf/{number:03d}",
            "messages": [{"role": "user", "content": text}],
            "grader_params": {},
            "target": ["x"],
        }
        for number, text in ((1, "court"), (2, "x" * 200_000), (3, "court aussi"))
    ]
    questions = base.build_questions("piaf", items)
    assert [q["id"] for q in questions] == ["rag/piaf/0001", "rag/piaf/0003"]
    assert "piaf : 1 questions écartées" in caplog.text
