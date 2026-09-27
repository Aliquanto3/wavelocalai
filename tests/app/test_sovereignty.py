"""
Tests de la souveraineté visible et des actions sensibles (story 8), avec AppTest : local au
démarrage, aucun modèle cloud quand le cloud est désactivé, badge Local ou Cloud sur chaque
modèle et chaque réponse, email en brouillon confirmé, vidage de la base confirmé.

Ollama, les fournisseurs cloud, l'inférence et SMTP sont simulés : aucun réseau, aucun envoi.
Référence : _bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md
(Souveraineté visible, confirm-dialog) et DESIGN.md (badge-local, badge-cloud).
Usage: python -m pytest tests/app/test_sovereignty.py -v
"""

import ast
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import streamlit

from src.app.formatting import NBSP
from src.core.llm_provider import LLMProvider
from tests.app.conftest import APP_DIR, FAKE_LOCAL_MODELS
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
    run_page,
)

# Rendu de st.badge (DESIGN.md) : directive Markdown native.
LOCAL_BADGE = ":green-badge[:material/computer: Local]"
CLOUD_BADGE = ":orange-badge[:material/cloud: Cloud]"

CLOUD_MODEL = {"model": "mistral-large-2512", "size": 0, "type": "cloud", "provider": "mistral"}
REMOTE_TAG = {"model": "glm-4.6:cloud", "size": 384, "type": "local", "provider": "ollama"}
LOCAL_MODEL = FAKE_LOCAL_MODELS[0]

# LLMProvider.list_models réel, capturé avant la simulation de tests/app/conftest.py.
REAL_LIST_MODELS = LLMProvider.__dict__["list_models"]


def _label(model: dict) -> str:
    from src.app.ui import model_label
    from src.core.model_defaults import is_remote_tag

    is_cloud = model["type"] == "cloud" or is_remote_tag(model)
    return model_label(_friendly(model), is_cloud)


def _markdowns(at) -> list[str]:
    return [m.value for m in at.markdown]


def _captions(at) -> list[str]:
    return [c.value for c in at.caption]


def _select(at, label: str, value: str, key: str | None = None) -> None:
    (box,) = [s for s in at.selectbox if s.label == label and (key is None or s.key == key)]
    box.set_value(value).run()
    assert not at.exception, [e.value for e in at.exception]


def _flat(node):
    """Éléments d'un bloc AppTest, dans l'ordre d'affichage."""
    children = getattr(node, "children", None)
    if not children:
        yield node
        return
    for key in sorted(children):
        yield from _flat(children[key])


@pytest.fixture
def cloud_models(monkeypatch):
    """Un modèle local et un modèle cloud, ce dernier seulement si le cloud est autorisé."""

    def list_models(cloud_enabled=False):
        return [dict(LOCAL_MODEL)] + ([dict(CLOUD_MODEL)] if cloud_enabled else [])

    monkeypatch.setattr(LLMProvider, "list_models", staticmethod(list_models))


@pytest.fixture
def cloud_page(cloud_models):
    """Page exécutée seule, cloud autorisé (le contrôle global vit dans le routeur)."""
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


# ---------------------------------------------------------------------------
# Démarrage : local, même avec des clés d'API
# ---------------------------------------------------------------------------


def test_startup_is_local_even_with_api_keys(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "cle-factice")
    monkeypatch.setenv("OPENAI_API_KEY", "cle-factice")
    at = _app()
    try:
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert at.toggle(key="cloud_enabled").value is False
        assert _metric(at, "Mode") == "Local"
        assert LOCAL_BADGE in _markdowns(at)
        assert CLOUD_BADGE not in _markdowns(at)
    finally:
        _stop_tracker(at)


# ---------------------------------------------------------------------------
# Cloud désactivé : aucun modèle cloud dans aucun sélecteur
# ---------------------------------------------------------------------------


@pytest.fixture
def real_listing(monkeypatch, indexed_base):
    """LLMProvider.list_models réel sur une factory simulée : Ollama sert un modèle local et
    un tag distant (`glm-4.6:cloud`), un fournisseur cloud sert Mistral Large."""
    from src.core.providers.provider_factory import LLMProviderFactory

    ollama = MagicMock(is_local=True)
    ollama.list_models.side_effect = lambda: [dict(LOCAL_MODEL), dict(REMOTE_TAG)]
    mistral = MagicMock(is_local=False)
    mistral.list_models.side_effect = lambda: [dict(CLOUD_MODEL)]
    factory = object.__new__(LLMProviderFactory)
    factory._providers = {"ollama": ollama, "mistral": mistral}

    monkeypatch.setattr(LLMProvider, "list_models", REAL_LIST_MODELS)
    monkeypatch.setattr("src.core.llm_provider.get_provider_factory", lambda: factory)


