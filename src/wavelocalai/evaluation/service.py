"""Service d'évaluation de la qualité d'une réponse documentaire (story 7.1, AD-5, AD-9, AD-14).

Un run racine `eval` :

1. **Recherche** : les extraits de chaque question sont cherchés **une fois** (feuille `embedding`
   par question), puis donnés tels quels à tous les modèles évalués (événement `sources`).
2. **Réponses** : chaque modèle répond à chaque question sur ces mêmes extraits (une lane et une
   feuille `generation` par modèle et question, appel silencieux : le texte part dans `eval_answer`,
   le débit et le CO2 dans `metrics`). Les modèles locaux passent l'un après l'autre par la place
   « Ollama local » (un seul enchaînement, pour ne pas faire charger et décharger les modèles à
   chaque question), les modèles cloud partent en parallèle (AD-14).
3. **Notation** par le juge, appels silencieux en feuilles `judge` : la fidélité (affirmations
   extraites puis vérifiées une à une contre les extraits), la pertinence (questions retrouvées
   depuis la réponse, cosinus moyen avec la question par l'`Embedder` de la base, AD-16) et la
   précision du contexte (les extraits utiles). Chaque note part dans `eval_metric` dès qu'elle est
   prête, et dans `evaluations` (elle survit à une annulation ou à un redémarrage).

Une note jamais calculable (juge indisponible, sortie invalide, réponse vide, modèle en échec) vaut
`score: null` avec sa raison, **jamais 0**. Le cloud n'est jamais pris sans `allow_cloud` (AD-9) :
modèles et juge passent par `registry.resolve`, avant toute écriture. 4 modèles évalués au plus
(décision du 2026-10-19). La question et les réponses vivent dans le flux (AD-7), jamais dans
`runs.params`.

`evaluation/` n'importe pas `rag/` : la base lui est donnée par le port `EvalBase`, câblé par
l'application (`rag/eval_base.py`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from wavelocalai.config import Settings
from wavelocalai.errors import ERRORS, AppError, ProviderError, build_envelope
from wavelocalai.evaluation import prompts, scoring
from wavelocalai.evaluation.judge import JudgeReply
from wavelocalai.evaluation.repo import insert_evaluation
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.chat import cloud_estimator
from wavelocalai.inference.judge_port import (
    NOT_EVALUATED_EMPTY,
    NOT_EVALUATED_INVALID,
    NOT_EVALUATED_UNAVAILABLE,
)
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import CANCELLED_CO2, NOT_MEASURED, Guard, stream_into_run
from wavelocalai.models.defaults import ModelDefaults, is_weak_judge
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import ChatModel, ChatRequest, Embedder, ModelRef
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.eval_snapshot import METRICS, aggregate
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import LeafResult, RunHandle
from wavelocalai.runs.system_bus import SystemBus

logger = logging.getLogger("wavelocalai.evaluation")

MIN_MODELS = 1
MAX_MODELS = 4  # décision du 2026-10-19 : au-delà, `422 invalid_request`
MAX_QUESTIONS = 20
MAX_QUESTION_CHARS = 20_000
STRATEGY = "naive"  # les extraits communs sont ceux de la stratégie la plus simple du RAG

NOT_EVALUATED_NO_CLAIM = "non évalué : aucune affirmation à vérifier"
NOT_EVALUATED_NO_QUESTION = "non évalué : aucune question retrouvée depuis la réponse"
NOT_EVALUATED_EMBEDDING = "non évalué : modèle d'embedding indisponible"
NOT_EVALUATED_TIMEOUT = "non évalué : délai dépassé"
NOT_EVALUATED_FAILED = "non évalué : réponse en échec"

# Statuts de lane : ceux de l'Arène (`inference/arena.py::LANE_STATUSES`) ; `judging` : notation.
TERMINAL = frozenset({"done", "timeout", "failed", "cancelled"})


class EvalBase(Protocol):
    """Ce que l'évaluation demande à la base documentaire (câblé par `rag/eval_base.py`)."""

    async def prepare(self) -> tuple[Embedder, int]:
        """Modèle d'embedding de la base et `top_k` ; lève `rag_base_empty` & co, avant tout run."""
        ...

    async def search(
        self, root_id: str, embedder: Embedder, top_k: int, question: str, question_index: int
    ) -> list[dict[str, Any]]:
        """Extraits communs de la question (forme de l'événement `sources`, `text` compris)."""
        ...

    async def embed(self, root_id: str, embedder: Embedder, texts: list[str]) -> list[list[float]]:
        """Vecteurs de `texts` par le modèle d'embedding de la base."""
        ...

    def request(self, question: str, sources: list[dict[str, Any]]) -> ChatRequest:
        """Invite de réponse du RAG."""
        ...


