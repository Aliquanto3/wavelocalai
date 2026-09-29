"""
Tests des états d'échec et des états vrais (story 5), avec AppTest : délai dépassé, non évalué,
service indisponible, accélérateur détecté, blocage mémoire, premier chargement, aucun modèle.

Ollama, l'inférence et Ragas sont simulés (tests/app/conftest.py) : aucun réseau.
Référence : _bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md.
Usage: python -m pytest tests/app/test_states.py -v
"""

import pytest
import streamlit
from streamlit.testing.v1 import AppTest

from src.app.states import (
    EMPTY_ANSWER,
    EMPTY_ANSWER_REASON,
    LOADED_LABEL,
    LOADING_FAILED_LABEL,
    LOADING_LABEL,
    NO_MODEL_ELSEWHERE,
    NO_MODEL_IN_ARENA,
    NOT_EVALUATED,
    OLLAMA_DOWN_MESSAGE,
    REASONING_LABEL,
)
from tests.app.conftest import APP_DIR, FAKE_LOCAL_MODELS, THIRD_LOCAL_MODEL
from tests.app.test_pages import RENDER_TIMEOUT_S

ARENA_PAGE = "views/02_Inference_Arena.py"
RAG_PAGE = "views/03_RAG_Knowledge.py"
AGENTS_PAGE = "views/04_Agent_Lab.py"
HARDWARE_PAGE = "views/01_Socle_Hardware.py"
MODULE_PAGES = [HARDWARE_PAGE, ARENA_PAGE, RAG_PAGE, AGENTS_PAGE]
# Délai par défaut d'InferenceService.run_inference (120 s), au format fr-FR.
TIMEOUT_TEXT = "Délai dépassé (2 min)"


def _app(page: str = "Accueil.py") -> AppTest:
    return AppTest.from_file(str(APP_DIR / page), default_timeout=RENDER_TIMEOUT_S)


def _stop_tracker(at):
    if "tracker" in at.session_state:
        at.session_state["tracker"].stop()


@pytest.fixture
def run_page():
    """Exécute une page (directement) et arrête le tracker CodeCarbon à la fin."""
    started = []

    def _run(page: str) -> AppTest:
        at = _app(page)
        started.append(at)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        return at

    yield _run
    for at in started:
        _stop_tracker(at)


def _metric(at, label):
    (metric,) = [m for m in at.metric if m.label == label]
    return metric.value


def _errors(at):
    return [e.value for e in at.error]


def _infos(at):
    return [i.value for i in at.info]


def _all_texts(at):
    """Textes affichés (markdown, légendes, métriques, alertes, cellules de tableau)."""
    texts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    texts += [m.value for m in at.metric] + _errors(at) + _infos(at)
    texts += [w.value for w in at.warning]
    for df in at.dataframe:
        texts += [str(v) for v in df.value.to_numpy().ravel()]
    return texts


def _button(at, label):
    (button,) = [b for b in at.button if b.label == label]
    return button


def _results_table(at):
    """Tableau de résultats (colonne « Statut ») : l'onglet « Gestion des modèles » a le sien."""
    (table,) = [df.value for df in at.dataframe if "Statut" in df.value.columns]
    return table


def _status_state(status) -> str:
    return status.state.removeprefix("state_")


def _label(model: dict) -> str:
    from src.app.ui import model_label
    from src.core.models_db import get_friendly_name_from_tag

    return model_label(get_friendly_name_from_tag(model["model"]), False)


def _friendly(model: dict) -> str:
    from src.core.models_db import get_friendly_name_from_tag

    return get_friendly_name_from_tag(model["model"])


# ---------------------------------------------------------------------------
# Service indisponible (accueil et en-tête de module)
# ---------------------------------------------------------------------------


def test_home_system_available_when_ollama_answers():
    """Ollama joignable : Système « Disponible »."""
    at = _app()
    try:
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert _metric(at, "Système") == "Disponible"
        assert OLLAMA_DOWN_MESSAGE not in _errors(at)
    finally:
        _stop_tracker(at)


def test_home_system_unavailable_when_ollama_down(ollama_down):
    """Ollama arrêté : Système « Indisponible » ; l'accueil n'affiche pas l'alerte (sa
    métrique suffit)."""
    at = _app()
    try:
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert _metric(at, "Système") == "Indisponible"
        assert OLLAMA_DOWN_MESSAGE not in _errors(at)
    finally:
        _stop_tracker(at)


@pytest.mark.parametrize("page", MODULE_PAGES)
def test_module_alert_when_ollama_down(ollama_down, page):
    """Ollama arrêté : `alert-error` en tête de chaque module, sans exception."""
    at = _app()
    try:
        at.run()
        at.switch_page(page).run()
        assert not at.exception, [e.value for e in at.exception]
        assert _errors(at)[0] == OLLAMA_DOWN_MESSAGE
        # Liste vide parce qu'Ollama est arrêté : pas d'état « aucun modèle installé ».
        assert not any(i.startswith("Aucun modèle installé") for i in _infos(at))
    finally:
        _stop_tracker(at)


@pytest.mark.parametrize("page", MODULE_PAGES)
def test_no_module_alert_when_ollama_answers(page):
    at = _app()
    try:
        at.run()
        at.switch_page(page).run()
        assert not at.exception, [e.value for e in at.exception]
        assert OLLAMA_DOWN_MESSAGE not in _errors(at)
    finally:
        _stop_tracker(at)


# ---------------------------------------------------------------------------
# Accélérateur
# ---------------------------------------------------------------------------


