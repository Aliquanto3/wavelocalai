"""Service de l'Arène : une même question sur 2 à 4 modèles, un run composite (AD-5, AD-6, AD-14).

Le hub crée une racine `arena` et une feuille `generation` par modèle (`parent_run_id`) ; la racine
publie seule le flux, chaque événement de lane porte `lane` = tag du modèle. Les lanes locales
passent l'une après l'autre par le sémaphore « Ollama local » (prise par appel), les lanes cloud
partent aussitôt en parallèle. Le délai d'une lane court depuis la prise de la place (local) ou le
départ de l'appel (cloud) : une lane en échec ou hors délai n'arrête pas les autres, et la racine
finit `ok` dès que l'orchestration aboutit (l'échec d'une lane reste dans son `lane_status`).

Chaque lane passe par `stream_into_run`, le chemin de feuille commun du chat : c'est lui qui portera
la mesure CO2 de chaque feuille ; sans mesure, le `co2` d'une feuille est « non mesurable ».
Aucune conversation : l'Arène n'est pas un genre de conversation (AD-5), la question vit dans
l'événement `question` du flux (AD-7), jamais dans `runs.params`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from wavelocalai.config import Settings
from wavelocalai.errors import AppError, build_envelope
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import NOT_MEASURED, stream_into_run
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import ChatMessage, ChatModel, ChatRequest, ModelRef
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import LeafResult, RunHandle

logger = logging.getLogger("wavelocalai.inference")

MIN_MODELS = 2
MAX_MODELS = 4
MAX_CRITERIA = 8
MAX_CRITERION_CHARS = 64
TEMPERATURE = 0.2  # la même pour toutes les lanes : la comparaison porte sur les modèles

LANE_STATUSES = (
    "waiting",
    "loading",
    "generating",
    "done",
    "timeout",
    "failed",
    "cancelled",
)  # `judging` (story 3.3) s'ajoutera quand le juge existera
TERMINAL = frozenset({"done", "timeout", "failed", "cancelled"})


@dataclass(frozen=True)
class ArenaCommand:
    models: Sequence[str]
    prompt: str
    judge: str | None = None  # noté par la story 3.3 ; vérifié ici (cloud autorisé ?)
    criteria: Sequence[str] = ()
    allow_cloud: bool = False


@dataclass
class _Lane:
    model: ChatModel
    run_id: str
    status: str = "waiting"

    @property
    def tag(self) -> str:
        return self.model.ref.tag


@dataclass
class _Arena:
    run_id: str
    lanes: list[_Lane] = field(default_factory=list)


class ArenaService:
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

    async def start(self, command: ArenaCommand) -> RunHandle:
        """Crée la racine et ses feuilles, rend `{run_id}` aussitôt ; les lanes suivent en tâches.

        Lève `invalid_request` (moins de 2 ou plus de 4 modèles, doublon, critères hors bornes),
        `model_not_found`, `cloud_not_allowed` ou `model_not_chat` (registre, avant tout appel et
        avant toute écriture) ou `run_busy` (une Arène est déjà active, AD-14)."""
        refs = self._resolve(command)
        models = [self._factory.chat_model(ref) for ref in refs]
        root = await self._hub.create_run(
            "arena",
            models=[ref.tag for ref in refs],
            params={
                "temperature": TEMPERATURE,
                "allow_cloud": command.allow_cloud,
                "judge": command.judge,
                "criteria": list(command.criteria),
            },
        )
        arena = _Arena(root.run_id)
        try:
            for model in models:
                leaf = await self._hub.create_run(
                    "generation", models=[model.ref.tag], parent_run_id=root.run_id
                )
                arena.lanes.append(_Lane(model, leaf.run_id))
        except BaseException:
            error = build_envelope("internal", "Création des lanes de l'Arène impossible.")
            await self._hub.finish_run(root.run_id, "error", error=error)
            raise
        self._hub.publish(root.run_id, "question", {"text": command.prompt})
        for lane in arena.lanes:  # les colonnes existent avant le premier jeton
            self._hub.publish(root.run_id, "lane_status", {"lane": lane.tag, "status": "waiting"})
        self._hub.set_cancel_hook(root.run_id, lambda: self._cancel_unfinished(arena))
        task = asyncio.create_task(
            self._orchestrate(arena, command.prompt), name=f"wavelocalai-arena-{root.run_id}"
        )
        self._hub.attach_task(root.run_id, task)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return root

    def _resolve(self, command: ArenaCommand) -> list[ModelRef]:
        if not MIN_MODELS <= len(command.models) <= MAX_MODELS:
            raise AppError(
                "invalid_request",
                f"models : {MIN_MODELS} à {MAX_MODELS} modèles, pas {len(command.models)}.",
            )
        if len(command.criteria) > MAX_CRITERIA or any(
            not 0 < len(c) <= MAX_CRITERION_CHARS for c in command.criteria
        ):
            raise AppError(
                "invalid_request",
                f"criteria : au plus {MAX_CRITERIA} critères de {MAX_CRITERION_CHARS} caractères.",
            )
        # Tout est résolu avant la moindre écriture ou le moindre appel (AD-9).
        refs = [self._registry.resolve(tag, command.allow_cloud) for tag in command.models]
        if command.judge:
            self._registry.resolve(command.judge, command.allow_cloud)
        tags = [ref.tag for ref in refs]
        if len(set(tags)) != len(tags):
            raise AppError("invalid_request", "models : un même modèle ne figure qu'une fois.")
        return refs

    # --- exécution -----------------------------------------------------------------------------

    async def _orchestrate(self, arena: _Arena, prompt: str) -> None:
        request = ChatRequest([ChatMessage("user", prompt)], temperature=TEMPERATURE)
        tasks: list[asyncio.Task[None]] = []
        try:
            for lane in arena.lanes:
                task = asyncio.create_task(
                    self._run_lane(arena, lane, request),
                    name=f"wavelocalai-arena-lane-{lane.run_id}",
                )
                self._hub.attach_task(lane.run_id, task)
                tasks.append(task)
            await asyncio.gather(*tasks, return_exceptions=True)
            await self._hub.finish_run(arena.run_id, "ok")
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            raise
        except Exception as exc:  # noqa: BLE001 - ne jamais laisser la racine active
            logger.error("Orchestration de l'Arène en échec", exc_info=exc)
            error = build_envelope(
                "internal", f"{type(exc).__name__}: {exc}", self._settings.secret_values()
            )
            for task in tasks:
                task.cancel()
            with contextlib.suppress(Exception):
                await self._hub.finish_run(arena.run_id, "error", error=error)

    async def _run_lane(self, arena: _Arena, lane: _Lane, request: ChatRequest) -> None:
        secrets = self._settings.secret_values()
        try:
            leaf = await stream_into_run(
                self._hub,
                lane.run_id,
                lane.model,
                request,
                secrets=secrets,
                slot=self._slot,
                timeout_s=self._settings.delays.lane_timeout_s,
                retry_interrupted=True,
                publish_to=arena.run_id,
                on_phase=lambda phase: self._set_status(arena, lane, phase),
            )
        except asyncio.CancelledError:
            self._set_status(arena, lane, "cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 - une lane qui casse n'arrête pas les autres
            logger.error("Lane %s de l'Arène en échec", lane.tag, exc_info=exc)
            error = build_envelope("internal", f"{type(exc).__name__}: {exc}", secrets)
            self._set_status(arena, lane, "failed", error)
            with contextlib.suppress(Exception):
                failed = LeafResult(status="error", origin=lane.model.ref.origin, error=error)
                await self._hub.finish_leaf(lane.run_id, failed, NOT_MEASURED)
            return
        if leaf.status == "ok":
            self._set_status(arena, lane, "done")
        else:
            code = (leaf.error or {}).get("code")
            self._set_status(arena, lane, "timeout" if code == "timeout" else "failed", leaf.error)

    def _set_status(
        self, arena: _Arena, lane: _Lane, status: str, error: dict[str, object] | None = None
    ) -> None:
        """Publie le `lane_status` d'une lane ; un état final ne change plus, un état répété
        n'est pas republié."""
        if lane.status in TERMINAL or lane.status == status:
            return
        lane.status = status
        data: dict[str, object] = {"lane": lane.tag, "status": status}
        if error is not None:
            data["error"] = error
        self._hub.publish(arena.run_id, "lane_status", data)

    def _cancel_unfinished(self, arena: _Arena) -> None:
        """Crochet du hub, juste avant `run_ended` : les lanes inachevées passent à `cancelled`."""
        for lane in arena.lanes:
            self._set_status(arena, lane, "cancelled")