class JudgeAsker(Protocol):
    async def ask(self, parent_run_id: str, judge: ChatModel, request: ChatRequest) -> JudgeReply:
        """Appel silencieux du juge ; ne lève que pour une annulation (`evaluation/judge.py`)."""
        ...


@dataclass(frozen=True)
class EvalCommand:
    questions: Sequence[str]
    models: Sequence[str]
    judge: str | None = None  # un tag du registre, sinon le défaut `judge`
    allow_cloud: bool = False


@dataclass(frozen=True)
class Metric:
    """Une note calculée : `score` nul = non évalué, `reason` dit pourquoi ; `detail` : `verdicts`,
    `questions` ou `useful` selon la métrique."""

    score: int | None
    reason: str
    detail: dict[str, Any] | None = None


@dataclass
class _Lane:
    model: ChatModel
    leaves: list[str]  # une feuille `generation` par question
    status: str = "waiting"
    answers: dict[int, str] = field(default_factory=dict)  # question -> texte (réponse obtenue)
    failures: dict[int, dict[str, Any]] = field(default_factory=dict)  # question -> enveloppe

    @property
    def tag(self) -> str:
        return self.model.ref.tag


@dataclass
class _Eval:
    run_id: str
    questions: list[str]
    lanes: list[_Lane]
    embedder: Embedder
    top_k: int
    judge: ChatModel | None  # `None` : aucun juge disponible, toutes les notes sont « non évalué »
    sources: list[list[dict[str, Any]]] = field(default_factory=list)
    scores: dict[tuple[str, str], dict[int, int | None]] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count < 2 else many}"


