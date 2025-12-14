from typing import Any

# On importe LLM natif de CrewAI
from crewai import LLM, Agent, Crew, Process, Task
from crewai.tools import BaseTool
from pydantic import PrivateAttr

# Import des outils Wavestone
from src.core.agent_tools import AVAILABLE_TOOLS
from src.core.config import MISTRAL_API_KEY


class LangChainAdapter(BaseTool):
    """
    Adaptateur universel pour rendre les outils LangChain compatibles avec CrewAI.
    """

    name: str = ""
    description: str = ""
    _func: Any = PrivateAttr()

    def __init__(self, tool_instance, **data):
        super().__init__(**data)
        self.name = tool_instance.name
        self.description = tool_instance.description
        self._func = tool_instance.run

    def _run(self, *args, **kwargs):
        """Exécution déléguée à l'outil LangChain d'origine."""
        try:
            # Gestion basique des arguments string vs dict
            if len(args) == 1 and isinstance(args[0], str) and not kwargs:
                return self._func(args[0])
            return self._func(*args, **kwargs)
        except Exception as e:
            return f"Erreur lors de l'exécution de l'outil {self.name}: {str(e)}"


class CrewFactory:
    """
    Usine à équipes d'agents (Crews).
    """

    @staticmethod
    def _map_tools(langchain_tools):
        """Convertit les outils LangChain en outils CrewAI via l'adaptateur."""
        return [LangChainAdapter(t) for t in langchain_tools]

    @staticmethod
    def _get_native_llm(model_tag: str, temperature: float = 0.1):
        """
        Configure le LLM natif CrewAI (via LiteLLM).
        """
        # 1. Routing Cloud (Mistral)
        if model_tag.startswith("mistral-") and not model_tag.startswith("mistral:"):
            if not MISTRAL_API_KEY:
                raise ValueError("Clé API Mistral manquante.")
            return LLM(
                model=f"mistral/{model_tag}", api_key=MISTRAL_API_KEY, temperature=temperature
            )

        # 2. Routing Local (Ollama)
        return LLM(
            model=f"ollama/{model_tag}", base_url="http://localhost:11434", temperature=temperature
        )

    @staticmethod
    def create_custom_crew(agents_config: list[dict[str, str]], topic: str):
        """
        Crée une équipe dynamique basée sur une configuration utilisateur.

        Args:
            agents_config: Liste de dicts {'role', 'goal', 'backstory', 'model_tag'}
            topic: Le sujet global de la mission
        """
        created_agents = []
        created_tasks = []

        # On prépare les outils une seule fois pour tous les agents
        # ✅ C'est ici que l'on donne la capacité "Tools" aux agents
        common_tools = CrewFactory._map_tools(AVAILABLE_TOOLS)

        # 1. Création des Agents
        for agent_conf in agents_config:
            # Instanciation du LLM spécifique à cet agent
            llm = CrewFactory._get_native_llm(agent_conf["model_tag"], temperature=0.7)

            new_agent = Agent(
                role=agent_conf["role"],
                goal=agent_conf["goal"],
                backstory=agent_conf.get("backstory", "Tu es un expert dans ton domaine."),
                verbose=True,
                allow_delegation=True,  # Permet aux agents de se parler entre eux
                llm=llm,
                tools=common_tools,  # ✅ Injection des outils (Calc, Time, Search)
            )
            created_agents.append(new_agent)

            # 2. Création d'une tâche générique liée au rôle
            task = Task(
                description=f"""
                Analyse le sujet suivant : '{topic}'.
                Ton objectif spécifique est : {agent_conf['goal']}.
                Utilise les outils à ta disposition si nécessaire (recherche, calcul, heure).
                Produis une analyse détaillée selon ton point de vue d'expert.
                """,
                expected_output=f"Un rapport complet rédigé par le {agent_conf['role']}.",
                agent=new_agent,
            )
            created_tasks.append(task)

        # 3. Assemblage de l'équipe
        crew = Crew(
            agents=created_agents,
            tasks=created_tasks,
            process=Process.sequential,
            verbose=True,
        )

        return crew

    @staticmethod
    def create_audit_crew(model_tag: str):
        """Legacy : Crée une équipe d'audit standard."""
        # On délègue à la nouvelle méthode générique pour éviter la duplication
        config = [
            {
                "role": "Senior Data Researcher",
                "goal": "Trouver des faits précis.",
                "backstory": "Tu es factuel et méticuleux.",
                "model_tag": model_tag,
            },
            {
                "role": "Briefing Manager",
                "goal": "Synthétiser les informations.",
                "backstory": "Tu écris des rapports parfaits.",
                "model_tag": model_tag,
            },
        ]
        return CrewFactory.create_custom_crew(config, topic="Mission par défaut")