def test_accelerator_none_without_gpu(monkeypatch, run_page):
    """Ni GPU NVIDIA ni Apple Silicon : « Aucun », jamais « Actif »."""
    monkeypatch.setattr("src.core.accelerator.detect_nvidia_gpu", lambda: None)
    monkeypatch.setattr("src.core.accelerator.is_apple_silicon", lambda: False)
    at = run_page(HARDWARE_PAGE)
    assert _metric(at, "Accélérateur IA") == "Aucun"
    assert "Actif" not in [m.value for m in at.metric]


def test_accelerator_shows_detected_gpu(monkeypatch, run_page):
    """GPU NVIDIA détecté par NVML : son nom."""
    monkeypatch.setattr("src.core.accelerator.detect_nvidia_gpu", lambda: "NVIDIA GeForce RTX 3060")
    at = run_page(HARDWARE_PAGE)
    assert _metric(at, "Accélérateur IA") == "NVIDIA GeForce RTX 3060"


# ---------------------------------------------------------------------------
# Aucun modèle installé
# ---------------------------------------------------------------------------


def test_arena_tabs_without_models(no_models, run_page):
    """Chat libre, Banc d'essai et Arène : `alert-info` vers « Gestion des modèles »."""
    at = run_page(ARENA_PAGE)
    assert _infos(at).count(NO_MODEL_IN_ARENA) == 3


@pytest.mark.parametrize("mode", ["Agent seul", "Équipe d'agents"])
def test_agents_without_models(no_models, run_page, mode):
    at = run_page(AGENTS_PAGE)
    (radio,) = [r for r in at.sidebar.radio if r.label == "Mode"]
    radio.set_value(mode).run()
    assert not at.exception, [e.value for e in at.exception]
    assert NO_MODEL_ELSEWHERE in _infos(at)


@pytest.fixture
def indexed_base(monkeypatch):
    """Base documentaire non vide (compteur simulé), recherche sans résultat."""
    from src.core.rag_engine import RAGEngine

    monkeypatch.setattr(
        RAGEngine,
        "get_stats",
        lambda self: {"count": 14, "sources": ["note.md"], "collection": "t"},
    )
    monkeypatch.setattr(RAGEngine, "search", lambda self, query, k=3, **kwargs: [])


def test_documents_assistant_without_models(no_models, indexed_base, run_page):
    """Discussion et Évaluation de la qualité, aucun modèle : `alert-info`, pas d'exception."""
    at = run_page(RAG_PAGE)
    assert _infos(at).count(NO_MODEL_ELSEWHERE) == 2


# ---------------------------------------------------------------------------
# Délai dépassé : Chat libre, Banc d'essai
# ---------------------------------------------------------------------------


def test_chat_timeout_shows_error_without_empty_answer(failing_inference, run_page):
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]

    assert any(e.startswith(TIMEOUT_TEXT) for e in _errors(at))
    # Question conservée, aucune réponse vide : le tour en échec est marqué en erreur.
    messages = at.session_state["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["error"] is True and messages[1]["content"].startswith(TIMEOUT_TEXT)
    assert "Détails techniques" in [e.label for e in at.expander]

    # Rerun suivant : l'erreur reste affichée sous la question.
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(e.startswith(TIMEOUT_TEXT) for e in _errors(at))
    assert "Bonjour" in [m.value for m in at.markdown]


def test_chat_failed_turn_not_sent_to_model(monkeypatch, fake_inference, run_page):
    """Le tour en échec (question et erreur) n'est pas renvoyé au modèle au tour suivant."""
    from src.core.inference_service import InferenceService

    fake_inference.errors.update(m["model"] for m in FAKE_LOCAL_MODELS)
    sent = []
    fake_run = InferenceService.run_inference

    async def run_inference(*args, **kwargs):
        sent.append([m["content"] for m in kwargs["messages"]])
        return await fake_run(*args, **kwargs)

    monkeypatch.setattr(InferenceService, "run_inference", staticmethod(run_inference))
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Première").run()
    fake_inference.errors.clear()
    at.chat_input[0].set_value("Seconde").run()
    assert not at.exception, [e.value for e in at.exception]
    assert sent == [["Première"], ["Seconde"]]


def test_chat_generic_failure(fake_inference, run_page):
    """Échec non lié au délai : message « La génération a échoué », conseil Ollama."""
    fake_inference.errors.update(m["model"] for m in FAKE_LOCAL_MODELS)
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]
    (error,) = _errors(at)
    assert error.startswith("La génération a échoué.") and "Ollama" in error


def _reasoning_only(fake_inference):
    """Tout dans le raisonnement pour chaque modèle installé (story 18)."""
    for m in FAKE_LOCAL_MODELS:
        fake_inference.answers[m["model"]] = ""
        fake_inference.thoughts[m["model"]] = "Je réfléchis seulement."


def test_chat_empty_answer_shows_marker(fake_inference, run_page):
    """Chat libre, réponse vide : « Réponse vide » et raisonnement, aussi au rerun."""
    _reasoning_only(fake_inference)
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]
    assert EMPTY_ANSWER in [w.value for w in at.warning]
    assert REASONING_LABEL in [e.label for e in at.expander]

    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert EMPTY_ANSWER in [w.value for w in at.warning]
    assert REASONING_LABEL in [e.label for e in at.expander]


