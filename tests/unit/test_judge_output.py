"""Tests de la sortie des juges Ragas : balises Markdown retirées pour Claude."""

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
            ('{"a": 1}', '{"a": 1}'),
            ("texte libre", "texte libre"),
            ("", ""),
            ('avant ```json\n{"a": 1}\n``` après', 'avant ```json\n{"a": 1}\n``` après'),
            ('{"code": "```x```"}', '{"code": "```x```"}'),
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


def _result():
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    msg = AIMessage(content='```json\n{"a": 1}\n```')
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


class TestFenceStrippingWrapper:
    def test_sync_and_async(self):
        wrapper = make_fence_stripping_wrapper(_FakeWrapper)()
        sync = wrapper.generate_text()
        assert sync.generations[0][0].text == '{"a": 1}'
        assert sync.generations[0][0].message.content == '{"a": 1}'
        res = asyncio.run(wrapper.agenerate_text())
        assert res.generations[0][0].text == '{"a": 1}'


class TestJudgeBranching:
    def _run(self, judge_tag):
        engine_module = importlib.import_module("src.core.eval_engine")
        factory = MagicMock(side_effect=lambda cls: lambda llm, **kw: ("enveloppe", llm))
        with (
            patch.object(engine_module, "evaluate", side_effect=Exception("stop")),
            patch.object(engine_module, "LLMProvider") as provider,
            patch.object(engine_module, "RAGAS_AVAILABLE", True),
            patch.object(engine_module, "LangchainLLMWrapper", MagicMock()),
            patch.object(engine_module, "make_fence_stripping_wrapper", factory),
            patch.object(engine_module, "Dataset", MagicMock(), create=True),
        ):
            provider.get_langchain_model.return_value = "juge"
            engine_module.EvalEngine().evaluate_single_turn("Q", "A", ["C"], judge_tag, MagicMock())
        return factory

    def test_anthropic_judge_is_wrapped(self):
        assert self._run("claude-opus-5-5").call_count == 1

    @pytest.mark.parametrize("tag", ["qwen2.5:1.5b", "mistral-large-latest", "gpt-5"])
    def test_other_judges_are_not_wrapped(self, tag):
        assert self._run(tag).call_count == 0
