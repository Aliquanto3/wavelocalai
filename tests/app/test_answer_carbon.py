"""
Une seule règle de CO₂ par réponse, selon l'origine réelle du modèle (story 23), avec
AppTest : un tag distant servi par Ollama (`glm-4.6:cloud`, hors catalogue), badge Cloud,
n'a plus de CO₂ local dans aucun onglet ; le Banc d'essai trouve la fiche par le tag ; le
badge mémoire de la Discussion documentaire vient de `ollama ps` (simulé), jamais « 0,0 Go ».

Aucun Ollama ni réseau : listes de modèles, inférence, `ps` et évaluation simulés.
Usage: python -m pytest tests/app/test_answer_carbon.py -v
"""

import math
from types import SimpleNamespace

import pytest
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df

from src.app.formatting import NBSP, format_co2
from src.core.green_monitor import CarbonCalculator
from src.core.llm_provider import LLMProvider
from src.core.providers.ollama_provider import OllamaProvider
from tests.app.conftest import FAKE_LOCAL_MODELS
from tests.app.test_sovereignty import (
    CLOUD_BADGE,
    LOCAL_BADGE,
    REMOTE_TAG,
    _captions,
    _label,
    _select,
)
from tests.app.test_states import (  # noqa: F401 (fixtures partagées)
    AGENTS_PAGE,
    ARENA_PAGE,
    RAG_PAGE,
    _app,
    _button,
    _friendly,
    _metric,
    _results_table,
    _stop_tracker,
    fake_agent,
    indexed_base,
)

LOCAL_MODEL = FAKE_LOCAL_MODELS[0]
GIB = 1024**3
LOCAL_7_6 = f"7,6{NBSP}mgCO₂"  # 40 tokens × 0,19 mg

# LLMProvider.loaded_model_size_gb réel, capturé avant la simulation de tests/app/conftest.py.
REAL_LOADED_MODEL_SIZE = LLMProvider.__dict__["loaded_model_size_gb"]


@pytest.fixture
def remote_page(monkeypatch):
    """Un modèle local et un tag distant d'Ollama, cloud autorisé ; page exécutée seule."""

    def list_models(cloud_enabled=False):
        return [dict(LOCAL_MODEL)] + ([dict(REMOTE_TAG)] if cloud_enabled else [])

    monkeypatch.setattr(LLMProvider, "list_models", staticmethod(list_models))
    started = []

    def _run(page: str):
        at = _app(page)
        started.append(at)
        at.session_state["cloud_enabled"] = True
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        return at

    yield _run
    for at in started:
        _stop_tracker(at)


@pytest.fixture
def ollama_ps(monkeypatch):
    """`ollama ps` simulé derrière le vrai LLMProvider.loaded_model_size_gb : `models` liste
    les modèles chargés, `error` fait échouer l'appel, `queried` garde les tags demandés."""
    state = SimpleNamespace(models=[], error=None, queried=[])

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def ps(self):
            if state.error:
                raise state.error
            return {"models": state.models}

    factory = SimpleNamespace(get_provider=lambda model_name: OllamaProvider())
    real = REAL_LOADED_MODEL_SIZE.__func__

    def loaded_model_size_gb(model_name, timeout=2.0):
        state.queried.append(model_name)
        return real(model_name, timeout=timeout)

    monkeypatch.setattr(LLMProvider, "loaded_model_size_gb", staticmethod(loaded_model_size_gb))
    monkeypatch.setattr("src.core.llm_provider.get_provider_factory", lambda: factory)
    monkeypatch.setattr("src.core.providers.ollama_provider.ollama.Client", FakeClient)
    return state


def _rag_stream(tokens=20):
    from src.core.metrics import InferenceMetrics

    async def stream(model_name, messages, temperature=0.7, system_prompt=None):
        yield "Réponse simulée."
        yield InferenceMetrics(model_name, 10, tokens, 1.0, 0.1, 20.0)

    return stream


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


# ---------------------------------------------------------------------------
# Tag distant d'Ollama, badge Cloud : jamais de CO₂ local
# ---------------------------------------------------------------------------


