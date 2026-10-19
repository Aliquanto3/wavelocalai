"""Bibliothèque d'équipes d'agents (story 6.5, décision Q3, D-36).

Les équipes d'origine sont celles de la v1 (`CREW_PROMPT_LIBRARY`), reprises dans le fichier versionné
`config/agent_crews.json`, en lecture seule. Ce que l'utilisateur modifie (« Configurer ») vit dans
la table `preferences`, clé `agents.crews`, équipe par équipe ; « Revenir à l'équipe d'origine » efface
la modification. L'équipe en vigueur est la modification si elle existe, sinon l'origine.

Une équipe est une suite ordonnée d'agents (rôle, objectif, contexte, outils, modèle) : un agent a une
tâche, dérivée de son objectif (comme la v1) ; la sortie d'un agent est l'entrée du suivant. Aucun
CrewAI : un enchaînement séquentiel de la boucle d'outils de la 6.1 suffit (variante conservatrice).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from wavelocalai.agents.tools import ToolRegistry
from wavelocalai.errors import AppError
from wavelocalai.models.registry import ModelRegistry

logger = logging.getLogger("wavelocalai.agents")

PREF_KEY = "agents.crews"


class PreferenceStore(Protocol):
    """Ce que la bibliothèque attend de la table `preferences` (`agents` n'importe pas `store`)."""

    def get(self, key: str) -> Any | None: ...

    def put(self, key: str, value: Any) -> None: ...


MAX_AGENTS = 5  # D-36
MAX_ROLE = 60
MAX_GOAL = 300
MAX_BACKSTORY = 500
DEFAULT_BACKSTORY = "Tu es un expert dans ton domaine."
TOPIC_MARK = "{topic}"


@dataclass(frozen=True)
class CrewAgent:
    role: str
    goal: str
    backstory: str = DEFAULT_BACKSTORY
    tools: tuple[str, ...] = ()
    model: str | None = None  # `None` : le modèle par défaut de la mission

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "goal": self.goal,
            "backstory": self.backstory,
            "tools": list(self.tools),
            "model": self.model,
        }


@dataclass(frozen=True)
class CrewDef:
    id: str
    label: str
    category: str
    description: str
    topic: str  # sujet suggéré
    agents: tuple[CrewAgent, ...] = field(default_factory=tuple)


def task_for(agent: CrewAgent, topic: str = TOPIC_MARK) -> dict[str, str]:
    """Tâche de l'agent (formulation de la v1) : `topic` vaut `{topic}` dans la bibliothèque."""
    tools = " Utilise les outils à ta disposition si nécessaire." if agent.tools else ""
    return {
        "agent": agent.role,
        "description": (
            f"Analyse le sujet suivant : « {topic} ». Ton objectif spécifique est : "
            f"{agent.goal}.{tools} Produis une analyse détaillée selon ton point de vue d'expert."
        ),
        "expected_output": f"Un rapport complet rédigé par le {agent.role}.",
    }


def agent_from(raw: Any) -> CrewAgent | None:
    """Agent lu d'un document (fichier, préférence ou corps de requête) ; `None` s'il n'a pas la
    forme d'un agent. Aucune valeur n'est corrigée : la validation dit ce qui ne va pas."""
    if not isinstance(raw, dict):
        return None
    tools = raw.get("tools")
    model = raw.get("model")
    backstory = raw.get("backstory")
    return CrewAgent(
        role=str(raw.get("role") or "").strip(),
        goal=str(raw.get("goal") or "").strip(),
        backstory=str(backstory).strip() if backstory else DEFAULT_BACKSTORY,
        tools=tuple(str(t) for t in tools) if isinstance(tools, list) else (),
        model=str(model).strip() or None if model else None,
    )


