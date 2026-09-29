"""
Réponse interrompue (story 24), avec AppTest : une génération coupée par Ollama (flux sans
`done`) est relancée une fois, automatiquement, par la règle du cœur. Le texte partiel
disparaît, la relance est annoncée sans « réponse interrompue », et le CO₂ compte les tokens
des tentatives coupées. Dans l'évaluation de la qualité, une interruption affiche son propre
message, jamais le conseil sur Ollama.

Aucun Ollama ni réseau : `LLMProvider.chat_stream` est simulé.
Usage: python -m pytest tests/app/test_interrupted_retry.py -v
"""

import asyncio

import pytest

from src.app.formatting import NBSP, format_co2, mg_to_grams
from src.app.states import INTERRUPTED_MESSAGE, RETRY_MESSAGE, generation_failure_advice
from src.core.answer_carbon import answer_carbon_mg
from src.core.llm_provider import LLMProvider
from src.core.metrics import InferenceMetrics, InterruptedResponseError
from tests.app.conftest import FAKE_LOCAL_MODELS
from tests.app.test_states import (  # noqa: F401 (fixture partagée)
    ARENA_PAGE,
    RAG_PAGE,
    _all_texts,
    _button,
    _errors,
    _friendly,
    _metric,
    _results_table,
    _run_arena,
    _run_evaluation,
    indexed_base,
    run_page,
)

PARTIAL = "Début coupé "
FINAL = "Réponse complète."
FINAL_TOKENS = 40
OLLAMA_ADVICE = "Vérifiez qu'Ollama est démarré"


def _flaky_stream(*attempts, per_tag=None, judge_attempts=("ok",)):
    """`LLMProvider.chat_stream` simulé. Pour chaque modèle (et pour le juge de l'Arène, à
    part), une entrée par appel, la dernière répétée : un entier n donne n fragments puis
    une coupure (`InterruptedResponseError` portant n) ; "ok" une réponse complète de
    FINAL_TOKENS tokens (le juge répond « 85 ») ; une exception est levée telle quelle.
    `per_tag` donne un script par tag ; (délai, n) : n fragments coupés après `délai` s."""
    calls: dict[str, int] = {}

    async def stream(model_name, messages, temperature=0.7, system_prompt=None):
        is_judge = "juge impartial" in (messages[-1].get("content") or "")
        key = "judge" if is_judge else model_name
        script = judge_attempts if is_judge else (per_tag or {}).get(model_name, attempts)
        n = calls[key] = calls.get(key, 0) + 1
        attempt = script[min(n, len(script)) - 1]
        if isinstance(attempt, BaseException):
            raise attempt
        if isinstance(attempt, tuple):  # (délai en s, fragments) : tentative lente coupée
            delay, attempt = attempt
            await asyncio.sleep(delay)
        if isinstance(attempt, int):
            for _ in range(attempt):
                yield PARTIAL
            raise InterruptedResponseError(output_tokens=attempt)
        yield "85" if is_judge else FINAL
        yield InferenceMetrics(
            model_name,
            10,
            FINAL_TOKENS,
            1.0,
            0.1,
            40.0,
            load_measured=True,
            eval_duration_s=1.0,
        )

    return stream


def _use(monkeypatch, stream):
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(stream))


def _lower_texts(at) -> list[str]:
    """Tout le texte de la page, masqué compris (suivi replié, expanders), en minuscules."""
    texts = _all_texts(at) + [s.label for s in at.status] + [e.label for e in at.expander]
    return [t.lower() for t in texts if isinstance(t, str)]


def _assert_no_interruption_shown(at):
    """Ni « réponse interrompue » (lu comme un échec par les tests e2e) ni texte partiel."""
    texts = _lower_texts(at)
    assert not [t for t in texts if "réponse interrompue" in t]
    assert not [t for t in texts if PARTIAL.strip().lower() in t]


def _co2_mg(tag, tokens):
    return answer_carbon_mg(tag, tokens, False)


def test_retry_message_never_reads_as_a_failure():
    assert "réponse interrompue" not in RETRY_MESSAGE.lower()


# ---------------------------------------------------------------------------
# Arène des modèles : Chat libre, Banc d'essai, Arène
# ---------------------------------------------------------------------------


def test_chat_retry_shows_second_answer_only(monkeypatch, run_page):
    _use(monkeypatch, _flaky_stream(12, "ok"))
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]

    user, answer = at.session_state["messages"]
    assert not answer.get("error")
    assert answer["content"] == FINAL
    expected = _co2_mg(answer["model_tag"], FINAL_TOKENS + 12)
    assert answer["metrics_data"]["co2_mg"] == pytest.approx(expected)
    assert not _errors(at)
    _assert_no_interruption_shown(at)
    session = format_co2(mg_to_grams(expected))
    assert any(t == f"Session : **{session}**" for t in _all_texts(at))