def test_lab_empty_answer_shows_marker(fake_inference, run_page):
    """Banc d'essai, réponse vide : « Réponse vide », raisonnement du modèle dépliable."""
    _reasoning_only(fake_inference)
    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert EMPTY_ANSWER in [w.value for w in at.warning]
    assert "Raisonnement du modèle" in [e.label for e in at.expander]


def test_lab_timeout_shows_error_and_survives_rerun(failing_inference, run_page):
    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(e.startswith(TIMEOUT_TEXT) for e in _errors(at))
    assert "Débit" not in [m.label for m in at.metric]

    # Rerun suivant : ni plantage ni métriques, l'erreur reste lisible.
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(e.startswith(TIMEOUT_TEXT) for e in _errors(at))


def test_lab_success_shows_metrics(fake_inference, run_page):
    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert not _errors(at)
    assert "Débit" in [m.label for m in at.metric]


# ---------------------------------------------------------------------------
# Arène : échec d'un modèle, de tous, du juge
# ---------------------------------------------------------------------------


def _run_arena(at, models):
    (multiselect,) = [m for m in at.multiselect if m.label == "Modèles à comparer"]
    multiselect.set_value([_label(m) for m in models]).run()
    _button(at, "Lancer la comparaison").click().run()
    assert not at.exception, [e.value for e in at.exception]


def _arena_status(at):
    (status,) = [s for s in at.status if s.label.startswith("Comparaison")]
    return status


def test_arena_one_model_times_out(three_models, fake_inference, run_page):
    """3 modèles, le 2ᵉ en délai dépassé : sa ligne le dit, les deux autres sont classés."""
    models = [*FAKE_LOCAL_MODELS, THIRD_LOCAL_MODEL]
    fake_inference.timeouts.add(models[1]["model"])
    at = run_page(ARENA_PAGE)
    _run_arena(at, models)

    assert _status_state(_arena_status(at)) == "complete"
    assert "Verdict" in [h.value for h in at.header]

    table = _results_table(at)
    rows = dict(zip(table["Modèle"], table["Statut"], strict=True))
    assert rows[_friendly(models[1])] == TIMEOUT_TEXT
    assert rows[_friendly(models[0])] == "Classé"
    assert rows[_friendly(models[2])] == "Classé"
    # Le modèle en échec est en dernière ligne, sans note.
    assert table["Modèle"].iloc[-1] == _friendly(models[1])
    assert table["Note"].iloc[-1] == "—"


def test_arena_all_models_fail(failing_inference, run_page):
    """Tous en échec : aucun podium, message d'erreur, statut `error`."""
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    assert _status_state(_arena_status(at)) == "error"
    assert "Verdict" not in [h.value for h in at.header]
    assert any(e.startswith("Aucun modèle n'a répondu") for e in _errors(at))


@pytest.mark.parametrize(
    "judge", [{"judge_reply": "Très bonne réponse, claire."}, {"judge_error": True}]
)
def test_arena_judge_failure_is_not_evaluated(fake_inference, run_page, judge):
    """Juge sans note lisible ou en échec : « non évalué », jamais 0/100, pas de vainqueur."""
    for key, value in judge.items():
        setattr(fake_inference, key, value)
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    texts = _all_texts(at)
    assert not any("0/100" in t for t in texts)
    table = _results_table(at)
    assert list(table["Note"]) == [NOT_EVALUATED, NOT_EVALUATED]
    assert all(s.startswith("Non évalué : ") for s in table["Statut"])
    assert "Vainqueur" not in texts


def test_arena_judge_score_ranks_models(fake_inference, run_page):
    fake_inference.judge_reply = "Note : 72/100"
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)
    table = _results_table(at)
    assert list(table["Note"]) == ["72/100", "72/100"]
    assert "Verdict" in [h.value for h in at.header]


# ---------------------------------------------------------------------------
# Arène : réponse vide, raisonnement, ex æquo (story 18)
# ---------------------------------------------------------------------------


def _response_headings(at) -> list[str]:
    """En-têtes de la section des réponses (2 modèles), dans l'ordre d'affichage."""
    return [m.value for m in at.markdown if "(note :" in m.value]


def _reasoning_expanders(at):
    return [e for e in at.expander if e.label == REASONING_LABEL]


def test_arena_empty_answer_is_not_judged(fake_inference, run_page):
    """Tout dans le raisonnement (Qwen 3.5 0.8B) : « réponse vide », raisonnement dépliable,
    « non évalué : réponse vide », et le juge ne reçoit que la réponse non vide."""
    empty, full = (m["model"] for m in FAKE_LOCAL_MODELS)
    fake_inference.answers[empty] = ""
    fake_inference.thoughts[empty] = "Je réfléchis longuement."
    fake_inference.judge_reply = "98"
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    # Le juge note la seule réponse non vide, juste après elle.
    assert [kind for kind, _ in fake_inference.calls] == ["model", "model", "judge"]
    assert ("model", full) in fake_inference.calls
    rows = dict(zip(*(_results_table(at)[k] for k in ("Modèle", "Statut")), strict=True))
    assert rows[_friendly(FAKE_LOCAL_MODELS[0])] == f"{NOT_EVALUATED.capitalize()} : réponse vide."
    assert rows[_friendly(FAKE_LOCAL_MODELS[1])] == "Classé"
    assert EMPTY_ANSWER in [w.value for w in at.warning]
    (reasoning,) = _reasoning_expanders(at)
    assert [m.value for m in reasoning.markdown] == ["Je réfléchis longuement."]