def load_crews(path: Path) -> dict[str, CrewDef]:
    """Équipes d'origine du fichier versionné ; illisible ou de forme inattendue : bibliothèque vide
    (journalisé), jamais une exception."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Équipes d'agents illisibles (%s) : %s", path, exc)
        return {}
    raw_crews = data.get("crews") if isinstance(data, dict) else None
    if not isinstance(raw_crews, dict):
        logger.warning("Équipes d'agents au format inattendu (%s) : ignorées", path)
        return {}
    crews: dict[str, CrewDef] = {}
    for crew_id, raw in raw_crews.items():
        if not isinstance(raw, dict):
            continue
        agents = tuple(a for a in map(agent_from, raw.get("agents") or []) if a is not None)
        crews[str(crew_id)] = CrewDef(
            id=str(crew_id),
            label=str(raw.get("label") or crew_id),
            category=str(raw.get("category") or ""),
            description=str(raw.get("description") or ""),
            topic=str(raw.get("topic") or ""),
            agents=agents,
        )
    return crews


class CrewLibrary:
    """Équipes d'origine + modifications de l'utilisateur ; validation d'une composition."""

    def __init__(
        self,
        path: Path,
        preferences: PreferenceStore,
        tools: ToolRegistry,
        models: ModelRegistry,
    ) -> None:
        self._path = path
        self._preferences = preferences
        self._tools = tools
        self._models = models
        self._origin: dict[str, CrewDef] | None = None

    def _crews(self) -> dict[str, CrewDef]:
        if self._origin is None:
            self._origin = load_crews(self._path)
        return self._origin

    def _modified(self) -> dict[str, Any]:
        stored = self._preferences.get(PREF_KEY)
        return stored if isinstance(stored, dict) else {}

    def effective_agents(self, crew_id: str) -> tuple[CrewAgent, ...]:
        """Agents en vigueur : la modification enregistrée, sinon l'origine. `not_found` si l'équipe
        n'existe pas."""
        origin = self.origin(crew_id)
        stored = self._modified().get(crew_id)
        if isinstance(stored, list):
            agents = tuple(a for a in map(agent_from, stored) if a is not None)
            if len(agents) == len(stored):
                return agents
        return origin.agents

    def origin(self, crew_id: str) -> CrewDef:
        crew = self._crews().get(crew_id)
        if crew is None:
            raise AppError("not_found", f"Équipe inconnue : {crew_id}.")
        return crew

    def listing(self) -> list[dict[str, Any]]:
        """Chaque équipe en vigueur : agents (rôle, objectif, outils, modèle) et tâches ordonnées ;
        `modified` dit qu'une modification de l'utilisateur est en vigueur."""
        crews = []
        modified = self._modified()
        for crew in self._crews().values():
            agents = self.effective_agents(crew.id)
            crews.append(
                {
                    "id": crew.id,
                    "label": crew.label,
                    "category": crew.category,
                    "description": crew.description,
                    "topic": crew.topic,
                    "modified": agents != crew.agents or crew.id in modified,
                    "agents": [a.as_dict() for a in agents],
                    "tasks": [task_for(a) for a in agents],
                }
            )
        return crews

    # --- validation ----------------------------------------------------------------------------

    def validate(
        self, agents: Sequence[CrewAgent], *, allow_cloud: bool = False
    ) -> list[dict[str, str]]:
        """Un message par champ en défaut : `[{field, message}]`, vide si l'équipe est valide."""
        errors: list[dict[str, str]] = []

        def bad(field_name: str, message: str) -> None:
            errors.append({"field": field_name, "message": message})

        if not agents:
            bad("agents", "Ajoutez au moins un agent.")
        elif len(agents) > MAX_AGENTS:
            bad(
                "agents",
                f"Une équipe compte {MAX_AGENTS} agents au plus : retirez un agent pour en "
                "ajouter un autre.",
            )
        roles: set[str] = set()
        for rank, agent in enumerate(agents):
            where = f"agents[{rank}]"
            if not agent.role:
                bad(f"{where}.role", "Le rôle est vide.")
            elif len(agent.role) > MAX_ROLE:
                bad(f"{where}.role", f"Le rôle dépasse {MAX_ROLE} caractères.")
            elif agent.role.casefold() in roles:
                bad(f"{where}.role", f"Le rôle « {agent.role} » est déjà pris dans l'équipe.")
            roles.add(agent.role.casefold())
            if not agent.goal:
                bad(f"{where}.goal", "L'objectif est vide.")
            elif len(agent.goal) > MAX_GOAL:
                bad(f"{where}.goal", f"L'objectif dépasse {MAX_GOAL} caractères.")
            if len(agent.backstory) > MAX_BACKSTORY:
                bad(f"{where}.backstory", f"Le contexte dépasse {MAX_BACKSTORY} caractères.")
            self._check_tools(agent, where, bad)
            if agent.model is not None:
                self._check_model(agent.model, allow_cloud, f"{where}.model", bad)
        return errors

    def _check_tools(self, agent: CrewAgent, where: str, bad: Any) -> None:
        if len(set(agent.tools)) != len(agent.tools):
            bad(f"{where}.tools", "Un outil est répété.")
            return
        for tool_id in agent.tools:
            try:
                self._tools.get([tool_id])
            except AppError as exc:
                text = str(exc).removeprefix("tools : ")
                bad(f"{where}.tools", text)
                return

    def _check_model(self, tag: str, allow_cloud: bool, field_name: str, bad: Any) -> None:
        try:
            self._models.resolve(tag, allow_cloud)
        except AppError as exc:
            reasons = {
                "model_not_found": f"Le modèle {tag} est inconnu.",
                "cloud_not_allowed": (
                    f"Le modèle {tag} est hébergé hors de ce poste : autorisez le cloud pour "
                    "l'utiliser."
                ),
                "model_not_chat": f"Le modèle {tag} ne sait pas converser.",
            }
            bad(field_name, reasons.get(exc.code, str(exc)))

    def check(self, agents: Sequence[CrewAgent], *, allow_cloud: bool = False) -> None:
        """Comme `validate`, mais lève `invalid_request` (422) avec tous les messages."""
        errors = self.validate(agents, allow_cloud=allow_cloud)
        if errors:
            raise AppError(
                "invalid_request", "; ".join(f"{e['field']} : {e['message']}" for e in errors)
            )

    # --- modification de l'utilisateur ---------------------------------------------------------

    def save(
        self, crew_id: str, agents: Sequence[CrewAgent], *, allow_cloud: bool = False
    ) -> CrewDef:
        """Enregistre la modification de l'équipe (validée) dans `preferences`."""
        crew = self.origin(crew_id)
        self.check(agents, allow_cloud=allow_cloud)
        stored = dict(self._modified())
        stored[crew_id] = [a.as_dict() for a in agents]
        self._preferences.put(PREF_KEY, stored)
        return crew

    def reset(self, crew_id: str) -> None:
        """« Revenir à l'équipe d'origine » : efface la modification (sans effet s'il n'y en a pas)."""
        self.origin(crew_id)
        stored = dict(self._modified())
        if stored.pop(crew_id, None) is not None:
            self._preferences.put(PREF_KEY, stored)

    def view(self, crew_id: str) -> dict[str, Any]:
        return next(c for c in self.listing() if c["id"] == crew_id)
