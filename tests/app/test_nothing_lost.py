"""
Rien ne se perd (story 9), avec AppTest : réponse de l'agent seul conservée avec son CO₂, son
modèle et son badge ; erreur conservée comme erreur ; historique envoyé au moteur ; modèle de
l'agent gardé après un passage en équipe ; reranker de l'Assistant documentaire réellement
appliqué, gardé au changement d'embedding, et score de reclassement réel des sources.

Moteur d'agent, reranker, embeddings et modèles simulés : ni Ollama, ni téléchargement.
Référence : _bmad-output/specs/spec-fiabilisation-frontend/stories/9-rien-ne-se-perd-agent-reglages-rag.md
Usage: python -m pytest tests/app/test_nothing_lost.py -v
"""

import pytest
from langchain_core.documents import Document

from src.app.formatting import NBSP, format_co2
from src.app.tabs.agent.solo import AGENT_MODEL_KEY, answer_carbon_mg
from src.core.agent_engine import history_to_messages
from src.core.green_monitor import CarbonCalculator
from src.core.llm_provider import LLMProvider
from tests.app.test_states import (  # noqa: F401 (fixtures partagées)
    AGENTS_PAGE,
    RAG_PAGE,
    _errors,
    run_page,
)

LOCAL_BADGE = ":green-badge[:material/computer: Local]"
QWEN_LABEL = "Qwen 2.5 1.5B · Local · outils vérifiés"
GEMMA_LABEL = "Gemma 3 1B · Local"
ANSWER = "Système en bon état."


class RecordingAgent:
    """AgentEngine simulé : enregistre la question et l'historique reçus, émet `events`."""

    events: list = []
    calls: list = []

    def __init__(self, model_tag, enabled_tools=None):
        self.model_tag = model_tag

    def run_stream(self, user_query, chat_history=None, system_prompt=None):
        RecordingAgent.calls.append(
            (self.model_tag, user_query, [dict(m) for m in chat_history or []])
        )
        yield from RecordingAgent.events


@pytest.fixture
def agent(monkeypatch):
    from src.core.resource_manager import ResourceCheckResult, ResourceManager

    RecordingAgent.events = [
        {"type": "tool_call", "tool": "system_monitor", "args": {}},
        {"type": "tool_result", "content": "CPU 12 %"},
        {
            "type": "final_answer",
            "content": f"<think>Je lis l'état.</think>{ANSWER}",
            "output_tokens": 40,
        },
    ]
    RecordingAgent.calls = []
    monkeypatch.setattr("src.app.tabs.agent.solo.AgentEngine", RecordingAgent)
    monkeypatch.setattr(
        ResourceManager,
        "check_resources",
        classmethod(lambda cls, *a, **k: ResourceCheckResult(True, "ok", 1.0, 8.0)),
    )
    return RecordingAgent


def _captions(at) -> list[str]:
    return [c.value for c in at.caption]


def _markdowns(at) -> list[str]:
    return [m.value for m in at.markdown]


def _agent_select(at):
    (select,) = [s for s in at.main.selectbox if s.label == "Modèle"]
    return select


def _set_mode(at, mode: str):
    (radio,) = [r for r in at.sidebar.radio if r.label == "Mode"]
    radio.set_value(mode).run()
    assert not at.exception, [e.value for e in at.exception]


# ---------------------------------------------------------------------------
# Agent seul : réponse, erreur, historique
# ---------------------------------------------------------------------------


def test_agent_answer_kept_after_rerun_with_co2_model_and_badge(agent, run_page):
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    assert not at.exception, [e.value for e in at.exception]

    # Rerun (autre interaction) : la réponse reste, avec ses métadonnées.
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert ANSWER in _markdowns(at)
    assert "Je lis l'état." in _markdowns(at)  # raisonnement replié
    expected_co2 = format_co2(CarbonCalculator.compute_local_theoretical_g(40))
    assert f"{LOCAL_BADGE} · Qwen 2.5 1.5B · {expected_co2}" in _captions(at)
    assert expected_co2.endswith(f"{NBSP}mgCO₂")

    answer = at.session_state["agent_messages"][-1]
    assert answer["content"] == ANSWER and answer["thought"] == "Je lis l'état."
    assert answer["model_tag"] == "qwen2.5:1.5b" and answer["is_cloud"] is False
    expected_mg = CarbonCalculator.compute_local_theoretical_g(40) * 1000
    assert answer["carbon_mg"] == pytest.approx(expected_mg)