def test_chat_two_interruptions_count_co2_in_session(monkeypatch, run_page):
    _use(monkeypatch, _flaky_stream(12, 8))
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]

    assert INTERRUPTED_MESSAGE in _errors(at)
    user, turn = at.session_state["messages"]
    assert turn["error"] is True and turn["content"] == INTERRUPTED_MESSAGE
    tag = FAKE_LOCAL_MODELS[0]["model"]
    # Rendu au rerun suivant : le total de session compte les 20 tokens coupés.
    at.run()
    expected = format_co2(mg_to_grams(_co2_mg(tag, 12 + 8)))
    assert any(t == f"Session : **{expected}**" for t in _all_texts(at)), _all_texts(at)
    # Aucun pied de réponse sous un tour en erreur.
    assert not any(t.startswith("Débit") or "Durée totale" in t for t in _all_texts(at))


def test_chat_complete_stream_unchanged(monkeypatch, run_page):
    _use(monkeypatch, _flaky_stream("ok"))
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()

    answer = at.session_state["messages"][1]
    assert answer["metrics_data"]["co2_mg"] == pytest.approx(
        _co2_mg(answer["model_tag"], FINAL_TOKENS)
    )


def test_lab_retry_counts_both_attempts(monkeypatch, run_page):
    _use(monkeypatch, _flaky_stream(12, "ok"))
    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]

    assert not _errors(at)
    assert FINAL in [m.value for m in at.markdown]
    tag = at.session_state["lab_last_tag"]
    assert _metric(at, "CO₂") == format_co2(mg_to_grams(_co2_mg(tag, FINAL_TOKENS + 12)))
    assert _metric(at, "Tokens générés") == str(FINAL_TOKENS)
    assert "environ 12 tokens" in _co2_help(at)
    _assert_no_interruption_shown(at)


def _co2_help(at) -> str:
    (metric,) = [m for m in at.metric if m.label == "CO₂"]
    return metric.proto.help


def test_lab_complete_stream_has_no_retry_help(monkeypatch, run_page):
    _use(monkeypatch, _flaky_stream("ok"))
    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]

    assert _co2_help(at) == ""


def test_arena_retry_announced_and_counted(monkeypatch, run_page):
    """Modèles et juge coupés une fois : lignes du suivi, résultats de la seconde tentative,
    CO₂ des deux, aucune ligne de résultat en plus pour le juge."""
    _use(monkeypatch, _flaky_stream(12, "ok", judge_attempts=(5, "ok")))
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    table = _results_table(at)
    assert len(table) == len(FAKE_LOCAL_MODELS)
    assert list(table["Note"]) == ["85/100", "85/100"]
    expected_mg = _co2_mg(FAKE_LOCAL_MODELS[0]["model"], FINAL_TOKENS + 12)
    assert list(table["CO₂"]) == [pytest.approx(expected_mg, abs=0.01)] * 2
    retries = [t for t in _all_texts(at) if RETRY_MESSAGE in t]
    assert len(retries) == len(FAKE_LOCAL_MODELS) + 1  # deux modèles, un juge
    assert any(t.startswith("**Juge") for t in retries)
    _assert_no_interruption_shown(at)


def test_arena_two_interruptions_unchanged(monkeypatch, run_page):
    _use(monkeypatch, _flaky_stream(12, 8))
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    # Tous en échec : pas de tableau ni de verdict, lignes du suivi comme avant la story.
    assert "Verdict" not in [h.value for h in at.header]
    assert len([t for t in _all_texts(at) if "Réponse interrompue" in t]) == 2
    assert len([t for t in _all_texts(at) if RETRY_MESSAGE in t]) == 2


# ---------------------------------------------------------------------------
# Assistant documentaire : Discussion, évaluation de la qualité
# ---------------------------------------------------------------------------


def test_documents_chat_retry(monkeypatch, indexed_base, run_page):
    _use(monkeypatch, _flaky_stream(12, "ok"))
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]

    user, answer = at.session_state["rag_messages"]
    assert answer["content"] == FINAL
    expected = _co2_mg(answer["model_tag"], FINAL_TOKENS + 12)
    assert answer["metrics"]["carbon_mg"] == pytest.approx(expected)
    assert not _errors(at)
    _assert_no_interruption_shown(at)


