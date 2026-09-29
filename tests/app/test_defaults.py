"""
Choix par défaut adaptés à la machine (story 7), avec AppTest : présélection de l'Arène, juge
par défaut et son avertissement, lancement désactivé sous 2 modèles, modèle proposé dans le
Chat libre, la Discussion et les Agents autonomes.

Mémoire disponible fixée à 16 Go et catalogue de test (tests/app/conftest.py) : empreintes
estimées Gemma 3 1B ≈ 1,0 Go, Qwen 2.5 1.5B ≈ 1,25 Go, llama3.2:1b ≈ 1,5 Go, et 5 Go pour le
8B hors catalogue ci-dessous.
Usage: python -m pytest tests/app/test_defaults.py -v
"""

import pytest
from streamlit.testing.v1 import AppTest

from src.app.states import (
    JUDGE_HELP_BENCHMARK,
    JUDGE_HELP_CLOUD,
    JUDGE_HELP_FITS,
    JUDGE_HELP_NO_LOCAL,
    JUDGE_HELP_NONE_FITS,
    JUDGE_SELF_CAPTION,
    JUDGE_UNFIT_WARNING,
    NO_STRONGER_JUDGE_ADVICE,
    STRONGER_JUDGE_ADVICE,
    WEAK_JUDGE_SMALL,
)
from src.app.tabs.inference.arena import MIN_MODELS_CAPTION
from tests.app.conftest import APP_DIR, FAKE_LOCAL_MODELS, THIRD_LOCAL_MODEL
from tests.app.test_pages import RENDER_TIMEOUT_S

ARENA_PAGE = "views/02_Inference_Arena.py"
RAG_PAGE = "views/03_RAG_Knowledge.py"
AGENTS_PAGE = "views/04_Agent_Lab.py"

GEMMA = "Gemma 3 1B · Local"
QWEN = "Qwen 2.5 1.5B · Local"
LLAMA = "Llama3.2 · Local"  # hors catalogue de test : nom tiré du tag
CLOUD = {"model": "mistral-large-2512", "size": 0, "type": "cloud", "provider": "mistral"}
# Modèle local de 8B hors catalogue, ≈ 5 Go estimés : tient dans les 16 Go simulés.
BIG_LOCAL = {
    "model": "granite4.2:8b",
    "size": 4 * 1024**3,
    "digest": "3" * 64,
    "details": {"family": "granite", "parameter_size": "8.8B", "quantization_level": "Q4_K_M"},
    "type": "local",
    "provider": "ollama",
}
BIG = "Granite4.2 · Local"


@pytest.fixture
def run_page():
    """Exécute une page et arrête le tracker CodeCarbon à la fin."""
    started = []

    def _run(page: str) -> AppTest:
        at = AppTest.from_file(str(APP_DIR / page), default_timeout=RENDER_TIMEOUT_S)
        started.append(at)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        return at

    yield _run
    for at in started:
        if "tracker" in at.session_state:
            at.session_state["tracker"].stop()


@pytest.fixture
def installed(monkeypatch):
    """Remplace les modèles installés par la liste donnée."""
    from src.core.llm_provider import LLMProvider

    def _set(models: list[dict]) -> None:
        monkeypatch.setattr(
            LLMProvider,
            "list_models",
            staticmethod(lambda cloud_enabled=True: [dict(m) for m in models]),
        )

    return _set


def _arena_select(at):
    (multiselect,) = [m for m in at.multiselect if m.label == "Modèles à comparer"]
    return multiselect


def _judge_select(at):
    (select,) = [s for s in at.selectbox if s.label == "Modèle juge"]
    return select


def _launch_button(at):
    (button,) = [b for b in at.button if b.label == "Lancer la comparaison"]
    return button


def _warnings(at):
    return [w.value for w in at.warning]


def _name(label: str) -> str:
    return label.removesuffix(" · Local")


def _weak_judge_text(label: str, stronger_fits: bool | None = None) -> str:
    """« Note peu fiable » (moins de 4B), avec le conseil quand `stronger_fits` est donné."""
    text = WEAK_JUDGE_SMALL.format(name=_name(label))
    if stronger_fits is None:
        return text
    return f"{text} {STRONGER_JUDGE_ADVICE if stronger_fits else NO_STRONGER_JUDGE_ADVICE}"