def test_agent_answer_kept_after_mode_switch(agent, run_page):
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    _set_mode(at, "Équipe d'agents")
    _set_mode(at, "Agent seul")
    assert ANSWER in _markdowns(at)
    assert any(c.startswith(LOCAL_BADGE) and "CO₂" in c for c in _captions(at))


def test_agent_carbon_cloud_and_local():
    """CO₂ comme les autres onglets : formule cloud (paramètres actifs) ou locale."""
    local = answer_carbon_mg("qwen2.5:1.5b", 100)
    assert local == pytest.approx(CarbonCalculator.compute_local_theoretical_g(100) * 1000)
    cloud = answer_carbon_mg("mistral-large-2512", 100)
    assert cloud == pytest.approx(CarbonCalculator.compute_mistral_impact_g(123.0, 100) * 1000)
    assert answer_carbon_mg("qwen2.5:1.5b", None) is None


def test_chat_carbon_uses_catalog_entry_not_selector_label():
    """Discussion : la fiche du modèle est trouvée par son tag (nom du catalogue), pas par le
    libellé « Nom · Cloud » du sélecteur ; la formule suit l'origine réelle du modèle."""
    from types import SimpleNamespace

    from src.app.tabs.inference.chat import _calculate_metrics

    metrics = SimpleNamespace(
        output_tokens=100,
        tokens_per_second=10.0,
        throughput_estimated=False,
        total_duration_s=1.0,
        load_duration_s=None,
        load_measured=False,
    )
    cloud_mg = CarbonCalculator.compute_mistral_impact_g(123.0, 100) * 1000
    local_mg = CarbonCalculator.compute_local_theoretical_g(100) * 1000
    assert _calculate_metrics(metrics, "mistral-large-2512", True)["co2_mg"] == pytest.approx(
        cloud_mg
    )
    # Origine inconnue : le type du catalogue décide.
    assert _calculate_metrics(metrics, "mistral-large-2512")["co2_mg"] == pytest.approx(cloud_mg)
    assert _calculate_metrics(metrics, "qwen2.5:1.5b", False)["co2_mg"] == pytest.approx(local_mg)
    # Cloud hors catalogue (tag distant) : CO₂ inconnu, jamais 0.
    assert _calculate_metrics(metrics, "modele-inconnu:cloud", True)["co2_mg"] is None


def test_chat_passes_tag_and_origin_to_carbon():
    """Le défaut du 27/09 était à l'appel : le libellé du sélecteur au lieu du tag."""
    import ast
    import inspect

    from src.app.tabs.inference import chat

    calls = [
        node
        for node in ast.walk(ast.parse(inspect.getsource(chat)))
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_calculate_metrics"
    ]
    assert calls
    for call in calls:
        assert [getattr(a, "id", None) for a in call.args[1:]] == ["active_tag", "active_is_cloud"]


def test_agent_carbon_follows_real_origin_and_rejects_bad_input():
    """Formule choisie par l'origine réelle (celle du badge), pas le seul catalogue ; modèle
    absent, tokens NaN ou infinis : CO₂ inconnu, jamais d'exception."""
    as_cloud = answer_carbon_mg("mistral-large-2512", 100, is_cloud=True)
    assert as_cloud == pytest.approx(CarbonCalculator.compute_mistral_impact_g(123.0, 100) * 1000)
    as_local = answer_carbon_mg("mistral-large-2512", 100, is_cloud=False)
    assert as_local == pytest.approx(CarbonCalculator.compute_local_theoretical_g(100) * 1000)
    # Cloud de taille inconnue : pas de CO₂ inventé.
    assert answer_carbon_mg("modele-inconnu:cloud", 100, is_cloud=True) is None
    assert answer_carbon_mg(None, 100) is None
    assert answer_carbon_mg("qwen2.5:1.5b", float("nan")) is None
    assert answer_carbon_mg("qwen2.5:1.5b", float("inf")) is None


