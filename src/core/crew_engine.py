"""
Crew Engine - Factory pour créer des équipes d'agents CrewAI.

Modifications principales :
- Support de la sélection d'outils par agent
- Chaque agent peut avoir sa propre liste d'outils
"""

from typing import Any

# On importe LLM natif de CrewAI
from crewai import LLM, Agent, Crew, Process, Task
from crewai.tools import BaseTool
from pydantic import PrivateAttr

# Import des outils Wavestone
from src.core.agent_tools import CREW_TOOL_OVERRIDES, get_tools_by_names
from src.core.config import MISTRAL_API_KEY
from src.core.model_detector import is_api_model
from src.core.providers import anthropic_provider, groq_provider, openai_provider
from src.core.providers.provider_factory import prefixed_cloud_provider


class LangChainAdapter(BaseTool):
    """
    Adaptateur universel pour rendre les outils LangChain compatibles avec CrewAI.
    """

    name: str = ""
    description: str = ""
    _func: Any = PrivateAttr()
    _arg_names: list = PrivateAttr(default_factory=list)

    def __init__(self, tool_instance, **data):
        super().__init__(**data)
        self.name = tool_instance.name
        self.description = tool_instance.description
        self._func = tool_instance.run
        self._arg_names = list(getattr(tool_instance, "args", {}) or {})

    def _run(self, *args, **kwargs):
        """Exécution déléguée à l'outil LangChain d'origine."""
        try:
            # Gestion basique des arguments string vs dict
            if len(args) == 1 and isinstance(args[0], str) and not kwargs:
                return self._func(args[0])
            # Arguments nommés (appel de CrewAI), éventuellement mêlés à des arguments
            # positionnels (dans l'ordre des paramètres de l'outil) ou à un dict d'arguments :
            # BaseTool.run attend un seul dict d'entrée.
            if kwargs or len(args) > 1:
                if len(args) == 1 and isinstance(args[0], dict):
                    tool_input = dict(args[0])
                else:
                    tool_input = dict(zip(self._arg_names, args, strict=False))
                tool_input.update(kwargs)
                return self._func(tool_input)
            return self._func(*args)
        except Exception as e:
            return f"Erreur lors de l'exécution de l'outil {self.name}: {str(e)}"