def test_chat_remote_tag_has_no_local_co2(remote_page, fake_inference):
    at = remote_page(ARENA_PAGE)
    _select(at, "Modèle actif", _label(REMOTE_TAG))
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]

    (footer,) = [c for c in _captions(at) if "Durée totale" in c]
    assert footer.startswith(f"{CLOUD_BADGE} · — · "), footer
    assert at.session_state["messages"][-1]["metrics_data"]["co2_mg"] is None
    # Session faite de seuls CO₂ inconnus : « — », jamais 0.
    assert "Session : **—**" in _captions(at)

    # Une réponse au CO₂ connu : le total la compte, l'inconnu est ignoré.
    _select(at, "Modèle actif", _label(LOCAL_MODEL))
    at.chat_input[0].set_value("Encore").run()
    assert not at.exception, [e.value for e in at.exception]
    assert f"Session : **{LOCAL_7_6}**" in _captions(at)


def test_agent_remote_tag_has_no_local_co2(remote_page, fake_agent):
    fake_agent.events = [{"type": "final_answer", "content": "Bon état.", "output_tokens": 40}]
    at = remote_page(AGENTS_PAGE)
    _select(at, "Modèle", _label(REMOTE_TAG))
    at.chat_input[0].set_value("Audit du système").run()
    assert not at.exception, [e.value for e in at.exception]

    answer = at.session_state["agent_messages"][-1]
    assert answer["is_cloud"] is True and answer["carbon_mg"] is None
    captions = [c for c in _captions(at) if c.startswith(CLOUD_BADGE)]
    assert captions and not any("CO₂" in c for c in captions)


def test_lab_remote_tag_has_no_local_co2(remote_page, fake_inference):
    at = remote_page(ARENA_PAGE)
    _select(at, "Modèle", _label(REMOTE_TAG), key="lab_model_select")
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert _metric(at, "CO₂") == "—"


def test_arena_remote_tag_has_no_local_co2(remote_page, fake_inference):
    at = remote_page(ARENA_PAGE)
    (multiselect,) = [m for m in at.multiselect if m.label == "Modèles à comparer"]
    multiselect.set_value([_label(LOCAL_MODEL), _label(REMOTE_TAG)]).run()
    _button(at, "Lancer la comparaison").click().run()
    assert not at.exception, [e.value for e in at.exception]

    table = _results_table(at)
    co2 = dict(zip(table["Modèle"], table["CO₂"], strict=True))
    assert co2[_friendly(LOCAL_MODEL)] == pytest.approx(7.6)
    assert _is_missing(co2[_friendly(REMOTE_TAG)])
    # Vainqueur, matrice et légende de taille : aucun échec, CO₂ inconnu en « — ».
    assert "Verdict" in [h.value for h in at.header]
    (legend,) = [c for c in _captions(at) if c.startswith("Taille du point : ")]
    # Taille minimale d'un CO₂ inconnu : nommée, jamais lue comme « le plus sobre ».
    assert f"CO₂ inconnu, taille minimale : {_friendly(REMOTE_TAG)}. " in legend


def test_documents_chat_remote_tag_has_no_local_co2(
    monkeypatch, remote_page, indexed_base, ollama_ps
):  # noqa: F811
    # `ps` liste le tag distant avec une taille : seul le garde de l'onglet (modèle cloud,
    # jamais interrogé) masque la mémoire.
    ollama_ps.models = [{"model": REMOTE_TAG["model"], "size": int(2.5 * GIB)}]
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_rag_stream()))
    at = remote_page(RAG_PAGE)
    _select(at, "Modèle actif", _label(REMOTE_TAG), key="rag_chat_select")
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]

    (meta,) = [c for c in _captions(at) if c.startswith(CLOUD_BADGE)]
    assert meta.endswith(" · —"), meta
    # Modèle cloud : pas de badge mémoire.
    assert "Go" not in meta
    assert at.session_state["rag_messages"][-1]["metrics"]["carbon_mg"] is None
    assert at.session_state["rag_messages"][-1]["metrics"]["ram_gb"] is None
    assert REMOTE_TAG["model"] not in ollama_ps.queried


