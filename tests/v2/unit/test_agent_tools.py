"""Registre des outils d'agent (story 6.1) : identifiants, doublons, schéma neutre."""

from __future__ import annotations

import pytest

from wavelocalai.agents.tools import AgentTool, ToolRegistry
from wavelocalai.errors import AppError


async def _noop(arguments):
    return "ok"


def test_a_tool_id_must_be_accepted_by_the_four_providers():
    for bad in ("", "Calc", "1calc", "a-b", "a b", "é", "x" * 65):
        with pytest.raises(ValueError):
            AgentTool(bad, "d", _noop)
    assert AgentTool("calc_2", "d", _noop).id == "calc_2"


def test_the_spec_is_the_neutral_schema_of_the_port():
    tool = AgentTool("calc", "Calcule.", _noop, parameters={"type": "object", "properties": {}})
    assert tool.spec() == {
        "name": "calc",
        "description": "Calcule.",
        "parameters": {"type": "object", "properties": {}},
    }


def test_the_registry_refuses_duplicates_and_resolves_ids_in_order():
    registry = ToolRegistry([AgentTool("a", "A", _noop), AgentTool("b", "B", _noop)])
    with pytest.raises(ValueError):
        registry.register(AgentTool("a", "encore", _noop))
    assert [t.id for t in registry.get(["b", "a"])] == ["b", "a"]
    assert [t.id for t in registry.all()] == ["a", "b"] and registry.get([]) == []


@pytest.mark.parametrize("ids", [["inconnu"], ["a", "a"]])
def test_unknown_and_repeated_ids_are_invalid_requests(ids):
    registry = ToolRegistry([AgentTool("a", "A", _noop)])
    with pytest.raises(AppError) as caught:
        registry.get(ids)
    assert caught.value.code == "invalid_request"
