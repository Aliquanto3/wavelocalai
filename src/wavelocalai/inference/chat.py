"""Service de chat libre : un message utilisateur, une réponse en flux (AD-5, AD-8, AD-9, AD-14).

Le service obtient le modèle par `registry.resolve(tag, allow_cloud)` seulement, demande au hub de
créer le run `chat` (conversation et message utilisateur compris), puis lance dans une tâche la
lecture du flux (`stream_into_run`) : le hub est seul à numéroter, persister et fixer le statut.
`runs.params` ne reçoit que la température et `allow_cloud`, jamais le texte saisi (AD-7).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from wavelocalai.config import Settings
from wavelocalai.errors import build_envelope
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import NOT_MEASURED, stream_into_run
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import ChatMessage, ChatModel, ChatRequest
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import LeafResult, RunHandle

logger = logging.getLogger("wavelocalai.inference")


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
    ) -> None:
        self._hub = hub
        self._registry = registry
        self._factory = factory
        self._slot = slot
        self._settings = settings
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
            return
        await stream_into_run(
            self._hub,
            handle.run_id,
            model,
            request,
            secrets=secrets,
            slot=self._slot,
            timeout_s=self._settings.delays.lane_timeout_s,
            retry_interrupted=True,
        )

    async def _request(self, handle: RunHandle, temperature: float) -> ChatRequest:
        """Toute la conversation, le message qui vient d'être écrit compris. Un message assistant
        vide (run annulé avant le premier jeton) est écarté."""
        assert handle.conversation_id is not None
        stored = await self._hub.conversation_messages(handle.conversation_id)
        messages = [ChatMessage(m.role, m.content) for m in stored if m.content]  # type: ignore[arg-type]
        return ChatRequest(messages=messages, temperature=temperature)
