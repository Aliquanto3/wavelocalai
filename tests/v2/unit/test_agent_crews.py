"""Bibliothèque d'équipes d'agents (story 6.5) : fichier versionné, validation, modification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wavelocalai.agents.crews import (
    MAX_AGENTS,
    CrewAgent,
    CrewLibrary,
    agent_from,
    load_crews,
    task_for,
)
from wavelocalai.agents.tools import AgentTool, ToolRegistry
from wavelocalai.errors import AppError
from wavelocalai.store.preferences import InMemoryPreferenceStore

REPO_FILE = Path(__file__).resolve().parents[3] / "config" / "agent_crews.json"


class StubModels:
    """Registre minimal : `local:1b` est local, `cloud:big` hébergé, `embed:1b` n'est pas un chat."""

    def resolve(self, tag: str, allow_cloud: bool = False):
        if tag == "cloud:big":
            if not allow_cloud:
                raise AppError("cloud_not_allowed", tag=tag)
            return tag
        if tag == "embed:1b":
            raise AppError("model_not_chat", tag=tag)
        if tag != "local:1b":
            raise AppError("model_not_found", tag=tag)
        return tag


def tools() -> ToolRegistry:
    async def run(arguments):
        return "ok"

    return ToolRegistry(
        [
            AgentTool("calculator", "Calcule.", run),
            AgentTool("broken", "Cassé.", run, available=False, reason="Module absent"),
        ]
    )


def library(tmp_path, crews=None, registry=None) -> CrewLibrary:
    path = tmp_path / "crews.json"
    path.write_text(
        json.dumps(
            {
                "crews": crews
                or {"un": {"label": "Un", "agents": [{"role": "A", "goal": "g", "tools": []}]}}
            }
        ),
        encoding="utf-8",
    )
    return CrewLibrary(path, InMemoryPreferenceStore(), registry or tools(), StubModels())


def fields(lib: CrewLibrary, agents, **kw) -> dict[str, str]:
    return {e["field"]: e["message"] for e in lib.validate(agents, **kw)}


def test_the_versioned_file_holds_the_v1_crews_and_each_is_valid(tmp_path):
    from wavelocalai.agents.tools import Workspace, build_registry
    from wavelocalai.config import load_settings

    settings = load_settings(
        toml_path=tmp_path / "x.toml", env_file=tmp_path / "x.env", environ={}, overrides={}
    )
    registry = build_registry(settings, Workspace(tmp_path / "work"))
    crews = load_crews(REPO_FILE)
    assert list(crews) == ["etude_concurrentielle", "audit_des_mesures", "comparaison_carbone"]
    known = {tool.id for tool in registry.all()}
    for crew in crews.values():
        assert 1 <= len(crew.agents) <= MAX_AGENTS and crew.topic and crew.label
        assert all(set(agent.tools) <= known for agent in crew.agents), crew.id
        assert all(agent.goal and agent.backstory for agent in crew.agents)


def test_an_unreadable_file_gives_an_empty_library(tmp_path):
    assert load_crews(tmp_path / "absent.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{pas du json", encoding="utf-8")
    assert load_crews(bad) == {}
    bad.write_text('{"crews": []}', encoding="utf-8")
    assert load_crews(bad) == {}


def test_agent_from_reads_what_it_is_given_without_fixing_it():
    assert agent_from("x") is None
    agent = agent_from({"role": " R ", "goal": "g", "tools": ["a"], "model": "", "backstory": None})
    assert agent == CrewAgent("R", "g", "Tu es un expert dans ton domaine.", ("a",), None)


def test_the_task_of_an_agent_is_derived_from_its_goal():
    task = task_for(CrewAgent("Chercheur", "Trouver", tools=("calculator",)), "Le sujet")
    assert task["agent"] == "Chercheur"
    assert "Le sujet" in task["description"] and "Trouver" in task["description"]
    assert "outils" in task["description"] and "Chercheur" in task["expected_output"]
    assert "outils" not in task_for(CrewAgent("R", "g"))["description"]


def test_validation_rejects_each_fault_with_one_message_per_field(tmp_path):
    lib = library(tmp_path)
    assert fields(lib, []) == {"agents": "Ajoutez au moins un agent."}
    six = [CrewAgent(f"R{i}", "g") for i in range(MAX_AGENTS + 1)]
    assert "5 agents au plus" in fields(lib, six)["agents"]
    assert lib.validate([CrewAgent(f"R{i}", "g") for i in range(MAX_AGENTS)]) == []

    got = fields(
        lib,
        [
            CrewAgent("", "", tools=("inconnu",)),
            CrewAgent("B", "g", tools=("broken",), model="nope:1b"),
            CrewAgent("C", "g", tools=("calculator", "calculator")),
            CrewAgent("b", "g"),
            CrewAgent("D", "g", model="embed:1b"),
            CrewAgent("E" * 61, "g" * 301, "b" * 501),
        ],
    )
    assert set(got) == {  # six agents : le plafond s’ajoute
        "agents", "agents[0].role", "agents[0].goal", "agents[0].tools",
        "agents[1].tools", "agents[1].model", "agents[2].tools", "agents[3].role",
        "agents[4].model", "agents[5].role", "agents[5].goal", "agents[5].backstory",
    }  # fmt: skip
    assert "inconnu" in got["agents[0].tools"] and "indisponible" in got["agents[1].tools"]
    assert "Module absent" in got["agents[1].tools"]
    assert "déjà pris" in got["agents[3].role"]


def test_a_cloud_model_needs_allow_cloud(tmp_path):
    lib = library(tmp_path)
    agents = [CrewAgent("A", "g", model="cloud:big")]
    assert "autorisez le cloud" in fields(lib, agents)["agents[0].model"]
    assert lib.validate(agents, allow_cloud=True) == []
    assert lib.validate([CrewAgent("A", "g", model="local:1b")]) == []


def test_check_raises_invalid_request_with_every_message(tmp_path):
    lib = library(tmp_path)
    with pytest.raises(AppError) as caught:
        lib.check([CrewAgent("", "")])
    assert caught.value.code == "invalid_request"
    assert "agents[0].role" in str(caught.value) and "agents[0].goal" in str(caught.value)


def test_a_modification_overrides_the_origin_and_reset_restores_it(tmp_path):
    lib = library(tmp_path)
    origin = lib.effective_agents("un")
    assert lib.view("un")["modified"] is False
    lib.save("un", [CrewAgent("Nouveau", "autre", tools=("calculator",))])
    assert [a.role for a in lib.effective_agents("un")] == ["Nouveau"]
    assert lib.view("un")["modified"] is True
    lib.reset("un")
    assert lib.effective_agents("un") == origin and lib.view("un")["modified"] is False
    lib.reset("un")  # sans effet


def test_a_stored_modification_that_is_not_readable_falls_back_to_the_origin(tmp_path):
    lib = library(tmp_path)
    lib._preferences.put("agents.crews", {"un": [{"role": "ok"}, "pas un agent"]})
    assert [a.role for a in lib.effective_agents("un")] == ["A"]
    lib._preferences.put("agents.crews", "n'importe quoi")
    assert [a.role for a in lib.effective_agents("un")] == ["A"]


def test_an_unknown_crew_is_not_found(tmp_path):
    lib = library(tmp_path)
    for call in (lib.origin, lib.effective_agents, lib.reset):
        with pytest.raises(AppError) as caught:
            call("zzz")
        assert caught.value.code == "not_found"
    with pytest.raises(AppError):
        lib.save("zzz", [CrewAgent("A", "g")])
