"""Boucle d'outils d'un agent : le modèle réfléchit, appelle des outils, reçoit leurs résultats, puis
répond (story 6.1, AD-5, AD-6, AD-8, AD-9, AD-14).

La boucle tourne **sous un run racine `agent`** déjà créé par le service ; elle ne fixe jamais son
statut (le service appelle `hub.finish_run` avec le `LoopOutcome`). Chaque appel de modèle est une
feuille `generation` du run (`stream_into_run` avec un `Turn` : texte et appels d'outils gardés, pas
publiés, `metrics` et chargement publiés), donc mesurée et avec son `co2` comme toute génération.

Étapes publiées (événement `step`, `contrat-api.md` §Agents) :

- `think` : la réflexion du tour (canal `thought` du modèle, et le texte écrit avant d'appeler des
  outils), à la fin de l'appel de modèle ;
- `tool_call` : l'appel, publié **avant** l'exécution (l'écran dit « Appel de l'outil… ») ;
- `tool_result` : le résultat ou l'erreur en texte, avec la durée de l'outil ;
- `answer` : la réponse finale, puis son texte en `token` (le texte d'un tour n'est publié qu'une
  fois le tour fini : on ne sait qu'alors s'il appelle des outils).

Un outil qui lève une exception ou dépasse son délai ne casse pas la boucle : l'erreur devient le
résultat, que le modèle lit et peut contourner. Annuler le run annule la tâche : l'appel de modèle
(flux fermé dans son `finally`) et l'outil en cours reçoivent `CancelledError`. Le nombre d'appels de
modèle est borné par `Settings.agents.max_turns` : la borne atteinte est une fin propre (`stopped`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from wavelocalai.agents.tools import AgentTool, ToolOutput
from wavelocalai.config import Settings
from wavelocalai.errors import mask_secrets
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.inference.chat import cloud_estimator
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import CANCELLED_CO2, Guard, Turn, stream_into_run
from wavelocalai.models.port import ChatMessage, ChatModel, ChatRequest, ToolCall
from wavelocalai.runs.hub import RunHub

logger = logging.getLogger("wavelocalai.agents")

STEP_KINDS = ("think", "tool_call", "tool_result", "answer")
NO_RESULT = "(aucun résultat)"
SENSITIVE_REFUSAL = (
    "L'outil « {tool} » est sensible : il ne s'exécute qu'après une validation explicite de "
    "l'utilisateur, qui n'est pas disponible. Dis à l'utilisateur ce que tu aurais fait."
)
MAX_TURNS_MESSAGE = (
    "Je m'arrête : la limite de {turns} appels de modèle est atteinte avant d'avoir pu conclure. "
    "Reformulez la tâche en plus précis, ou réduisez les outils proposés."
)


@dataclass(frozen=True)
class LoopOutcome:
    """Fin d'une boucle : `ok` (réponse, ou borne atteinte : `stopped = "max_turns"`) ou `error`
    avec l'enveloppe d'AD-18 de l'appel de modèle qui a échoué."""

    status: Literal["ok", "error"]
    answer: str = ""
    error: dict[str, Any] | None = None
    turns: int = 0  # appels de modèle
    tool_calls: int = 0
    duration_s: float = 0.0
    stopped: str | None = None


@dataclass
class _ToolRun:
    text: str  # rendu au modèle
    failed: bool
    duration_s: float
    artifact_url: str | None = None


