"""Tests de la sortie des juges Ragas : bloc JSON extrait pour Claude, sans temperature."""

import asyncio
import importlib
from unittest.mock import MagicMock, patch

import pytest

from src.core.judge_output import make_fence_stripping_wrapper, strip_markdown_fences


class TestStripMarkdownFences:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ('```json\n{"a": 1}\n```', '{"a": 1}'),
            ('```\n{"a": 1}\n```', '{"a": 1}'),
            ('  \n```JSON\n{"a": [1,\n 2]}\n```  \n', '{"a": [1,\n 2]}'),
            ('```json\r\n{"a": 1}\r\n```', '{"a": 1}'),
            ('```json\n{"a": 1}```', '{"a": 1}'),
            # Préambule et texte après le bloc : seul le contenu du bloc reste.
            ('Voici le JSON :\n```json\n{"a": 1}\n```', '{"a": 1}'),
            ('Voici :\n\n```json\n{"a": 1}\n```\nJ\'espère que cela aide.', '{"a": 1}'),
            # Plusieurs blocs : le premier, sans balise résiduelle.
            ('```json\n{"a": 1}\n```\n```json\n{"b": 2}\n```', '{"a": 1}'),
            # Contenu intérieur jamais altéré, y compris des ``` dans une chaîne.
            ('```json\n{"code": "x```y", "t": "  a  "}\n```', '{"code": "x```y", "t": "  a  "}'),
            # Sans bloc complet : texte inchangé.
            ('{"a": 1}', '{"a": 1}'),
            ("texte libre", "texte libre"),
            ("", ""),
            ('{"code": "```x```"}', '{"code": "```x```"}'),
            ('{\n  "code": "```json x ```"\n}', '{\n  "code": "```json x ```"\n}'),
            ('avant ```json {"a": 1} ``` après', 'avant ```json {"a": 1} ``` après'),
            ('```json\n{"a": 1', '```json\n{"a": 1'),
        ],
    )
    def test_cases(self, raw, expected):
        assert strip_markdown_fences(raw) == expected


class _FakeWrapper:
    """Remplace LangchainLLMWrapper : renvoie un LLMResult figé."""

    def __init__(self, llm=None, **kwargs):
        self.llm = llm

    def generate_text(self, *args, **kwargs):
        return _result()

    async def agenerate_text(self, *args, **kwargs):
        return _result()


def _result(prompts=None):
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    def gen():
        return [ChatGeneration(message=AIMessage(content='Voici :\n```json\n{"a": 1}\n```'))]

    return LLMResult(generations=[gen() for _ in (prompts or [None])])


class TestFenceStrippingWrapper:
    def test_sync_and_async(self):
        wrapper = make_fence_stripping_wrapper(_FakeWrapper)()
        sync = wrapper.generate_text()
        assert sync.generations[0][0].text == '{"a": 1}'
        assert sync.generations[0][0].message.content == '{"a": 1}'
        res = asyncio.run(wrapper.agenerate_text())
        assert res.generations[0][0].text == '{"a": 1}'


class _FakeChatModel:
    """Modèle LangChain minimal qui note la `temperature` vue à chaque appel."""

    def __init__(self):
        self.temperature = None
        self.seen = []

    def generate_prompt(self, prompts, stop=None, callbacks=None, **kwargs):
        self.seen.append(self.temperature)
        return _result(prompts)

    async def agenerate_prompt(self, prompts, stop=None, callbacks=None, **kwargs):
        self.seen.append(self.temperature)
        return _result(prompts)


class TestRealRagasWrapperTemperature:
    """Avec le vrai `LangchainLLMWrapper` : aucune `temperature` n'atteint le modèle."""

    @pytest.fixture
    def wrapper_cls(self):
        base = pytest.importorskip("ragas.llms.base")
        return make_fence_stripping_wrapper(base.LangchainLLMWrapper)

    def test_sync_and_async_never_set_temperature(self, wrapper_cls):
        from langchain_core.prompt_values import StringPromptValue

        llm = _FakeChatModel()
        wrapper = wrapper_cls(llm, bypass_temperature=True)
        prompt = StringPromptValue(text="q")
        res = wrapper.generate_text(prompt, n=3)
        ares = asyncio.run(wrapper.agenerate_text(prompt, n=3))
        assert llm.seen == [None, None]
        assert wrapper.langchain_llm is llm
        for out in (res, ares):
            assert [g.text for g in out.generations[0]] == ['{"a": 1}'] * 3

    def test_sync_sets_temperature_without_bypass(self, wrapper_cls):
        from langchain_core.prompt_values import StringPromptValue

        llm = _FakeChatModel()
        wrapper_cls(llm).generate_text(StringPromptValue(text="q"))
        assert llm.seen == [0.01]


class TestJudgeBranching:
    def _run(self, judge_tag):
        engine_module = importlib.import_module("src.core.eval_engine")
        wrapper_cls = MagicMock(name="FenceStrippingLLMWrapper")
        factory = MagicMock(return_value=wrapper_cls)
        base_wrapper = MagicMock(name="LangchainLLMWrapper")
        evaluate = MagicMock(side_effect=Exception("stop"))
        with (
            patch.object(engine_module, "evaluate", evaluate),
            patch.object(engine_module, "LLMProvider") as provider,
            patch.object(engine_module, "RAGAS_AVAILABLE", True),
            patch.object(engine_module, "LangchainLLMWrapper", base_wrapper),
            patch.object(engine_module, "make_fence_stripping_wrapper", factory),
            patch.object(engine_module, "Dataset", MagicMock(), create=True),
        ):
            provider.get_langchain_model.return_value = "juge"
            engine_module.EvalEngine().evaluate_single_turn("Q", "A", ["C"], judge_tag, MagicMock())
        return factory, base_wrapper, wrapper_cls, evaluate

    def test_anthropic_judge_is_wrapped(self):
        factory, base_wrapper, wrapper_cls, evaluate = self._run("claude-opus-5-5")
        factory.assert_called_once_with(base_wrapper)
        wrapper_cls.assert_called_once_with("juge", bypass_temperature=True)
        assert evaluate.call_args.kwargs["llm"] is wrapper_cls.return_value
        for metric in evaluate.call_args.kwargs["metrics"]:
            assert metric.llm is wrapper_cls.return_value

    @pytest.mark.parametrize("tag", ["qwen2.5:1.5b", "mistral-large-latest", "gpt-5"])
    def test_other_judges_are_not_wrapped(self, tag):
        factory, _, _, evaluate = self._run(tag)
        assert factory.call_count == 0
        assert evaluate.call_args.kwargs["llm"] == "juge"