class CrewFactory:
    """
    Usine à équipes d'agents (Crews).
    """

    @staticmethod
    def _map_tools(langchain_tools):
        """Convertit les outils LangChain en outils CrewAI via l'adaptateur. L'outil d'email
        est remplacé par sa variante d'équipe : brouillon complet, aucun envoi possible."""
        return [LangChainAdapter(CREW_TOOL_OVERRIDES.get(t.name, t)) for t in langchain_tools]

    @staticmethod
    def _get_native_llm(model_tag: str, temperature: float = 0.1):
        """
        Configure le LLM de CrewAI pour un tag, dans l'ordre de la fabrique de providers :
        Groq, puis OpenAI et Anthropic (préfixe), puis Mistral (catalogue), puis Ollama.
        Groq, OpenAI et Anthropic passent par les fournisseurs natifs de CrewAI, sans LiteLLM.
        """
        # 1. Routing Cloud (Groq) : fournisseur OpenAI natif de CrewAI.
        # `custom_openai` retire un préfixe « openai/ » : il est doublé pour que Groq reçoive
        # le tag exact (`openai/gpt-oss-120b`, `llama-3.3-70b-versatile`).
        if groq_provider.is_groq_model(model_tag):
            if not groq_provider.GROQ_API_KEY:
                raise ValueError("Clé API Groq manquante.")
            return LLM(
                model=f"openai/{model_tag}",
                custom_openai=True,
                base_url=groq_provider.GROQ_BASE_URL,
                api_key=groq_provider.GROQ_API_KEY,
                temperature=temperature,
            )

        # 2. Routing Cloud (OpenAI, Anthropic) : nom sans variante préfixé `gpt-`, `o1-` ou
        # `claude-` (`gpt-oss:20b` reste local). Fournisseurs natifs de CrewAI.
        prefixed = prefixed_cloud_provider(model_tag)
        if prefixed == "openai":
            if not openai_provider.OPENAI_API_KEY:
                raise ValueError("Clé API OpenAI manquante.")
            return LLM(
                model=f"openai/{model_tag}",
                api_key=openai_provider.OPENAI_API_KEY,
                temperature=temperature,
            )
        if prefixed == "anthropic":
            if not anthropic_provider.ANTHROPIC_API_KEY:
                raise ValueError("Clé API Anthropic manquante.")
            return LLM(
                model=f"anthropic/{model_tag}",
                api_key=anthropic_provider.ANTHROPIC_API_KEY,
                temperature=temperature,
            )

        # 3. Routing Cloud (Mistral)
        if is_api_model(model_tag):
            if not MISTRAL_API_KEY:
                raise ValueError("Clé API Mistral manquante.")
            return LLM(
                model=f"mistral/{model_tag}", api_key=MISTRAL_API_KEY, temperature=temperature
            )

        # 4. Routing Local (Ollama)
        return LLM(
            model=f"ollama/{model_tag}", base_url="http://localhost:11434", temperature=temperature
        )

    @staticmethod
    def create_custom_crew(agents_config: list[dict[str, Any]], topic: str):
        """
        Crée une équipe dynamique basée sur une configuration utilisateur.

        Args:
            agents_config: Liste de dicts avec clés:
                - 'role': str
                - 'goal': str
                - 'backstory': str
                - 'model_tag': str
                - 'tools': list[str] (NOUVEAU - optionnel)
            topic: Le sujet global de la mission

        Exemple:
            agents_config = [
                {
                    "role": "Analyste",
                    "goal": "Analyser les données",
                    "backstory": "Expert en data",
                    "model_tag": "qwen2.5:1.5b",
                    "tools": ["calculator", "analyze_csv", "system_monitor"]
                },
                {
                    "role": "Rédacteur",
                    "goal": "Rédiger le rapport",
                    "backstory": "Expert en communication",
                    "model_tag": "qwen2.5:3b",
                    "tools": ["generate_document", "generate_markdown_report"]
                }
            ]
        """
        created_agents = []
        created_tasks = []

        # 1. Création des Agents
        for agent_conf in agents_config:
            # Instanciation du LLM spécifique à cet agent
            llm = CrewFactory._get_native_llm(agent_conf["model_tag"], temperature=0.7)

            # Sélection des outils pour cet agent
            if "tools" in agent_conf and agent_conf["tools"]:
                # L'agent a une liste d'outils spécifique
                selected_tools = get_tools_by_names(agent_conf["tools"])
                agent_tools = CrewFactory._map_tools(selected_tools)
            else:
                # Aucun outil par défaut
                agent_tools = []

            new_agent = Agent(
                role=agent_conf["role"],
                goal=agent_conf["goal"],
                backstory=agent_conf.get("backstory", "Tu es un expert dans ton domaine."),
                verbose=True,
                allow_delegation=True,  # Permet aux agents de se parler entre eux
                llm=llm,
                tools=agent_tools,  # Outils spécifiques à cet agent
            )
            created_agents.append(new_agent)

            # 2. Création d'une tâche générique liée au rôle
            task = Task(
                description=f"""
                Analyse le sujet suivant : '{topic}'.
                Ton objectif spécifique est : {agent_conf['goal']}.
                {"Utilise les outils à ta disposition si nécessaire." if agent_tools else ""}
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
        """
        Legacy : Crée une équipe d'audit standard avec tous les outils.
        Maintenu pour compatibilité avec l'ancien code.
        """
        # On délègue à la nouvelle méthode générique
        config = [
            {
                "role": "Senior Data Researcher",
                "goal": "Trouver des faits précis.",
                "backstory": "Tu es factuel et méticuleux.",
                "model_tag": model_tag,
                "tools": ["get_current_time", "calculator", "search_wavestone_internal"],
            },
            {
                "role": "Briefing Manager",
                "goal": "Synthétiser les informations.",
                "backstory": "Tu écris des rapports parfaits.",
                "model_tag": model_tag,
                "tools": ["generate_markdown_report", "generate_document"],
            },
        ]
        return CrewFactory.create_custom_crew(config, topic="Mission par défaut")