def _captions(at):
    return [c.value for c in at.caption]


# ---------------------------------------------------------------------------
# Arène
# ---------------------------------------------------------------------------


def test_arena_preselects_small_local_models(installed, run_page):
    """Trois petits locaux et un cloud : le juge est le plus gros (llama3.2:1b), les deux
    autres sont présélectionnés, du plus rapide (plus petite empreinte) au plus lent ; locaux
    d'abord, cloud en dernier ; lancement actif."""
    installed([CLOUD, *FAKE_LOCAL_MODELS, THIRD_LOCAL_MODEL])
    at = run_page(ARENA_PAGE)

    multiselect = _arena_select(at)
    assert _judge_select(at).value == LLAMA
    assert multiselect.value == [GEMMA, QWEN]
    assert multiselect.options == [GEMMA, QWEN, LLAMA, "Mistral Large · Cloud"]
    assert not _launch_button(at).disabled
    assert MIN_MODELS_CAPTION not in [c.value for c in at.caption]


def test_arena_default_judge_is_largest_local_with_warning(run_page):
    """Deux locaux de moins de 4B : juge = le plus gros (Qwen 2.5 1.5B), « note peu fiable » ;
    les deux restent présélectionnés pour atteindre le minimum de 2."""
    at = run_page(ARENA_PAGE)

    assert _arena_select(at).value == [GEMMA, QWEN]
    assert _judge_select(at).value == QWEN
    assert _judge_select(at).help == JUDGE_HELP_FITS
    # Aucun juge plus gros ne tient : le conseil le dit, sans proposer l'impossible.
    assert _warnings(at) == [_weak_judge_text(QWEN, stronger_fits=False)]
    # Le juge est aussi comparé : il note sa propre réponse, la légende le dit.
    assert JUDGE_SELF_CAPTION.format(name=_name(QWEN)) in _captions(at)


def test_arena_results_repeat_judge_limits(run_page, fake_inference):
    """Résultats : la note vient d'un juge faible qui se note lui-même ; les deux limites
    accompagnent le podium."""
    at = run_page(ARENA_PAGE)
    _launch_button(at).click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert ("judge", "qwen2.5:1.5b") in fake_inference.calls

    captions = _captions(at)
    assert _weak_judge_text(QWEN) in captions
    assert captions.count(JUDGE_SELF_CAPTION.format(name=_name(QWEN))) == 2


def test_arena_judge_of_at_least_4b_has_no_warning(installed, run_page):
    """Un local ≥ 4B tient : il est le juge par défaut, sans avertissement, et il n'est pas
    présélectionné (il ne note pas sa propre réponse) ; le cloud n'est ni juge ni
    présélectionné."""
    installed([*FAKE_LOCAL_MODELS, BIG_LOCAL, CLOUD])
    at = run_page(ARENA_PAGE)

    assert _judge_select(at).value == BIG
    assert not _warnings(at)
    assert _arena_select(at).value == [GEMMA, QWEN]
    assert not [c for c in _captions(at) if "propre réponse" in c]

    # Choisir un petit juge à la main fait apparaître l'avertissement, avec le conseil de
    # prendre un juge plus gros (il en tient un).
    _judge_select(at).set_value(GEMMA).run()
    assert _warnings(at) == [_weak_judge_text(GEMMA, stronger_fits=True)]
    assert JUDGE_SELF_CAPTION.format(name=_name(GEMMA)) in _captions(at)


def test_arena_launch_disabled_with_one_model(run_page):
    """Un seul modèle : « Lancer la comparaison » désactivé, légende qui nomme le prérequis."""
    at = run_page(ARENA_PAGE)
    _arena_select(at).set_value([GEMMA]).run()

    assert _launch_button(at).disabled
    assert MIN_MODELS_CAPTION in [c.value for c in at.caption]
    assert MIN_MODELS_CAPTION == "Choisissez au moins 2 modèles."