def test_arena_empty_answer_with_three_models(three_models, fake_inference, run_page):
    """Trois modèles (réponses repliées) : le raisonnement se déplie dans la réponse."""
    models = [*FAKE_LOCAL_MODELS, THIRD_LOCAL_MODEL]
    fake_inference.answers[models[2]["model"]] = ""
    fake_inference.thoughts[models[2]["model"]] = "Pensée seule."
    at = run_page(ARENA_PAGE)
    _run_arena(at, models)

    assert sum(1 for kind, _ in fake_inference.calls if kind == "judge") == 2
    assert EMPTY_ANSWER in [w.value for w in at.warning]
    (reasoning,) = _reasoning_expanders(at)
    assert [m.value for m in reasoning.markdown] == ["Pensée seule."]


def test_arena_answer_with_reasoning_is_judged(fake_inference, run_page):
    """Raisonnement et réponse : la réponse est notée, le raisonnement se déplie à part."""
    tag = FAKE_LOCAL_MODELS[0]["model"]
    fake_inference.thoughts[tag] = "Étapes du raisonnement."
    fake_inference.judge_reply = "80"
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    assert sum(1 for kind, _ in fake_inference.calls if kind == "judge") == 2
    assert list(_results_table(at)["Note"]) == ["80/100", "80/100"]
    assert EMPTY_ANSWER not in [w.value for w in at.warning]
    (reasoning,) = _reasoning_expanders(at)
    assert [m.value for m in reasoning.markdown] == ["Étapes du raisonnement."]


def test_arena_tie_same_order_everywhere(fake_inference, run_page):
    """Ex æquo à 72 : le plus rapide (90 tokens/s, 2ᵉ de la sélection) en tête de l'étoile,
    du vainqueur, du tableau et de la section des réponses ; « Pourquoi ? » le dit."""
    slow, fast = FAKE_LOCAL_MODELS
    fake_inference.throughput.update({slow["model"]: 60.0, fast["model"]: 90.0})
    fake_inference.judge_reply = "72"
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    assert list(_results_table(at)["Modèle"]) == [_friendly(fast), _friendly(slow)]
    assert at.subheader[0].value == _friendly(fast)
    headings = _response_headings(at)
    assert headings[0].startswith(f"**{_friendly(fast)}**")
    assert headings[1].startswith(f"**{_friendly(slow)}**")
    assert any(i.startswith("**Pourquoi ?** À note égale, le plus rapide") for i in _infos(at))


# ---------------------------------------------------------------------------
# Premier chargement
# ---------------------------------------------------------------------------


def test_loading_status_shown_before_generation(monkeypatch, fake_inference, run_page):
    """Modèle absent de `ollama ps` : « Chargement du modèle en mémoire… » avant la
    génération, puis `complete`."""
    from src.core.llm_provider import LLMProvider

    events = []
    real_status = streamlit.status

    def status(label, *args, **kwargs):
        events.append(("status", label))
        return real_status(label, *args, **kwargs)

    monkeypatch.setattr(streamlit, "status", status)
    monkeypatch.setattr(
        LLMProvider, "is_model_loaded", staticmethod(lambda model_name, timeout=2.0: False)
    )
    from src.core.inference_service import InferenceService

    real_run = InferenceService.run_inference

    async def run_inference(*args, **kwargs):
        events.append(("inference", kwargs.get("model_tag")))
        return await real_run(*args, **kwargs)

    monkeypatch.setattr(InferenceService, "run_inference", staticmethod(run_inference))

    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]

    assert ("status", LOADING_LABEL) in events
    first_inference = next(i for i, e in enumerate(events) if e[0] == "inference")
    assert events.index(("status", LOADING_LABEL)) < first_inference
    assert LOADED_LABEL in [s.label for s in at.status]


def test_no_loading_status_when_state_unknown(monkeypatch, fake_inference, run_page):
    """`ps()` en échec (état inconnu) : ni indicateur ni erreur."""
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(
        LLMProvider, "is_model_loaded", staticmethod(lambda model_name, timeout=2.0: None)
    )
    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [s.label for s in at.status]
    assert LOADING_LABEL not in labels and LOADED_LABEL not in labels
    assert not _errors(at)


# ---------------------------------------------------------------------------
# Garde-fou mémoire (Agent seul)
# ---------------------------------------------------------------------------


def test_memory_guard_keeps_question(monkeypatch, run_page):
    """Mémoire insuffisante : la question reste dans l'historique ; `alert-warning` avec la
    mémoire nécessaire, la mémoire libre et les deux issues."""
    from src.core.resource_manager import ResourceCheckResult, ResourceManager

    message = (
        "Mémoire vive insuffisante : environ 6,0 Go nécessaires, 2,0 Go libres dont "
        "1,0 Go réservé au système. Choisissez un modèle plus petit ou libérez la mémoire "
        "depuis la barre latérale."
    )
    monkeypatch.setattr(
        ResourceManager,
        "check_resources",
        classmethod(lambda cls, *a, **k: ResourceCheckResult(False, message, 6.0, 2.0)),
    )
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Résume l'état du système").run()
    assert not at.exception, [e.value for e in at.exception]

    assert message in [w.value for w in at.warning]
    assert at.session_state["agent_messages"] == [
        {"role": "user", "content": "Résume l'état du système", "blocked": True}
    ]
    # Au rerun suivant, la question est toujours affichée.
    at.run()
    assert "Résume l'état du système" in [m.value for m in at.markdown]


# ---------------------------------------------------------------------------
# Assistant documentaire : erreur du fournisseur, évaluation impossible
# ---------------------------------------------------------------------------


