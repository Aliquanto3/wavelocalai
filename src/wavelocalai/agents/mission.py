"""Mission d'une équipe d'agents : les agents s'enchaînent, la sortie de l'un est l'entrée du suivant
(story 6.5, AD-5, AD-6, AD-14).

Un seul run racine `agent` (créé par le service) porte toute la mission. Chaque agent rejoue la boucle
d'outils de la 6.1 (`AgentLoop.run`, un seul compteur `step_id` pour le run) avec son modèle, ses
outils et son nom (`step.agent`). Chaque appel de modèle est une feuille du run racine avec son `co2`.

- Seule la réponse du **dernier** agent est publiée en `token` : c'est le rapport, gardé par le hub
  dans la conversation. Les réponses intermédiaires sont dites par leur étape `answer`.
- Un agent que la mission n'atteint pas (arrêt, erreur d'un agent précédent) ne publie aucune étape.
- L'annulation garde le **rapport partiel** : la dernière réponse d'agent terminé est publiée en
  `token` par le crochet d'annulation du hub, juste avant la clôture `cancelled` (« Arrêté »).
- `mission_totals` (`duration_s`, `peak_memory_gb`, `agents_done`) est publié à la fin de la mission,
  ou par le crochet d'annulation ; `GET /api/runs/{id}` le lit dans `mission`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from wavelocalai.agents.crews import CrewAgent, task_for
from wavelocalai.agents.loop import AgentLoop, LoopOutcome
from wavelocalai.agents.tools import AgentTool
from wavelocalai.hardware.memory import read_memory
from wavelocalai.models.port import ChatMessage, ChatModel
from wavelocalai.runs.hub import RunHub

logger = logging.getLogger("wavelocalai.agents")

MISSION_TOTALS = "mission_totals"
NO_ANSWER = "(aucune réponse)"
TRUNCATED = "\n[sortie tronquée : {limit} caractères sur {size}]"
SYSTEM_PROMPT = (
    "Tu es {role}, un agent d'une équipe qui mène une mission, en français.\n"
    "Objectif : {goal}\n"
    "Contexte : {backstory}\n"
    "Tu es l'agent {rank} sur {count}. {position} Quand un outil permet d'obtenir une information "
    "ou de produire un résultat que tu ne peux pas donner toi-même, appelle-le au lieu d'inventer ; "
    "lis son résultat, y compris son erreur, puis poursuis ou change de méthode. Quand tu as ce "
    "qu'il faut, réponds sans appeler d'outil : ta réponse est transmise telle quelle."
)
FIRST = "Tu ouvres la mission."
NEXT = "Tu reprends le travail de l'agent précédent."
LAST = " Ta réponse est le rapport final de la mission."


@dataclass
class _Mission:
    """État partagé avec le crochet d'annulation (synchrone)."""

    started: float
    lane: str = ""
    last_output: str = ""  # sortie du dernier agent terminé : le rapport partiel
    done: int = 0
    reported: bool = False  # le rapport final est déjà parti en `token`
    totals_sent: bool = False
    peak_gb: float | None = None


def sample_used_gb() -> float | None:
    """Mémoire du poste occupée en ce moment (total − disponible, Go) ; `None` si illisible."""
    try:
        reading = read_memory()
    except Exception:  # noqa: BLE001 - une mesure manquée ne casse jamais la mission
        return None
    return reading.total_gb - reading.available_gb


def agent_system(agent: CrewAgent, rank: int, count: int) -> str:
    position = (FIRST if rank == 1 else NEXT) + (LAST if rank == count else "")
    return SYSTEM_PROMPT.format(
        role=agent.role,
        goal=agent.goal,
        backstory=agent.backstory,
        rank=rank,
        count=count,
        position=position,
    )