def test_arena_nothing_preselected_when_nothing_fits(monkeypatch, run_page):
    """Aucun local ne tient : aucune présélection, lancement désactivé ; le premier proposé
    reste le plus petit local."""
    monkeypatch.setattr("src.app.ui.available_memory_gb", lambda: 1.0)
    at = run_page(ARENA_PAGE)

    assert _arena_select(at).value == []
    assert _launch_button(at).disabled
    (chat_select,) = [s for s in at.selectbox if s.label == "Modèle actif"]
    assert chat_select.value == GEMMA
    # Juge par défaut = le plus petit local, qui ne tient pas : l'aide et l'alerte le disent.
    assert _judge_select(at).value == GEMMA
    assert _judge_select(at).help == JUDGE_HELP_NONE_FITS
    assert _warnings(at) == [
        JUDGE_UNFIT_WARNING.format(name=_name(GEMMA)),
        _weak_judge_text(GEMMA, stronger_fits=False),
    ]


def test_arena_with_cloud_models_only(installed, run_page):
    """Seulement du cloud : aucun juge par défaut (None), la page s'affiche, rien n'est
    présélectionné et l'aide dit qu'aucun modèle local n'est installé."""
    installed([CLOUD])
    at = run_page(ARENA_PAGE)

    assert _arena_select(at).value == []
    assert _judge_select(at).value == "Mistral Large · Cloud"
    assert _judge_select(at).help == JUDGE_HELP_NO_LOCAL
    assert not _warnings(at)


# ---------------------------------------------------------------------------
# Modèle proposé : Chat libre, Banc d'essai, Discussion, Agents autonomes
# ---------------------------------------------------------------------------


def test_chat_and_lab_default_to_fastest_fitting_local(installed, run_page):
    """Chat libre et Banc d'essai : le modèle local le plus rapide qui tient, même si un modèle
    cloud est proposé et que l'ordre du fournisseur est différent."""
    installed([CLOUD, BIG_LOCAL, *FAKE_LOCAL_MODELS])
    at = run_page(ARENA_PAGE)

    (chat_select,) = [s for s in at.selectbox if s.label == "Modèle actif"]
    (lab_select,) = [s for s in at.selectbox if s.label == "Modèle"]
    assert chat_select.value == GEMMA
    assert lab_select.value == GEMMA
    assert chat_select.options[-1] == "Mistral Large · Cloud"


def test_documents_chat_defaults_to_fastest_fitting_local(installed, monkeypatch, run_page):
    """Discussion : le modèle local le plus rapide qui tient ; le cloud (« api ») en dernier.
    Évaluation de la qualité : juge = plus gros local qui tient."""
    from src.core.rag_engine import RAGEngine

    monkeypatch.setattr(
        RAGEngine,
        "get_stats",
        lambda self: {"count": 14, "sources": ["note.md"], "collection": "t"},
    )
    installed([CLOUD, BIG_LOCAL, *FAKE_LOCAL_MODELS])
    at = run_page(RAG_PAGE)

    (chat_select,) = [s for s in at.selectbox if s.label == "Modèle actif"]
    assert chat_select.value == GEMMA
    assert chat_select.options == [GEMMA, QWEN, BIG, "Mistral Large · Cloud"]
    assert _judge_select(at).value == BIG
    assert not _warnings(at)
    # Modèle évalué par défaut : le premier proposé, pas le juge.
    (candidates,) = [m for m in at.multiselect if m.label == "Modèles évalués"]
    assert candidates.value == [GEMMA]


def test_documents_eval_warns_about_weak_judge(monkeypatch, run_page):
    """Évaluation de la qualité : aucun local ≥ 4B, juge = le plus gros (Qwen 2.5 1.5B) et
    avertissement « note peu fiable » visible."""
    from src.core.rag_engine import RAGEngine

    monkeypatch.setattr(
        RAGEngine,
        "get_stats",
        lambda self: {"count": 14, "sources": ["note.md"], "collection": "t"},
    )
    at = run_page(RAG_PAGE)

    assert _judge_select(at).value == QWEN
    assert _warnings(at) == [_weak_judge_text(QWEN, stronger_fits=False)]
    (candidates,) = [m for m in at.multiselect if m.label == "Modèles évalués"]
    assert candidates.value == [GEMMA]


@pytest.fixture
def documents_indexed(monkeypatch):
    """Base documentaire non vide : les onglets Discussion et Évaluation s'affichent."""
    from src.core.rag_engine import RAGEngine

    monkeypatch.setattr(
        RAGEngine,
        "get_stats",
        lambda self: {"count": 14, "sources": ["note.md"], "collection": "t"},
    )