def test_documents_chat_provider_error(monkeypatch, indexed_base, run_page):
    """Erreur du fournisseur : `alert-error`, jamais affichée comme une réponse."""
    from src.core.llm_provider import LLMProvider

    async def failing_stream(*args, **kwargs):
        raise ConnectionError("Connection refused")
        yield  # pragma: no cover (générateur asynchrone)

    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(failing_stream))
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]

    assert any(e.startswith("La réponse n'a pas pu être générée") for e in _errors(at))
    assert [m["role"] for m in at.session_state["rag_messages"]] == ["user"]


def test_documents_evaluation_without_ragas(monkeypatch, indexed_base, run_page):
    """Ragas absent : « non évalué » avec la raison, ni 0/100 ni podium."""
    from src.core.llm_provider import LLMProvider
    from src.core.metrics import InferenceMetrics

    async def stream(model_name, messages, temperature=0.7, system_prompt=None):
        yield "Réponse simulée."
        yield InferenceMetrics(model_name, 10, 20, 1.0, 0.1, 20.0)

    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(stream))
    monkeypatch.setattr("src.core.eval_engine.RAGAS_AVAILABLE", False)

    at = run_page(RAG_PAGE)
    _button(at, "Lancer l'évaluation").click().run()
    assert not at.exception, [e.value for e in at.exception]

    texts = _all_texts(at)
    assert not any("0/100" in t for t in texts)
    assert "Note globale" not in [m.label for m in at.metric]
    table = _results_table(at)
    assert table["Note"].isna().all()
    assert all(s.startswith("Non évalué : Ragas") for s in table["Statut"])


def test_arena_generic_failure_label(fake_inference, run_page):
    """Échec non lié au délai : la ligne du modèle dit « Échec de la génération »."""
    fake_inference.errors.add(FAKE_LOCAL_MODELS[1]["model"])
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)
    table = _results_table(at)
    rows = dict(zip(table["Modèle"], table["Statut"], strict=True))
    assert rows[_friendly(FAKE_LOCAL_MODELS[1])] == "Échec de la génération"
    assert rows[_friendly(FAKE_LOCAL_MODELS[0])] == "Classé"


def test_arena_judge_error_details_folded(fake_inference, run_page):
    """Erreur du juge : raison courte dans le tableau, texte technique replié."""
    fake_inference.judge_error = True
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)
    assert "Détails techniques" in [e.label for e in at.expander]
    assert any("Juge (" in c.value and "Timeout" in c.value for c in at.code)
    assert not any("Timeout (" in s for s in _results_table(at)["Statut"])


# ---------------------------------------------------------------------------
# Indicateur de chargement : Chat libre, Agent seul, Discussion
# ---------------------------------------------------------------------------


@pytest.fixture
def status_spy(monkeypatch):
    """Enregistre chaque st.status créé (st.status ou placeholder.status) et chacune de ses
    mises à jour (label, état)."""
    from streamlit.elements.layouts import LayoutsMixin

    events = []
    real_status = LayoutsMixin.status

    def spied(dg, label, *args, **kwargs):
        events.append(("status", label, kwargs.get("state", "running")))
        box = real_status(dg, label, *args, **kwargs)
        real_update = box.update

        def update(*, label=None, expanded=None, state=None):
            events.append(("update", label, state))
            return real_update(label=label, expanded=expanded, state=state)

        box.update = update
        return box

    def status(label, *args, **kwargs):
        return spied(streamlit._main, label, *args, **kwargs)

    monkeypatch.setattr(LayoutsMixin, "status", spied)
    monkeypatch.setattr(streamlit, "status", status)
    return events


@pytest.fixture
def model_not_loaded(monkeypatch):
    """Modèle absent de `ollama ps` : le premier appel doit le charger."""
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(
        LLMProvider, "is_model_loaded", staticmethod(lambda model_name, timeout=2.0: False)
    )


def _loading_updates(events):
    """Mises à jour de l'indicateur de chargement, après sa création."""
    start = events.index(("status", LOADING_LABEL, "running"))
    return [e for e in events[start + 1 :] if e[0] == "update"]


def test_chat_loading_status_completes(model_not_loaded, fake_inference, status_spy, run_page):
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]
    assert ("update", LOADED_LABEL, "complete") in _loading_updates(status_spy)


def test_chat_loading_status_fails(model_not_loaded, failing_inference, run_page):
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]
    (status,) = [s for s in at.status if s.label == LOADING_FAILED_LABEL]
    assert _status_state(status) == "error"


def test_lab_loading_status_fails(model_not_loaded, failing_inference, run_page):
    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]
    (status,) = [s for s in at.status if s.label == LOADING_FAILED_LABEL]
    assert _status_state(status) == "error"


class FakeAgentEngine:
    """AgentEngine simulé : enregistre l'historique reçu, émet `events`."""

    events: list = []
    histories: list = []

    def __init__(self, model_tag, enabled_tools=None):
        self.model_tag = model_tag

    def run_stream(self, user_query, chat_history=None, system_prompt=None):
        FakeAgentEngine.histories.append([dict(m) for m in chat_history or []])
        yield from FakeAgentEngine.events


@pytest.fixture
def fake_agent(monkeypatch):
    from src.core.resource_manager import ResourceCheckResult, ResourceManager

    FakeAgentEngine.events = [{"type": "final_answer", "content": "Système en bon état."}]
    FakeAgentEngine.histories = []
    monkeypatch.setattr("src.app.tabs.agent.solo.AgentEngine", FakeAgentEngine)
    monkeypatch.setattr(
        ResourceManager,
        "check_resources",
        classmethod(lambda cls, *a, **k: ResourceCheckResult(True, "ok", 1.0, 8.0)),
    )
    return FakeAgentEngine