def _model_options(at) -> list[str]:
    """Options de tous les sélecteurs de modèles de la page (listes et choix multiples ; la
    barre latérale n'a que des modèles d'embedding et de reclassement)."""
    options = []
    for widget in [*at.main.selectbox, *at.main.multiselect]:
        if widget.label.startswith("Modèle"):
            options += list(widget.options)
    return options


def test_cloud_disabled_hides_cloud_models_in_every_selector(real_listing):
    at = _app()
    try:
        at.run()
        local = _label(LOCAL_MODEL)
        pages = [ARENA_PAGE, RAG_PAGE, AGENTS_PAGE]
        for page in pages:
            at.switch_page(page).run()
            assert not at.exception, [e.value for e in at.exception]
            options = _model_options(at)
            assert options, page
            assert all(o.startswith(local) for o in options), (page, options)

        # Équipe d'agents : sélecteur de chaque agent.
        (mode,) = [r for r in at.sidebar.radio if r.label == "Mode"]
        mode.set_value("Équipe d'agents").run()
        assert not at.exception, [e.value for e in at.exception]
        options = _model_options(at)
        assert options and all(o.startswith(local) for o in options), options

        # Cloud autorisé : le tag distant et le modèle cloud apparaissent, en « · Cloud ».
        at.switch_page(ARENA_PAGE).run()
        at.toggle(key="cloud_enabled").set_value(True).run()
        assert not at.exception, [e.value for e in at.exception]
        options = _model_options(at)
        assert _label(REMOTE_TAG) in options and _label(CLOUD_MODEL) in options
        assert _label(REMOTE_TAG).endswith("· Cloud")
    finally:
        _stop_tracker(at)


# ---------------------------------------------------------------------------
# Badges : modèle choisi et chaque réponse
# ---------------------------------------------------------------------------


def test_chat_badges_follow_chosen_model(cloud_page, fake_inference):
    at = cloud_page(ARENA_PAGE)
    # Défaut : le modèle local, badge Local à côté du sélecteur.
    assert LOCAL_BADGE in _markdowns(at)

    _select(at, "Modèle actif", _label(CLOUD_MODEL))
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]

    footers = [c for c in _captions(at) if "CO₂" in c and "Durée totale" in c]
    assert len(footers) == 1 and footers[0].startswith(f"{CLOUD_BADGE} · "), footers
    assert at.session_state["messages"][-1]["is_cloud"] is True

    # Réponse suivante avec le modèle local : chaque réponse garde son propre badge.
    _select(at, "Modèle actif", _label(LOCAL_MODEL))
    at.chat_input[0].set_value("Encore").run()
    footers = [c for c in _captions(at) if "CO₂" in c and "Durée totale" in c]
    assert [f.split(" · ")[0] for f in footers] == [CLOUD_BADGE, LOCAL_BADGE]


def test_lab_badge_on_chosen_model_and_answer(cloud_page, fake_inference):
    at = cloud_page(ARENA_PAGE)
    _select(at, "Modèle", _label(CLOUD_MODEL), key="lab_model_select")
    before = _markdowns(at).count(CLOUD_BADGE)
    # Badge du modèle choisi, et celui du juge de l'Arène : cloud autorisé, le juge par
    # défaut est le modèle cloud le plus capable (story 15).
    assert before == 2

    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert _markdowns(at).count(CLOUD_BADGE) == before + 1  # badge de la réponse
    assert at.session_state["lab_last_is_cloud"] is True


