"""Commande ``generate --campaign <c>`` sur un jeu synthétique et un Ollama simulé
(``httpx2.MockTransport``) : ordre d'AD-14, reprise, arrêt, pannes, chauffe, préflight,
manifeste et sorties corrigeables par ``grade_line``."""

from __future__ import annotations

import json

import httpx2
import pytest
import yaml

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.canonical import pretty_bytes
from scripts.quality_bench.common.config import DEFAULT_GENERATION
from scripts.quality_bench.common.jsonl import read_jsonl, rewrite_jsonl
from scripts.quality_bench.common.locks import FileLock
from scripts.quality_bench.common.manifest import blocking_hash
from scripts.quality_bench.common.schemas import TRACKS, validate
from scripts.quality_bench.common.selection import selected_ids
from scripts.quality_bench.generation import commands
from scripts.quality_bench.generation.preflight import LaunchError
from scripts.quality_bench.generation.runner import build_plan, warmup_prompt
from scripts.quality_bench.grading.registry import grade_line

from .grading_factories import EXTRACTION_SCHEMA, GOOD_STEPS, questions, tool_call
from .ollama_fake import FakeModel, FakeOllama, OutageError, call, is_warmup, reply
from .set_factories import synthetic_question

CAMPAIGN = "gen-test"
SET_ID = "small-gen"
THINK = "m-think:1b"
PLAIN = "m-plain:1b"
MODELS = [
    {
        "tag": THINK,
        "family": "qwen",
        "tracks": ["think_off", "think_on"],
        "think_off": False,
        "think_on": True,
        "num_ctx_max": 32768,
    },
    {
        "tag": PLAIN,
        "family": "mistral",
        "tracks": ["think_off"],
        "think_off": None,
        "num_ctx_max": 32768,
    },
]


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _set_questions():
    qs = questions()
    chosen = {
        name: qs[name] for name in ("bbeh", "var_math", "piaf", "bfcl_ast", "bfcl_multi", "writing")
    }
    chosen["formatted"] = synthetic_question(
        "jsonschemabench",
        2,
        format=EXTRACTION_SCHEMA,
        grader_params={"schema": EXTRACTION_SCHEMA, "subset": "Github_easy"},
    )
    return chosen