def test_agent_loading_status_completes(model_not_loaded, fake_agent, status_spy, run_page):
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    assert not at.exception, [e.value for e in at.exception]
    assert ("status", LOADING_LABEL, "running") in status_spy
    assert ("update", "L'agent réfléchit…", None) in _loading_updates(status_spy)
    (done,) = [s for s in at.status if s.label == "Terminé"]
    assert _status_state(done) == "complete"


def test_agent_stream_without_answer_closes_status(
    model_not_loaded, fake_agent, status_spy, run_page
):
    """Flux terminé sans réponse finale : l'indicateur ne reste pas « Chargement… »."""
    fake_agent.events = []
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    assert not at.exception, [e.value for e in at.exception]
    assert _loading_updates(status_spy)[-1][2] == "error"
    assert LOADING_LABEL not in [s.label for s in at.status]


def test_agent_exception_shows_details(fake_agent, run_page, monkeypatch):
    def boom(self, *args, **kwargs):
        raise RuntimeError("graphe cassé")

    monkeypatch.setattr(FakeAgentEngine, "run_stream", boom)
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    assert not at.exception, [e.value for e in at.exception]
    (error,) = _errors(at)
    assert error.startswith("L'agent s'est arrêté avant de répondre.")
    assert "graphe cassé" not in error
    assert any("graphe cassé" in c.value for c in at.code)


def test_blocked_question_not_sent_to_agent(monkeypatch, fake_agent, run_page):
    """Question bloquée : affichée, puis jamais transmise au moteur comme tour orphelin."""
    from src.core.resource_manager import ResourceCheckResult, ResourceManager

    verdicts = iter([False, True])
    monkeypatch.setattr(
        ResourceManager,
        "check_resources",
        classmethod(
            lambda cls, *a, **k: ResourceCheckResult(next(verdicts), "Mémoire vive insuffisante")
        ),
    )
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Question bloquée").run()
    at.chat_input[0].set_value("Question suivante").run()
    assert not at.exception, [e.value for e in at.exception]

    (history,) = fake_agent.histories
    assert "Question bloquée" not in [m["content"] for m in history]
    assert "Question bloquée" in [m.value for m in at.markdown]


def test_free_memory_keeps_blocked_question(monkeypatch, run_page):
    """« Libérer la mémoire » après un blocage : la question reste dans l'historique."""
    from src.core.resource_manager import ResourceCheckResult, ResourceManager

    monkeypatch.setattr(
        ResourceManager,
        "check_resources",
        classmethod(lambda cls, *a, **k: ResourceCheckResult(False, "Mémoire vive insuffisante")),
    )
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Question bloquée").run()
    (free,) = [b for b in at.sidebar.button if b.label == "Libérer la mémoire"]
    free.click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert [m["content"] for m in at.session_state["agent_messages"]] == ["Question bloquée"]
    assert "Question bloquée" in [m.value for m in at.markdown]


def _fake_stream(fail_tags=()):
    from src.core.metrics import InferenceMetrics

    async def stream(model_name, messages, temperature=0.7, system_prompt=None):
        if model_name in fail_tags:
            raise ConnectionError(f"refus pour {model_name}")
        yield "Réponse simulée."
        yield InferenceMetrics(model_name, 10, 20, 1.0, 0.1, 20.0)

    return stream


def test_documents_chat_loading_checked_before_search(
    monkeypatch, model_not_loaded, indexed_base, status_spy, run_page
):
    """Discussion : chargement annoncé une fois, avant la recherche ; statut final complete."""
    from src.core.llm_provider import LLMProvider
    from src.core.rag_engine import RAGEngine

    order = []
    monkeypatch.setattr(
        LLMProvider,
        "is_model_loaded",
        staticmethod(lambda model_name, timeout=2.0: order.append("ps") or False),
    )
    monkeypatch.setattr(
        RAGEngine, "search", lambda self, query, k=3, **kw: order.append("search") or []
    )
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_fake_stream()))
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]

    assert order == ["ps", "search"]
    assert [e for e in status_spy if e[1] == LOADING_LABEL] == [
        ("status", LOADING_LABEL, "running")
    ]
    assert _loading_updates(status_spy)[-1][2] == "complete"


def test_documents_chat_search_error(monkeypatch, indexed_base, run_page):
    """Échec de la recherche (base, embeddings) : message propre, pas un problème de modèle."""
    from src.core.rag_engine import RAGEngine

    def search(self, query, k=3, **kwargs):
        raise RuntimeError("collection Chroma illisible")

    monkeypatch.setattr(RAGEngine, "search", search)
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]
    (error,) = _errors(at)
    assert error.startswith("La recherche dans vos documents a échoué")
    assert "Ollama" not in error


def _run_evaluation(at, models):
    (multiselect,) = [m for m in at.multiselect if m.label == "Modèles évalués"]
    multiselect.set_value([_label(m) for m in models]).run()
    _button(at, "Lancer l'évaluation").click().run()
    assert not at.exception, [e.value for e in at.exception]