def test_arena_badges_in_table_winner_and_answers(cloud_page, fake_inference):
    at = cloud_page(ARENA_PAGE)
    (multiselect,) = [m for m in at.multiselect if m.label == "Modèles à comparer"]
    multiselect.set_value([_label(LOCAL_MODEL), _label(CLOUD_MODEL)]).run()
    _button(at, "Lancer la comparaison").click().run()
    assert not at.exception, [e.value for e in at.exception]

    table = _results_table(at)
    execution = dict(zip(table["Modèle"], table["Exécution"], strict=True))
    assert execution == {_friendly(LOCAL_MODEL): "Local", _friendly(CLOUD_MODEL): "Cloud"}

    # Vainqueur : badge juste sous son nom.
    elements = list(_flat(at.main))
    names = {_friendly(LOCAL_MODEL): LOCAL_BADGE, _friendly(CLOUD_MODEL): CLOUD_BADGE}
    (idx,) = [
        i
        for i, e in enumerate(elements)
        if getattr(e, "type", None) == "subheader" and e.value in names
    ]
    assert elements[idx + 1].value == names[elements[idx].value]

    # Réponses des modèles : chacune avec son badge.
    for name, badge in names.items():
        assert any(m.startswith(f"**{name}**") and m.endswith(badge) for m in _markdowns(at))


def _fake_stream():
    from src.core.metrics import InferenceMetrics

    async def stream(model_name, messages, temperature=0.7, system_prompt=None):
        yield "Réponse simulée."
        yield InferenceMetrics(model_name, 10, 20, 1.0, 0.1, 20.0)

    return stream


def test_documents_chat_badge_and_model_in_history(
    monkeypatch, cloud_page, indexed_base
):  # noqa: F811
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_fake_stream()))
    at = cloud_page(RAG_PAGE)
    _select(at, "Modèle actif", _label(CLOUD_MODEL), key="rag_chat_select")
    assert CLOUD_BADGE in _markdowns(at)

    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]
    (meta,) = [c for c in _captions(at) if c.startswith(CLOUD_BADGE)]
    assert _friendly(CLOUD_MODEL) in meta
    message = at.session_state["rag_messages"][-1]
    assert message["model_tag"] == CLOUD_MODEL["model"] and message["is_cloud"] is True


def test_documents_evaluation_badges(monkeypatch, cloud_page, indexed_base):  # noqa: F811
    from src.core.eval_engine import EvalEngine, EvalResult

    scores = iter([EvalResult(0.8, 0.9, 0.85), EvalResult(0.6, 0.7, 0.65)])
    monkeypatch.setattr(EvalEngine, "evaluate_single_turn", lambda self, **kw: next(scores))
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_fake_stream()))
    at = cloud_page(RAG_PAGE)
    before = _markdowns(at).count(CLOUD_BADGE)
    (multiselect,) = [m for m in at.multiselect if m.label == "Modèles évalués"]
    multiselect.set_value([_label(LOCAL_MODEL), _label(CLOUD_MODEL)]).run()
    _button(at, "Lancer l'évaluation").click().run()
    assert not at.exception, [e.value for e in at.exception]

    table = _results_table(at)
    execution = dict(zip(table["Modèle"], table["Exécution"], strict=True))
    assert execution == {_friendly(LOCAL_MODEL): "Local", _friendly(CLOUD_MODEL): "Cloud"}
    # Podium et réponses : un badge Cloud de plus pour chacun.
    assert _markdowns(at).count(CLOUD_BADGE) == before + 2


def test_agent_solo_answer_badge(fake_agent, run_page):  # noqa: F811
    at = run_page(AGENTS_PAGE)
    assert LOCAL_BADGE in _markdowns(at)  # modèle choisi
    at.chat_input[0].set_value("Audit du système").run()
    assert not at.exception, [e.value for e in at.exception]
    assert any(c.startswith(LOCAL_BADGE) for c in _captions(at))


def test_crew_is_cloud():
    from src.app.tabs.agent.crew import crew_is_cloud
    from src.app.ui import model_menu

    menu = model_menu([dict(LOCAL_MODEL), dict(FAKE_LOCAL_MODELS[1]), dict(CLOUD_MODEL)])
    local, other, cloud = (m["model"] for m in (LOCAL_MODEL, FAKE_LOCAL_MODELS[1], CLOUD_MODEL))
    assert crew_is_cloud([{"model_tag": local}, {"model_tag": cloud}], menu) is True
    assert crew_is_cloud([{"model_tag": local}, {"model_tag": other}], menu) is False
    assert crew_is_cloud([{"model_tag": local}, {"model_tag": "N/A"}], menu) is None