def test_documents_eval_candidate_is_not_the_judge(monkeypatch, documents_indexed, run_page):
    """1 Go disponible : rien ne tient, le juge par défaut est le plus petit local, premier
    libellé ; le modèle évalué par défaut est le suivant, pas le juge."""
    monkeypatch.setattr("src.app.ui.available_memory_gb", lambda: 1.0)
    at = run_page(RAG_PAGE)

    judge = _judge_select(at)
    assert judge.value == GEMMA == judge.options[0]
    assert judge.help == JUDGE_HELP_NONE_FITS
    (candidates,) = [m for m in at.multiselect if m.label == "Modèles évalués"]
    assert candidates.value == [QWEN]
    assert JUDGE_UNFIT_WARNING.format(name=_name(GEMMA)) in _warnings(at)


def test_documents_eval_with_cloud_models_only(installed, documents_indexed, run_page):
    """Seulement du cloud : aucun juge par défaut, la page s'affiche sans avertissement."""
    installed([CLOUD])
    at = run_page(RAG_PAGE)

    assert _judge_select(at).value == "Mistral Large · Cloud"
    assert _judge_select(at).help == JUDGE_HELP_NO_LOCAL
    assert not _warnings(at)


def test_agents_local_fitting_then_verified_tools_then_memory_rule(installed, run_page):
    """Agents autonomes : local avant cloud, puis ceux qui tiennent, puis outils vérifiés,
    puis la règle mémoire (Gemma 3 1B, plus petit, avant llama3.2:1b) ; un cloud aux outils
    vérifiés reste après tous les locaux."""
    installed([THIRD_LOCAL_MODEL, CLOUD, *FAKE_LOCAL_MODELS])
    at = run_page(AGENTS_PAGE)

    (select,) = [s for s in at.selectbox if s.label == "Modèle"]
    assert select.options == [
        "Qwen 2.5 1.5B · Local · outils vérifiés",
        GEMMA,
        LLAMA,
        "Mistral Large · Cloud · outils vérifiés",
    ]
    assert select.value == "Qwen 2.5 1.5B · Local · outils vérifiés"


def test_crew_default_agent_model_follows_the_rule(installed, run_page):
    """Équipe d'agents : le modèle du premier agent est le premier de la liste triée, pas le
    premier renvoyé par le fournisseur."""
    installed([THIRD_LOCAL_MODEL, CLOUD, *FAKE_LOCAL_MODELS])
    at = run_page(AGENTS_PAGE)
    (radio,) = [r for r in at.sidebar.radio if r.label == "Mode"]
    radio.set_value("Équipe d'agents").run()
    assert not at.exception, [e.value for e in at.exception]

    assert at.session_state["crew_agents"][0]["model_tag"] == "qwen2.5:1.5b"


def test_crew_add_agent_uses_the_rule(installed, run_page):
    """« Ajouter un agent » : le nouvel agent prend le premier modèle de la liste triée, pas
    le premier renvoyé par le fournisseur."""
    installed([THIRD_LOCAL_MODEL, CLOUD, *FAKE_LOCAL_MODELS])
    at = run_page(AGENTS_PAGE)
    (radio,) = [r for r in at.sidebar.radio if r.label == "Mode"]
    radio.set_value("Équipe d'agents").run()
    n_agents = len(at.session_state["crew_agents"])

    (add,) = [b for b in at.button if b.label == "Ajouter un agent"]
    add.click().run()
    assert not at.exception, [e.value for e in at.exception]

    agents = at.session_state["crew_agents"]
    assert len(agents) == n_agents + 1
    assert agents[-1]["model_tag"] == "qwen2.5:1.5b"


def test_agents_local_that_does_not_fit_stays_after_fitting_ones(installed, monkeypatch, run_page):
    """Un local aux outils vérifiés qui ne tient pas passe après les locaux qui tiennent : il
    ne devient pas le modèle par défaut de l'agent."""
    monkeypatch.setattr("src.app.ui.available_memory_gb", lambda: 1.8)
    installed([*FAKE_LOCAL_MODELS])
    at = run_page(AGENTS_PAGE)

    # 1,8 Go : Gemma (≈ 1,0 Go) tient, Qwen (≈ 1,25 Go × 1,10 > 1,3 Go utilisables) non.
    (select,) = [s for s in at.selectbox if s.label == "Modèle"]
    assert select.options == [GEMMA, "Qwen 2.5 1.5B · Local · outils vérifiés"]
    assert select.value == GEMMA