def test_documents_evaluation_mixed(monkeypatch, indexed_base, run_page):
    """Un modèle noté, un « non évalué » : podium du seul modèle noté, statut de chacun."""
    from src.core.eval_engine import EvalEngine, EvalResult
    from src.core.llm_provider import LLMProvider

    results = iter(
        [
            EvalResult(0.8, 0.9, 0.85),
            EvalResult.not_evaluated("l'évaluation par le juge a échoué.", "ValueError: nan"),
        ]
    )
    monkeypatch.setattr(EvalEngine, "evaluate_single_turn", lambda self, **kw: next(results))
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_fake_stream()))
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS)

    podium = [m for m in at.metric if m.label == "Note globale"]
    assert [m.value for m in podium] == ["85/100"]
    table = _results_table(at)
    assert list(table["Statut"]) == [
        "Évalué",
        "Non évalué : l'évaluation par le juge a échoué.",
    ]
    assert any("ValueError: nan" in c.value for c in at.code)


def test_documents_evaluation_generation_failures(monkeypatch, indexed_base, run_page):
    """Génération en échec : message qui nomme le modèle ; tous en échec : statut `error`,
    sans avertissement « Aucun résultat » en double."""
    from src.core.eval_engine import EvalEngine, EvalResult
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(
        EvalEngine, "evaluate_single_turn", lambda self, **kw: EvalResult(0.8, 0.9, 0.85)
    )
    failing = FAKE_LOCAL_MODELS[1]["model"]
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_fake_stream({failing})))
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS)
    (error,) = _errors(at)
    assert _friendly(FAKE_LOCAL_MODELS[1]) in error
    (status,) = [s for s in at.status if s.label.startswith("Évaluation")]
    assert _status_state(status) == "complete"

    all_tags = {m["model"] for m in FAKE_LOCAL_MODELS}
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_fake_stream(all_tags)))
    _button(at, "Lancer l'évaluation").click().run()
    assert not at.exception, [e.value for e in at.exception]
    (status,) = [s for s in at.status if s.label.startswith("Évaluation")]
    assert _status_state(status) == "error"
    assert len(_errors(at)) == 1
    assert not [w.value for w in at.warning if w.value.startswith("Aucun résultat")]


def test_documents_evaluation_empty_answer_not_judged(monkeypatch, indexed_base, run_page):
    """Candidat qui ne répond que par du raisonnement (Qwen 3.5 0.8B) : ni juge ni Ragas,
    « Non évalué : réponse vide. », « Réponse vide » affichée avec son raisonnement (story 20)."""
    from src.core.eval_engine import EvalEngine, EvalResult
    from src.core.llm_provider import LLMProvider
    from src.core.metrics import InferenceMetrics, ReasoningChunk

    thinker = FAKE_LOCAL_MODELS[0]["model"]

    async def stream(model_name, messages, temperature=0.7, system_prompt=None):
        if model_name == thinker:
            yield ReasoningChunk("Je réfléchis ")
            yield ReasoningChunk("seulement.")
        else:
            yield "Réponse simulée."
        yield InferenceMetrics(model_name, 10, 20, 1.0, 0.1, 20.0)

    judged = []
    monkeypatch.setattr(
        EvalEngine,
        "evaluate_single_turn",
        lambda self, **kw: judged.append(kw["response"]) or EvalResult(0.8, 0.9, 0.85),
    )
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(stream))
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS)

    assert judged == ["Réponse simulée."]
    table = _results_table(at)
    statuses = dict(zip(table["Modèle"], table["Statut"], strict=True))
    assert statuses[_friendly(FAKE_LOCAL_MODELS[0])] == (
        f"{NOT_EVALUATED.capitalize()} : {EMPTY_ANSWER_REASON}"
    )
    assert statuses[_friendly(FAKE_LOCAL_MODELS[1])] == "Évalué"
    # Génération mesurée même sans note : CO₂ et durée restent renseignés.
    (empty_row,) = table[table["Modèle"] == _friendly(FAKE_LOCAL_MODELS[0])].to_dict("records")
    assert empty_row["CO₂"] > 0 and empty_row["Durée"] >= 0, empty_row
    (response,) = [
        e for e in at.expander if e.label == f"Réponse de {_friendly(FAKE_LOCAL_MODELS[0])}"
    ]
    assert [w.value for w in response.warning] == [EMPTY_ANSWER]
    assert any("Je réfléchis seulement." in i.value for i in response.info)


# ---------------------------------------------------------------------------
# Discussion : réponse vide, raisonnement, ancien historique ; flux interrompu (story 19)
# ---------------------------------------------------------------------------


def _scripted_stream(*items, interrupt_judge_only=False):
    """`LLMProvider.chat_stream` simulé : produit `items` ; une exception y est levée. Avec
    `interrupt_judge_only`, seules les requêtes du juge de l'Arène sont interrompues."""
    from src.core.metrics import InferenceMetrics, InterruptedResponseError

    async def stream(model_name, messages, temperature=0.7, system_prompt=None):
        is_judge = "juge impartial" in (messages[-1].get("content") or "")
        if interrupt_judge_only and not is_judge:
            yield "Réponse complète."
            yield InferenceMetrics(model_name, 10, 20, 1.0, 0.1, 20.0)
            return
        for item in items:
            if isinstance(item, BaseException):
                raise item
            yield item
        if interrupt_judge_only:
            raise InterruptedResponseError()

    return stream


def _interrupted_stream():
    from src.core.metrics import InterruptedResponseError

    return _scripted_stream("Début de la répon", InterruptedResponseError())


def _download_buttons(at):
    return at.get("download_button")