def test_agent_carbon_failure_keeps_answer(agent, run_page, monkeypatch):
    def broken(*args, **kwargs):
        raise ValueError("catalogue illisible")

    monkeypatch.setattr("src.app.tabs.agent.solo.get_model_info", broken)
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert ANSWER in _markdowns(at)
    answer = at.session_state["agent_messages"][-1]
    assert answer["content"] == ANSWER and answer["carbon_mg"] is None
    assert f"{LOCAL_BADGE} · Qwen 2.5 1.5B" in _captions(at)


def test_agent_empty_answer_keeps_caption(agent, run_page):
    """Réponse réduite à son raisonnement : badge, modèle et CO₂ restent affichés."""
    agent.events = [{"type": "final_answer", "content": "<think>Rien.</think>", "output_tokens": 3}]
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(
        c.startswith(f"{LOCAL_BADGE} · Qwen 2.5 1.5B · ") and "CO₂" in c for c in _captions(at)
    )


def _failure_message() -> str:
    from src.app.states import generation_failure_advice
    from src.app.tabs.agent.solo import AGENT_FAILED_MESSAGE

    return AGENT_FAILED_MESSAGE + generation_failure_advice("qwen2.5:1.5b")


def test_agent_error_kept_as_error_and_not_sent_as_answer(agent, run_page):
    agent.events = [{"type": "error", "content": "Erreur critique de l'agent : graphe cassé"}]
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Question en échec").run()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    # Même message que les autres échecs, conseil compris ; l'exception en détail.
    assert _errors(at) == [_failure_message()]
    assert any("graphe cassé" in c.value for c in at.code)
    # Modèle et badge sous l'erreur.
    assert f"{LOCAL_BADGE} · Qwen 2.5 1.5B" in _captions(at)

    agent.events = [{"type": "final_answer", "content": ANSWER, "output_tokens": 5}]
    at.chat_input[0].set_value("Question suivante").run()
    assert not at.exception, [e.value for e in at.exception]
    # Toujours visible comme une erreur, jamais transmise au moteur comme une réponse.
    assert _errors(at) == [_failure_message()]
    _, query, history = agent.calls[-1]
    assert query == "Question suivante"
    assert history_to_messages(history) == []


def test_agent_exception_kept_as_error(agent, run_page, monkeypatch):
    def boom(self, *args, **kwargs):
        raise RuntimeError("graphe cassé")

    monkeypatch.setattr(RecordingAgent, "run_stream", boom)
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    (error,) = _errors(at)
    assert error.startswith("L'agent s'est arrêté avant de répondre.")
    assert any("graphe cassé" in c.value for c in at.code)


def test_agent_stream_without_answer_kept_as_error(agent, run_page):
    """Flux terminé sans réponse ni erreur : un tour d'erreur reste, avec son modèle."""
    from src.app.tabs.agent.solo import AGENT_NO_ANSWER_MESSAGE

    agent.events = []
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert _errors(at) == [AGENT_NO_ANSWER_MESSAGE]
    last = at.session_state["agent_messages"][-1]
    assert last["error"] is True and last["model_tag"] == "qwen2.5:1.5b"
    assert f"{LOCAL_BADGE} · Qwen 2.5 1.5B" in _captions(at)


def test_agent_construction_failure_shown_as_error(agent, run_page, monkeypatch):
    """AgentEngine qui échoue à sa construction (clé d'API manquante) : erreur conservée,
    conseil et détail, statut clos, aucune trace brute."""

    def broken_init(self, model_tag, enabled_tools=None):
        raise ValueError("MISTRAL_API_KEY manquante")

    monkeypatch.setattr(RecordingAgent, "__init__", broken_init)
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    assert not at.exception, [e.value for e in at.exception]
    assert _errors(at) == [_failure_message()]
    assert any("MISTRAL_API_KEY manquante" in c.value for c in at.code)
    assert all(s.state != "running" for s in at.status)
    at.run()
    assert _errors(at) == [_failure_message()]