def test_crew_library_load_uses_the_rule(installed, monkeypatch, run_page):
    """« Charger une équipe » puis « Charger » : chaque agent de l'équipe reçoit le modèle de
    la règle, pas le premier renvoyé par le fournisseur.

    AppTest ne rejoue pas un dialogue ouvert au run précédent : le bouton « Charger » est
    cliqué dans un script qui ouvre le dialogue avec le modèle transmis par la page."""
    from src.app.tabs.agent import crew

    dialog_function = crew.open_crew_library
    opened_with = []
    monkeypatch.setattr(crew, "open_crew_library", opened_with.append)
    installed([THIRD_LOCAL_MODEL, CLOUD, *FAKE_LOCAL_MODELS])
    at = run_page(AGENTS_PAGE)
    (radio,) = [r for r in at.sidebar.radio if r.label == "Mode"]
    radio.set_value("Équipe d'agents").run()
    (open_library,) = [b for b in at.button if b.label == "Charger une équipe"]
    open_library.click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert opened_with == ["qwen2.5:1.5b"]
    monkeypatch.setattr(crew, "open_crew_library", dialog_function)

    def library_script():
        from src.app.tabs.agent import crew

        crew.open_crew_library("qwen2.5:1.5b")

    dialog = AppTest.from_function(library_script, default_timeout=RENDER_TIMEOUT_S)
    dialog.run()
    load = [b for b in dialog.button if b.label == "Charger"]
    assert load, "le dialogue « Charger une équipe » devrait proposer des équipes"
    load[0].click().run()
    assert not dialog.exception, [e.value for e in dialog.exception]

    first_crew = next(iter(next(iter(crew.CREW_PROMPT_LIBRARY.values())).values()))
    agents = dialog.session_state["crew_agents"]
    assert [a["role"] for a in agents] == [a["role"] for a in first_crew["suggested_crew"]]
    assert {a["model_tag"] for a in agents} == {"qwen2.5:1.5b"}


# ---------------------------------------------------------------------------
# Gestion des modèles
# ---------------------------------------------------------------------------


def test_manager_reads_megabytes_as_fraction_of_gigabyte(installed, monkeypatch, run_page):
    """« 350 MB » (taille du catalogue) est lu comme 0,35 Go, pas 350 Go."""
    from src.core.models_db import MODELS_DB

    monkeypatch.setitem(
        MODELS_DB,
        "Granite 4.0 350M",
        {
            "ollama_tag": "granite4:350m",
            "type": "local",
            "size_gb": "350 MB",
            "params_tot": "0.35B",
            "params_act": "0.35B",
        },
    )
    granite = {
        "model": "granite4:350m",
        "size": 0,
        "details": {"parameter_size": "352.16M"},
        "type": "local",
        "provider": "ollama",
    }
    installed([granite, *FAKE_LOCAL_MODELS])
    at = run_page(ARENA_PAGE)

    (table,) = [t.value for t in at.dataframe if "RAM" in t.value.columns]
    ram = dict(zip(table["Tag"], table["RAM"], strict=True))
    assert ram["granite4:350m"] == pytest.approx(0.35)


# ---------------------------------------------------------------------------
# Story 15 : juge d'après le cloud ou le benchmark du poste, modèles de raisonnement
# ---------------------------------------------------------------------------

CLOUD_BADGE = ":orange-badge[:material/cloud: Cloud]"
# Modèle local de 4,7B hors catalogue (≈ 4,2 Go estimés) : juge fiable, rapide sur le poste.
MID_LOCAL = {
    "model": "qwen3.5:4b",
    "size": int(3.4 * 1024**3),
    "digest": "4" * 64,
    "details": {"family": "qwen35", "parameter_size": "4.7B", "quantization_level": "Q4_K_M"},
    "type": "local",
    "provider": "ollama",
}
MID = "Qwen3.5 · Local"
# Modèle dédié au raisonnement, le plus petit (donc le plus rapide selon la règle).
THINKING_LOCAL = {
    "model": "lfm2.5-thinking:1.2b",
    "size": 731 * 1024**2,
    "digest": "5" * 64,
    "details": {"family": "lfm2", "parameter_size": "1.2B", "quantization_level": "Q4_K_M"},
    "type": "local",
    "provider": "ollama",
}
THINKING = "Lfm2.5-thinking · Local"
# Modèles cloud tels que les listent les fournisseurs Anthropic et OpenAI.
CLAUDE_SONNET_4 = {
    "model": "claude-sonnet-4-20250514",
    "name": "Claude Sonnet 4",
    "size": 0,
    "type": "cloud",
    "provider": "anthropic",
}
GPT_4O = {"model": "gpt-4o", "name": "GPT-4o", "size": 0, "type": "cloud", "provider": "openai"}