def test_documents_chat_retry_announced_while_running(monkeypatch, indexed_base, run_page):
    """Coupure puis autre échec à la relance (ConnectionError) : le suivi garde l'annonce de
    la relance, et la page finale (échec générique) ne contient ni « réponse interrompue »
    ni le texte partiel."""
    _use(monkeypatch, _flaky_stream(12, ConnectionError("refus")))
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]

    assert any(RETRY_MESSAGE in t for t in _all_texts(at))
    _assert_no_interruption_shown(at)


def test_documents_chat_two_interruptions(monkeypatch, indexed_base, run_page):
    _use(monkeypatch, _flaky_stream(12, 8))
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()

    assert INTERRUPTED_MESSAGE in _errors(at)
    assert [m["role"] for m in at.session_state["rag_messages"]] == ["user"]


def test_documents_evaluation_retry(monkeypatch, indexed_base, run_page):
    from src.core.eval_engine import EvalEngine, EvalResult

    judged = []
    monkeypatch.setattr(
        EvalEngine,
        "evaluate_single_turn",
        lambda self, **kw: judged.append(kw["response"]) or EvalResult(0.8, 0.9, 0.85),
    )
    _use(monkeypatch, _flaky_stream(12, "ok"))
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS[:1])

    assert judged == [FINAL]
    assert not _errors(at)
    assert any(RETRY_MESSAGE in t for t in _all_texts(at))
    tag = FAKE_LOCAL_MODELS[0]["model"]
    co2 = format_co2(mg_to_grams(_co2_mg(tag, FINAL_TOKENS + 12)))
    assert any(t == f"CO₂ : {co2}" for t in _all_texts(at)), _all_texts(at)
    _assert_no_interruption_shown(at)


def test_documents_evaluation_interruption_message(monkeypatch, indexed_base, run_page):
    """Candidat coupé deux fois : message d'interruption, sans le conseil sur Ollama ; autre
    échec du même lot : conseil actuel pour celui-là."""
    from src.core.eval_engine import EvalEngine, EvalResult

    monkeypatch.setattr(
        EvalEngine, "evaluate_single_turn", lambda self, **kw: EvalResult(0.8, 0.9, 0.85)
    )
    cut, down = (m["model"] for m in FAKE_LOCAL_MODELS)
    _use(monkeypatch, _flaky_stream(per_tag={cut: (12, 8), down: (ConnectionError("refus"),)}))
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS)

    errors = _errors(at)
    assert len(errors) == 2
    (interrupted,) = [e for e in errors if INTERRUPTED_MESSAGE in e]
    assert _friendly(FAKE_LOCAL_MODELS[0]) in interrupted
    assert OLLAMA_ADVICE not in interrupted
    (other,) = [e for e in errors if INTERRUPTED_MESSAGE not in e]
    assert _friendly(FAKE_LOCAL_MODELS[1]) in other
    assert _friendly(FAKE_LOCAL_MODELS[0]) not in other
    assert OLLAMA_ADVICE in other
    assert generation_failure_advice(down).startswith(OLLAMA_ADVICE)


def test_documents_evaluation_retry_times_only_the_successful_attempt(
    monkeypatch, indexed_base, run_page
):
    """La durée du tableau ne compte pas la tentative coupée (1 s ici) : une relance ne
    pénalise pas le modèle."""
    from src.core.eval_engine import EvalEngine, EvalResult

    monkeypatch.setattr(
        EvalEngine, "evaluate_single_turn", lambda self, **kw: EvalResult(0.8, 0.9, 0.85)
    )
    _use(monkeypatch, _flaky_stream((1.0, 12), "ok"))
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS[:1])

    (duration,) = _results_table(at)["Durée"]
    assert duration < 0.5


def test_documents_evaluation_only_interrupted(monkeypatch, indexed_base, run_page):
    """Tous coupés deux fois : une seule erreur, pas d'avertissement « Aucun résultat »."""
    _use(monkeypatch, _flaky_stream(12, 8))
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS)

    (error,) = _errors(at)
    assert INTERRUPTED_MESSAGE in error
    assert not [w.value for w in at.warning if w.value.startswith("Aucun résultat")]


def test_documents_evaluation_success_and_interrupted(monkeypatch, indexed_base, run_page):
    """Un modèle noté, un coupé deux fois : compté parmi les modèles en échec."""
    from src.core.eval_engine import EvalEngine, EvalResult

    monkeypatch.setattr(
        EvalEngine, "evaluate_single_turn", lambda self, **kw: EvalResult(0.8, 0.9, 0.85)
    )
    ok, cut = (m["model"] for m in FAKE_LOCAL_MODELS)
    _use(monkeypatch, _flaky_stream(per_tag={ok: ("ok",), cut: (12, 8)}))
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS)

    (status,) = [s for s in at.status if s.label.startswith("Évaluation")]
    assert f"1{NBSP}modèle en échec" in status.label
