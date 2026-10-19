"""Jeu fixe de cas du juge de l'évaluation (story 7.2) : non-régression avec des sorties rejouées.

Aucun modèle, aucun réseau : un faux juge rend les sorties de `judge-replay.json`. Les verdicts
attendus sont des propositions à relire par Anaël (`cases.json`, `review`) ; ces tests prouvent
que le code rend les notes attendues, pas que les verdicts attendus sont justes.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from wavelocalai.errors import ProviderError
from wavelocalai.evaluation import metrics, prompts
from wavelocalai.evaluation.judge import JudgeReply
from wavelocalai.inference.judge_port import NOT_EVALUATED_INVALID, NOT_EVALUATED_UNAVAILABLE
from wavelocalai.models.port import ChatRequest, Done, ModelRef, TextDelta

from .. import eval_fixed_set as fixed

DOC = fixed.load_cases()
REPLAY = json.loads(fixed.REPLAY_FILE.read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in DOC["cases"]}
NO_CLAIM_CASE = "prime-naissance-sans-reponse"
LONG_CASE = "chantier-fin-de-journee"
RERECORD = "python -m tests.v2.eval_fixed_set record"


def _replayed(replay=REPLAY):
    import asyncio

    return asyncio.run(fixed.replay_all(DOC, replay))


# --- le jeu lui-même ----------------------------------------------------------------------------


def test_the_set_has_about_a_dozen_cases_that_cover_every_verdict_and_the_edge_cases():
    verdicts = {c["verdict"] for case in DOC["cases"] for c in case["claims"]}
    assert len(DOC["cases"]) >= 10
    assert verdicts == set(prompts.VERDICTS)
    assert len({case["id"] for case in DOC["cases"]}) == len(DOC["cases"])
    assert not CASES[NO_CLAIM_CASE]["claims"]  # une réponse qui dit ne pas savoir
    assert (
        len(CASES[LONG_CASE]["claims"]) > prompts.MAX_CLAIMS
    )  # plus d'affirmations que le plafond
    assert any(fixed.expected_faithfulness(c) == 0 for c in DOC["cases"])  # un vrai 0
    assert any(len(c["useful"]) < len(c["sources"]) for c in DOC["cases"])


def test_every_expected_verdict_points_at_an_existing_extract():
    for case in DOC["cases"]:
        numbers = {source["n"] for source in case["sources"]}
        assert numbers == set(range(1, len(numbers) + 1)), case["id"]
        assert set(case["useful"]) <= numbers, case["id"]
        for claim in case["claims"]:
            if claim["verdict"] == prompts.UNSUPPORTED:
                assert claim["support"] is None, (case["id"], claim)
            else:
                assert claim["support"] in numbers, (case["id"], claim)
        assert len(case["relevance_questions"]) == prompts.RELEVANCE_QUESTIONS


def test_the_review_state_is_declared_and_never_claims_a_human_review_nobody_made():
    review = DOC["review"]
    assert review["status"] in fixed.REVIEW_STATES
    states = {case["review"] for case in DOC["cases"]}
    assert states <= set(fixed.REVIEW_STATES)
    if states != {"proposed"}:  # un cas marqué relu : la relecture est signée
        assert review["reviewed_by"] and review["reviewed_on"]
    if not review["reviewed_by"]:
        assert states == {"proposed"} and review["status"] == "proposed"
        assert not review["reviewed_on"]
    else:  # relecture signée : datée (AAAA-MM-JJ), fichier et cas tous relus
        date.fromisoformat(review["reviewed_on"])
        assert review["status"] != "proposed" and "proposed" not in states


def test_the_minimum_agreement_is_a_share_between_zero_and_one():
    minimum = DOC["minimum_agreement"]
    assert set(minimum) == {"verdict", "useful"}
    assert all(0.0 <= value <= 1.0 for value in minimum.values())


def test_the_replay_file_matches_the_cases():
    import asyncio

    stale = asyncio.run(fixed.record(DOC)) != REPLAY
    assert not stale, f"judge-replay.json n'est plus celui de cases.json : `{RERECORD}`."


# --- non-régression : les notes rejouées égalent les attendues -----------------------------------


@pytest.mark.parametrize("case_id", list(CASES))
def test_the_replayed_scores_and_verdicts_equal_the_expected_ones(case_id):
    case = CASES[case_id]
    notes = _replayed()[case_id]
    faith, precision = notes["faithfulness"], notes["context_precision"]
    assert faith.score == fixed.expected_faithfulness(case)
    if faith.score is None:
        assert faith.reason == metrics.NOT_EVALUATED_NO_CLAIM  # jamais 0
    else:
        assert faith.detail["verdicts"] == [
            {**v, "reason": got["reason"]}
            for v, got in zip(fixed.expected_verdicts(case), faith.detail["verdicts"], strict=True)
        ]
    assert precision.score == fixed.expected_precision(case)
    assert precision.detail == {"useful": case["useful"]}
    assert notes["relevance"].score == REPLAY["relevance"][case_id]
    assert notes["relevance"].detail == {"questions": case["relevance_questions"]}


def test_a_zero_is_a_real_score_and_not_the_same_as_not_evaluated():
    assert _replayed()["preavis-cadre"]["faithfulness"].score == 0
    assert _replayed()[NO_CLAIM_CASE]["faithfulness"].score is None
    assert _replayed()[NO_CLAIM_CASE]["context_precision"].score == 0


def test_only_the_first_ten_claims_are_verified_and_the_reason_says_so():
    faith = _replayed()[LONG_CASE]["faithfulness"]
    assert len(faith.detail["verdicts"]) == prompts.MAX_CLAIMS
    assert faith.score == 80
    assert "Notée sur les 10 premières affirmations sur 12." in faith.reason
    assert "1 contredite" in faith.reason
    others = [n["faithfulness"].reason for cid, n in _replayed().items() if cid != LONG_CASE]
    assert not any("premières affirmations" in reason for reason in others)


# --- sensibilité : une modification de l'invite ou du verdict fait échouer ------------------------


def test_a_changed_prompt_is_not_replayed_and_the_failure_says_what_to_do(monkeypatch):
    monkeypatch.setattr(prompts, "VERDICT_SYSTEM", prompts.VERDICT_SYSTEM + " Sois indulgent.")
    with pytest.raises(fixed.UnrecordedRequestError, match="judge-replay.json"):
        _replayed()
    monkeypatch.setattr(
        prompts, "VERDICT_SYSTEM", prompts.VERDICT_SYSTEM.removesuffix(" Sois indulgent.")
    )


def test_another_cut_of_the_claims_changes_the_replayed_score(monkeypatch):
    monkeypatch.setattr(prompts, "MAX_CLAIMS", 9)  # la 10e affirmation (contredite) n'est plus vue
    faith = _replayed()[LONG_CASE]["faithfulness"]
    assert faith.score == 89 != 80  # 8 appuyées sur 9, au lieu de 8 sur 10


def test_a_changed_verdict_changes_the_replayed_score():
    case = CASES["mediatheque-pret"]
    request = prompts.verdict_request(case["claims"][0]["claim"], case["sources"])
    key = fixed.request_key(request)
    altered = json.loads(json.dumps(REPLAY))
    altered["entries"][key]["output"] = json.dumps(
        {"verdict": prompts.CONTRADICTED, "support": 1, "reason": "Modifié."}
    )
    assert _replayed(altered)["mediatheque-pret"]["faithfulness"].score == 80
    assert fixed.expected_faithfulness(case) == 100


# --- une réponse coupée ou plafonnée le dit dans sa raison (report de la revue 7.1) -------------


async def _echo(request: ChatRequest) -> JudgeReply:
    schema = request.response_schema
    if schema is prompts.CLAIMS_SCHEMA:
        return JudgeReply(json.dumps({"claims": ["Une affirmation."]}), "")
    if schema is prompts.VERDICT_SCHEMA:
        return JudgeReply(json.dumps({"verdict": "appuyée", "support": 1, "reason": "Oui."}), "")
    if schema is prompts.QUESTIONS_SCHEMA:
        return JudgeReply(json.dumps({"questions": ["Une question ?"]}), "")
    return JudgeReply(json.dumps({"useful": [1], "reason": "Le premier extrait sert"}), "")


async def _embed(texts):
    return [[1.0, 0.0] for _ in texts]


SOURCES = [{"n": 1, "document": "d.txt", "page": None, "text": "Texte."}]


async def test_a_very_long_answer_says_in_every_reason_that_it_was_cut():
    long = "a" * (prompts.MAX_ANSWER_CHARS + 1)
    faith = await metrics.faithfulness(_echo, "Q ?", long, SOURCES)
    relevance = await metrics.relevance(_echo, _embed, "Q ?", long)
    precision = await metrics.context_precision(_echo, "Q ?", long, SOURCES)
    for note in (faith, relevance, precision):
        assert (
            "Réponse tronquée à 12 000 caractères pour le juge : notée sur son début."
            in note.reason
        )
    assert precision.reason.startswith("Le premier extrait sert.")  # un point avant l'avis
    short = await metrics.faithfulness(_echo, "Q ?", "a" * prompts.MAX_ANSWER_CHARS, SOURCES)
    assert "tronquée" not in short.reason


async def test_more_than_ten_claims_say_how_many_were_left_out():
    async def many(request: ChatRequest) -> JudgeReply:
        if request.response_schema is prompts.CLAIMS_SCHEMA:
            claims = [f"Affirmation numéro {i}." for i in range(14)] + ["Affirmation numéro 3."]
            return JudgeReply(json.dumps({"claims": claims}), "")  # un doublon : 14 distinctes
        return await _echo(request)

    note = await metrics.faithfulness(many, "Q ?", "Réponse.", SOURCES)
    assert len(note.detail["verdicts"]) == prompts.MAX_CLAIMS
    assert "Notée sur les 10 premières affirmations sur 14." in note.reason
    assert prompts.read_claims(json.dumps({"claims": ["A.", "B."]})) == (["A.", "B."], 2)


# --- la mesure avec un vrai juge, éprouvée sans modèle -------------------------------------------


async def test_a_judge_that_agrees_with_the_set_scores_full_agreement():
    judge = fixed.ReplayJudge(REPLAY)
    agreement = await fixed.measure(DOC, judge.ask)
    expected = sum(len(fixed.verified_claims(c)) for c in DOC["cases"])
    assert (agreement.verdicts_same, agreement.verdicts_total) == (expected, expected)
    assert agreement.verdict_rate == agreement.useful_rate == 1.0
    assert agreement.verdicts_invalid == 0 and agreement.faithfulness_gap == 0
    assert agreement.support_same == agreement.support_total > 0
    assert agreement.shortfalls(DOC["minimum_agreement"]) == []
    assert "non informatif" not in agreement.summary(0, len(DOC["cases"]))


async def test_a_lenient_judge_agrees_only_on_the_supported_claims():
    async def lenient(request: ChatRequest) -> JudgeReply:
        if request.response_schema is prompts.VERDICT_SCHEMA:
            return JudgeReply(json.dumps({"verdict": "appuyée", "support": 1, "reason": "Ok."}), "")
        return await fixed.ReplayJudge(REPLAY).ask(request)

    agreement = await fixed.measure(DOC, lenient)
    supported = sum(
        1
        for c in DOC["cases"]
        for claim in fixed.verified_claims(c)
        if claim["verdict"] == "appuyée"
    )
    assert agreement.verdicts_same == supported < agreement.verdicts_total
    # toujours « appuyée » : exactement le juge trivial, donc non informatif même au-dessus du seuil
    assert agreement.majority_verdict == "appuyée"
    assert agreement.verdicts_same == agreement.verdicts_majority
    assert not agreement.verdicts_informative
    assert any(
        "juge non informatif sur les verdicts" in s
        for s in agreement.shortfalls({"verdict": 0.0, "useful": 0.0})
    )
    assert any("attendu contredite, rendu appuyée" in line for line in agreement.lines)
    assert "non relus par Anaël" in agreement.summary(
        fixed.unreviewed_cases(DOC), len(DOC["cases"])
    )


async def test_a_judge_that_calls_every_extract_useful_is_not_informative():
    async def all_useful(request: ChatRequest) -> JudgeReply:
        if request.response_schema is prompts.USEFUL_SCHEMA:
            last = request.messages[-1].content
            case = next(c for c in DOC["cases"] if c["answer"] in last and c["question"] in last)
            useful = [s["n"] for s in case["sources"]]
            return JudgeReply(json.dumps({"useful": useful, "reason": "Tous."}), "")
        return await fixed.ReplayJudge(REPLAY).ask(request)

    agreement = await fixed.measure(DOC, all_useful)
    useful = sum(len(c["useful"]) for c in DOC["cases"])
    assert agreement.extracts_same == useful <= agreement.extracts_majority
    assert not agreement.extracts_informative and agreement.verdicts_informative


async def test_an_unusable_judge_output_is_never_an_agreement():
    async def broken(request: ChatRequest) -> JudgeReply:
        return JudgeReply("pas du JSON", "")

    agreement = await fixed.measure(DOC, broken)
    assert agreement.verdicts_same == 0 and agreement.verdicts_invalid == agreement.verdicts_total
    assert agreement.extracts_same == 0 and agreement.faithfulness_gap is None
    assert len(agreement.shortfalls(DOC["minimum_agreement"])) == 4


class _Streaming:
    ref = ModelRef("faux:1b", "ollama", "local", "chat")

    def __init__(self, chunks=(), error=None):
        self._chunks, self._error = list(chunks), error

    async def stream(self, request):
        for chunk in self._chunks:
            yield chunk
        if self._error is not None:
            raise self._error
        yield Done(None)  # type: ignore[arg-type]


async def test_a_model_used_as_judge_gives_its_text_or_the_reason_it_could_not():
    request = prompts.questions_request("Réponse.")
    ok = _Streaming([TextDelta("{"), TextDelta("}"), TextDelta("pensée", "thought")])
    assert await fixed.ModelAsker(ok).ask(request) == JudgeReply("{}", "")
    invalid = _Streaming(error=ProviderError("invalid_output"))
    assert (await fixed.ModelAsker(invalid).ask(request)).reason == NOT_EVALUATED_INVALID
    down = _Streaming(error=ProviderError("ollama_down"))
    assert (await fixed.ModelAsker(down).ask(request)).reason == NOT_EVALUATED_UNAVAILABLE