def test_agent_tool_logs_closed_after_failure(agent, run_page):
    """Échec pendant un appel d'outil : le journal passe « interrompu », jamais « running »."""
    from src.app.tabs.agent.solo import TOOL_INTERRUPTED_NOTE

    agent.events = [
        {"type": "tool_call", "tool": "system_monitor", "args": {}},
        {"type": "error", "content": "Erreur critique de l'agent : outil bloqué"},
    ]
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Audit du système").run()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    (log,) = [m for m in at.session_state["agent_messages"] if m.get("type") == "tool_log"]
    assert log["done"] is True and log["interrupted"] is True
    assert TOOL_INTERRUPTED_NOTE in log["content"]
    assert all(s.state != "running" for s in at.status)


def test_agent_history_sent_once_without_tool_logs(agent, run_page):
    """2ᵉ question après une réponse avec outils : Q1, R1 puis Q2 une seule fois."""
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Q1").run()
    at.chat_input[0].set_value("Q2").run()
    assert not at.exception, [e.value for e in at.exception]

    first, second = agent.calls
    assert first[1] == "Q1" and first[2] == []
    _, query, history = second
    assert query == "Q2"
    assert "Q2" not in [m["content"] for m in history]
    sent = [(type(m).__name__, m.content) for m in history_to_messages(history)]
    assert sent == [("HumanMessage", "Q1"), ("AIMessage", ANSWER)]


# ---------------------------------------------------------------------------
# Agent seul : modèle choisi conservé
# ---------------------------------------------------------------------------


def test_agent_first_display_uses_default_rule(run_page):
    at = run_page(AGENTS_PAGE)
    assert _agent_select(at).value == QWEN_LABEL


def test_agent_model_kept_after_crew_mode(agent, run_page):
    at = run_page(AGENTS_PAGE)
    _agent_select(at).set_value(GEMMA_LABEL).run()
    assert at.session_state[AGENT_MODEL_KEY] == "gemma3:1b"

    _set_mode(at, "Équipe d'agents")
    _set_mode(at, "Agent seul")
    assert _agent_select(at).value == GEMMA_LABEL

    # Et c'est bien lui qui répond.
    at.chat_input[0].set_value("Audit du système").run()
    assert agent.calls[-1][0] == "gemma3:1b"


def test_agent_missing_model_falls_back_to_first(run_page):
    from tests.app.test_states import _app

    at = _app(AGENTS_PAGE)
    at.session_state[AGENT_MODEL_KEY] = "modele-disparu:7b"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert _agent_select(at).value == QWEN_LABEL
    # Le choix enregistré n'est pas écrasé par le repli : seul l'utilisateur le change.
    assert at.session_state[AGENT_MODEL_KEY] == "modele-disparu:7b"


def test_agent_model_restored_when_back_in_list(agent, run_page, monkeypatch):
    """Modèle choisi absent un instant (liste incomplète) : premier de la liste, puis le
    choix revient dès que le modèle est de nouveau proposé."""
    from tests.app.conftest import FAKE_LOCAL_MODELS

    at = run_page(AGENTS_PAGE)
    _agent_select(at).set_value(GEMMA_LABEL).run()

    only_qwen = [dict(FAKE_LOCAL_MODELS[0])]
    monkeypatch.setattr(
        LLMProvider, "list_models", staticmethod(lambda cloud_enabled=True: list(only_qwen))
    )
    at.run()
    assert _agent_select(at).value == QWEN_LABEL
    assert at.session_state[AGENT_MODEL_KEY] == "gemma3:1b"

    monkeypatch.setattr(
        LLMProvider,
        "list_models",
        staticmethod(lambda cloud_enabled=True: [dict(m) for m in FAKE_LOCAL_MODELS]),
    )
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert _agent_select(at).value == GEMMA_LABEL


# ---------------------------------------------------------------------------
# Assistant documentaire : reranker appliqué, score de reclassement réel
# ---------------------------------------------------------------------------


class FakeReranker:
    """CrossEncoder simulé : score lu d'après le texte de l'extrait."""

    SCORES = {"extrait faible": 0.12, "extrait fort": 0.87, "extrait moyen": 0.45}

    def __init__(self, name):
        self.name = name

    def predict(self, pairs):
        return [self.SCORES.get(text, 0.0) for _query, text in pairs]