def test_documents_evaluation_remote_tag(monkeypatch, remote_page, indexed_base, ollama_ps):
    """Tag distant : CO₂ « — », laissé hors de la matrice ; mémoire lue dans `ps` pour le
    modèle local, vide pour le modèle cloud."""
    from src.core.eval_engine import EvalEngine, EvalResult

    # `ps` liste le tag distant avec une taille : seul le garde de l'onglet (modèle cloud,
    # jamais interrogé) masque la mémoire.
    ollama_ps.models = [
        {"model": m["model"], "size": int(2.5 * GIB)} for m in (LOCAL_MODEL, REMOTE_TAG)
    ]
    scores = iter([EvalResult(0.9, 0.9, 0.9), EvalResult(0.8, 0.8, 0.8)])
    monkeypatch.setattr(EvalEngine, "evaluate_single_turn", lambda self, **kw: next(scores))
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_rag_stream()))
    at = remote_page(RAG_PAGE)
    (multiselect,) = [m for m in at.multiselect if m.label == "Modèles évalués"]
    multiselect.set_value([_label(LOCAL_MODEL), _label(REMOTE_TAG)]).run()
    _button(at, "Lancer l'évaluation").click().run()
    assert not at.exception, [e.value for e in at.exception]

    local, remote = _friendly(LOCAL_MODEL), _friendly(REMOTE_TAG)
    table = _results_table(at)
    co2 = dict(zip(table["Modèle"], table["CO₂"], strict=True))
    memory = dict(zip(table["Modèle"], table["Mémoire"], strict=True))
    assert co2[local] == pytest.approx(3.8) and _is_missing(co2[remote])
    assert memory[local] == pytest.approx(2.5) and _is_missing(memory[remote])
    assert REMOTE_TAG["model"] not in ollama_ps.queried

    assert f"CO₂ : {format_co2(None)}" in _captions(at)  # podium du tag distant
    assert f"CO₂ inconnu, absent de la matrice : {remote}." in _captions(at)
    # Points de la matrice : le seul modèle au CO₂ connu (le domaine de couleur, registre
    # stable des modèles évalués, garde le tag distant).
    (chart,) = at.get("vega_lite_chart")
    (dataset,) = chart.proto.datasets
    assert list(convert_arrow_bytes_to_pandas_df(dataset.data.data)["Modèle"]) == [local]


def test_documents_evaluation_only_unknown_co2_says_so(
    monkeypatch, remote_page, indexed_base, ollama_ps
):
    """Seul modèle noté au CO₂ inconnu : pas de matrice, mais le message le dit."""
    from src.core.eval_engine import EvalEngine, EvalResult

    monkeypatch.setattr(
        EvalEngine, "evaluate_single_turn", lambda self, **kw: EvalResult(0.9, 0.9, 0.9)
    )
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_rag_stream()))
    at = remote_page(RAG_PAGE)
    (multiselect,) = [m for m in at.multiselect if m.label == "Modèles évalués"]
    multiselect.set_value([_label(REMOTE_TAG)]).run()
    _button(at, "Lancer l'évaluation").click().run()
    assert not at.exception, [e.value for e in at.exception]

    assert f"CO₂ inconnu, absent de la matrice : {_friendly(REMOTE_TAG)}." in _captions(at)
    assert not at.get("vega_lite_chart")


# ---------------------------------------------------------------------------
# Banc d'essai : fiche trouvée par le tag, pas par le libellé « Nom (tag) »
# ---------------------------------------------------------------------------