def test_documents_chat_empty_answer_with_reasoning(monkeypatch, indexed_base, run_page):
    """Qwen 3.5 0.8B : raisonnement seul. « Réponse vide », raisonnement dépliable,
    historique en "" (jamais None), et la question suivante ne plante pas."""
    from src.core.llm_provider import LLMProvider
    from src.core.metrics import InferenceMetrics, ReasoningChunk

    monkeypatch.setattr(
        LLMProvider,
        "chat_stream",
        staticmethod(
            _scripted_stream(
                ReasoningChunk("Je réfléchis "),
                ReasoningChunk("seulement."),
                InferenceMetrics("m", 10, 20, 1.0, 0.1, 20.0),
            )
        ),
    )
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]

    first = at.session_state["rag_messages"][1]
    assert first["content"] == ""
    assert first["thought"] == "Je réfléchis seulement."
    assert EMPTY_ANSWER in [w.value for w in at.warning]
    (reasoning,) = [e for e in at.expander if e.label == REASONING_LABEL]
    assert [m.value for m in reasoning.markdown] == ["Je réfléchis seulement."]

    at.chat_input[0].set_value("Et les mesures ?").run()
    assert not at.exception, [e.value for e in at.exception]
    assert [m["role"] for m in at.session_state["rag_messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert EMPTY_ANSWER in [w.value for w in at.warning]
    assert at.chat_input, "le champ de question a disparu"


def test_documents_chat_think_tags_only(monkeypatch, indexed_base, run_page):
    """Balises `<think>` seules : même rendu, raisonnement « x »."""
    from src.core.llm_provider import LLMProvider
    from src.core.metrics import InferenceMetrics

    monkeypatch.setattr(
        LLMProvider,
        "chat_stream",
        staticmethod(
            _scripted_stream("<think>x</think>", InferenceMetrics("m", 10, 20, 1.0, 0.1, 20.0))
        ),
    )
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]

    answer = at.session_state["rag_messages"][1]
    assert answer["content"] == "" and answer["thought"] == "x"
    assert EMPTY_ANSWER in [w.value for w in at.warning]
    (reasoning,) = [e for e in at.expander if e.label == REASONING_LABEL]
    assert [m.value for m in reasoning.markdown] == ["x"]


def test_documents_chat_reasoning_and_think_tags(monkeypatch, indexed_base, run_page):
    """Raisonnement transmis à part puis balises `<think>` : les deux, dans cet ordre."""
    from src.core.llm_provider import LLMProvider
    from src.core.metrics import InferenceMetrics, ReasoningChunk

    monkeypatch.setattr(
        LLMProvider,
        "chat_stream",
        staticmethod(
            _scripted_stream(
                ReasoningChunk("A"),
                "<think>B</think>Réponse",
                InferenceMetrics("m", 10, 20, 1.0, 0.1, 20.0),
            )
        ),
    )
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]

    answer = at.session_state["rag_messages"][1]
    assert answer["thought"] == "A\n\nB"
    assert answer["content"] == "Réponse"


def test_documents_chat_old_history_with_none(indexed_base, run_page):
    """Ancien historique (`content: None`) : « Réponse vide », Télécharger inactif."""
    at = run_page(RAG_PAGE)
    at.session_state["rag_messages"] = [
        {"role": "user", "content": "Question"},
        {"role": "assistant", "content": None, "thought": None},
    ]
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert EMPTY_ANSWER in [w.value for w in at.warning]
    (download,) = _download_buttons(at)
    assert download.proto.disabled is True


def test_documents_chat_interrupted_stream(monkeypatch, indexed_base, run_page):
    """Flux tronqué : « Réponse interrompue… », question gardée, aucune réponse ajoutée."""
    from src.app.states import INTERRUPTED_MESSAGE
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_interrupted_stream()))
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]

    assert INTERRUPTED_MESSAGE in _errors(at)
    assert [m["role"] for m in at.session_state["rag_messages"]] == ["user"]
    assert not any("Début de la répon" in m.value for m in at.markdown)


def test_chat_interrupted_stream(monkeypatch, run_page):
    """Chat libre, flux tronqué : « Réponse interrompue… », jamais présenté comme réponse."""
    from src.app.states import INTERRUPTED_MESSAGE
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_interrupted_stream()))
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]

    assert INTERRUPTED_MESSAGE in _errors(at)
    messages = at.session_state["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["error"] is True and messages[1]["content"] == INTERRUPTED_MESSAGE
    assert not any("Début de la répon" in m.value for m in at.markdown)


def test_lab_interrupted_stream(monkeypatch, run_page):
    """Banc d'essai, flux tronqué : « Réponse interrompue… », ni réponse ni débit."""
    from src.app.states import INTERRUPTED_MESSAGE
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_interrupted_stream()))
    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]

    assert INTERRUPTED_MESSAGE in _errors(at)
    assert "Débit" not in [m.label for m in at.metric]


def test_arena_interrupted_stream(monkeypatch, run_page):
    """Arène, flux tronqué pour tous : lignes « Réponse interrompue », aucun vainqueur."""
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_interrupted_stream()))
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    assert "Verdict" not in [h.value for h in at.header]
    assert any("Réponse interrompue" in t for t in _all_texts(at))


def test_arena_interrupted_judge_is_not_evaluated(monkeypatch, run_page):
    """Juge tronqué : réponse « non évaluée », avec la raison."""
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(
        LLMProvider,
        "chat_stream",
        staticmethod(_scripted_stream("Note : 9", interrupt_judge_only=True)),
    )
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    table = _results_table(at)
    assert list(table["Note"]) == [NOT_EVALUATED, NOT_EVALUATED]
    assert all("réponse interrompue" in s for s in table["Statut"])