@pytest.fixture
def rag_models(tmp_path, monkeypatch):
    """data/models simulé : deux embeddings, un reranker qui se charge, un qui échoue."""
    from src.core.rag.models_factory import RAGModelsFactory

    data_dir = tmp_path / "data"
    for sub in ("embeddings/e1", "embeddings/e2", "rerankers/a-reranker", "rerankers/z-casse"):
        (data_dir / "models" / sub).mkdir(parents=True)
    monkeypatch.setattr("src.core.config.DATA_DIR", data_dir)

    def get_reranker_model(model_name, device="cpu"):
        if not model_name or model_name == "z-casse":
            return None
        return FakeReranker(model_name)

    monkeypatch.setattr(RAGModelsFactory, "get_reranker_model", staticmethod(get_reranker_model))
    return data_dir


def _rerank_select(at):
    (select,) = [s for s in at.sidebar.selectbox if s.label == "Modèle de reclassement"]
    return select


def _embedding_select(at):
    (select,) = [s for s in at.sidebar.selectbox if s.label == "Modèle"]
    return select


def test_reranker_default_and_choice_applied(rag_models, run_page):
    at = run_page(RAG_PAGE)
    engine = at.session_state["rag_engine"]
    assert _rerank_select(at).options == ["Aucun", "a-reranker", "z-casse"]
    assert _rerank_select(at).value == "a-reranker"
    assert engine.reranker_model.name == "a-reranker"

    # « Aucun » : aucun reranker appliqué.
    _rerank_select(at).set_value("Aucun").run()
    assert not at.exception, [e.value for e in at.exception]
    engine = at.session_state["rag_engine"]
    assert engine.current_reranker_name is None and engine.reranker_model is None
    assert _rerank_select(at).value == "Aucun"

    # Retour sur « a-reranker » : appliqué de nouveau.
    _rerank_select(at).set_value("a-reranker").run()
    engine = at.session_state["rag_engine"]
    assert engine.reranker_model.name == "a-reranker"


def test_embedding_change_keeps_reranker(rag_models, run_page):
    at = run_page(RAG_PAGE)
    _embedding_select(at).set_value("e2").run()
    assert not at.exception, [e.value for e in at.exception]
    engine = at.session_state["rag_engine"]
    assert engine.current_embedding_name == "e2"
    assert engine.reranker_model.name == "a-reranker"
    assert _rerank_select(at).value == "a-reranker"


def test_reranker_load_failure_shows_error_and_none(rag_models, run_page):
    at = run_page(RAG_PAGE)
    _rerank_select(at).set_value("z-casse").run()
    assert not at.exception, [e.value for e in at.exception]
    (error,) = _errors(at)
    assert "« z-casse » n'a pas pu être chargé" in error
    engine = at.session_state["rag_engine"]
    assert engine.current_reranker_name is None and engine.reranker_model is None
    assert _rerank_select(at).value == "Aucun"

    # Affichée une fois, sans nouvelle tentative de chargement.
    at.run()
    assert not _errors(at)
    assert _rerank_select(at).value == "Aucun"


def test_default_reranker_failing_at_startup(rag_models, monkeypatch, run_page):
    """Reranker par défaut (premier dossier) qui ne se charge pas au démarrage : erreur au
    premier affichage, sélecteur sur « Aucun », erreur absente au rerun suivant."""
    from src.core.rag.models_factory import RAGModelsFactory

    monkeypatch.setattr(
        RAGModelsFactory, "get_reranker_model", staticmethod(lambda name, device="cpu": None)
    )
    at = run_page(RAG_PAGE)
    (error,) = _errors(at)
    assert "« a-reranker » n'a pas pu être chargé" in error
    assert _rerank_select(at).value == "Aucun"
    assert at.session_state["rag_engine"].reranker_model is None

    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert not _errors(at)
    assert _rerank_select(at).value == "Aucun"


def test_rerankers_sorted_whatever_disk_order(rag_models, monkeypatch, run_page):
    """Path.iterdir en ordre inverse : options triées, défaut = premier alphabétique."""
    from pathlib import Path

    real_iterdir = Path.iterdir
    monkeypatch.setattr(
        Path, "iterdir", lambda self: iter(sorted(real_iterdir(self), reverse=True))
    )
    at = run_page(RAG_PAGE)
    assert _rerank_select(at).options == ["Aucun", "a-reranker", "z-casse"]
    assert _rerank_select(at).value == "a-reranker"
    assert at.session_state["rag_engine"].reranker_model.name == "a-reranker"
    # Embeddings : ordre du disque conservé (leur défaut fixe la collection Chroma).
    assert _embedding_select(at).options == ["e2", "e1"]