def test_crew_cloud_agent_switched_to_local(run_page):  # noqa: F811
    """Cloud désactivé : un agent configuré sur un modèle cloud passe sur un local ; le badge
    du modèle principal le dit dès ce run, avec une légende."""
    from src.app.tabs.agent.crew import CLOUD_FALLBACK_CAPTION

    at = run_page(AGENTS_PAGE)
    at.session_state["crew_agents"] = [
        {
            "role": "Analyste",
            "goal": "Analyser",
            "backstory": "Consultant",
            "model_tag": CLOUD_MODEL["model"],
            "tools": [],
        }
    ]
    (mode,) = [r for r in at.sidebar.radio if r.label == "Mode"]
    mode.set_value("Équipe d'agents").run()
    assert not at.exception, [e.value for e in at.exception]

    assert at.session_state["crew_agents"][0]["model_tag"] != CLOUD_MODEL["model"]
    assert CLOUD_BADGE not in _markdowns(at) and LOCAL_BADGE in _markdowns(at)
    assert any(c.startswith("Analyste utilisait un modèle cloud") for c in _captions(at))
    assert CLOUD_FALLBACK_CAPTION.startswith("{role} utilisait un modèle cloud")


def test_crew_main_model_badge_and_email_caption(run_page):  # noqa: F811
    from src.app.tabs.agent.crew import CREW_EMAIL_CAPTION

    at = run_page(AGENTS_PAGE)
    at.session_state["crew_agents"] = [
        {
            "role": "Rédacteur",
            "goal": "Informer le client",
            "backstory": "Consultant",
            "model_tag": LOCAL_MODEL["model"],
            "tools": ["send_email"],
        }
    ]
    (mode,) = [r for r in at.sidebar.radio if r.label == "Mode"]
    mode.set_value("Équipe d'agents").run()
    assert not at.exception, [e.value for e in at.exception]
    assert LOCAL_BADGE in _markdowns(at)
    assert CREW_EMAIL_CAPTION in _captions(at)


# ---------------------------------------------------------------------------
# Groq (story 16) : modèles cloud seulement si le cloud est autorisé, client simulé
# ---------------------------------------------------------------------------

GROQ_TAGS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]


@pytest.fixture
def groq_listing(monkeypatch, indexed_base):  # noqa: F811
    """LLMProvider réel sur une factory simulée : Ollama sert les modèles locaux, un vrai
    GroqProvider (clé factice) sert ses modèles ; son client est simulé, sans réseau :
    `create` échoue avec un 429 de Groq et compte ses appels."""
    import httpx
    import openai

    from src.core.providers.groq_provider import GroqProvider
    from src.core.providers.provider_factory import LLMProviderFactory

    ollama = MagicMock(is_local=True, provider_name="ollama")
    ollama.list_models.side_effect = lambda: [dict(m) for m in FAKE_LOCAL_MODELS]
    groq = GroqProvider(api_key="cle-factice")
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    quota = openai.RateLimitError(
        "Error code: 429 - Rate limit reached for model",
        response=httpx.Response(429, request=request),
        body=None,
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=quota)
    groq._client = client
    list_groq = MagicMock(side_effect=groq.list_models)
    monkeypatch.setattr(groq, "list_models", list_groq)

    factory = object.__new__(LLMProviderFactory)
    factory._providers = {"ollama": ollama, "groq": groq}
    monkeypatch.setattr(LLMProvider, "list_models", REAL_LIST_MODELS)
    monkeypatch.setattr("src.core.llm_provider.get_provider_factory", lambda: factory)
    return SimpleNamespace(create=client.chat.completions.create, list_models=list_groq)


def _groq_label(tag: str) -> str:
    from src.app.ui import model_label
    from src.core.providers.groq_provider import GROQ_MODELS

    return model_label(GROQ_MODELS[tag]["name"], True)


def test_groq_models_listed_as_cloud_after_locals_and_judge(groq_listing):
    at = _app(ARENA_PAGE)
    try:
        at.session_state["cloud_enabled"] = True
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        (box,) = [s for s in at.selectbox if s.label == "Modèle actif"]
        options = list(box.options)
        groq_labels = [_groq_label(t) for t in GROQ_TAGS]
        assert all(label.endswith("· Cloud") for label in groq_labels)
        locals_ = [_label(m) for m in FAKE_LOCAL_MODELS]
        assert sorted(options[: len(locals_)]) == sorted(locals_)
        assert sorted(options[len(locals_) :]) == sorted(groq_labels)
        # Groq seul fournisseur cloud : juge par défaut = GPT-OSS 120B, badge Cloud.
        (judge,) = [s for s in at.selectbox if s.label == "Modèle juge"]
        assert judge.value == _groq_label("openai/gpt-oss-120b")
        assert CLOUD_BADGE in _markdowns(at)
        assert groq_listing.create.await_count == 0
    finally:
        _stop_tracker(at)