def test_lab_finds_catalog_entry_by_tag(monkeypatch, fake_inference):
    """Deux modèles cloud au même nom (« Mistral Large ») : libellés « Nom (tag) ». La fiche
    du catalogue (123B, cloud) vient du tag : formule cloud, pas 7,6 mg locaux."""
    same_name = [
        {"model": tag, "size": 0, "type": "cloud", "provider": "mistral"}
        for tag in ("mistral-large-2512", "mistral-large-2512:latest")
    ]

    def list_models(cloud_enabled=False):
        return [dict(LOCAL_MODEL)] + ([dict(m) for m in same_name] if cloud_enabled else [])

    monkeypatch.setattr(LLMProvider, "list_models", staticmethod(list_models))
    at = _app(ARENA_PAGE)
    at.session_state["cloud_enabled"] = True
    at.run()
    try:
        (box,) = [s for s in at.selectbox if s.key == "lab_model_select"]
        (option,) = [o for o in box.options if "(mistral-large-2512)" in o]
        box.set_value(option).run()
        _button(at, "Lancer le test").click().run()
        assert not at.exception, [e.value for e in at.exception]
        expected = format_co2(CarbonCalculator.compute_mistral_impact_g(123.0, 40))
        assert _metric(at, "CO₂") == expected != LOCAL_7_6
    finally:
        _stop_tracker(at)


# ---------------------------------------------------------------------------
# Discussion documentaire : mémoire réelle (`ollama ps`), jamais « 0,0 Go »
# ---------------------------------------------------------------------------


def _documents_answer(monkeypatch, run_page):
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_rag_stream()))
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]
    (meta,) = [c for c in _captions(at) if c.startswith(LOCAL_BADGE)]
    return at, meta


@pytest.fixture
def run_page():
    started = []

    def _run(page: str):
        at = _app(page)
        started.append(at)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        return at

    yield _run
    for at in started:
        _stop_tracker(at)


def test_documents_chat_memory_from_ps(monkeypatch, indexed_base, ollama_ps, run_page):
    ollama_ps.models = [
        {"model": m["model"], "name": m["model"], "size": int(2.5 * GIB)} for m in FAKE_LOCAL_MODELS
    ]
    at, meta = _documents_answer(monkeypatch, run_page)
    assert f" · 2,5{NBSP}Go · " in meta, meta
    assert meta.endswith(f" · 3,8{NBSP}mgCO₂")
    assert at.session_state["rag_messages"][-1]["metrics"]["ram_gb"] == pytest.approx(2.5)


@pytest.mark.parametrize(
    "setup",
    [
        pytest.param(lambda s: setattr(s, "error", ConnectionError("refused")), id="ps-echec"),
        pytest.param(lambda s: setattr(s, "models", []), id="tag-absent"),
        pytest.param(
            lambda s: setattr(
                s, "models", [{"model": m["model"], "size": 0} for m in FAKE_LOCAL_MODELS]
            ),
            id="taille-nulle",
        ),
    ],
)
def test_documents_chat_memory_unknown_hides_badge(
    monkeypatch, indexed_base, ollama_ps, run_page, setup
):
    setup(ollama_ps)
    at, meta = _documents_answer(monkeypatch, run_page)
    assert "Go" not in meta, meta
    assert meta.endswith(f" · 3,8{NBSP}mgCO₂")
    assert at.session_state["rag_messages"][-1]["metrics"]["ram_gb"] is None


def test_documents_chat_old_history_at_zero_hides_badge(indexed_base):  # noqa: F811
    """Ancien historique, mémoire enregistrée à 0,0 : pas de badge « 0,0 Go »."""
    at = _app(RAG_PAGE)
    at.session_state["rag_messages"] = [
        {"role": "user", "content": "Question ?"},
        {
            "role": "assistant",
            "content": "Réponse.",
            "is_cloud": False,
            "model_name": "Qwen 2.5 1.5B",
            "metrics": {"total_time": 1.0, "ram_gb": 0.0, "carbon_mg": 3.8},
        },
    ]
    at.run()
    try:
        assert not at.exception, [e.value for e in at.exception]
        (meta,) = [c for c in _captions(at) if c.startswith(LOCAL_BADGE)]
        assert "Go" not in meta and meta.endswith(f" · 3,8{NBSP}mgCO₂")
    finally:
        _stop_tracker(at)