@pytest.fixture
def machine_benchmark(monkeypatch):
    """Benchmark de ce poste simulé ({tag : précision, débit prudent[, outils]})."""
    from src.core.benchmark_results import BenchScore

    def _set(scores: dict[str, tuple]) -> None:
        bench = {tag: BenchScore(*values) for tag, values in scores.items()}
        monkeypatch.setattr("src.app.ui.machine_benchmark", lambda: bench)

    return _set


def _judge_badges(at) -> list[str]:
    (expander,) = [e for e in at.expander if e.label == "Réglages du juge"]
    return [m.value for m in expander.markdown]


def test_arena_judge_from_machine_benchmark(installed, machine_benchmark, run_page):
    """Poste benchmarké : juge = le plus précis d'au moins 4B à plus de 10 tokens/s (pas le
    plus gros, trop lent, ni le petit plus précis) ; aide qui le dit, aucun avertissement."""
    installed([*FAKE_LOCAL_MODELS, BIG_LOCAL, MID_LOCAL])
    machine_benchmark(
        {
            "granite4.2:8b": (0.795, 5.05),
            "qwen3.5:4b": (0.87, 62.5),
            "qwen2.5:1.5b": (0.95, 150.0),
        }
    )
    at = run_page(ARENA_PAGE)

    assert _judge_select(at).value == MID
    assert _judge_select(at).help == JUDGE_HELP_BENCHMARK
    assert not _warnings(at)
    assert MID not in _arena_select(at).value


def test_arena_cloud_enabled_judge_is_most_capable_cloud(monkeypatch, machine_benchmark):
    """Cloud activé (clé Anthropic et OpenAI) : juge = Claude Sonnet 4, badge Cloud ; cloud
    désactivé : juge local, aucun modèle cloud proposé."""
    from src.core.llm_provider import LLMProvider

    def list_models(cloud_enabled=False):
        cloud = [dict(GPT_4O), dict(CLAUDE_SONNET_4)] if cloud_enabled else []
        return [*cloud, *(dict(m) for m in (*FAKE_LOCAL_MODELS, MID_LOCAL))]

    monkeypatch.setattr(LLMProvider, "list_models", staticmethod(list_models))
    machine_benchmark({"qwen3.5:4b": (0.87, 62.5)})

    for enabled, judge in ((True, "Claude Sonnet 4 · Cloud"), (False, MID)):
        at = AppTest.from_file(str(APP_DIR / ARENA_PAGE), default_timeout=RENDER_TIMEOUT_S)
        at.session_state["cloud_enabled"] = enabled
        at.run()
        try:
            assert not at.exception, [e.value for e in at.exception]
            assert _judge_select(at).value == judge
            assert _judge_select(at).help == (JUDGE_HELP_CLOUD if enabled else JUDGE_HELP_BENCHMARK)
            assert (CLOUD_BADGE in _judge_badges(at)) is enabled
            assert not _warnings(at)
        finally:
            if "tracker" in at.session_state:
                at.session_state["tracker"].stop()


def test_documents_chat_first_model_is_not_a_reasoning_model(
    installed, documents_indexed, run_page
):
    """Discussion : le modèle dédié au raisonnement, le plus petit, n'est pas proposé en
    premier ; il reste sélectionnable."""
    installed([THINKING_LOCAL, *FAKE_LOCAL_MODELS])
    at = run_page(RAG_PAGE)

    (chat_select,) = [s for s in at.selectbox if s.label == "Modèle actif"]
    assert chat_select.value == GEMMA
    assert THINKING in chat_select.options


def test_arena_does_not_preselect_reasoning_model(installed, run_page):
    """Arène : ni premier proposé, ni présélectionné."""
    installed([THINKING_LOCAL, *FAKE_LOCAL_MODELS, THIRD_LOCAL_MODEL])
    at = run_page(ARENA_PAGE)

    assert THINKING not in _arena_select(at).value
    (chat_select,) = [s for s in at.selectbox if s.label == "Modèle actif"]
    assert chat_select.value == GEMMA