def test_groq_hidden_and_never_called_when_cloud_disabled(groq_listing):
    at = _app()
    try:
        at.run()
        for page in (ARENA_PAGE, RAG_PAGE, AGENTS_PAGE):
            at.switch_page(page).run()
            assert not at.exception, [e.value for e in at.exception]
            options = _model_options(at)
            assert options, page
            assert not [o for o in options if o.endswith("· Cloud")], (page, options)
        # Aucun appel au fournisseur Groq : ni listing, ni génération.
        assert groq_listing.list_models.call_count == 0
        assert groq_listing.create.await_count == 0
    finally:
        _stop_tracker(at)


def test_groq_quota_error_is_readable_and_question_kept(groq_listing):
    at = _app(ARENA_PAGE)
    try:
        at.session_state["cloud_enabled"] = True
        at.run()
        _select(at, "Modèle actif", _groq_label("llama-3.1-8b-instant"))
        at.chat_input[0].set_value("Bonjour Groq").run()
        assert not at.exception, [e.value for e in at.exception]
        assert groq_listing.create.await_count == 1

        (error,) = [e.value for e in at.error]
        assert error.startswith("La génération a échoué.") and "Groq" in error
        assert "429" not in error  # trace brute repliée dans « Détails techniques »
        messages = at.session_state["messages"]
        assert messages[-2] == {"role": "user", "content": "Bonjour Groq"}
        assert messages[-1]["error"] is True and "429" in messages[-1]["detail"]
        # Jamais renvoyée comme un token : aucune réponse ne contient l'erreur.
        assert not [m for m in _markdowns(at) if "Rate limit" in m]
    finally:
        _stop_tracker(at)


# ---------------------------------------------------------------------------
# Email (D2) : décoché par défaut, brouillon confirmé, SMTP simulé
# ---------------------------------------------------------------------------


