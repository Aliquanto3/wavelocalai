"""
Historique envoyé au moteur de l'agent et tokens de la réponse finale (story 9), sans Ollama :
le graphe LangGraph est remplacé par un double qui enregistre les messages reçus.
Usage: python -m pytest tests/unit/test_agent_history.py -v
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.core.agent_engine import AgentEngine, history_to_messages, output_token_count

Q1 = {"role": "user", "content": "Quelle heure est-il ?"}
TOOL_LOG = {
    "role": "assistant",
    "type": "tool_log",
    "tool": "get_current_time",
    "args": {},
    "content": "Résultat de l'outil :\n09:15",
    "done": True,
}
R1 = {"role": "assistant", "content": "Il est 09:15.", "thought": "L'outil donne l'heure."}


def _pairs(messages):
    return [(type(m).__name__, m.content) for m in messages]


class FakeGraph:
    """Double du graphe ReAct : enregistre les messages d'entrée, émet `states`."""

    def __init__(self, states):
        self.states = states
        self.inputs = None

    def stream(self, inputs, stream_mode="values"):
        self.inputs = inputs["messages"]
        for messages in self.states:
            yield {"messages": messages}


def _engine(states) -> AgentEngine:
    engine = AgentEngine.__new__(AgentEngine)
    engine.model_name = "qwen2.5:1.5b"
    engine.agent_executor = FakeGraph(states)
    return engine


def test_history_keeps_only_real_turns():
    """Q1 et R1 seulement : ni journal d'outil, ni raisonnement, ni métadonnées."""
    messages = history_to_messages([Q1, TOOL_LOG, R1])
    assert _pairs(messages) == [("HumanMessage", Q1["content"]), ("AIMessage", R1["content"])]


def test_history_drops_blocked_and_failed_turns():
    """Question bloquée, tour en erreur et question restée sans réponse : jamais envoyés."""
    blocked = {"role": "user", "content": "Question bloquée", "blocked": True}
    failed_q = {"role": "user", "content": "Question en échec"}
    failure = {"role": "assistant", "content": "Erreur critique de l'agent : x", "error": True}
    unanswered = {"role": "user", "content": "Flux interrompu"}
    history = [blocked, Q1, R1, failed_q, failure, unanswered]
    assert _pairs(history_to_messages(history)) == [
        ("HumanMessage", Q1["content"]),
        ("AIMessage", R1["content"]),
    ]


def test_history_drops_current_question_already_in_history():
    """Question courante déjà ajoutée à l'historique : ignorée, envoyée une seule fois."""
    assert _pairs(history_to_messages([Q1, R1, {"role": "user", "content": "Q2"}])) == [
        ("HumanMessage", Q1["content"]),
        ("AIMessage", R1["content"]),
    ]


def test_run_stream_sends_each_question_once():
    """2ᵉ question après une réponse avec outils : Q1, R1 puis Q2 une seule fois."""
    engine = _engine([[AIMessage(content="Réponse 2")]])
    events = list(engine.run_stream("Q2", [Q1, TOOL_LOG, R1]))
    assert events[-1]["type"] == "final_answer"

    sent = engine.agent_executor.inputs
    assert isinstance(sent[0], SystemMessage)
    assert _pairs(sent[1:]) == [
        ("HumanMessage", Q1["content"]),
        ("AIMessage", R1["content"]),
        ("HumanMessage", "Q2"),
    ]
    assert [m.content for m in sent].count("Q2") == 1


def test_final_answer_counts_output_tokens_of_the_turn():
    """Tokens de sortie du tour : usage_metadata de chaque message du modèle (appel d'outil
    compris), additionnés dans final_answer."""
    call = AIMessage(
        content="",
        tool_calls=[{"name": "calculator", "args": {"expression": "2+2"}, "id": "c1"}],
        usage_metadata={"input_tokens": 50, "output_tokens": 12, "total_tokens": 62},
    )
    result = ToolMessage(content="4", tool_call_id="c1")
    answer = AIMessage(
        content="2 + 2 = 4.",
        usage_metadata={"input_tokens": 70, "output_tokens": 30, "total_tokens": 100},
    )
    engine = _engine([[HumanMessage("Q"), call], [call, result], [call, result, answer]])
    events = list(engine.run_stream("Combien font 2 + 2 ?"))

    assert [e["type"] for e in events] == ["tool_call", "tool_result", "final_answer"]
    assert events[-1]["output_tokens"] == 42


def test_output_tokens_estimated_without_usage():
    """Sans usage_metadata : estimation par la longueur, comme les fournisseurs."""
    assert output_token_count(AIMessage(content="x" * 40)) == 10
    assert output_token_count(AIMessage(content="x" * 40, usage_metadata=None)) == 10
    usage = {"input_tokens": 1, "output_tokens": 0, "total_tokens": 1}
    assert output_token_count(AIMessage(content="x" * 40, usage_metadata=usage)) == 0


def test_output_tokens_estimate_counts_tool_calls():
    """Appel d'outil sans usage_metadata (contenu vide) : le JSON des appels compte."""
    call = AIMessage(
        content="",
        tool_calls=[{"name": "calculator", "args": {"expression": "2+2"}, "id": "c1"}],
    )
    expected = len(json.dumps([{"name": "calculator", "args": {"expression": "2+2"}}])) // 4
    assert expected > 0
    assert output_token_count(call) == expected


def test_output_tokens_estimate_joins_text_blocks_only():
    """Contenu en liste de blocs : seuls les blocs texte comptent, jamais le repr Python."""
    blocks = [
        {"type": "text", "text": "x" * 20},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 400}},
        "y" * 20,
    ]
    assert output_token_count(AIMessage(content=blocks)) == 10


def test_error_event_is_yielded():
    class Broken:
        def stream(self, inputs, stream_mode="values"):
            raise RuntimeError("graphe cassé")
            yield  # pragma: no cover

    engine = _engine([])
    engine.agent_executor = Broken()
    (event,) = list(engine.run_stream("Q"))
    assert event["type"] == "error" and "graphe cassé" in event["content"]


def test_groq_tag_uses_provider_model_not_ollama():
    """Tag Groq (story 16) : modèle LangChain du provider Groq, jamais ChatOllama."""
    from unittest.mock import patch

    engine = object.__new__(AgentEngine)
    with (
        patch("src.core.agent_engine.LLMProvider.get_langchain_model") as get_model,
        patch("src.core.agent_engine.ChatOllama") as chat_ollama,
    ):
        llm = engine._initialize_llm("openai/gpt-oss-120b")
    get_model.assert_called_once_with("openai/gpt-oss-120b", temperature=0.0)
    assert llm is get_model.return_value
    chat_ollama.assert_not_called()