def masked(value: Any, secrets: Sequence[str]) -> Any:
    """`value` (arguments d'un outil) avec ses textes masqués, à toute profondeur (AD-18)."""
    if isinstance(value, str):
        return mask_secrets(value, secrets)
    if isinstance(value, dict):
        return {key: masked(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [masked(item, secrets) for item in value]
    return value


def clip(text: str, limit: int) -> str:
    """Texte replié à `limit` caractères au plus (`…` en fin s'il est coupé)."""
    text = text.strip()
    return text if len(text) <= limit else text[: max(limit - 1, 0)].rstrip() + "…"


class AgentLoop:
    """Une boucle par run racine `agent` ; `run` s'appelle une fois (agent seul) ou une fois par agent
    d'une équipe (story 6.5), le compteur `step_id` étant celui du run."""

    def __init__(
        self,
        hub: RunHub,
        root_id: str,
        settings: Settings,
        *,
        slot: LocalSlot,
        meter: LocalMeter | None = None,
        guard: Guard | None = None,
        announce: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._hub = hub
        self._root = root_id
        self._settings = settings
        self._slot = slot
        self._meter = meter
        self._guard = guard
        self._announce = announce
        self._secrets = settings.secret_values()
        self._steps = 0

    async def run(
        self,
        model: ChatModel,
        messages: Sequence[ChatMessage],
        tools: Sequence[AgentTool] = (),
        *,
        temperature: float = 0.2,
        agent: str | None = None,
        stream_answer: bool = True,
    ) -> LoopOutcome:
        """Joue la boucle jusqu'à la réponse, la borne de tours ou l'échec d'un appel de modèle.

        `agent` : nom de l'agent d'une équipe (`null` pour l'agent seul). `stream_answer` faux : la
        réponse est dite par l'étape `answer` sans être publiée en `token`."""
        cfg = self._settings.agents
        lane = model.ref.tag
        conversation = list(messages)
        by_name = {tool.id: tool for tool in tools}
        specs = [tool.spec() for tool in tools]
        started = time.perf_counter()
        tool_calls = 0
        for turn_no in range(1, cfg.max_turns + 1):
            turn = Turn()
            leaf_id = await self._leaf(lane)
            leaf = await stream_into_run(
                self._hub,
                leaf_id,
                model,
                ChatRequest(list(conversation), tools=specs, temperature=temperature),
                secrets=self._secrets,
                estimate_co2=cloud_estimator(model, self._settings),
                slot=self._slot,
                timeout_s=self._settings.delays.lane_timeout_s,
                retry_interrupted=True,
                publish_to=self._root,
                meter=self._meter,
                on_leaf_closed=self._announce,
                metrics_extra={"turn": turn_no},
                guard=self._guard,
                turn=turn,
            )
            if leaf.status != "ok":
                return LoopOutcome(
                    "error",
                    error=leaf.error,
                    turns=turn_no,
                    tool_calls=tool_calls,
                    duration_s=time.perf_counter() - started,
                )
            text = "".join(turn.text).strip()
            thought = "".join(turn.thought).strip()
            model_s = leaf.total_s
            if not turn.tool_calls:
                if thought:
                    self._step("think", lane, agent, turn_no, model_s, thought)
                self._step("answer", lane, agent, turn_no, model_s, text)
                if text and stream_answer:
                    self._hub.publish_token(self._root, lane, text, "answer")
                return LoopOutcome(
                    "ok",
                    answer=text,
                    turns=turn_no,
                    tool_calls=tool_calls,
                    duration_s=time.perf_counter() - started,
                )
            reasoning = "\n\n".join(part for part in (thought, text) if part)
            if reasoning:
                self._step("think", lane, agent, turn_no, model_s, reasoning)
            conversation.append(
                ChatMessage(
                    "assistant",
                    text,
                    tool_calls=[
                        {"id": call.id, "name": call.name, "arguments": call.arguments}
                        for call in turn.tool_calls
                    ],
                )
            )
            for call in turn.tool_calls:
                tool_calls += 1
                ran = await self._call(call, by_name, lane, agent, turn_no)
                conversation.append(ChatMessage("tool", ran.text, tool_call_id=call.id))
        # Borne atteinte : fin propre, la raison est la réponse.
        message = MAX_TURNS_MESSAGE.format(turns=cfg.max_turns)
        self._step("answer", lane, agent, cfg.max_turns, None, message, stopped="max_turns")
        if stream_answer:
            self._hub.publish_token(self._root, lane, message, "answer")
        return LoopOutcome(
            "ok",
            answer=message,
            turns=cfg.max_turns,
            tool_calls=tool_calls,
            duration_s=time.perf_counter() - started,
            stopped="max_turns",
        )

    # --- feuilles et étapes --------------------------------------------------------------------

    async def _leaf(self, tag: str) -> str:
        """Feuille `generation` du prochain appel de modèle, annulée par défaut tant qu'elle n'est pas
        jouée (AD-10). Le parent qui se clôt (annulation) interrompt la boucle."""
        try:
            leaf = await self._hub.create_run("generation", models=[tag], parent_run_id=self._root)
        except ValueError:
            raise asyncio.CancelledError from None
        self._hub.declare_leaf(leaf.run_id, CANCELLED_CO2)
        return leaf.run_id

    def _step(
        self,
        kind: str,
        lane: str,
        agent: str | None,
        turn: int,
        duration_s: float | None,
        summary: str,
        **extra: Any,
    ) -> None:
        """Publie un `step`. Les champs additifs (`tool`, `call_id`, `arguments`, `failed`,
        `artifact_url`, `stopped`) sont absents quand ils n'ont pas de sens."""
        self._steps += 1
        data: dict[str, Any] = {
            "lane": lane,
            "step_id": self._steps,
            "agent": agent,
            "kind": kind,
            "turn": turn,
            "duration_s": None if duration_s is None else round(duration_s, 3),
            "summary": mask_secrets(
                clip(summary, self._settings.agents.summary_chars), self._secrets
            ),
        }
        data.update({key: value for key, value in extra.items() if value is not None})
        self._hub.publish(self._root, "step", data)

    # --- outils --------------------------------------------------------------------------------

    async def _call(
        self,
        call: ToolCall,
        by_name: dict[str, AgentTool],
        lane: str,
        agent: str | None,
        turn: int,
    ) -> _ToolRun:
        """`tool_call` (avant l'exécution), exécution, `tool_result`. Rend ce que lira le modèle."""
        self._step(
            "tool_call",
            lane,
            agent,
            turn,
            None,
            json.dumps(call.arguments, ensure_ascii=False, default=str),
            tool=call.name,
            call_id=call.id,
            arguments=masked(call.arguments, self._secrets),
        )
        ran = await self._execute(call, by_name.get(call.name), list(by_name))
        self._step(
            "tool_result",
            lane,
            agent,
            turn,
            ran.duration_s,
            ran.text,
            tool=call.name,
            call_id=call.id,
            failed=True if ran.failed else None,
            artifact_url=ran.artifact_url,
        )
        limit = self._settings.agents.result_chars
        shown = ran.text
        if len(shown) > limit:
            shown = f"{shown[:limit]}\n[résultat tronqué : {limit} caractères sur {len(shown)}]"
        return _ToolRun(shown or NO_RESULT, ran.failed, ran.duration_s, ran.artifact_url)

    async def _execute(
        self, call: ToolCall, tool: AgentTool | None, offered: list[str]
    ) -> _ToolRun:
        started = time.perf_counter()

        def done(text: str, failed: bool, artifact_url: str | None = None) -> _ToolRun:
            return _ToolRun(
                mask_secrets(text, self._secrets),
                failed,
                round(time.perf_counter() - started, 3),
                artifact_url,
            )

        if call.error:
            return done(call.error, True)
        if tool is None:
            known = ", ".join(offered) or "aucun"
            return done(f"Outil inconnu : {call.name}. Outils disponibles : {known}.", True)
        if tool.sensitive:  # AD-9 : jamais d'exécution sans approbation (story 6.3)
            return done(SENSITIVE_REFUSAL.format(tool=tool.id), True)
        timeout_s = self._settings.agents.tool_timeout_s
        deadline = asyncio.timeout(timeout_s)
        try:
            async with deadline:
                output = await tool.run(dict(call.arguments))
        except Exception as exc:  # noqa: BLE001 - l'erreur d'un outil est son résultat
            if isinstance(exc, TimeoutError) and deadline.expired():
                return done(f"Délai dépassé ({timeout_s:g} s) : l'outil n'a pas répondu.", True)
            logger.warning("Outil %s en échec : %r", tool.id, exc)
            return done(f"{type(exc).__name__}: {exc}", True)
        if isinstance(output, ToolOutput):
            return done(output.text, False, output.artifact_url)
        return done(str(output), False)