def test_active_reranker_kept_when_folder_removed(rag_models, run_page):
    """Dossier du reranker actif supprimé : il reste proposé et actif, pas « Aucun »."""
    import shutil

    at = run_page(RAG_PAGE)
    shutil.rmtree(rag_models / "models" / "rerankers" / "a-reranker")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert "a-reranker" in _rerank_select(at).options
    assert _rerank_select(at).value == "a-reranker"
    assert at.session_state["rag_engine"].reranker_model.name == "a-reranker"


def test_embedding_load_failure_shows_error(rag_models, monkeypatch, run_page):
    from src.core.rag.models_factory import RAGModelsFactory

    at = run_page(RAG_PAGE)
    before = at.session_state["rag_engine"].current_embedding_name
    other = "e2" if before == "e1" else "e1"

    def broken(model_name, device="cpu"):
        raise OSError(f"dossier illisible : {model_name}")

    monkeypatch.setattr(RAGModelsFactory, "get_embedding_model", staticmethod(broken))
    _embedding_select(at).set_value(other).run()
    assert not at.exception, [e.value for e in at.exception]
    (error,) = _errors(at)
    assert f"« {other} » n'a pas pu être chargé" in error
    assert any("dossier illisible" in c.value for c in at.code)
    engine = at.session_state["rag_engine"]
    assert engine.current_embedding_name == before
    assert engine.reranker_model.name == "a-reranker"
    assert _embedding_select(at).value == before

    at.run()
    assert not _errors(at)


def test_no_reranker_installed_only_none(tmp_path, monkeypatch, run_page):
    monkeypatch.setattr("src.core.config.DATA_DIR", tmp_path / "vide")
    at = run_page(RAG_PAGE)
    assert _rerank_select(at).options == ["Aucun"]
    assert _rerank_select(at).value == "Aucun"
    assert at.session_state["rag_engine"].reranker_model is None


@pytest.fixture
def base_with_documents(monkeypatch):
    """Base non vide : trois extraits renvoyés par la recherche vectorielle simulée."""
    from src.core.rag.vector_store import VectorStoreManager
    from src.core.rag_engine import RAGEngine

    class Store:
        def similarity_search(self, query, k=4):
            docs = [
                Document(page_content="extrait faible", metadata={"source": "faible.md"}),
                Document(page_content="extrait fort", metadata={"source": "fort.md"}),
                Document(page_content="extrait moyen", metadata={"source": "moyen.md"}),
            ]
            return docs[:k]

    monkeypatch.setattr(
        RAGEngine,
        "get_stats",
        lambda self: {"count": 3, "sources": ["faible.md", "fort.md", "moyen.md"]},
    )
    monkeypatch.setattr(VectorStoreManager, "get_store", lambda self: Store())

    async def stream(model_name, messages, temperature=0.7, system_prompt=None):
        from src.core.metrics import InferenceMetrics

        yield "Réponse simulée."
        yield InferenceMetrics(model_name, 10, 20, 1.0, 0.1, 20.0)

    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(stream))


def _source_captions(at) -> list[str]:
    return [c for c in _captions(at) if c.startswith("**Source ")]


def test_sources_follow_reranker_scores(rag_models, base_with_documents, run_page):
    at = run_page(RAG_PAGE)
    (slider,) = [s for s in at.sidebar.slider if s.label == "Nombre d'extraits"]
    slider.set_value(2).run()
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]
    assert _source_captions(at) == [
        "**Source 1** : fort.md (score de reclassement : 0,87)",
        "**Source 2** : moyen.md (score de reclassement : 0,45)",
    ]


def test_relevance_without_reranker_is_missing(rag_models, base_with_documents, run_page):
    at = run_page(RAG_PAGE)
    _rerank_select(at).set_value("Aucun").run()
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]
    captions = _source_captions(at)
    assert captions[0] == "**Source 1** : faible.md (score de reclassement : —)"
    assert not any("0,00" in c for c in captions)