def agent_task(agent: CrewAgent, topic: str, previous: tuple[str, str] | None, limit: int) -> str:
    """Tâche de l'agent : sujet, objectif, puis la sortie de l'agent précédent (rôle, texte)."""
    text = task_for(agent, topic)["description"]
    if previous is None:
        return text
    role, output = previous
    if len(output) > limit:
        output = output[:limit] + TRUNCATED.format(limit=limit, size=len(output))
    return f"{text}\n\nTravail de l'agent précédent ({role}) :\n{output}"


class MissionRunner:
    """Joue la mission d'une équipe sous le run racine `root_id`."""

    def __init__(
        self,
        hub: RunHub,
        root_id: str,
        loop: AgentLoop,
        *,
        sample_s: float,
        result_chars: int,
        sampler: Callable[[], float | None] = sample_used_gb,
    ) -> None:
        self._hub = hub
        self._root = root_id
        self._loop = loop
        self._sample_s = sample_s
        self._result_chars = result_chars
        self._sampler = sampler
        self._state = _Mission(started=time.perf_counter())
        hub.set_cancel_hook(root_id, self._on_cancel)

    # --- totaux et annulation ------------------------------------------------------------------

    def _sample(self) -> None:
        used = self._sampler()
        if used is not None and (self._state.peak_gb is None or used > self._state.peak_gb):
            self._state.peak_gb = used

    def _publish_totals(self) -> None:
        state = self._state
        if state.totals_sent:
            return
        state.totals_sent = True
        self._sample()
        self._hub.publish(
            self._root,
            MISSION_TOTALS,
            {
                "duration_s": round(time.perf_counter() - state.started, 3),
                "peak_memory_gb": None if state.peak_gb is None else round(state.peak_gb, 2),
                "agents_done": state.done,
            },
        )

    def _on_cancel(self) -> None:
        """Crochet du hub, juste avant `cancelled` : rapport partiel, puis totaux de la mission."""
        state = self._state
        if state.last_output and not state.reported and state.lane:
            state.reported = True
            self._hub.publish_token(self._root, state.lane, state.last_output, "answer")
        self._publish_totals()

    async def _watch_memory(self) -> None:
        while True:
            self._sample()
            await asyncio.sleep(self._sample_s)

    # --- mission -------------------------------------------------------------------------------

    async def run(
        self,
        agents: list[CrewAgent],
        models: list[ChatModel],
        tools: list[list[AgentTool]],
        topic: str,
        *,
        temperature: float,
    ) -> LoopOutcome:
        """Enchaîne les agents. Rend la fin de la mission : `ok` avec le rapport final (réponse du
        dernier agent), ou `error` à l'échec d'un appel de modèle (les agents suivants ne partent
        pas)."""
        state = self._state
        watcher = asyncio.create_task(self._watch_memory(), name="wavelocalai-mission-memory")
        outcome = LoopOutcome("ok")
        turns = tool_calls = 0
        try:
            previous: tuple[str, str] | None = None
            for rank, (agent, model, agent_tools) in enumerate(
                zip(agents, models, tools, strict=True), start=1
            ):
                last = rank == len(agents)
                state.lane = model.ref.tag
                messages = [
                    ChatMessage("system", agent_system(agent, rank, len(agents))),
                    ChatMessage("user", agent_task(agent, topic, previous, self._result_chars)),
                ]
                outcome = await self._loop.run(
                    model,
                    messages,
                    agent_tools,
                    temperature=temperature,
                    agent=agent.role,
                    stream_answer=last,
                )
                turns += outcome.turns
                tool_calls += outcome.tool_calls
                if outcome.status != "ok":
                    break
                state.done += 1
                state.last_output = outcome.answer or NO_ANSWER
                state.reported = last and bool(outcome.answer)
                previous = (agent.role, state.last_output)
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
        self._publish_totals()
        return LoopOutcome(
            outcome.status,
            answer=outcome.answer,
            error=outcome.error,
            turns=turns,
            tool_calls=tool_calls,
            duration_s=time.perf_counter() - state.started,
            stopped=outcome.stopped,
        )