def _write_campaign(config_dir, models=None, **generation):
    doc = {"set": SET_ID, "generation": {**generation, "models": models or MODELS}}
    (config_dir / f"{CAMPAIGN}.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Jeu synthétique, YAML de campagne et Ollama simulé injecté dans la commande."""
    config_dir = tmp_path / "campaigns_yaml"
    config_dir.mkdir()
    monkeypatch.setattr(paths, "campaign_config_path", lambda c: config_dir / f"{c}.yaml")
    _write_campaign(config_dir)
    named = _set_questions()
    question_list = sorted(named.values(), key=lambda q: q["id"])
    tracks = {
        "think_off": [q["id"] for q in question_list],
        "think_on": sorted([named["bbeh"]["id"], named["piaf"]["id"]]),
    }
    rewrite_jsonl(paths.set_questions_path(SET_ID), question_list)
    paths.set_tracks_path(SET_ID).write_bytes(pretty_bytes(tracks))
    fake = FakeOllama(
        models={
            THINK: FakeModel(["completion", "thinking", "tools"]),
            PLAIN: FakeModel(["completion", "tools"], context_length=4096),
        }
    )
    monkeypatch.setattr(commands, "make_client", lambda url: fake.client())
    clock = FakeClock()
    monkeypatch.setattr(commands, "SLEEP", clock.sleep)
    monkeypatch.setattr(commands, "CLOCK", clock)
    return {
        "fake": fake,
        "config_dir": config_dir,
        "named": named,
        "by_id": {q["id"]: q for q in question_list},
        "tracks": tracks,
        "clock": clock,
    }


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    from scripts.quality_bench.common.logs import setup_logging

    setup_logging("test", None)


def _run(*extra):
    from scripts.quality_bench.__main__ import main

    return main(["generate", "--campaign", CAMPAIGN, *extra])


def _lines():
    return read_jsonl(paths.generation_path(CAMPAIGN))


def _expected_keys(env, models=MODELS, seeds=(0,)):
    """Clés dans l'ordre d'AD-14 : modèle > piste > palier > question > seed."""
    keys = []
    for model in models:
        for track in TRACKS:
            if track not in model["tracks"]:
                continue
            ordered = sorted(
                (env["by_id"][qid] for qid in env["tracks"][track]),
                key=lambda q: (q["num_ctx"], q["id"]),
            )
            for question in ordered:
                for seed in seeds:
                    keys.append(f"{CAMPAIGN}|{model['tag']}|{track}|{question['id']}|{seed}")
    return keys


def _content(body):
    return body["messages"][0]["content"]


# --- Campagne nominale -------------------------------------------------------------------


def test_nominal_campaign_writes_ordered_raw_lines(env):
    fake = env["fake"]
    assert _run() == 0
    lines = _lines()
    assert [line["key"] for line in lines] == _expected_keys(env)
    for line in lines:
        validate(line)
        assert "score" not in line and "success" not in line
    manifest_path = paths.generation_manifest_path(CAMPAIGN)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert {line["manifest"] for line in lines} == {blocking_hash(manifest)}
    resolved = manifest["blocking"]["models_resolved"]
    assert [m["tag"] for m in resolved] == [THINK, PLAIN]
    assert resolved[0]["capabilities"] == ["completion", "thinking", "tools"]
    assert resolved[1]["num_ctx_max"] == 4096  # contexte déclaré plus petit que la configuration
    assert manifest["blocking"]["ollama_version"] == "0.40.2"
    assert manifest["informative"]["checklist"]["reminders"]

    by_key = {line["key"]: line for line in lines}
    think_on = [line for line in lines if line["track"] == "think_on"]
    assert think_on and {line["model"] for line in think_on} == {THINK}
    assert all(
        line["think"] is (line["track"] == "think_on") for line in lines if line["model"] == THINK
    )
    assert all(line["think"] is None for line in lines if line["model"] == PLAIN)

    # Paliers au-delà du maximum effectif : context_exceeded sans requête.
    plain_8192 = [line for line in lines if line["model"] == PLAIN and line["num_ctx"] == 8192]
    assert plain_8192 and all(
        (line["status"], line["calls"], line["attempts"], line["output"])
        == ("context_exceeded", 0, 0, [])
        for line in plain_8192
    )
    assert all(line["status"] == "ok" for line in lines if line not in plain_8192)

    # Requêtes : think seulement si la capacité est déclarée, tools seulement si la question en a,
    # format de la question, num_predict selon la piste et l'usage.
    chats = fake.chats()
    assert len(chats) == sum(line["calls"] for line in lines)
    for body in chats:
        line = next(
            line
            for line in lines
            if line["model"] == body["model"]
            and env["by_id"][line["question_id"]]["messages"][0]["content"] == _content(body)
            and line["num_predict"] == body["options"]["num_predict"]
            and line["seed"] == body["options"]["seed"]
            and line["num_ctx"] == body["options"]["num_ctx"]
            and ("think" not in body or line["think"] == body["think"])
        )
        question = env["by_id"][line["question_id"]]
        assert ("tools" in body) == bool(question["tools"])
        assert body["format"] == question["format"]
        assert ("think" in body) == (body["model"] == THINK)
        assert body["options"]["temperature"] == 0
    bbeh = env["named"]["bbeh"]["id"]
    assert by_key[f"{CAMPAIGN}|{THINK}|think_on|{bbeh}|0"]["num_predict"] == 4096
    assert by_key[f"{CAMPAIGN}|{THINK}|think_off|{bbeh}|0"]["num_predict"] == 2048

    # Chauffe : à chaque changement du couple (modèle, num_ctx) requêté.
    warmups = read_jsonl(paths.warmups_path(CAMPAIGN))
    assert [(w["model"], w["num_ctx"]) for w in warmups] == [
        (THINK, 4096),
        (THINK, 8192),
        (THINK, 4096),
        (THINK, 8192),
        (PLAIN, 4096),
    ]
    for warmup in warmups:
        validate(warmup)
        assert (warmup["size"], warmup["size_vram"], warmup["prefill_tok_s"]) == (4000, 3000, 500.0)
        assert warmup["prompt_tokens"] == 1000 and warmup["load_ns"] == 1_000_000
    warmup_bodies = fake.warmups()
    assert [b["think"] for b in warmup_bodies[:4]] == [False, False, True, True]
    assert "think" not in warmup_bodies[4]
    assert _content(warmup_bodies[0]) == warmup_prompt(4096)
    assert fake.unloads == [THINK, PLAIN]
    assert not paths.generation_stop_path(CAMPAIGN).exists()

    log = paths.log_path(CAMPAIGN, "generate").read_text(encoding="utf-8")
    assert "Liste de contrôle" in log and "OLLAMA_NUM_PARALLEL" in log
    for question in env["by_id"].values():  # jamais de contenu de question ni de réponse
        assert question["messages"][0]["content"] not in log
    assert "Réponse synthétique" not in log


def test_think_on_only_for_capable_model_and_k_seeds(env):
    _write_campaign(env["config_dir"], request={"seed_base": 10, "k": 2})
    assert _run() == 0
    keys = [line["key"] for line in _lines()]
    assert keys == _expected_keys(env, seeds=(10, 11))
    assert {(line["seed"], line["epoch"]) for line in _lines()} == {(10, 0), (11, 1)}


def test_warmup_below_threshold_is_logged(env):
    env["fake"].warmup_prompt_ns = 100_000_000_000  # 10 tok/s
    assert _run() == 0
    log = paths.log_path(CAMPAIGN, "generate").read_text(encoding="utf-8")
    assert "sous le seuil de 50" in log
    assert read_jsonl(paths.warmups_path(CAMPAIGN))[0]["prefill_tok_s"] == 10.0


def test_failed_warmup_with_live_service_writes_no_line(env):
    fake = env["fake"]
    original = fake._chat

    def chat(body):
        if is_warmup(body):
            return httpx2.Response(400, json={"error": "refus"})
        return original(body)

    fake._chat = chat
    assert _run() == 0
    assert not read_jsonl(paths.warmups_path(CAMPAIGN))
    assert [line["key"] for line in _lines()] == _expected_keys(env)


def test_warmup_503_with_live_service_writes_no_line(env):
    fake = env["fake"]
    original = fake._chat

    def chat(body):
        if is_warmup(body):
            return httpx2.Response(503, json={"error": "surchargé"})
        return original(body)

    fake._chat = chat
    assert _run() == 0
    assert not read_jsonl(paths.warmups_path(CAMPAIGN))
    assert env["clock"].now == 0  # service vivant : aucune attente
    assert [line["key"] for line in _lines()] == _expected_keys(env)


def test_warmup_outage_waits_then_retries_warmup(env):
    fake = env["fake"]
    original = fake._chat
    state = {"failed": False}

    def chat(body):
        if is_warmup(body) and not state["failed"]:
            state["failed"] = True
            fake.down = 2  # sonde immédiate, puis un premier essai de wait_for_ollama
            raise OutageError
        return original(body)

    fake._chat = chat
    assert _run() == 0
    assert env["clock"].now == 5  # une seule attente
    warmups = read_jsonl(paths.warmups_path(CAMPAIGN))
    assert [(w["model"], w["num_ctx"]) for w in warmups][:2] == [(THINK, 4096), (THINK, 8192)]
    assert len(fake.warmups()) == len(warmups) + 1  # chauffe refaite, une seule ligne
    assert [line["key"] for line in _lines()] == _expected_keys(env)


def test_num_parallel_warning_and_checklist(env, monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_PARALLEL", "4")
    assert _run() == 0
    log = paths.log_path(CAMPAIGN, "generate").read_text(encoding="utf-8")
    assert "OLLAMA_NUM_PARALLEL=4" in log and "de ce processus" in log
    manifest = json.loads(paths.generation_manifest_path(CAMPAIGN).read_text(encoding="utf-8"))
    assert manifest["informative"]["checklist"]["ollama_num_parallel"] == "4"


# --- Reprise et arrêt --------------------------------------------------------------------


def test_stop_then_resume_completes_without_duplicates(env):
    fake = env["fake"]
    seen = []

    def on_request(path, body):
        if path == "/api/chat" and not is_warmup(body):
            seen.append(body)
            if len(seen) == 3:
                paths.generation_stop_path(CAMPAIGN).write_text("stop", encoding="utf-8")

    fake.on_request = on_request
    assert _run() == 0
    first = _lines()
    expected = _expected_keys(env)
    # La question en cours au dépôt de STOP est terminée et écrite, puis le modèle déchargé.
    assert first and [line["key"] for line in first] == expected[: len(first)]
    assert sum(line["calls"] for line in first) >= 3
    assert len(first) < len(expected)
    assert fake.unloads == [THINK]
    assert not paths.generation_stop_path(CAMPAIGN).exists()

    fake.on_request = None
    chats_before = len(fake.chats())
    assert _run() == 0
    lines = _lines()
    assert [line["key"] for line in lines] == expected
    assert lines[: len(first)] == first
    resumed = lines[len(first) :]
    assert len(fake.chats()) - chats_before == sum(line["calls"] for line in resumed)

    # Troisième lancement : tout est présent, aucune requête de chat.
    chats_before = len(fake.chats())
    assert _run() == 0
    assert len(_lines()) == len(expected) and len(fake.chats()) == chats_before


def test_stop_present_at_launch_is_removed(env):
    paths.campaign_dir(CAMPAIGN).mkdir(parents=True)
    paths.generation_stop_path(CAMPAIGN).write_text("ancien", encoding="utf-8")
    assert _run() == 0
    assert len(_lines()) == len(_expected_keys(env))


def test_partial_final_line_is_replayed(env):
    assert _run() == 0
    lines = _lines()
    data = paths.generation_path(CAMPAIGN).read_bytes()
    last = data.rstrip(b"\n").rsplit(b"\n", 1)[-1]
    paths.generation_path(CAMPAIGN).write_bytes(data[: len(data) - len(last) - 1] + last[:20])
    assert _run() == 0
    assert [line["key"] for line in _lines()] == [line["key"] for line in lines]


# --- Statuts -----------------------------------------------------------------------------


def test_truncation_keeps_output_and_stops(env):
    env["fake"].responder = lambda body, fake: reply("coupé", done_reason="length")
    assert _run() == 0
    multi = [line for line in _lines() if line["question_id"] == env["named"]["bfcl_multi"]["id"]]
    assert all(line["status"] == "truncated" and line["calls"] == 1 for line in multi)
    assert multi[0]["output"][0]["content"] == "coupé"
    graded = grade_line(env["named"]["bfcl_multi"], multi[0]).record
    assert (graded["status"], graded["score"], graded["success"]) == ("truncated", 0.0, False)


def test_context_exceeded_by_prompt(env):
    env["fake"].responder = lambda body, fake: reply("x", prompt=3000, cached=100)
    assert _run() == 0
    statuses = {
        line["status"] for line in _lines() if line["model"] == THINK and line["num_ctx"] == 4096
    }
    assert statuses == {"context_exceeded"}  # 3100 ≥ 4096 − 2048


# --- Préflight, configuration et jeu ------------------------------------------------------


def _assert_nothing_written(code):
    assert _run() == code
    assert not paths.campaign_dir(CAMPAIGN).exists()


def _assert_refusal_logged(capsys, *fragments):
    """Le message de refus (console : aucun journal de campagne) nomme modèle et raison."""
    err = capsys.readouterr().err
    refusal = next(line for line in err.splitlines() if "Lancement refusé" in line)
    for fragment in fragments:
        assert fragment in refusal, (fragment, refusal)


def test_think_on_without_thinking_capability_exits_2_and_writes_nothing(env, capsys):
    env["fake"].models[THINK] = FakeModel(["completion", "tools"])
    _assert_nothing_written(2)
    _assert_refusal_logged(capsys, THINK, "sans capacité « thinking »")


@pytest.mark.parametrize(
    "model, reason",
    [
        (FakeModel(["completion", "thinking", "tools"], digest=None), "aucun digest"),
        (
            FakeModel(["completion", "thinking", "tools"], remote_host="https://ollama.com:443"),
            "distant",
        ),
        (
            FakeModel(["completion", "thinking", "tools"], show_remote_host="https://ollama.com"),
            "distant",
        ),
        (FakeModel(["completion", "thinking", "tools", "decision"]), "decision"),
        (FakeModel(["completion", "thinking"]), "sans capacité « tools »"),
        (
            FakeModel(["completion", "thinking", "tools"], thinking_values=[True]),
            "absente des valeurs publiées",
        ),
    ],
)
def test_preflight_refusals_exit_2(env, model, reason, capsys):
    env["fake"].models[THINK] = model
    _assert_nothing_written(2)
    _assert_refusal_logged(capsys, THINK, reason)


def test_model_absent_from_tags_exits_2(env, capsys):
    del env["fake"].models[PLAIN]
    _assert_nothing_written(2)
    _assert_refusal_logged(capsys, PLAIN, "absent de /api/tags")


def test_think_string_value_is_refused(env, capsys):
    models = [dict(MODELS[0], think_on="high"), MODELS[1]]
    _write_campaign(env["config_dir"], models=models)
    _assert_nothing_written(2)
    _assert_refusal_logged(capsys, THINK, "valeur think 'high'")


def test_think_off_true_is_refused(env, capsys):
    models = [dict(MODELS[0], think_off=True), MODELS[1]]
    _write_campaign(env["config_dir"], models=models)
    _assert_nothing_written(2)
    _assert_refusal_logged(capsys, THINK, "think_off = True")


def test_caps_reaching_num_ctx_are_refused(env, capsys):
    _write_campaign(env["config_dir"], caps={"think_off": {"default": 4096}})
    _assert_nothing_written(2)
    _assert_refusal_logged(capsys, "piste think_off", "num_predict 4096 ≥ num_ctx 4096")


def test_invalid_yaml_exits_2(env):
    (env["config_dir"] / f"{CAMPAIGN}.yaml").write_text("set: [\n", encoding="utf-8")
    _assert_nothing_written(2)


def test_missing_config_exits_2(env):
    (env["config_dir"] / f"{CAMPAIGN}.yaml").unlink()
    _assert_nothing_written(2)


def test_missing_set_exits_1(env):
    paths.set_questions_path(SET_ID).unlink()
    _assert_nothing_written(1)


def test_selection_outside_set_exits_2(env):
    _write_campaign(env["config_dir"], selection={"ids": ["reasoning/bbeh-mini/9999"]})
    _assert_nothing_written(2)


def test_tier_outside_configuration_exits_2(env):
    _write_campaign(env["config_dir"], num_ctx_tiers=[8192, 16384])
    _assert_nothing_written(2)


def test_non_local_url_exits_2(env):
    assert _run("--ollama-url", "http://192.168.1.10:11434") == 2
    assert not paths.campaign_dir(CAMPAIGN).exists()


def test_busy_machine_lock_exits_1(env):
    with FileLock(paths.machine_lock_path()):
        _assert_nothing_written(1)


def test_ollama_down_at_launch_exits_1(env):
    env["fake"].down = 10**6
    _assert_nothing_written(1)


def test_selection_ids_restrict_both_tracks(env):
    piaf = env["named"]["piaf"]["id"]
    bbeh = env["named"]["bbeh"]["id"]
    _write_campaign(env["config_dir"], selection={"ids": [piaf, env["named"]["writing"]["id"]]})
    assert _run() == 0
    keys = [line["key"] for line in _lines()]
    assert f"{CAMPAIGN}|{THINK}|think_on|{piaf}|0" in keys
    assert not any(bbeh in key for key in keys)
    assert len(keys) == 2 + 1 + 2


def test_selection_sample_is_seeded_per_usage(env):
    generation = {
        "selection": {"sample": {"per_usage": 1, "seed": 7}},
        "num_ctx_tiers": [4096, 8192, 16384, 32768],
        "caps": DEFAULT_GENERATION["caps"],
    }
    plan = build_plan(generation, env["by_id"], env["tracks"])
    assert plan == build_plan(generation, env["by_id"], env["tracks"])
    usages = [q["usage"] for q in plan["think_off"]]
    assert (
        sorted(usages) == sorted(set(usages)) == sorted({q["usage"] for q in env["by_id"].values()})
    )
    assert {q["id"] for q in plan["think_on"]} <= {q["id"] for q in plan["think_off"]}
    assert {q["id"] for q in plan["think_on"]} <= set(env["tracks"]["think_on"])
    assert [(q["num_ctx"], q["id"]) for q in plan["think_off"]] == sorted(
        (q["num_ctx"], q["id"]) for q in plan["think_off"]
    )


def test_plan_refuses_non_user_follow_up_turn(env):
    question = dict(env["named"]["bfcl_multi"])
    question["turns"] = [[{"role": "system", "content": "x"}]]
    by_id = {**env["by_id"], question["id"]: question}
    generation = {
        "selection": None,
        "num_ctx_tiers": [4096, 8192],
        "caps": DEFAULT_GENERATION["caps"],
    }
    with pytest.raises(LaunchError, match="user"):
        build_plan(generation, by_id, env["tracks"])


def test_plan_refuses_num_predict_reaching_num_ctx(env):
    generation = {
        "selection": None,
        "num_ctx_tiers": [4096, 8192],
        "caps": {"think_off": {"default": 2048}, "think_on": {"reasoning": 8192, "default": 2048}},
    }
    bbeh = env["named"]["bbeh"]["id"]
    with pytest.raises(LaunchError, match=f"{bbeh}, piste think_on : num_predict 8192"):
        build_plan(generation, env["by_id"], env["tracks"])


def _sample_plan(seed, extra=()):
    qs = [synthetic_question("piaf", n) for n in range(1, 7)]
    qs += [synthetic_question("bbeh-mini", n) for n in range(1, 7)]
    qs += list(extra)
    by_id = {q["id"]: q for q in qs}
    tracks = {"think_off": sorted(by_id), "think_on": ["rag/piaf/0002", "rag/piaf/0003"]}
    generation = {
        "selection": {"sample": {"per_usage": 2, "seed": seed}},
        "num_ctx_tiers": [4096, 8192],
        "caps": DEFAULT_GENERATION["caps"],
    }
    plan = build_plan(generation, by_id, tracks)
    return {track: [q["id"] for q in questions] for track, questions in plan.items()}


def test_selection_sample_draw_is_pinned():
    seven = _sample_plan(7)
    assert seven == {
        "think_off": [
            "rag/piaf/0001",
            "rag/piaf/0002",
            "reasoning/bbeh-mini/0001",
            "reasoning/bbeh-mini/0006",
        ],
        "think_on": ["rag/piaf/0002"],
    }
    assert _sample_plan(8)["think_off"] != seven["think_off"]
    # Une question d'un autre usage ne change pas le tirage des usages déjà présents.
    with_writing = _sample_plan(7, [synthetic_question("writing-fr", 1)])
    assert sorted(with_writing["think_off"]) == sorted(
        [*seven["think_off"], "writing/writing-fr/0001"]
    )


def _grouped_set():
    """Jeu à groupes : raisonnement (bbeh-mini, 12 groupes d'une question ; var-math-fr,
    6 groupes de trois variantes), RAG (piaf, 8 groupes de deux). ``think_on`` : les groupes
    pairs de chaque source, en entier."""
    questions, think_on = {}, []
    for source, usage, groups, size in (
        ("bbeh-mini", "reasoning", 12, 1),
        ("var-math-fr", "reasoning", 6, 3),
        ("piaf", "rag", 8, 2),
    ):
        for g in range(groups):
            for v in range(size):
                qid = f"{usage}/{source}/{g:04d}-{v}"
                questions[qid] = {
                    "id": qid,
                    "usage": usage,
                    "source": source,
                    "group": f"{source}/g{g}",
                }
                if g % 2 == 0:
                    think_on.append(qid)
    return questions, sorted(questions), think_on


def _groups(seed, reasoning, rag=(0, 0)):
    per_usage = {"reasoning": {"think_off": reasoning[0], "think_on": reasoning[1]}}
    if rag != (0, 0):
        per_usage["rag"] = {"think_off": rag[0], "think_on": rag[1]}
    return {"groups": {"seed": seed, "per_usage": per_usage}}


def _group_of(questions, ids):
    return {questions[qid]["group"] for qid in ids}


@pytest.mark.parametrize("seed", [0, 8, 41])
def test_selection_groups_prefix_is_a_subset_of_whole_groups(seed):
    questions, think_off, think_on = _grouped_set()
    big = selected_ids(_groups(seed, (12, 6), (6, 3)), questions, think_off, think_on)
    small = selected_ids(_groups(seed, (5, 2), (2, 1)), questions, think_off, think_on)
    assert small <= big
    for chosen, (reasoning, rag) in ((big, ((12, 6), (6, 3))), (small, ((5, 2), (2, 1)))):
        groups = _group_of(questions, chosen)
        # Groupes entiers : toutes les questions think_off d'un groupe retenu.
        assert chosen == {qid for qid in think_off if questions[qid]["group"] in groups}
        for usage, (total, on) in (("reasoning", reasoning), ("rag", rag)):
            mine = {
                g
                for g in groups
                if any(
                    questions[q]["usage"] == usage and questions[q]["group"] == g for q in chosen
                )
            }
            with_on = {
                g for g in mine if any(q in think_on and questions[q]["group"] == g for q in chosen)
            }
            assert (len(mine), len(with_on)) == (total, on)


@pytest.mark.parametrize("seed", [0, 8, 41])
def test_selection_groups_represents_each_source_in_proportion(seed):
    questions, think_off, think_on = _grouped_set()
    on_ids = set(think_on)
    pools = {}  # (ensemble, source) → nombre de groupes de la source dans l'ensemble
    for qid in think_off:
        q = questions[qid]
        if q["usage"] != "reasoning":
            continue
        pool = (
            "on"
            if any(o in on_ids and questions[o]["group"] == q["group"] for o in questions)
            else "off"
        )
        pools.setdefault((pool, q["source"]), set()).add(q["group"])
    sizes = {key: len(groups) for key, groups in pools.items()}
    total = {pool: sum(n for (p, _), n in sizes.items() if p == pool) for pool in ("on", "off")}
    for on in range(total["on"] + 1):
        for off in range(total["off"] + 1):
            chosen = selected_ids(_groups(seed, (on + off, on)), questions, think_off, think_on)
            groups = _group_of(questions, chosen)
            for (pool, source), n in sizes.items():
                count = len(groups & pools[(pool, source)])
                wanted = (on if pool == "on" else off) * n / total[pool]
                assert abs(count - wanted) <= 1, (pool, source, on, off)


def test_selection_groups_short_pool_takes_everything_and_warns(caplog):
    import logging

    questions, think_off, think_on = _grouped_set()
    logger = logging.getLogger("scripts.quality_bench.common.selection")
    logger.addHandler(caplog.handler)  # le logger du paquet peut ne pas propager
    try:
        with caplog.at_level(logging.WARNING, logger=logger.name):
            # Raisonnement : 9 groupes avec think_on (6 bbeh-mini + 3 var-math-fr), 9 sans.
            chosen = selected_ids(_groups(1, (40, 20)), questions, think_off, think_on)
    finally:
        logger.removeHandler(caplog.handler)
    reasoning = {qid for qid in think_off if questions[qid]["usage"] == "reasoning"}
    assert chosen == reasoning  # les deux ensembles trop courts : tout est pris
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "9 groupes avec une question think_on seulement (20 demandés)" in m for m in messages
    )
    assert any("9 groupes sans think_on seulement (20 demandés)" in m for m in messages)


def test_selection_groups_plan_keeps_the_think_on_intersection():
    qs = [synthetic_question("bbeh-mini", n) for n in range(1, 9)]
    qs += [synthetic_question("piaf", n, group=f"piaf/{n // 2}") for n in range(1, 9)]
    by_id = {q["id"]: q for q in qs}
    think_on = [q["id"] for q in qs if q["id"].endswith(("1", "2", "3"))]
    tracks = {"think_off": sorted(by_id), "think_on": think_on}
    generation = {
        "selection": {
            "groups": {
                "seed": 5,
                "per_usage": {
                    "reasoning": {"think_off": 4, "think_on": 2},
                    "rag": {"think_off": 2, "think_on": 1},
                },
            }
        },
        "num_ctx_tiers": [4096, 8192],
        "caps": DEFAULT_GENERATION["caps"],
    }
    plan = build_plan(generation, by_id, tracks)
    off = [q["id"] for q in plan["think_off"]]
    on = [q["id"] for q in plan["think_on"]]
    assert set(off) == selected_ids(generation["selection"], by_id, tracks["think_off"], think_on)
    assert on == sorted(set(off) & set(think_on))
    assert sum(1 for qid in off if qid.startswith("reasoning/")) == 4
    rag_groups = {by_id[qid]["group"] for qid in off if qid.startswith("rag/")}
    assert len(rag_groups) == 2
    for group in rag_groups:  # groupes entiers
        members = {q["id"] for q in qs if q["group"] == group}
        assert members <= set(off)
    # Le tirage sample et le tirage épinglé restent inchangés (test précédent).
    assert _sample_plan(7)["think_on"] == ["rag/piaf/0002"]


# --- Manifeste ---------------------------------------------------------------------------


def _first_run():
    assert _run() == 0
    return paths.generation_path(CAMPAIGN).read_bytes()


def test_digest_change_refuses_resume(env):
    before = _first_run()
    env["fake"].models[THINK].digest = "e" * 64
    assert _run() == 1
    assert paths.generation_path(CAMPAIGN).read_bytes() == before


def test_ollama_version_change_refuses_resume(env):
    before = _first_run()
    env["fake"].version = "0.40.3"
    assert _run() == 1
    assert paths.generation_path(CAMPAIGN).read_bytes() == before


def test_configuration_change_refuses_resume(env):
    before = _first_run()
    _write_campaign(env["config_dir"], max_attempts=4)
    assert _run() == 1
    assert paths.generation_path(CAMPAIGN).read_bytes() == before


# --- Pannes ------------------------------------------------------------------------------


def _fail_question(name, env, make_failure, times=1):
    """Responder qui échoue ``times`` fois sur la question ``name``, puis répond."""
    target = env["named"][name]["messages"][0]["content"]
    state = {"failures": 0}

    def responder(body, fake):
        if _content(body) == target and state["failures"] < times:
            state["failures"] += 1
            return make_failure(fake)
        return reply()

    env["fake"].responder = responder
    return state


def _outage_then_back(fake):
    fake.down = 2  # sonde immédiate, puis un premier essai de wait_for_ollama
    raise OutageError


def test_confirmed_outage_redoes_question_without_counting(env):
    fake = env["fake"]
    _fail_question("piaf", env, _outage_then_back)
    assert _run() == 0
    piaf = env["named"]["piaf"]["id"]
    line = next(line for line in _lines() if line["question_id"] == piaf)
    assert (line["status"], line["attempts"], line["calls"]) == ("ok", 1, 1)
    assert [line["key"] for line in _lines()] == _expected_keys(env)
    assert env["clock"].now == 5  # une attente de wait_for_ollama, horloge simulée
    warmups = [(w["model"], w["num_ctx"]) for w in read_jsonl(paths.warmups_path(CAMPAIGN))]
    assert warmups[:2] == [(THINK, 4096), (THINK, 4096)]  # nouvelle chauffe après la panne
    assert fake.loaded is None


def test_service_gone_exits_1_without_line(env):
    _write_campaign(env["config_dir"], ollama_wait_s=12)

    def gone(fake):
        fake.down = 10**6
        raise OutageError

    _fail_question("piaf", env, gone)
    assert _run() == 1
    piaf = env["named"]["piaf"]["id"]
    assert not any(line["question_id"] == piaf for line in _lines())
    assert env["clock"].now == 12


def test_service_back_in_another_version_exits_1(env):
    def other_version(fake):
        fake.down = 1
        fake.version = "0.40.3"
        raise OutageError

    _fail_question("piaf", env, other_version)
    assert _run() == 1
    piaf = env["named"]["piaf"]["id"]
    assert not any(line["question_id"] == piaf for line in _lines())


@pytest.mark.parametrize("status", [500, 400])
def test_live_service_failures_count_attempts_then_error(env, status):
    state = _fail_question(
        "piaf", env, lambda fake: httpx2.Response(status, json={"error": "panne synthétique"}), 10
    )
    assert _run() == 0
    piaf = env["named"]["piaf"]["id"]
    lines = [line for line in _lines() if line["question_id"] == piaf]
    first = lines[0]
    assert (first["status"], first["attempts"]) == ("error", 3)
    assert str(status) in first["error"] and "panne synthétique" in first["error"]
    assert first["output"] == [] and first["calls"] == 0
    assert state["failures"] == 3 * len(lines)  # aucune autre ligne en erreur
    # 5xx : le modèle a pu tomber, nouvelle chauffe après chaque essai compté, y compris le
    # dernier (avant la question suivante du palier, bfcl-live). 4xx : le modèle reste chargé,
    # aucune chauffe de plus (l'invite de chauffe viendrait du cache de préfixe).
    warmups = [(w["model"], w["num_ctx"]) for w in read_jsonl(paths.warmups_path(CAMPAIGN))]
    count = 4 if status == 500 else 1
    assert warmups[: count + 1] == [(THINK, 4096)] * count + [(THINK, 8192)]


def test_live_unavailable_counts_attempt_then_succeeds(env):
    _fail_question("piaf", env, lambda fake: httpx2.Response(503, json={"error": "x"}), 2)
    assert _run() == 0
    piaf = env["named"]["piaf"]["id"]
    line = next(line for line in _lines() if line["question_id"] == piaf)
    assert (line["status"], line["attempts"]) == ("ok", 3)
    # Nouvelle chauffe avant chaque nouvel essai compté (deux échecs : deux chauffes de plus).
    warmups = [(w["model"], w["num_ctx"]) for w in read_jsonl(paths.warmups_path(CAMPAIGN))]
    assert warmups[:4] == [(THINK, 4096)] * 3 + [(THINK, 8192)]


def test_live_failure_with_other_version_exits_1(env):
    def other_version(fake):
        fake.version = "0.40.3"  # /api/version répond aussitôt, dans une autre version
        return httpx2.Response(503, json={"error": "x"})

    _fail_question("piaf", env, other_version)
    assert _run() == 1
    piaf = env["named"]["piaf"]["id"]
    assert not any(line["question_id"] == piaf for line in _lines())
    assert env["clock"].now == 0


def test_error_line_keeps_partial_output_of_last_attempt(env):
    target = env["named"]["bfcl_multi"]["messages"][0]["content"]

    def responder(body, fake):
        if _content(body) == target and len(body["messages"]) > 1:
            return httpx2.Response(400, json={"error": "refus"})
        return reply("tour 0")

    env["fake"].responder = responder
    assert _run() == 0
    line = next(
        line for line in _lines() if line["question_id"] == env["named"]["bfcl_multi"]["id"]
    )
    assert line["status"] == "error" and line["calls"] == 1
    assert [m["role"] for m in line["output"]] == ["assistant", "user"]


def test_consecutive_error_counter_resets_on_ok_lines(env):
    _write_campaign(env["config_dir"], max_consecutive_errors=2, max_attempts=1)
    failing = {env["named"][name]["messages"][0]["content"] for name in ("piaf", "writing")}

    def responder(body, fake):
        if _content(body) in failing:
            return httpx2.Response(400, json={"error": "refus"})
        return reply()

    env["fake"].responder = responder
    assert _run() == 0
    lines = _lines()
    assert [line["key"] for line in lines] == _expected_keys(env)
    statuses = [line["status"] for line in lines]
    assert statuses.count("error") >= 4
    assert not any(a == b == "error" for a, b in zip(statuses, statuses[1:], strict=False))


def test_lines_without_request_do_not_reset_error_counter(env):
    """error, context_exceeded sans requête, error : la série continue (code 1)."""
    _write_campaign(
        env["config_dir"],
        models=[MODELS[1], MODELS[0]],
        max_consecutive_errors=2,
        max_attempts=1,
    )
    writing = env["named"]["writing"]["messages"][0]["content"]
    formatted = env["named"]["formatted"]["messages"][0]["content"]

    def responder(body, fake):
        if _content(body) == writing or (_content(body) == formatted and body["model"] == THINK):
            return httpx2.Response(400, json={"error": "refus"})
        return reply()

    env["fake"].responder = responder
    assert _run() == 1
    statuses = [line["status"] for line in _lines()]
    assert statuses[-4:] == ["error", "context_exceeded", "context_exceeded", "error"]


def test_consecutive_errors_stop_campaign(env):
    _write_campaign(env["config_dir"], max_consecutive_errors=2, max_attempts=1)
    env["fake"].responder = lambda body, fake: httpx2.Response(400, json={"error": "refus"})
    assert _run() == 1
    lines = _lines()
    assert [line["status"] for line in lines] == ["error", "error"]
    assert env["fake"].unloads == [THINK]


def test_bench_defect_is_raised_never_counted_as_an_attempt(env, monkeypatch):
    """Un défaut du banc (paramètre refusé par le client, avant toute requête) remonte tel
    quel : ni essai compté, ni ligne ``error`` qui marquerait la clé comme faite."""
    from scripts.quality_bench.ollama.client import OllamaClient

    target = env["named"]["piaf"]["messages"][0]["content"]
    original = OllamaClient.chat

    def chat(self, model, messages, **kwargs):
        if messages[0]["content"] == target:
            raise ValueError("format refusé par le client")
        return original(self, model, messages, **kwargs)

    monkeypatch.setattr(OllamaClient, "chat", chat)
    with pytest.raises(ValueError, match="format refusé"):
        _run()
    piaf = env["named"]["piaf"]["id"]
    assert _lines() and not any(line["question_id"] == piaf for line in _lines())
    assert not any(line["status"] == "error" for line in _lines())


def test_failed_unload_and_ps_do_not_stop_the_campaign(env):
    """Déchargement (``keep_alive: 0``) et ``/api/ps`` après la chauffe sont « au mieux » :
    leur échec est journalisé, la campagne continue."""
    fake = env["fake"]
    fake._generate = lambda body: httpx2.Response(500, json={"error": "déchargement"})
    fake._ps = lambda body: httpx2.Response(500, json={"error": "ps"})
    assert _run() == 0
    assert [line["key"] for line in _lines()] == _expected_keys(env)
    warmups = read_jsonl(paths.warmups_path(CAMPAIGN))
    assert warmups and all(w["size"] is None and w["size_vram"] is None for w in warmups)
    log = paths.log_path(CAMPAIGN, "generate").read_text(encoding="utf-8")
    assert "déchargement impossible" in log and "/api/ps illisible" in log


# --- Outils ------------------------------------------------------------------------------


def _scripted_tools(env):
    multi = env["named"]["bfcl_multi"]["messages"][0]["content"]
    single = env["named"]["bfcl_ast"]["messages"][0]["content"]
    script = []
    for steps in GOOD_STEPS:
        script += [reply("", tool_calls=[call(n, **a) for n, a in step]) for step in steps]
        script.append(reply("Fait."))

    def responder(body, fake):
        if _content(body) == multi:
            index = sum(1 for m in body["messages"] if m["role"] == "assistant")
            return script[index]
        if _content(body) == single:
            return reply("", tool_calls=[tool_call("weather_get", {"city": "Paris", "days": 2.5})])
        return reply()

    env["fake"].responder = responder


def test_tool_outputs_are_gradable(env):
    _scripted_tools(env)
    assert _run() == 0
    for line in _lines():
        question = env["by_id"][line["question_id"]]
        if question["grader"]["name"] not in ("bfcl_state", "bfcl_ast"):
            continue
        graded = grade_line(question, line).record
        assert (graded["status"], graded["success"]) == ("ok", True), line["key"]
        if question["grader"]["name"] == "bfcl_ast":
            assert line["calls"] == 1 and [m["role"] for m in line["output"]] == ["assistant"]
        else:
            assert line["calls"] == 5
            roles = [m["role"] for m in line["output"]]
            assert roles.count("tool") == 3 and roles.count("user") == 1


def test_tool_call_cap_reached(env):
    _write_campaign(env["config_dir"], max_tool_calls_per_turn=1)
    multi = env["named"]["bfcl_multi"]["messages"][0]["content"]

    def responder(body, fake):
        if _content(body) == multi:
            return reply("", tool_calls=[call("cd", folder="docs"), call("ls")])
        return reply()

    env["fake"].responder = responder
    assert _run() == 0
    line = next(
        line for line in _lines() if line["question_id"] == env["named"]["bfcl_multi"]["id"]
    )
    assert line["call_cap_reached"] and line["calls"] == 1 and line["status"] == "ok"
    question = env["by_id"][line["question_id"]]
    assert grade_line(question, line).record["status"] == "non_compliant"