class FakeSMTP:
    """smtplib.SMTP simulé : enregistre les messages, aucun réseau."""

    sent: list = []
    error: Exception | None = None

    def __init__(self, server, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        if FakeSMTP.error:
            raise FakeSMTP.error
        FakeSMTP.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    """SMTP configuré (valeurs factices) et simulé."""
    import src.core.agent_tools as agent_tools

    FakeSMTP.sent = []
    FakeSMTP.error = None
    monkeypatch.setattr(agent_tools, "SMTP_SERVER", "smtp.test.invalid")
    monkeypatch.setattr(agent_tools, "SMTP_USER", "demo@test.invalid")
    monkeypatch.setattr(agent_tools, "SMTP_PASSWORD", "secret")
    monkeypatch.setattr(agent_tools.smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


@pytest.fixture
def no_smtp(monkeypatch):
    """Variables SMTP vides ; tout envoi ferait échouer le test."""
    import src.core.agent_tools as agent_tools

    def refuse(*args, **kwargs):
        raise AssertionError("aucune connexion SMTP attendue")

    monkeypatch.setattr(agent_tools, "SMTP_USER", "")
    monkeypatch.setattr(agent_tools, "SMTP_PASSWORD", "")
    monkeypatch.setattr(agent_tools.smtplib, "SMTP", refuse)


def _pills(at, label):
    (pills,) = [p for p in at.button_group if p.label == label]
    return pills


def test_email_tool_unchecked_by_default(smtp, run_page):
    from src.core.agent_tools import TOOLS_METADATA

    at = run_page(AGENTS_PAGE)
    tools = _pills(at, "Outils")
    assert len(tools.options) == 9
    names = {meta["name"] for meta in TOOLS_METADATA.values()}
    assert set(tools.value) == names - {"Envoi d'email"}
    assert len(tools.value) == 8
    assert "send_email" not in at.session_state["selected_tools"]
    assert not [p for p in at.button_group if p.label == "Outil non configuré"]


def test_email_tool_visible_but_disabled_without_smtp(no_smtp, run_page):
    at = run_page(AGENTS_PAGE)
    tools = _pills(at, "Outils")
    assert len(tools.options) == 8 and len(tools.value) == 8
    unavailable = _pills(at, "Outil non configuré")
    assert list(unavailable.options) == ["Envoi d'email"]
    assert unavailable.disabled
    assert unavailable.help.startswith("Configuration SMTP absente")
    assert "SMTP_USER" in unavailable.help and "SMTP_PASSWORD" in unavailable.help


DRAFT = {"to": "dsi@client.invalid", "subject": "Synthèse de l'audit", "body": "Bonjour,\nVoici."}


@pytest.fixture
def email_agent(fake_agent, smtp):  # noqa: F811
    """L'agent appelle l'outil d'email (brouillon), puis répond."""
    from src.core.agent_tools import send_email

    fake_agent.events = [
        {"type": "tool_call", "tool": "send_email", "args": dict(DRAFT)},
        {"type": "tool_result", "content": send_email.invoke(dict(DRAFT))},
        {"type": "final_answer", "content": "L'email attend votre validation."},
    ]
    return fake_agent


def _ask_for_email(run_page):
    from src.core.agent_tools import TOOLS_METADATA

    at = run_page(AGENTS_PAGE)
    at.session_state["selected_tools"] = list(TOOLS_METADATA)
    at.run()
    at.chat_input[0].set_value("Envoie la synthèse au DSI").run()
    assert not at.exception, [e.value for e in at.exception]
    return at


@pytest.mark.parametrize(
    ("args", "valid"),
    [
        (dict(DRAFT), True),
        ({**DRAFT, "to": "pas-une-adresse"}, False),
        ({**DRAFT, "subject": ""}, False),
        (None, False),
    ],
)
def test_email_draft_from_tool_arguments(args, valid):
    from src.app.tabs.agent.solo import email_draft

    assert email_draft(args) == (DRAFT if valid else None)


def test_dismiss_email_removes_first_draft(monkeypatch):
    from src.app.tabs.agent import solo

    second = {**DRAFT, "to": "rssi@client.invalid"}
    state = {solo.EMAIL_DRAFTS_KEY: [dict(DRAFT), second]}
    monkeypatch.setattr(solo.st, "session_state", state)
    solo._dismiss_email()
    assert state[solo.EMAIL_DRAFTS_KEY] == [second]


def test_email_requested_shows_draft_without_sending(email_agent, smtp, run_page):
    at = _ask_for_email(run_page)
    assert smtp.sent == []
    assert any("dsi@client.invalid" in w.value for w in at.warning)
    assert "**Destinataire** : dsi@client.invalid" in _markdowns(at)
    assert "**Objet** : Synthèse de l'audit" in _markdowns(at)
    assert DRAFT["body"] in [t.value for t in at.text]
    assert {"Envoyer l'email", "Annuler"} <= {b.label for b in at.button}

    # Rien ne part au rerun suivant sans clic.
    at.run()
    assert smtp.sent == []


def test_email_sent_only_after_confirmation(email_agent, smtp, run_page):
    at = _ask_for_email(run_page)
    _button(at, "Envoyer l'email").click().run()
    assert not at.exception, [e.value for e in at.exception]

    (msg,) = smtp.sent
    assert msg["To"] == DRAFT["to"] and msg["Subject"] == DRAFT["subject"]
    assert [s.value for s in at.success] == ["Email envoyé à dsi@client.invalid."]
    assert "Envoyer l'email" not in [b.label for b in at.button]


def test_email_cancel_sends_nothing(email_agent, smtp, run_page):
    at = _ask_for_email(run_page)
    _button(at, "Annuler").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert smtp.sent == []
    assert not at.success and not at.error
    assert "Envoyer l'email" not in [b.label for b in at.button]
    at.run()
    assert smtp.sent == []


def test_email_not_queued_when_tool_not_selected(email_agent, smtp, run_page):
    """Appel d'email alors que l'outil n'est pas choisi (défaut) : aucune confirmation."""
    at = run_page(AGENTS_PAGE)
    at.chat_input[0].set_value("Envoie la synthèse au DSI").run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Envoyer l'email" not in [b.label for b in at.button]
    assert "agent_email_drafts" not in at.session_state


def test_email_not_queued_without_smtp(email_agent, monkeypatch, run_page):
    import src.core.agent_tools as agent_tools

    monkeypatch.setattr(agent_tools, "SMTP_USER", "")
    at = _ask_for_email(run_page)
    assert "Envoyer l'email" not in [b.label for b in at.button]


def test_identical_email_calls_give_one_confirmation(email_agent, smtp, run_page):
    email_agent.events = [email_agent.events[0], *email_agent.events]
    at = _ask_for_email(run_page)
    assert at.session_state["agent_email_drafts"] == [DRAFT]


def test_drafts_cleared_with_conversation_and_crew_mode(email_agent, smtp, run_page):
    at = _ask_for_email(run_page)
    (clear,) = [b for b in at.sidebar.button if b.label == "Effacer la conversation"]
    clear.click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "agent_email_drafts" not in at.session_state
    assert "Envoyer l'email" not in [b.label for b in at.button]

    at.chat_input[0].set_value("Envoie la synthèse au DSI").run()
    assert at.session_state["agent_email_drafts"] == [DRAFT]
    (mode,) = [r for r in at.sidebar.radio if r.label == "Mode"]
    mode.set_value("Équipe d'agents").run()
    assert not at.exception, [e.value for e in at.exception]
    assert "agent_email_drafts" not in at.session_state


def test_pending_draft_then_scenario_library(email_agent, smtp, run_page):
    """Brouillon en attente puis « Scénarios » : un seul dialogue, aucune exception."""
    at = _ask_for_email(run_page)
    _button(at, "Scénarios").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["agent_email_drafts"] == [DRAFT]
    assert smtp.sent == []


def test_email_smtp_error_shows_alert_only(email_agent, smtp, run_page):
    import smtplib

    smtp.error = smtplib.SMTPException("relais refusé")
    at = _ask_for_email(run_page)
    _button(at, "Envoyer l'email").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert smtp.sent == [] and not at.success
    (error,) = [e.value for e in at.error]
    assert error.startswith("L'email n'a pas été envoyé.")
    assert any("relais refusé" in c.value for c in at.code)


# ---------------------------------------------------------------------------
# Vider la base documentaire : confirmation chiffrée
# ---------------------------------------------------------------------------


@pytest.fixture
def dialog_clicks(monkeypatch):
    """AppTest ne rejoue pas un dialogue (fragment) : un bouton du dialogue listé dans
    `labels` est considéré comme cliqué une fois, rappel on_click compris, comme en vrai."""
    state = SimpleNamespace(labels=[])
    real_button = streamlit.button

    def button(label, *args, **kwargs):
        clicked = real_button(label, *args, **kwargs)
        if label in state.labels and not kwargs.get("disabled"):
            state.labels.remove(label)
            if kwargs.get("on_click"):
                kwargs["on_click"](*kwargs.get("args", ()), **kwargs.get("kwargs", {}))
            return True
        return clicked

    monkeypatch.setattr(streamlit, "button", button)
    return state


@pytest.fixture
def base(monkeypatch):
    """Base documentaire simulée : 42 extraits de 3 documents ; vidages comptés."""
    from src.core.rag_engine import RAGEngine

    state = SimpleNamespace(count=42, sources=["a.pdf", "b.docx", "c.md"], cleared=0)

    def clear_database(self):
        state.cleared += 1
        state.count, state.sources = 0, []

    monkeypatch.setattr(
        RAGEngine,
        "get_stats",
        lambda self: {"count": state.count, "sources": list(state.sources), "collection": "t"},
    )
    monkeypatch.setattr(RAGEngine, "clear_database", clear_database)
    return state


def _open_manager(at):
    (button,) = [b for b in at.sidebar.button if b.label == "Gérer la base documentaire"]
    button.click().run()
    assert not at.exception, [e.value for e in at.exception]


CLEAR_WARNING = f"42{NBSP}extraits de 3{NBSP}documents seront supprimés."


def _clear_warnings(at) -> list[str]:
    """Avertissements du vidage (l'onglet d'évaluation a les siens, sur le juge)."""
    return [w.value for w in at.warning if "supprim" in w.value]


def test_clear_base_first_click_only_requests_confirmation(base, dialog_clicks, run_page):
    """Premier clic : rien n'est supprimé ; le drapeau est posé pour le run suivant du
    dialogue, qui affiche la confirmation (render_clear_section, testée ci-dessous)."""
    at = run_page(RAG_PAGE)
    dialog_clicks.labels = ["Vider la base documentaire"]
    _open_manager(at)
    assert base.cleared == 0
    assert at.session_state["rag_clear_pending"] is True
    assert not at.success


def test_clear_confirmation_reset_when_dialog_reopens(base, run_page):
    at = run_page(RAG_PAGE)
    at.session_state["rag_clear_pending"] = True
    _open_manager(at)
    assert not _clear_warnings(at)
    assert at.session_state["rag_clear_pending"] is False
    assert "Vider la base documentaire" in [b.label for b in at.button]


def test_clear_disabled_when_base_is_empty(base, run_page):
    base.count, base.sources = 0, []
    at = run_page(RAG_PAGE)
    _open_manager(at)
    (button,) = [b for b in at.button if b.label == "Vider la base documentaire"]
    assert button.disabled


def test_clear_success_shown_once_on_page(base, run_page):
    at = run_page(RAG_PAGE)
    at.session_state["rag_last_clear"] = "Base documentaire vidée : 1 extrait supprimé."
    at.run()
    assert [s.value for s in at.success] == ["Base documentaire vidée : 1 extrait supprimé."]
    at.run()
    assert not at.success


def _clear_section_script():
    """render_clear_section seule, avec un moteur simulé (session : stats, échec)."""
    import streamlit as st

    from src.app.rag_clear import CLEAR_PENDING_KEY, render_clear_section

    class Engine:
        def clear_database(self):
            st.session_state.cleared = st.session_state.get("cleared", 0) + 1
            if st.session_state.get("fail"):
                raise RuntimeError("collection verrouillée")

    stats = st.session_state.get("stats", {"count": 42, "sources": ["a.pdf", "b.docx", "c.md"]})
    render_clear_section(Engine(), stats, st.session_state.get(CLEAR_PENDING_KEY, False))


def _clear_section(**state):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_clear_section_script)
    at.session_state["rag_clear_pending"] = True
    at.session_state["rag_messages"] = [{"role": "assistant", "content": "Réponse", "sources": []}]
    for key, value in state.items():
        at.session_state[key] = value
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_clear_confirmation_names_the_consequence():
    at = _clear_section()
    assert _clear_warnings(at) == [CLEAR_WARNING]
    assert "**Vider la base documentaire ?**" in _markdowns(at)
    labels = [b.label for b in at.button]
    assert "Vider définitivement" in labels and "Annuler" in labels
    assert "Vider la base documentaire" not in labels
    assert "cleared" not in at.session_state


def test_clear_singular_agreement():
    at = _clear_section(stats={"count": 1, "sources": ["note.md"]})
    assert _clear_warnings(at) == [f"1{NBSP}extrait de 1{NBSP}document sera supprimé."]


def test_clear_cancel_deletes_nothing():
    at = _clear_section()
    _button(at, "Annuler").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "cleared" not in at.session_state
    assert at.session_state["rag_clear_pending"] is False
    assert len(at.session_state["rag_messages"]) == 1
    assert "rag_last_clear" not in at.session_state


def test_clear_confirmed_empties_base_and_answers():
    at = _clear_section()
    _button(at, "Vider définitivement").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["cleared"] == 1
    assert at.session_state["rag_messages"] == []
    assert at.session_state["rag_clear_pending"] is False
    assert at.session_state["rag_last_clear"] == (
        f"Base documentaire vidée : 42{NBSP}extraits de 3{NBSP}documents supprimés."
    )


def test_clear_failure_shows_error_and_resets():
    at = _clear_section(fail=True)
    _button(at, "Vider définitivement").click().run()
    assert not at.exception, [e.value for e in at.exception]
    (error,) = [e.value for e in at.error]
    assert error.startswith("La base documentaire n'a pas pu être vidée.")
    assert any("collection verrouillée" in c.value for c in at.code)
    assert at.session_state["rag_clear_pending"] is False
    assert len(at.session_state["rag_messages"]) == 1
    assert "rag_last_clear" not in at.session_state


# ---------------------------------------------------------------------------
# Deltas : jamais d'étiquette dans le delta d'un st.metric
# ---------------------------------------------------------------------------

# Formateurs de nombres : un delta passé par eux est une variation chiffrée.
NUMERIC_FORMATTERS = {"format_unit", "format_number", "format_percent", "format_gb"}


def _delta_values():
    for path in sorted((APP_DIR).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "delta":
                        yield path.relative_to(APP_DIR), keyword.value


def test_metric_deltas_are_numeric():
    """« Hybride », « API Active », « 100 % Local » ne vont jamais dans un delta."""
    deltas = list(_delta_values())
    assert deltas, "au moins un delta chiffré attendu (mémoire de l'Agent Lab)"
    for path, value in deltas:
        if isinstance(value, ast.Constant):
            assert isinstance(value.value, int | float) or value.value is None, (path, value)
            continue
        assert isinstance(value, ast.Call), (path, ast.unparse(value))
        name = getattr(value.func, "id", getattr(value.func, "attr", None))
        assert name in NUMERIC_FORMATTERS, (path, ast.unparse(value))
