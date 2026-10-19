"""Service de chat libre : un message utilisateur, une réponse en flux (AD-5, AD-8, AD-9, AD-14).

Le service obtient le modèle par `registry.resolve(tag, allow_cloud)` seulement, demande au hub de
créer le run `chat` (conversation et message utilisateur compris), puis lance dans une tâche la
lecture du flux (`stream_into_run`) : le hub est seul à numéroter, persister et fixer le statut.
`runs.params` ne reçoit que la température et `allow_cloud`, jamais le texte saisi (AD-7).

Une réponse locale est mesurée par le `LocalMeter` de `greenops/` dans la place du `LocalSlot`
(AD-11) ; la feuille close, le service publie `carbon_updated` sur le `SystemBus` (AD-10).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from wavelocalai.config import Settings
from wavelocalai.errors import build_envelope
from wavelocalai.greenops.cloud_estimate import estimate_cloud_co2
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import CANCELLED_CO2, NOT_MEASURED, Guard, stream_into_run
from wavelocalai.models.cloud import model_of, provider_of
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import ChatMessage, ChatModel, ChatRequest, ChatResult
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import Co2, LeafResult, RunHandle
from wavelocalai.runs.system_bus import SystemBus

logger = logging.getLogger("wavelocalai.inference")


def cloud_estimator(model: ChatModel, settings: Settings) -> Callable[[ChatResult], Co2] | None:
    """Estimation ecologits d'une réponse cloud (AD-11) ; rien pour un modèle local.

    Partagée par le chat et les lanes cloud de l'Arène.
    """
    if model.ref.origin != "cloud":
        return None
    provider, name = provider_of(model.ref.tag), model_of(model.ref.tag)
    groq_table = settings.cloud.groq_ecologits
    return lambda result: estimate_cloud_co2(
        provider,
        name,
        output_tokens=result.output_tokens,
        latency_s=result.total_s,
        groq_table=groq_table,
    )


@dataclass(frozen=True)
class ChatCommand:
    model: str
    message: str
    temperature: float = 0.2
    allow_cloud: bool = False
    conversation_id: str | None = None


class ChatService:
    def __init__(
        self,
        hub: RunHub,
        registry: ModelRegistry,
        factory: ModelFactory,
        slot: LocalSlot,
        settings: Settings,
        meter: LocalMeter | None = None,
        bus: SystemBus | None = None,
        guard: Guard | None = None,
    ) -> None:
        self._hub = hub
        self._registry = registry
        self._factory = factory
        self._slot = slot
        self._settings = settings
        self._meter = meter  # sans compteur, le CO2 d'une réponse locale n'est pas mesuré
        self._bus = bus  # sans bus, `carbon_updated` n'est pas publié
        self._guard = guard  # garde-fou mémoire d'une réponse locale (story 4.8)
        self._tasks: set[asyncio.Task[None]] = set()  # références fortes jusqu'à la fin

    async def start(self, command: ChatCommand) -> RunHandle:
        """Crée le run et rend `{run_id, conversation_id}` aussitôt ; la génération suit en tâche.

        Lève `model_not_found`, `cloud_not_allowed` ou `model_not_chat` (registre), `run_busy`
        (un run `chat` est déjà actif, AD-14) ou `not_found` (conversation inconnue)."""
        ref = self._registry.resolve(command.model, command.allow_cloud)
        model = self._factory.chat_model(ref)
        handle = await self._hub.create_run(
            "chat",
            models=[ref.tag],
            params={"temperature": command.temperature, "allow_cloud": command.allow_cloud},
            user_message=command.message,
            conversation_id=command.conversation_id,
        )
        # Annulé avant même la lecture du flux, le run garde un `co2` (AD-10).
        self._hub.declare_leaf(handle.run_id, CANCELLED_CO2)
        task = asyncio.create_task(
            self._run(handle, model, command.temperature),
            name=f"wavelocalai-chat-{handle.run_id}",
        )
        self._hub.attach_task(handle.run_id, task)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return handle

    async def _run(self, handle: RunHandle, model: ChatModel, temperature: float) -> None:
        secrets = self._settings.secret_values()
        try:
            request = await self._request(handle, temperature)
        except Exception as exc:  # noqa: BLE001 - ne jamais laisser le run actif
            logger.error("Historique du chat illisible", exc_info=exc)
            error = build_envelope("internal", f"{type(exc).__name__}: {exc}", secrets)
            await self._hub.finish_leaf(
                handle.run_id,
                LeafResult(status="error", origin=model.ref.origin, error=error),
                NOT_MEASURED,
            )
            await self._announce_carbon()
            return
        await stream_into_run(
            self._hub,
            handle.run_id,
            model,
            request,
            secrets=secrets,
            estimate_co2=self._cloud_estimator(model),
            slot=self._slot,
            timeout_s=self._settings.delays.lane_timeout_s,
            retry_interrupted=True,
            meter=self._meter,
            on_leaf_closed=self._announce_carbon,
            guard=self._guard,
        )

    def _cloud_estimator(self, model: ChatModel) -> Callable[[ChatResult], Co2] | None:
        return cloud_estimator(model, self._settings)

    async def _announce_carbon(self) -> None:
        """`carbon_updated` après chaque feuille, annulation comprise (le hub a déjà écrit le
        `co2` de la feuille annulée, `unmeasurable`) : le panneau de la barre haute se met à jour.
        """
        session_id = self._hub.app_session_id
        if self._bus is None or session_id is None:
            return
        try:
            await announce_carbon_updated(self._bus, self._hub.store, session_id)
        except Exception as exc:  # noqa: BLE001 - une annonce manquée ne change pas le run
            logger.warning("carbon_updated non publié : %r", exc)

    async def _request(self, handle: RunHandle, temperature: float) -> ChatRequest:
        """Toute la conversation, le message qui vient d'être écrit compris. Un message assistant
        vide (run annulé avant le premier jeton) est écarté, ainsi qu'une question restée sans
        réponse que la personne a renvoyée telle quelle (refus `ram_guard`, story 4.8) : le modèle
        ne la lit qu'une fois."""
        assert handle.conversation_id is not None
        stored = await self._hub.conversation_messages(handle.conversation_id)
        messages: list[ChatMessage] = []
        for m in stored:
            if not m.content:
                continue
            message = ChatMessage(m.role, m.content)  # type: ignore[arg-type]
            if message.role == "user" and messages and messages[-1] == message:
                continue  # la même question, renvoyée après un échec sans réponse
            messages.append(message)
        return ChatRequest(messages=messages, temperature=temperature)
