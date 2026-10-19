"""Service de l'agent seul : une tâche, un modèle, des outils, une boucle (AD-5, AD-8, AD-9, AD-14).

Le service obtient le modèle par `registry.resolve(tag, allow_cloud)` seulement, les outils par le
`ToolRegistry`, demande au hub de créer le run racine `agent` (conversation et message utilisateur
compris), puis lance dans une tâche la boucle d'outils (`agents/loop.py`) : le hub est seul à
numéroter, persister et fixer le statut ; ce service ne termine le run qu'avec `hub.finish_run`.
`runs.params` ne reçoit ni la tâche saisie ni les arguments des outils (AD-7).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

from wavelocalai.agents.loop import AgentLoop
from wavelocalai.agents.outbox import build_actions
from wavelocalai.agents.tools import AgentTool, ToolRegistry
from wavelocalai.config import Settings
from wavelocalai.errors import AppError, build_envelope
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import Guard
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import ChatMessage, ChatModel
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import RunHandle
from wavelocalai.runs.system_bus import SystemBus

logger = logging.getLogger("wavelocalai.agents")

SOLO_MODE = "solo"
TEMPERATURE = 0.2
SYSTEM_PROMPT = (
    "Tu es un agent qui mène à bien la tâche de l'utilisateur, en français. Quand un outil permet "
    "d'obtenir une information ou de produire un résultat que tu ne peux pas donner toi-même, "
    "appelle-le au lieu d'inventer ; lis son résultat, y compris son erreur, puis poursuis ou "
    "change de méthode. Quand tu as ce qu'il faut, réponds à l'utilisateur sans appeler d'outil."
)


@dataclass(frozen=True)
class AgentCommand:
    model: str
    prompt: str
    tools: tuple[str, ...] = ()
    temperature: float = TEMPERATURE
    allow_cloud: bool = False
    conversation_id: str | None = None
    mode: str = SOLO_MODE


class AgentService:
    def __init__(
        self,
        hub: RunHub,
        registry: ModelRegistry,
        factory: ModelFactory,
        slot: LocalSlot,
        settings: Settings,
        tools: ToolRegistry,
        *,
        meter: LocalMeter | None = None,
        bus: SystemBus | None = None,
        guard: Guard | None = None,
    ) -> None:
        self._hub = hub
        self._registry = registry
        self._factory = factory
        self._slot = slot
        self._settings = settings
        self._tools = tools
        self._meter = meter  # sans compteur, le CO2 d'une feuille locale n'est pas mesuré
        self._bus = bus  # sans bus, `carbon_updated` n'est pas publié
        self._guard = guard  # garde-fou mémoire de chaque appel local (story 4.8)
        self._tasks: set[asyncio.Task[None]] = set()  # références fortes jusqu'à la fin

    async def start(self, command: AgentCommand) -> RunHandle:
        """Crée le run et rend `{run_id, conversation_id}` aussitôt ; la boucle suit en tâche.

        Lève `model_not_found`, `cloud_not_allowed` ou `model_not_chat` (registre, AD-9),
        `invalid_request` (mode autre que `solo`, outil inconnu ou indisponible), `run_busy` (un
        run `agent` est déjà actif, AD-14) ou `not_found` (conversation inconnue)."""
        if command.mode != SOLO_MODE:
            raise AppError("invalid_request", f"mode : {command.mode!r} n'est pas pris en charge.")
        ref = self._registry.resolve(command.model, command.allow_cloud)
        model = self._factory.chat_model(ref)
        tools = self._tools.get(command.tools)
        handle = await self._hub.create_run(
            "agent",
            models=[ref.tag],
            params={
                "mode": SOLO_MODE,
                "tools": [tool.id for tool in tools],
                "allow_cloud": command.allow_cloud,
                "temperature": command.temperature,
                "max_turns": self._settings.agents.max_turns,
            },
            user_message=command.prompt,
            conversation_id=command.conversation_id,
        )
        task = asyncio.create_task(
            self._run(handle, model, tools, command.temperature),
            name=f"wavelocalai-agent-{handle.run_id}",
        )
        self._hub.attach_task(handle.run_id, task)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return handle

    async def _run(
        self, handle: RunHandle, model: ChatModel, tools: list[AgentTool], temperature: float
    ) -> None:
        root = handle.run_id
        try:
            messages = await self._history(handle)
            loop = AgentLoop(
                self._hub,
                root,
                self._settings,
                slot=self._slot,
                meter=self._meter,
                guard=self._guard,
                announce=self._announce_carbon,
                actions=build_actions(self._settings),
            )
            outcome = await loop.run(model, messages, tools, temperature=temperature)
            if outcome.status == "ok":
                await self._hub.finish_run(root, "ok")
            else:
                await self._hub.finish_run(root, "error", error=outcome.error)
        except asyncio.CancelledError:
            raise  # `hub.cancel` a déjà fixé `cancelled` ; les feuilles sont closes avec lui
        except Exception as exc:  # noqa: BLE001 - ne jamais laisser le run actif
            logger.error("Run agent en échec", exc_info=exc)
            error = build_envelope(
                "internal", f"{type(exc).__name__}: {exc}", self._settings.secret_values()
            )
            with contextlib.suppress(Exception):
                await self._hub.finish_run(root, "error", error=error)

    async def _history(self, handle: RunHandle) -> list[ChatMessage]:
        """Consigne, puis toute la conversation, la tâche qui vient d'être écrite comprise (une
        conversation d'agent se prolonge). Un message vide (run annulé avant sa réponse) est écarté,
        ainsi qu'une tâche restée sans réponse que la personne a renvoyée telle quelle."""
        assert handle.conversation_id is not None
        stored = await self._hub.conversation_messages(handle.conversation_id)
        messages = [ChatMessage("system", SYSTEM_PROMPT)]
        for item in stored:
            if not item.content:
                continue
            message = ChatMessage(item.role, item.content)  # type: ignore[arg-type]
            if message.role == "user" and messages[-1] == message:
                continue
            messages.append(message)
        return messages

    async def _announce_carbon(self) -> None:
        """`carbon_updated` après chaque feuille (AD-10) ; un échec est journalisé, sans effet."""
        session_id = self._hub.app_session_id
        if self._bus is None or session_id is None:
            return
        try:
            await announce_carbon_updated(self._bus, self._hub.store, session_id)
        except Exception as exc:  # noqa: BLE001 - une annonce manquée ne change pas le run
            logger.warning("carbon_updated non publié : %r", exc)
