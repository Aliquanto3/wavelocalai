"""
Tests unitaires pour l'interface Solo.
Usage: pytest tests/unit/test_solo_interface.py -v
"""

import pytest


class TestPromptLibrary:
    """Tests pour la bibliothèque de prompts."""

    def test_prompt_library_structure(self):
        """Test que PROMPT_LIBRARY a la bonne structure."""
        from src.app.tabs.agent.solo import PROMPT_LIBRARY

        assert isinstance(PROMPT_LIBRARY, dict)
        assert len(PROMPT_LIBRARY) > 0

        for _category, prompts in PROMPT_LIBRARY.items():
            assert isinstance(prompts, dict)

            for _prompt_name, prompt_data in prompts.items():
                assert "prompt" in prompt_data
                assert "required_tools" in prompt_data
                assert "description" in prompt_data

                assert isinstance(prompt_data["required_tools"], list)

    def test_prompt_library_required_tools_exist(self):
        """Test que les outils requis existent."""
        from src.app.tabs.agent.solo import PROMPT_LIBRARY
        from src.core.agent_tools import TOOLS_METADATA

        for _category, prompts in PROMPT_LIBRARY.items():
            for prompt_name, prompt_data in prompts.items():
                for tool in prompt_data["required_tools"]:
                    assert (
                        tool in TOOLS_METADATA
                    ), f"Outil {tool} requis par '{prompt_name}' n'existe pas"


class TestCrewPromptLibrary:
    """Tests pour la bibliothèque de workflows Crew."""

    def test_crew_library_structure(self):
        """Test structure de CREW_PROMPT_LIBRARY."""
        from src.app.tabs.agent.crew import CREW_PROMPT_LIBRARY

        assert isinstance(CREW_PROMPT_LIBRARY, dict)
        assert len(CREW_PROMPT_LIBRARY) > 0

        for _category, workflows in CREW_PROMPT_LIBRARY.items():
            for _workflow_name, workflow_data in workflows.items():
                assert "prompt" in workflow_data
                assert "description" in workflow_data
                assert "suggested_crew" in workflow_data

                # Chaque agent suggéré doit avoir la bonne structure
                for agent in workflow_data["suggested_crew"]:
                    assert "role" in agent
                    assert "goal" in agent
                    assert "backstory" in agent
                    assert "tools" in agent
                    assert isinstance(agent["tools"], list)

    def test_crew_library_tools_exist(self):
        """Test que tous les outils suggérés existent."""
        from src.app.tabs.agent.crew import CREW_PROMPT_LIBRARY
        from src.core.agent_tools import TOOLS_METADATA

        for _category, workflows in CREW_PROMPT_LIBRARY.items():
            for workflow_name, workflow_data in workflows.items():
                for agent in workflow_data["suggested_crew"]:
                    for tool in agent["tools"]:
                        assert (
                            tool in TOOLS_METADATA
                        ), f"Outil {tool} dans workflow '{workflow_name}' n'existe pas"