def test_agents_default_is_not_a_reasoning_model(installed, monkeypatch, run_page):
    """Agents autonomes : un modèle dédié au raisonnement aux outils vérifiés, le plus petit,
    n'est pas le modèle par défaut ; il passe après les locaux non dédiés au raisonnement."""
    from src.core.models_db import MODELS_DB

    monkeypatch.setitem(
        MODELS_DB,
        "LFM 2.5 1.2B Thinking",
        {
            "ollama_tag": "lfm2.5-thinking:1.2b",
            "type": "local",
            "size_gb": "0.7 GB",
            "params_tot": "1.2B",
            "params_act": "1.2B",
            "capabilities": ["chat", "tools"],
        },
    )
    installed([THINKING_LOCAL, *FAKE_LOCAL_MODELS])
    at = run_page(AGENTS_PAGE)

    thinking = "LFM 2.5 1.2B Thinking · Local · outils vérifiés"
    (select,) = [s for s in at.selectbox if s.label == "Modèle"]
    assert select.value != thinking
    assert select.options == ["Qwen 2.5 1.5B · Local · outils vérifiés", GEMMA, thinking]


# ---------------------------------------------------------------------------
# Story 18 : modèle proposé par défaut sur la page Agents, d'après le benchmark du poste
# ---------------------------------------------------------------------------

AGENT_BENCH = {
    # Candidat : ≥ 3B, outils vérifiés, rapide, tient en mémoire.
    "qwen3.5:4b": (0.87, 62.5, 1.0),
    # Plus précis mais trop lent (5 tokens/s).
    "granite4.2:8b": (0.9, 5.05, 1.0),
    # Plus précis et rapide mais < 3B.
    "qwen2.5:1.5b": (0.95, 150.0, 1.0),
}
AGENT_MID = f"{MID} · outils vérifiés"


def _agent_select(at):
    (select,) = [s for s in at.selectbox if s.label == "Modèle"]
    return select


def test_agents_default_from_machine_benchmark(installed, machine_benchmark, run_page):
    """Poste benchmarké : premier proposé = le candidat de la règle, « outils vérifiés » (le
    benchmark les a vérifiés) ; aucun modèle retiré de la liste."""
    installed([*FAKE_LOCAL_MODELS, BIG_LOCAL, MID_LOCAL])
    machine_benchmark(AGENT_BENCH)
    at = run_page(AGENTS_PAGE)

    select = _agent_select(at)
    assert select.options[0] == AGENT_MID
    assert select.value == AGENT_MID
    assert len(select.options) == 4


def test_crew_default_from_machine_benchmark(installed, machine_benchmark, run_page):
    """Équipe d'agents : le premier agent prend aussi le candidat de la règle."""
    installed([*FAKE_LOCAL_MODELS, BIG_LOCAL, MID_LOCAL])
    machine_benchmark(AGENT_BENCH)
    at = run_page(AGENTS_PAGE)
    (radio,) = [r for r in at.sidebar.radio if r.label == "Mode"]
    radio.set_value("Équipe d'agents").run()
    assert not at.exception, [e.value for e in at.exception]

    assert at.session_state["crew_agents"][0]["model_tag"] == "qwen3.5:4b"


@pytest.mark.parametrize(
    "bench",
    [
        {**AGENT_BENCH, "qwen3.5:4b": (0.87, 62.5, 0.5)},  # outils sous 0,75
        {**AGENT_BENCH, "qwen3.5:4b": (0.87, 9.0, 1.0)},  # 10 tokens/s ou moins
        {},  # poste inconnu
    ],
    ids=["outils", "debit", "poste-inconnu"],
)
def test_agents_without_candidate_keep_current_order(installed, machine_benchmark, run_page, bench):
    """Aucun candidat, ou pas de benchmark : l'ordre actuel (outils vérifiés du catalogue)."""
    installed([*FAKE_LOCAL_MODELS, BIG_LOCAL, MID_LOCAL])
    machine_benchmark(bench)
    at = run_page(AGENTS_PAGE)

    select = _agent_select(at)
    assert select.value == "Qwen 2.5 1.5B · Local · outils vérifiés"
    assert MID in select.options
