"""Service de l'Arène : une même question sur 2 à 4 modèles, un run composite (AD-5, AD-6, AD-14).

Le hub crée une racine `arena` et une feuille `generation` par modèle (`parent_run_id`) ; la racine
publie seule le flux, chaque événement de lane porte `lane` = tag du modèle. Les lanes locales
passent l'une après l'autre par le sémaphore « Ollama local » (prise par appel), les lanes cloud
partent aussitôt en parallèle. Le délai d'une lane court depuis la prise de la place (local) ou le
départ de l'appel (cloud) : une lane en échec ou hors délai n'arrête pas les autres, et la racine
finit `ok` dès que l'orchestration aboutit (l'échec d'une lane reste dans son `lane_status`).

Chaque lane passe par `stream_into_run`, le chemin de feuille commun du chat : une lane locale est
mesurée par son propre tracker CodeCarbon, démarré et arrêté sous la place Ollama (AD-10, AD-11) ;
une lane cloud reste « non mesurable » jusqu'à ecologits. `carbon_updated` suit chaque feuille.
Aucune conversation : l'Arène n'est pas un genre de conversation (AD-5). La question et les critères
de notation, du texte saisi, vivent dans l'événement `question` du flux (AD-7), jamais dans
`runs.params`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from wavelocalai.config import Settings
from wavelocalai.errors import AppError, build_envelope
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.judge_port import (
    DEFAULT_CRITERIA,
    NOT_EVALUATED_EMPTY,
    NOT_EVALUATED_UNAVAILABLE,
    JudgeVerdict,
    LaneJudge,
)
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import CANCELLED_CO2, NOT_MEASURED, stream_into_run
from wavelocalai.models.defaults import ModelDefaults, is_weak_judge
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import (
    ChatChunk,
    ChatMessage,
    ChatModel,
    ChatRequest,
    ModelRef,
    TextDelta,
)
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import LeafResult, RunHandle
from wavelocalai.runs.system_bus import SystemBus

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
    "judging",
    "done",
    "timeout",
    "failed",
    "cancelled",
)
TERMINAL = frozenset({"done", "timeout", "failed", "cancelled"})


@dataclass(frozen=True)
class ArenaCommand:
    models: Sequence[str]
    prompt: str
    # Juge : un tag du registre, sinon le défaut `judge` (plus gros local qui tient). Le cloud n'est
    # jamais pris sans `allow_cloud` (AD-9).
    judge: str | None = None
    criteria: Sequence[str] = ()  # vide : le juge applique `DEFAULT_CRITERIA`
    allow_cloud: bool = False


class _RecordingModel:
    """Enveloppe d'un `ChatModel` qui garde le texte de réponse de la tentative en cours, pour
    le juge. Chaque appel de `stream` repart de zéro (relance comprise)."""

    def __init__(self, model: ChatModel) -> None:
        self.ref = model.ref
        self._model = model
        self.answer: list[str] = []

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        self.answer.clear()
        async with contextlib.aclosing(self._model.stream(request)) as upstream:
            async for chunk in upstream:
                if isinstance(chunk, TextDelta) and chunk.channel == "answer":
                    self.answer.append(chunk.text)
                yield chunk


@dataclass
class _Lane:
    model: _RecordingModel
    run_id: str
    status: str = "waiting"

    @property
    def tag(self) -> str:
        return self.model.ref.tag


@dataclass
class _Arena:
    run_id: str
    prompt: str = ""
    criteria: Sequence[str] = ()
    judge: ChatModel | None = None  # `None` : aucun juge disponible, les notes sont « non évalué »
    lanes: list[_Lane] = field(default_factory=list)


class ArenaService:
    def __init__(
        self,
        hub: RunHub,
        registry: ModelRegistry,
        factory: ModelFactory,
        slot: LocalSlot,
        settings: Settings,
        meter: LocalMeter | None = None,
        bus: SystemBus | None = None,
        defaults: ModelDefaults | None = None,
        judge: LaneJudge | None = None,
    ) -> None:
        self._hub = hub
        self._registry = registry
        self._factory = factory
        self._slot = slot
        self._settings = settings
        self._meter = meter  # sans compteur, le CO2 d'une lane locale n'est pas mesuré
        self._bus = bus  # sans bus, `carbon_updated` n'est pas publié
        self._defaults = defaults  # défaut `judge` ; sans lui, seul un juge nommé note
        self._judge = judge  # sans service de notation, les notes sont « non évalué »
        self._tasks: set[asyncio.Task[None]] = set()  # références fortes jusqu'à la fin

    async def start(self, command: ArenaCommand) -> RunHandle:
        """Crée la racine et ses feuilles, rend `{run_id}` aussitôt ; les lanes suivent en tâches.

        Lève `invalid_request` (moins de 2 ou plus de 4 modèles, doublon, critères hors bornes),
        `model_not_found`, `cloud_not_allowed` ou `model_not_chat` (registre, avant tout appel et
        avant toute écriture) ou `run_busy` (une Arène est déjà active, AD-14)."""
        refs, named_judge = self._resolve(command)
        judge_ref = named_judge or await self._default_judge(command.allow_cloud)
        judge_info = await self._judge_info(judge_ref, command.allow_cloud)
        models = [_RecordingModel(self._factory.chat_model(ref)) for ref in refs]
        root = await self._hub.create_run(
            "arena",
            models=[ref.tag for ref in refs],
            params={
                "temperature": TEMPERATURE,
                "allow_cloud": command.allow_cloud,
                "judge": judge_ref.tag if judge_ref else None,  # tag du registre, pas du texte
            },
        )
        arena = _Arena(
            root.run_id,
            command.prompt,
            list(command.criteria),
            self._factory.chat_model(judge_ref) if judge_ref else None,
        )
        try:
            for model in models:
                leaf = await self._hub.create_run(
                    "generation", models=[model.ref.tag], parent_run_id=root.run_id
                )
                # Annulée avant même sa première tentative, la feuille garde un `co2` (AD-10).
                self._hub.declare_leaf(leaf.run_id, CANCELLED_CO2)
                arena.lanes.append(_Lane(model, leaf.run_id))
        except BaseException:
            error = build_envelope("internal", "Création des lanes de l'Arène impossible.")
            await self._hub.finish_run(root.run_id, "error", error=error)
            raise
        self._hub.publish(
            root.run_id, "question", {"text": command.prompt, "criteria": list(command.criteria)}
        )
        self._hub.publish(
            root.run_id,
            "judge",
            self._judge_event(judge_ref, judge_info, named=named_judge is not None),
        )
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

    async def _default_judge(self, allow_cloud: bool) -> ModelRef | None:
        """Défaut `judge` (plus gros local qui tient, ou cloud autorisé) ; `None` sans service de
        notation ni modèle de conversation : les notes seront « non évalué : juge indisponible »."""
        if self._judge is None or self._defaults is None:
            return None
        try:
            chosen = await self._defaults.get("judge", allow_cloud)
            return self._registry.resolve(chosen.tags[0], allow_cloud) if chosen.tags else None
        except AppError as exc:  # `no_model`, ou un modèle devenu introuvable
            logger.info("Aucun juge par défaut : %s", exc.code)
            return None

    async def _judge_info(self, ref: ModelRef | None, allow_cloud: bool) -> float | None:
        """Paramètres actifs (milliards) du juge d'après le registre ; `None` si inconnus."""
        if ref is None or ref.origin != "local":
            return None
        try:
            listed = await self._registry.list_models(allow_cloud=allow_cloud)
        except Exception:  # noqa: BLE001 - un registre en peine ne bloque pas l'Arène
            logger.warning("Liste des modèles indisponible pour le juge", exc_info=True)
            return None
        info = next((m for m in listed.models if m.tag == ref.tag), None)
        return info.params_active_b if info else None

    @staticmethod
    def _judge_event(ref: ModelRef | None, params_b: float | None, *, named: bool) -> dict:
        """Données de l'événement `judge` : le juge retenu et la fiabilité de ses notes."""
        if ref is None:
            return {
                "model": None,
                "origin": None,
                "params_active_b": None,
                "unreliable": None,
                "single_judge": False,
                "chosen": "none",
                "default_criteria": list(DEFAULT_CRITERIA),
            }
        return {
            "model": ref.tag,
            "origin": ref.origin,
            "params_active_b": params_b,
            # Moins de ~4 milliards de paramètres actifs, ou inconnus, pour un juge local.
            "unreliable": is_weak_judge(ref.origin != "local", params_b),
            "single_judge": True,
            "chosen": "request" if named else "default",
            "default_criteria": list(DEFAULT_CRITERIA),
        }

    def _resolve(self, command: ArenaCommand) -> tuple[list[ModelRef], ModelRef | None]:
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
        judge = (
            self._registry.resolve(command.judge, command.allow_cloud) if command.judge else None
        )
        tags = [ref.tag for ref in refs]
        if len(set(tags)) != len(tags):
            raise AppError("invalid_request", "models : un même modèle ne figure qu'une fois.")
        return refs, judge

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
            self._cancel_unfinished(arena)  # aucune lane sans `lane_status` final
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
                meter=self._meter,
                on_leaf_closed=self._announce_carbon,
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
            with contextlib.suppress(Exception):
                await self._announce_carbon()
            return
        if leaf.status == "ok":
            try:
                await self._judge_lane(arena, lane)
            except asyncio.CancelledError:
                self._set_status(arena, lane, "cancelled")
                raise
            self._set_status(arena, lane, "done")
        else:
            code = (leaf.error or {}).get("code")
            self._set_status(arena, lane, "timeout" if code == "timeout" else "failed", leaf.error)

    async def _judge_lane(self, arena: _Arena, lane: _Lane) -> None:
        """Note la réponse d'une lane terminée : `judging`, puis `judge_score` (story 3.3).

        Une réponse vide, un juge absent ou en panne et une sortie invalide donnent `score: null`
        et une raison, jamais 0. Le juge est un run enfant à part : la lane reste `judging` tant
        qu'il attend la place locale ou la note."""
        answer = "".join(lane.model.answer)
        if not answer.strip():
            verdict = JudgeVerdict(None, NOT_EVALUATED_EMPTY)
        elif self._judge is None or arena.judge is None:
            verdict = JudgeVerdict(None, NOT_EVALUATED_UNAVAILABLE)
        else:
            self._set_status(arena, lane, "judging")
            try:
                verdict = await self._judge.score(
                    arena.run_id, arena.judge, arena.prompt, arena.criteria, answer
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - un juge qui casse ne casse pas la lane
                logger.exception("Notation de %s en échec", lane.tag)
                verdict = JudgeVerdict(None, NOT_EVALUATED_UNAVAILABLE)
        self._hub.publish(
            arena.run_id,
            "judge_score",
            {
                "lane": lane.tag,
                "score": verdict.score,
                "reason": verdict.reason,
                "judge": arena.judge.ref.tag if arena.judge else None,
            },
        )

    async def _announce_carbon(self) -> None:
        """`carbon_updated` après chaque feuille (AD-10), annulation comprise."""
        session_id = self._hub.app_session_id
        if self._bus is not None and session_id is not None:
            await announce_carbon_updated(self._bus, self._hub.store, session_id)

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