class EvaluationService:
    def __init__(
        self,
        hub: RunHub,
        registry: ModelRegistry,
        factory: ModelFactory,
        slot: LocalSlot,
        settings: Settings,
        base: EvalBase,
        judge: JudgeAsker | None,
        *,
        meter: LocalMeter | None = None,
        bus: SystemBus | None = None,
        guard: Guard | None = None,
        defaults: ModelDefaults | None = None,
    ) -> None:
        self._hub = hub
        self._registry = registry
        self._factory = factory
        self._slot = slot
        self._settings = settings
        self._base = base
        self._judge = judge  # sans service de notation, toutes les notes sont « non évalué »
        self._meter = meter  # sans compteur, le CO2 d'une feuille locale n'est pas mesuré
        self._bus = bus  # sans bus, `carbon_updated` n'est pas publié
        self._guard = guard  # garde-fou mémoire des réponses locales (story 4.8)
        self._defaults = defaults  # défaut `judge` ; sans lui, seul un juge nommé note
        self._tasks: set[asyncio.Task[None]] = set()  # références fortes jusqu'à la fin

    # --- départ --------------------------------------------------------------------------------

    async def start(self, command: EvalCommand) -> RunHandle:
        """Crée la racine et ses feuilles de réponse, rend `{run_id}` aussitôt ; la suite est une
        tâche. Lève `invalid_request` (questions ou modèles hors bornes, doublon),
        `model_not_found`, `cloud_not_allowed` ou `model_not_chat` (registre, AD-9), `rag_base_empty`
        et consorts (la base), ou `run_busy` (une évaluation est déjà active, AD-14) : avant toute
        écriture, sauf `run_busy` qui vient de la création de la racine."""
        questions = self._questions(command)
        refs, named_judge = self._resolve(command)
        judge_ref = named_judge or await self._default_judge(command.allow_cloud)
        if self._judge is None:  # sans service de notation, aucun juge n'est annoncé
            judge_ref = None
        params_b = await self._judge_params(judge_ref, command.allow_cloud)
        models = [self._factory.chat_model(ref) for ref in refs]
        judge_model = self._factory.chat_model(judge_ref) if judge_ref else None
        embedder, top_k = await self._base.prepare()
        root = await self._hub.create_run(
            "eval",
            models=[ref.tag for ref in refs],
            params={
                "allow_cloud": command.allow_cloud,
                "judge": judge_ref.tag if judge_ref else None,  # tag du registre, pas du texte
                "embedding_model": embedder.ref.tag,
                "top_k": top_k,
                "question_count": len(questions),
                "strategy": STRATEGY,
            },
        )
        ev = _Eval(root.run_id, questions, [], embedder, top_k, judge_model)
        try:
            lanes = [_Lane(model, []) for model in models]
            for _ in questions:
                for lane in lanes:
                    leaf = await self._hub.create_run(
                        "generation", models=[lane.tag], parent_run_id=root.run_id
                    )
                    # Annulée avant sa première tentative, la feuille garde un `co2` (AD-10).
                    self._hub.declare_leaf(leaf.run_id, CANCELLED_CO2)
                    lane.leaves.append(leaf.run_id)
            ev.lanes = lanes
        except BaseException:
            error = build_envelope("internal", "Création des feuilles de l'évaluation impossible.")
            with contextlib.suppress(Exception):
                await self._hub.finish_run(root.run_id, "error", error=error)
            raise
        self._hub.publish(root.run_id, "eval_questions", {"questions": questions})
        self._hub.publish(root.run_id, "judge", self._judge_event(judge_ref, params_b, command))
        for lane in ev.lanes:  # les lignes du tableau existent avant la première réponse
            self._hub.publish(root.run_id, "lane_status", {"lane": lane.tag, "status": "waiting"})
        self._hub.set_cancel_hook(root.run_id, lambda: self._cancel_unfinished(ev))
        task = asyncio.create_task(self._orchestrate(ev), name=f"wavelocalai-eval-{root.run_id}")
        self._hub.attach_task(root.run_id, task)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return root

    @staticmethod
    def _questions(command: EvalCommand) -> list[str]:
        questions = list(command.questions)
        if not 1 <= len(questions) <= MAX_QUESTIONS:
            raise AppError(
                "invalid_request",
                f"questions : 1 à {MAX_QUESTIONS} questions, pas {len(questions)}.",
            )
        if any(not q.strip() or len(q) > MAX_QUESTION_CHARS for q in questions):
            raise AppError(
                "invalid_request",
                f"questions : chaque question est non vide, de {MAX_QUESTION_CHARS} caractères au plus.",
            )
        return questions

    def _resolve(self, command: EvalCommand) -> tuple[list[ModelRef], ModelRef | None]:
        if not MIN_MODELS <= len(command.models) <= MAX_MODELS:
            raise AppError(
                "invalid_request",
                f"models : {MIN_MODELS} à {MAX_MODELS} modèles évalués, pas {len(command.models)}.",
            )
        tags = list(command.models)
        if len(set(tags)) != len(tags):
            raise AppError("invalid_request", "models : un même modèle ne figure qu'une fois.")
        # Tout est résolu avant la moindre écriture ou le moindre appel (AD-9).
        refs = [self._registry.resolve(tag, command.allow_cloud) for tag in tags]
        judge = (
            self._registry.resolve(command.judge, command.allow_cloud) if command.judge else None
        )
        return refs, judge

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

    async def _judge_params(self, ref: ModelRef | None, allow_cloud: bool) -> float | None:
        """Paramètres actifs (milliards) d'un juge local d'après le registre ; `None` si inconnus."""
        if ref is None or ref.origin != "local":
            return None
        try:
            listed = await self._registry.list_models(allow_cloud=allow_cloud)
        except Exception:  # noqa: BLE001 - un registre en peine ne bloque pas l'évaluation
            logger.warning("Liste des modèles indisponible pour le juge", exc_info=True)
            return None
        info = next((m for m in listed.models if m.tag == ref.tag), None)
        return info.params_active_b if info else None

    @staticmethod
    def _judge_event(ref: ModelRef | None, params_b: float | None, command: EvalCommand) -> dict:
        """Données de l'événement `judge` (celles de l'Arène, sans `default_criteria`) : le juge
        retenu et la fiabilité de ses notes."""
        if ref is None:
            return {
                "model": None,
                "origin": None,
                "params_active_b": None,
                "unreliable": None,
                "single_judge": False,
                "chosen": "none",
            }
        return {
            "model": ref.tag,
            "origin": ref.origin,
            "params_active_b": params_b,
            # Moins de ~4 milliards de paramètres actifs, ou inconnus, pour un juge local.
            "unreliable": is_weak_judge(ref.origin != "local", params_b),
            "single_judge": True,
            "chosen": "request" if command.judge else "default",
        }

    # --- exécution -----------------------------------------------------------------------------

    async def _orchestrate(self, ev: _Eval) -> None:
        tasks: list[asyncio.Task[None]] = []
        try:
            await self._retrieve(ev)
            tasks = self._start_answers(ev)
            await asyncio.gather(*tasks)
            tasks = [
                asyncio.create_task(
                    self._score_lane(ev, lane), name=f"wavelocalai-eval-score-{lane.tag}"
                )
                for lane in ev.lanes
            ]
            await asyncio.gather(*tasks)
            await self._hub.finish_run(ev.run_id, "ok")
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            raise  # `hub.cancel` a déjà fixé `cancelled` ; le crochet a clos les lanes
        except Exception as exc:  # noqa: BLE001 - ne jamais laisser la racine active
            logger.error("Évaluation en échec", exc_info=exc)
            for task in tasks:
                task.cancel()
            error = self._envelope(exc)
            self._cancel_unfinished(ev)  # aucune lane sans `lane_status` final
            with contextlib.suppress(Exception):
                await self._hub.finish_run(ev.run_id, "error", error=error)

    async def _retrieve(self, ev: _Eval) -> None:
        """Les extraits communs, une recherche par question, avant toute réponse."""
        for index, question in enumerate(ev.questions):
            found = await self._base.search(ev.run_id, ev.embedder, ev.top_k, question, index)
            ev.sources.append(found)
            self._hub.publish(
                ev.run_id,
                "sources",
                {"strategy": STRATEGY, "question_index": index, "sources": found},
            )

    def _start_answers(self, ev: _Eval) -> list[asyncio.Task[None]]:
        """Modèles cloud en parallèle ; modèles locaux en un enchaînement (AD-14)."""
        local = [lane for lane in ev.lanes if lane.model.ref.origin == "local"]
        tasks = [
            asyncio.create_task(self._answer_lane(ev, lane), name=f"wavelocalai-eval-{lane.tag}")
            for lane in ev.lanes
            if lane not in local
        ]
        if local:
            tasks.append(
                asyncio.create_task(self._answer_locals(ev, local), name="wavelocalai-eval-local")
            )
        return tasks

    async def _answer_locals(self, ev: _Eval, lanes: list[_Lane]) -> None:
        for lane in lanes:  # un modèle à la fois : pas de chargement alterné entre deux questions
            await self._answer_lane(ev, lane)

    async def _answer_lane(self, ev: _Eval, lane: _Lane) -> None:
        """Les réponses d'un modèle, question après question. Une réponse en échec ou hors délai
        n'arrête ni les autres questions ni les autres modèles ; une lane qui n'a répondu à aucune
        question finit `failed` (ou `timeout`)."""
        secrets = self._settings.secret_values()
        for index, question in enumerate(ev.questions):
            captured: list[str] = []
            try:
                leaf = await stream_into_run(
                    self._hub,
                    lane.leaves[index],
                    lane.model,
                    self._base.request(question, ev.sources[index]),
                    secrets=secrets,
                    estimate_co2=cloud_estimator(lane.model, self._settings),
                    slot=self._slot,
                    timeout_s=self._settings.delays.lane_timeout_s,
                    retry_interrupted=True,
                    publish_to=ev.run_id,
                    on_phase=lambda phase, lane=lane: self._set_status(ev, lane, phase),
                    meter=self._meter,
                    on_leaf_closed=self._announce_carbon,
                    capture=captured,
                    publish_metrics=True,
                    metrics_extra={"question_index": index},
                    guard=self._guard,
                )
                error = None if leaf.status == "ok" else (leaf.error or {})
            except asyncio.CancelledError:
                self._set_status(ev, lane, "cancelled")
                raise
            except Exception as exc:  # noqa: BLE001 - une lane qui casse n'arrête pas les autres
                logger.error("Lane %s de l'évaluation en échec", lane.tag, exc_info=exc)
                error = self._envelope(exc)
                with contextlib.suppress(Exception):
                    failed = LeafResult(status="error", origin=lane.model.ref.origin, error=error)
                    await self._hub.finish_leaf(lane.leaves[index], failed, NOT_MEASURED)
            if error is None:
                lane.answers[index] = "".join(captured)
            else:
                lane.failures[index] = error
            self._hub.publish(
                ev.run_id,
                "eval_answer",
                {
                    "lane": lane.tag,
                    "question_index": index,
                    "text": lane.answers.get(index),
                    "error": error,
                },
            )
        if not lane.answers:  # aucune réponse : rien à noter
            error = lane.failures[len(ev.questions) - 1]
            code = error.get("code")
            self._set_status(ev, lane, "timeout" if code == "timeout" else "failed", error)

    async def _score_lane(self, ev: _Eval, lane: _Lane) -> None:
        """La notation des réponses d'un modèle : `judging`, chaque note publiée dès qu'elle est
        prête, puis `done`. Une réponse absente, vide ou un juge en panne donnent « non évalué »."""
        if lane.status not in TERMINAL:
            self._set_status(ev, lane, "judging")
        for index in range(len(ev.questions)):
            answer = lane.answers.get(index)
            reason = self._unscorable(lane, index, answer)
            if reason is not None:
                for metric in METRICS:
                    await self._record(ev, lane, index, metric, Metric(None, reason))
                continue
            assert answer is not None
            await self._record(
                ev,
                lane,
                index,
                "faithfulness",
                await self._guarded(self._faithfulness(ev, index, answer)),
            )
            await self._record(
                ev,
                lane,
                index,
                "relevance",
                await self._guarded(self._relevance(ev, index, answer)),
            )
            await self._record(
                ev,
                lane,
                index,
                "context_precision",
                await self._guarded(self._precision(ev, index, answer)),
            )
        self._set_status(ev, lane, "done")

    @staticmethod
    def _unscorable(lane: _Lane, index: int, answer: str | None) -> str | None:
        """La raison « non évalué » d'une réponse qu'on ne peut pas noter, sinon `None`."""
        if answer is None:
            code = (lane.failures.get(index) or {}).get("code")
            return NOT_EVALUATED_TIMEOUT if code == "timeout" else NOT_EVALUATED_FAILED
        if not answer.strip():
            return NOT_EVALUATED_EMPTY  # inutile de déranger le juge
        return None

    @staticmethod
    async def _guarded(metric: Any) -> Metric:
        """Une note ne fait jamais tomber l'évaluation : un incident inattendu la rend « non
        évaluée » (juge indisponible) ; seule l'annulation passe."""
        try:
            return await metric
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Notation en échec")
            return Metric(None, NOT_EVALUATED_UNAVAILABLE)

    # --- les trois notes -----------------------------------------------------------------------

    async def _ask(self, ev: _Eval, request: ChatRequest) -> JudgeReply:
        if self._judge is None or ev.judge is None:
            return JudgeReply(None, NOT_EVALUATED_UNAVAILABLE)
        return await self._judge.ask(ev.run_id, ev.judge, request)

    async def _faithfulness(self, ev: _Eval, index: int, answer: str) -> Metric:
        """Affirmations extraites (un appel), puis vérifiées une à une contre les extraits communs
        (un appel chacune) ; la note est la part d'affirmations appuyées."""
        question, sources = ev.questions[index], ev.sources[index]
        reply = await self._ask(ev, prompts.claims_request(question, answer))
        if reply.text is None:
            return Metric(None, reply.reason)
        try:
            claims = prompts.parse_claims(reply.text)
        except ProviderError:
            return Metric(None, NOT_EVALUATED_INVALID)
        if not claims:
            return Metric(None, NOT_EVALUATED_NO_CLAIM)
        verdicts: list[dict[str, Any]] = []
        for claim in claims:
            reply = await self._ask(ev, prompts.verdict_request(claim, sources))
            if reply.text is None:
                return Metric(None, reply.reason)
            try:
                verdicts.append({"claim": claim, **prompts.parse_verdict(reply.text, len(sources))})
            except ProviderError:
                return Metric(None, NOT_EVALUATED_INVALID)
        supported = sum(1 for v in verdicts if v["verdict"] == prompts.SUPPORTED)
        contradicted = sum(1 for v in verdicts if v["verdict"] == prompts.CONTRADICTED)
        reason = f"{_plural(supported, 'affirmation', 'affirmations')} sur {len(verdicts)} "
        reason += "appuyée par les extraits" if supported < 2 else "appuyées par les extraits"
        if contradicted:
            reason += f", {_plural(contradicted, 'contredite', 'contredites')}"
        return Metric(scoring.faithfulness(verdicts), reason + ".", {"verdicts": verdicts})

    async def _relevance(self, ev: _Eval, index: int, answer: str) -> Metric:
        """Questions retrouvées depuis la réponse (un appel du juge), puis cosinus moyen avec la
        question posée, par l'`Embedder` de la base (une feuille `embedding`)."""
        question = ev.questions[index]
        reply = await self._ask(ev, prompts.questions_request(answer))
        if reply.text is None:
            return Metric(None, reply.reason)
        try:
            retrieved = prompts.parse_questions(reply.text)
        except ProviderError:
            return Metric(None, NOT_EVALUATED_INVALID)
        if not retrieved:
            return Metric(None, NOT_EVALUATED_NO_QUESTION)
        try:
            vectors = await self._base.embed(ev.run_id, ev.embedder, [question, *retrieved])
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - embedding en panne : note impossible, pas 0
            logger.warning("Embedding de la pertinence en échec : %r", exc)
            return Metric(None, NOT_EVALUATED_EMBEDDING)
        score, mean = scoring.relevance(vectors[0], vectors[1:])
        reason = (
            f"Cosinus moyen de {f'{mean:.2f}'.replace('.', ',')} entre la question posée et "
            f"{_plural(len(retrieved), 'question retrouvée', 'questions retrouvées')} "
            "depuis la réponse."
        )
        return Metric(score, reason, {"questions": retrieved})

    async def _precision(self, ev: _Eval, index: int, answer: str) -> Metric:
        """Les extraits utiles à la réponse, désignés par le juge (un appel)."""
        sources = ev.sources[index]
        reply = await self._ask(ev, prompts.useful_request(ev.questions[index], answer, sources))
        if reply.text is None:
            return Metric(None, reply.reason)
        try:
            useful, why = prompts.parse_useful(reply.text, len(sources))
        except ProviderError:
            return Metric(None, NOT_EVALUATED_INVALID)
        reason = why or (
            f"{_plural(len(useful), 'extrait', 'extraits')} sur {len(sources)} "
            f"{'sert' if len(useful) < 2 else 'servent'} à répondre."
        )
        return Metric(scoring.context_precision(useful, len(sources)), reason, {"useful": useful})

    # --- publication ---------------------------------------------------------------------------

    async def _record(
        self, ev: _Eval, lane: _Lane, index: int, metric: str, result: Metric
    ) -> None:
        """Écrit la note dans `evaluations` (elle survit à l'arrêt), puis la publie : `eval_metric`
        porte la note de la question et la moyenne du modèle sur les questions déjà notées
        (`aggregate`, de quoi dire « sur 8 questions (1 non évaluée) »)."""
        now = _now()
        await self._hub.store.awrite(
            lambda conn: insert_evaluation(
                conn,
                ev.run_id,
                lane.tag,
                index,
                metric,
                result.score,
                result.reason,
                result.detail,
                now,
            )
        )
        seen = ev.scores.setdefault((lane.tag, metric), {})
        seen[index] = result.score
        detail = result.detail or {}
        self._hub.publish(
            ev.run_id,
            "eval_metric",
            {
                "lane": lane.tag,
                "question_index": index,
                "question_count": len(ev.questions),
                "metric": metric,
                "score": result.score,
                "reason": result.reason,
                "verdicts": detail.get("verdicts"),
                "questions": detail.get("questions"),
                "useful": detail.get("useful"),
                "aggregate": aggregate(seen.values(), len(ev.questions), settled=False),
            },
        )

    def _set_status(
        self, ev: _Eval, lane: _Lane, status: str, error: dict[str, Any] | None = None
    ) -> None:
        """Publie le `lane_status` d'une lane ; un état final ne change plus, un état répété n'est
        pas republié."""
        if lane.status in TERMINAL or lane.status == status:
            return
        lane.status = status
        data: dict[str, Any] = {"lane": lane.tag, "status": status}
        if error is not None:
            data["error"] = error
        self._hub.publish(ev.run_id, "lane_status", data)

    def _cancel_unfinished(self, ev: _Eval) -> None:
        """Crochet du hub, juste avant `run_ended` : les lanes inachevées passent à `cancelled`."""
        for lane in ev.lanes:
            self._set_status(ev, lane, "cancelled")

    def _envelope(self, exc: Exception) -> dict[str, Any]:
        """Enveloppe d'AD-18 d'une exception ; une exception inattendue devient `internal`."""
        secrets = self._settings.secret_values()
        if isinstance(exc, AppError):
            declared = ERRORS[exc.code].detail_keys
            detail = {key: value for key, value in exc.detail.items() if key in declared}
            return build_envelope(exc.code, exc.technical, secrets, **detail)
        return build_envelope("internal", f"{type(exc).__name__}: {exc}", secrets)

    async def _announce_carbon(self) -> None:
        """`carbon_updated` après chaque feuille (AD-10) ; un échec est journalisé, sans effet."""
        session_id = self._hub.app_session_id
        if self._bus is None or session_id is None:
            return
        try:
            await announce_carbon_updated(self._bus, self._hub.store, session_id)
        except Exception as exc:  # noqa: BLE001 - une annonce manquée ne change pas le run
            logger.warning("carbon_updated non publié : %r", exc)
