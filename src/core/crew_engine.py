from typing import Any

# On importe LLM natif de CrewAI
from crewai import LLM, Agent, Crew, Process, Task
from crewai.tools import BaseTool
from pydantic import PrivateAttr

from src.core.agent_tools import AVAILABLE_TOOLS
from src.core.config import MISTRAL_API_KEY


class LangChainAdapter(BaseTool):
    """
    Adaptateur universel pour rendre les outils LangChain compatibles avec CrewAI.
    Utilise PrivateAttr pour stocker la fonction callable sans perturber Pydantic v2.
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
        Gère les préfixes obligatoires 'ollama/' et 'mistral/'.
        """
        # 1. Routing Cloud (Mistral)
        if model_tag.startswith("mistral-") and not model_tag.startswith("mistral:"):
            if not MISTRAL_API_KEY:
                raise ValueError("Clé API Mistral manquante.")
            # LiteLLM attend 'mistral/nom-du-model'
            return LLM(
                model=f"mistral/{model_tag}", api_key=MISTRAL_API_KEY, temperature=temperature
            )

        # 2. Routing Local (Ollama)
        # LiteLLM attend 'ollama/nom-du-tag'
        return LLM(
            model=f"ollama/{model_tag}", base_url="http://localhost:11434", temperature=temperature
        )

    @staticmethod
    def create_audit_crew(model_tag: str):
        """
        Crée une équipe d'audit standard (Chercheur + Analyste).
        """
        # 1. Instanciation du Cerveau (Natif CrewAI/LiteLLM)
        llm = CrewFactory._get_native_llm(model_tag, temperature=0.1)

        # 2. Conversion des outils
        crew_tools = CrewFactory._map_tools(AVAILABLE_TOOLS)

        # 3. Définition des Agents
        researcher = Agent(
            role="Senior Data Researcher",
            goal="Trouver des informations factuelles précises dans la base de connaissance.",
            backstory="""Tu es un enquêteur méticuleux. Tu ne te bases que sur des faits vérifiés.
            Tu utilises les outils de recherche à ta disposition pour répondre à la mission.""",
            verbose=True,
            allow_delegation=False,
            tools=crew_tools,
            llm=llm,
        )

        analyst = Agent(
            role="Briefing Manager",
            goal="Synthétiser les informations pour produire un rapport exécutif.",
            backstory="""Tu es expert en communication. Tu transformes les données brutes
            du chercheur en un rapport clair, concis et professionnel en Français.""",
            verbose=True,
            allow_delegation=False,
            llm=llm,
        )

        # 4. Définition des Tâches
        task_research = Task(
            description="""
            Recherche des informations sur le sujet : '{topic}'.
            Utilise l'outil 'search_wavestone_internal' si pertinent.
            Cherche des chiffres, des dates et des faits concrets.
            """,
            expected_output="Une liste des faits trouvés.",
            agent=researcher,
        )

        task_write = Task(
            description="""
            Rédige une note de synthèse à partir des recherches précédentes.
            Le ton doit être professionnel.
            """,
            expected_output="Un paragraphe de synthèse en Markdown.",
            agent=analyst,
        )

        # 5. Assemblage de l'Équipe
        crew = Crew(
            agents=[researcher, analyst],
            tasks=[task_research, task_write],
            process=Process.sequential,
            verbose=True,
        )

        return crew
